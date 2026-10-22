'''Shared base class for MaRDMO entity handlers.

Provides the four methods that are identical between the Model and Algorithm
Information classes:
  - _entry
  - _collect_existing_ids
  - _hydrate_relatants
  - _fill

Both handlers pass catalog through every call.  The algorithm handler
simply uses the default catalog='' everywhere.
'''

from dataclasses import dataclass, field
from typing import Any, Optional

from .constants import ALGORITHM_PROPS, SOFTWARE_PROPS
from .models import Algorithm, Software
from .getters import (
    get_id,
    get_items,
    get_properties,
    get_sparql_query,
    get_sparql_query_optional,
    get_url,
)
from .helpers import process_qualifier, value_editor
from .adders import add_basics, add_references, add_relations_flexible, add_relations_static
from .workflow.models import ProcessStepUsage
from .queries import query_sparql

# Lazy singleton – instantiated on first use so that the Django app registry
# is guaranteed to be ready (publication.handlers imports rdmo ORM models).
_PUB_INFO: list = []


def _get_pub_info():
    '''Return the singleton :class:`~MaRDMO.publication.handlers.Information` instance.'''
    if not _PUB_INFO:
        from .publication.handlers import Information  # pylint: disable=import-outside-toplevel
        _PUB_INFO.append(Information())
    return _PUB_INFO[0]


@dataclass
class _RelatantSpec:
    '''Bundles section-target and call-context parameters for _hydrate_relatants.

    question_id_uri   – RDMO attribute URI for the relatant's ID field
    question_set_uri  – RDMO attribute URI for the relatant's set field
    prefix            – label prefix used when registering new set entries
    fill_method       – pre-configured callable (usually a partial of _fill)
    catalog           – current project catalog string (forwarded to fill methods)
    visited           – mutable set of already-processed external IDs
    batch_fill_method – optional batch SPARQL hydrator; when set, mardi/wikidata
                        relatants are collected and dispatched in one query
    section_indices   – deprecated / ignored. Was a shared {question_set_uri:
                        next_idx} cache to skip the max-set_index DB query, but
                        hydration recurses and creates sibling pages mid-loop,
                        so a cached index went stale and caused entities to
                        overwrite each other. The set_index is now always read
                        fresh via _next_set_index. Kept in the signature so the
                        existing call sites need not change.
    '''
    question_id_uri: str
    question_set_uri: str
    prefix: str
    fill_method: Any
    catalog: str
    visited: set
    batch_fill_method: Any = None
    section_indices: Optional[dict] = field(default=None)


def _values_clause(items):
    '''Build a SPARQL VALUES list string ``"wd:Q1 wd:Q2 …"`` from item tuples.

    Args:
        items: List of ``(text, external_id, set_index)`` tuples; the
               ``external_id`` field is expected in ``"source:QID"`` format.

    Returns:
        Space-separated string of ``wd:QID`` tokens suitable for insertion
        into a SPARQL VALUES clause.
    '''
    return ' '.join(f'wd:{ext_id.split(":")[-1]}' for _, ext_id, _ in items)


def _next_set_index(project, question_set_uri):
    '''Return the next free ``set_index`` for the section at *question_set_uri*.

    Always reads the current maximum straight from the database. Hydration is
    recursive: while an entity is being filled it can pull in and create sibling
    pages in the *same* section, so any ``set_index`` cached in memory goes stale
    mid-loop. Reusing a stale index makes :func:`~MaRDMO.helpers.value_editor`
    (which keys ``update_or_create`` on ``set_index`` alone) overwrite an
    unrelated page — the entity then silently vanishes from the questionnaire.
    '''
    existing = get_id(project, question_set_uri, ['set_index'])
    return max((e for e in existing if e is not None), default=-1) + 1


def _fetch_by_source(items, mardi_file, wikidata_file, model_class):
    '''Run one SPARQL query per source and return a ``{external_id: instance}`` dict.

    Splits *items* by source prefix (``mardi:`` / ``wikidata:``), fires a
    separate SPARQL request to each endpoint, and merges the results.

    Uses :func:`~MaRDMO.getters.get_sparql_query` for the MaRDI template
    (always required) and :func:`~MaRDMO.getters.get_sparql_query_optional`
    for the Wikidata template (no-op if the file is absent).  Both helpers
    are LRU-cached so repeated calls are free.

    Args:
        items:          List of ``(text, external_id, set_index)`` tuples.
        mardi_file:     Relative path to the MaRDI SPARQL template.
        wikidata_file:  Relative path to the Wikidata SPARQL template.
        model_class:    Dataclass with a ``from_query_batch(results)`` class
                        method that parses the raw SPARQL bindings.

    Returns:
        Dict mapping ``"source:QID"`` external IDs to dataclass instances.
    '''
    data_by_id     = {}
    mardi_items    = [(t, eid, si) for t, eid, si in items if eid.startswith('mardi:')]
    wikidata_items = [(t, eid, si) for t, eid, si in items if eid.startswith('wikidata:')]

    if mardi_items:
        query   = get_sparql_query(mardi_file).format(
            _values_clause(mardi_items), **get_items(), **get_properties()
        )
        results = query_sparql(query, get_url('mardi', 'sparql'))
        if results:
            data_by_id.update(model_class.from_query_batch(results))

    if wikidata_items:
        tmpl = get_sparql_query_optional(wikidata_file)
        if tmpl:
            query   = tmpl.format(
                _values_clause(wikidata_items), **get_items(), **get_properties()
            )
            results = query_sparql(query, get_url('wikidata', 'sparql'))
            if results:
                data_by_id.update(model_class.from_query_batch(results))

    return data_by_id


class BaseInformation:  # pylint: disable=too-few-public-methods
    '''Shared infrastructure for Model and Algorithm handlers.

    Subclasses must set self.questions and self.base in __init__, and
    declare _ENTITY_KEYS as a tuple of question-group keys whose ID URIs
    are collected by _collect_existing_ids.
    '''

    # Declared here so pylint and type checkers know these attributes exist;
    # concrete values are assigned by each subclass __init__.
    base: str
    questions: dict

    _ENTITY_KEYS: tuple = ()

    # Subclass-provided attributes; None signals "not implemented by this handler".
    mathalgodb = None
    _fill_problem_batch = None
    _fill_benchmark_batch = None

    def _entry(self, instance, item_type, batch_fill_method):
        '''Common signal entry-point: build visited set, then delegate to :meth:`_fill`.

        Args:
            instance:          RDMO Value instance that triggered the signal,
                               carrying ``project``, ``text``, ``external_id``,
                               and ``set_index`` attributes.
            item_type:         Questionnaire item type string (e.g. ``'Task'``).
            batch_fill_method: Bound method (e.g. ``_fill_task_batch``) used to
                               hydrate the entity from the knowledge graph.
        '''
        visited = self._collect_existing_ids(instance.project)
        self._fill(
            project           = instance.project,
            text              = instance.text,
            external_id       = instance.external_id,
            set_index         = instance.set_index,
            item_type         = item_type,
            batch_fill_method = batch_fill_method,
            catalog           = str(getattr(instance.project, 'catalog', '')),
            visited           = visited,
        )

    def _collect_existing_ids(self, project):
        '''Return the set of external IDs already recorded in the questionnaire.

        Issues a single batched DB query across all entity sections defined in
        :attr:`_ENTITY_KEYS` so that hydration can skip already-present items.

        Args:
            project: RDMO project instance whose questionnaire values are queried.

        Returns:
            Set of external ID strings (e.g. ``{'mardi:Q42', 'wikidata:Q7'}``).
        '''
        from rdmo.domain.models import Attribute  # pylint: disable=import-outside-toplevel
        id_uris = [
            f'{self.base}{self.questions[k]["ID"]["uri"]}'
            for k in self._ENTITY_KEYS
        ]
        attr_ids = Attribute.objects.filter(uri__in=id_uris).values_list('id', flat=True)
        return set(
            project.values.filter(
                snapshot=None,
                attribute_id__in=attr_ids,
                external_id__isnull=False,
            ).exclude(external_id='').values_list('external_id', flat=True)
        )

    def _hydrate_relatants(self, project, data, prop_keys, spec):
        '''Register and hydrate all relatants found under the given property keys.

        Skips IDs already in ``spec.visited``.  When ``spec.batch_fill_method``
        is set, MaRDI and Wikidata items are collected and dispatched in a single
        SPARQL query; otherwise ``spec.fill_method`` is called per relatant.
        See :class:`_RelatantSpec` for full parameter documentation.

        Args:
            project:   RDMO project instance.
            data:      Dataclass instance whose attributes are iterated over
                       ``prop_keys`` to yield :class:`~MaRDMO.models.Relatant` items.
            prop_keys: Sequence of attribute names on *data* to iterate.
            spec:      :class:`_RelatantSpec` instance bundling context parameters.
        '''
        batch_items = []

        for prop in prop_keys:
            for relatant in getattr(data, prop, []):
                if not relatant.id or relatant.id in spec.visited:
                    continue
                spec.visited.add(relatant.id)

                source = relatant.id.split(':')[0]
                text   = f'{relatant.label} ({relatant.description}) [{source}]'

                # Re-read the free index every iteration: a preceding
                # fill_method / batch_fill_method call may have created pages
                # in this same section (see _next_set_index).
                next_idx = _next_set_index(project, spec.question_set_uri)

                value_editor(project=project, uri=spec.question_set_uri,
                             info={'text': f'{spec.prefix}{next_idx + 1}',
                                   'set_index': next_idx})
                value_editor(project=project, uri=spec.question_id_uri,
                             info={'text': text, 'external_id': relatant.id,
                                   'set_index': next_idx})

                if spec.batch_fill_method and source in ('mardi', 'wikidata'):
                    batch_items.append((text, relatant.id, next_idx))
                else:
                    spec.fill_method(project=project, text=text,
                                     external_id=relatant.id, set_index=next_idx,
                                     catalog=spec.catalog, visited=spec.visited)

        if batch_items and spec.batch_fill_method:
            spec.batch_fill_method(project=project, items=batch_items,
                                   catalog=spec.catalog, visited=spec.visited)

    def _hydrate_qualifier_entities(self, project, data, prop_keys, spec, attr='qualifier'):
        '''Register and hydrate entities embedded as qualifier values on relatants.

        Iterates over the relatant lists named by *prop_keys*, inspects the
        ``qualifier`` attribute of each :class:`~MaRDMO.models.RelatantWithQualifier`,
        and for every qualifier item that has not yet been visited, creates a
        new set entry and calls the appropriate fill method.

        The ``qualifier`` string is parsed by
        :func:`~MaRDMO.helpers.process_qualifier` and must follow the
        ``"id || label || description"`` format (``' <<||>> '``-separated for
        multiple entries).  Entities already in ``spec.visited`` are skipped.

        When ``spec.batch_fill_method`` is set, MaRDI and Wikidata items are
        collected and dispatched as a single batch query after the loop;
        otherwise ``spec.fill_method`` is called per item.

        Args:
            project:   RDMO project instance.
            data:      Dataclass instance whose attributes are iterated over
                       *prop_keys* to yield relatant objects.
            prop_keys: Sequence of attribute names on *data* to inspect for
                       qualifier values.
            spec:      :class:`_RelatantSpec` instance bundling the target
                       question URIs, prefix, fill methods, ``catalog``,
                       ``visited``, and optional ``section_indices``.
        '''
        batch_items = []

        for prop in prop_keys:
            for relatant in getattr(data, prop, []):
                qualifier = getattr(relatant, attr, None)
                if not qualifier:
                    continue

                if isinstance(relatant, ProcessStepUsage):
                    source = qualifier.split(':')[0]
                    qualifier_items = [{
                        'id': qualifier,
                        'label': getattr(relatant, f'{attr}_label', '') or '',
                        'description': getattr(relatant, f'{attr}_description', '') or '',
                        'source': source,
                    }]
                else:
                    qualifier_items = process_qualifier(qualifier).values()

                for item in qualifier_items:
                    ext_id = item['id']
                    if ext_id in spec.visited:
                        continue
                    spec.visited.add(ext_id)
                    source = ext_id.split(':')[0]
                    text   = f'{item["label"]} ({item["description"]}) [{source}]'

                    # Re-read every iteration — see _hydrate_relatants / _next_set_index.
                    next_idx = _next_set_index(project, spec.question_set_uri)

                    value_editor(project=project, uri=spec.question_set_uri,
                                 info={'text': f'{spec.prefix}{next_idx + 1}',
                                       'set_index': next_idx})
                    value_editor(project=project, uri=spec.question_id_uri,
                                 info={'text': text, 'external_id': ext_id,
                                       'set_index': next_idx})

                    if spec.batch_fill_method and source in ('mardi', 'wikidata'):
                        batch_items.append((text, ext_id, next_idx))
                    else:
                        spec.fill_method(project=project, text=text,
                                         external_id=ext_id, set_index=next_idx,
                                         catalog=spec.catalog, visited=spec.visited)

        if batch_items and spec.batch_fill_method:
            spec.batch_fill_method(project=project, items=batch_items,
                                   catalog=spec.catalog, visited=spec.visited)

    def _hydrate_publications(self, project, publications, catalog, visited):
        '''Register and hydrate related publications via the publication handler.

        Args:
            project:      RDMO project instance.
            publications: Iterable of :class:`~MaRDMO.models.Relatant` items
                          representing publications to register.
            catalog:      Current project catalog string, forwarded to the
                          publication handler.
            visited:      Mutable set of already-processed external IDs;
                          updated in place to prevent duplicate processing.
        '''
        pub_info    = _get_pub_info()
        pub_id_uri  = f'{self.base}{self.questions["Publication"]["ID"]["uri"]}'
        pub_set_uri = f'{self.base}{self.questions["Publication"]["uri"]}'

        existing = get_id(project, pub_set_uri, ['set_index'])
        next_idx = max((e for e in existing if e is not None), default=-1) + 1

        for pub in publications:
            if pub.id in visited:
                continue
            visited.add(pub.id)

            source = pub.id.split(':')[0]
            text   = f'{pub.label} ({pub.description}) [{source}]'
            value_editor(project=project, uri=pub_set_uri,
                         info={'text': f'P{next_idx + 1}', 'set_index': next_idx})
            value_editor(project=project, uri=pub_id_uri,
                         info={'text': text, 'external_id': pub.id,
                               'set_index': next_idx})

            pub_info.fill_citation(project=project, text=text,
                                   external_id=pub.id, set_index=next_idx,
                                   catalog=catalog)
            next_idx += 1

    def _fill_algorithm_batch(self, project, items, catalog='', visited=None):
        '''Hydrate multiple Algorithm pages with a single SPARQL query per source.

        Available in both the Algorithm and Workflow catalogs.  The Problem
        cascade and intra-class relations are skipped when the catalog does
        not have a Problem section or ``mathalgodb`` is not initialised.

        Args:
            project:  RDMO project instance.
            items:    List of ``(text, external_id, set_index)`` tuples to process.
            catalog:  Active catalog URI suffix (default ``""``).
            visited:  Set of external IDs already processed (mutated to avoid cycles).
        '''
        from functools import partial  # pylint: disable=import-outside-toplevel

        if not items:
            return
        if visited is None:
            visited = set()

        algorithm  = self.questions['Algorithm']
        data_by_id = _fetch_by_source(
            items,
            'queries/algorithm_mardi.sparql',
            'queries/algorithm_wikidata.sparql',
            Algorithm,
        )
        if not data_by_id:
            return

        section_indices = {}
        for text, external_id, set_index in items:
            data = data_by_id.get(external_id)
            if not data:
                continue

            add_basics(project=project, text=text, questions=self.questions,
                       item_type='Algorithm', index=(0, set_index))

            add_relations_static(
                project=project, data=data,
                props={'keys': ALGORITHM_PROPS['A2P']},
                index={'set_prefix': set_index},
                statement={'relatant': f'{self.base}{algorithm["PRelatant"]["uri"]}'})

            if 'Problem' in self.questions:
                self._hydrate_relatants(
                    project=project, data=data, prop_keys=ALGORITHM_PROPS['A2P'],
                    spec=_RelatantSpec(
                        question_id_uri=f'{self.base}{self.questions["Problem"]["ID"]["uri"]}',
                        question_set_uri=f'{self.base}{self.questions["Problem"]["uri"]}',
                        prefix='AT',
                        fill_method=partial(self._fill, item_type='Problem',
                                            batch_fill_method=self._fill_problem_batch),
                        catalog=catalog, visited=visited,
                        batch_fill_method=self._fill_problem_batch,
                        section_indices=section_indices,
                    ))

            add_relations_static(
                project=project, data=data,
                props={'keys': ALGORITHM_PROPS['A2S']},
                index={'set_prefix': set_index},
                statement={'relatant': f'{self.base}{algorithm["SRelatant"]["uri"]}'})

            self._hydrate_relatants(
                project=project, data=data, prop_keys=ALGORITHM_PROPS['A2S'],
                spec=_RelatantSpec(
                    question_id_uri=f'{self.base}{self.questions["Software"]["ID"]["uri"]}',
                    question_set_uri=f'{self.base}{self.questions["Software"]["uri"]}',
                    prefix='S',
                    fill_method=partial(self._fill, item_type='Software',
                                        batch_fill_method=self._fill_software_batch),
                    catalog=catalog, visited=visited,
                    batch_fill_method=self._fill_software_batch,
                    section_indices=section_indices,
                ))

            if self.mathalgodb is not None and 'IntraClassRelation' in algorithm:
                add_relations_flexible(
                    project=project, data=data,
                    props={'keys': ALGORITHM_PROPS['Algorithm'], 'mapping': self.mathalgodb},
                    index={'set_prefix': set_index},
                    statement={
                        'relation': f'{self.base}{algorithm["IntraClassRelation"]["uri"]}',
                        'relatant': f'{self.base}{algorithm["IntraClassElement"]["uri"]}',
                    })

            self._hydrate_publications(project, data.publications, catalog, visited)

    def _fill_software_batch(self, project, items, catalog='', visited=None):
        '''Hydrate multiple Software pages with a single SPARQL query per source.

        Writes references, programming languages, and dependencies for all
        catalogs.  The benchmark cascade and publication hydration are only
        executed when the active catalog contains a ``Benchmark`` or
        ``Publication`` section respectively (i.e. the algorithm catalog).

        Args:
            project:  RDMO project instance.
            items:    List of ``(text, external_id, set_index)`` tuples to process.
            catalog:  Active catalog URI suffix (default ``""``).
            visited:  Set of external IDs already processed (mutated to avoid cycles).
        '''
        from functools import partial  # pylint: disable=import-outside-toplevel

        if not items:
            return
        if visited is None:
            visited = set()

        software   = self.questions['Software']
        data_by_id = _fetch_by_source(
            items,
            'queries/software_mardi.sparql',
            'queries/software_wikidata.sparql',
            Software,
        )
        if not data_by_id:
            return

        section_indices = {}
        for text, external_id, set_index in items:
            data = data_by_id.get(external_id)
            if not data:
                continue

            add_basics(project=project, text=text, questions=self.questions,
                       item_type='Software', index=(0, set_index))

            add_references(project=project, data=data,
                           uri=f'{self.base}{software["Reference"]["uri"]}',
                           set_prefix=set_index)

            add_relations_static(
                project=project, data=data,
                props={'keys': SOFTWARE_PROPS['S2PL']},
                index={'set_prefix': set_index},
                statement={'relatant': f'{self.base}{software["Programming Language"]["uri"]}'})

            add_relations_static(
                project=project, data=data,
                props={'keys': SOFTWARE_PROPS['S2DP']},
                index={'set_prefix': set_index},
                statement={'relatant': f'{self.base}{software["Dependency"]["uri"]}'})

            if 'Benchmark' in self.questions:
                add_relations_static(
                    project=project, data=data,
                    props={'keys': SOFTWARE_PROPS['S2B']},
                    index={'set_prefix': set_index},
                    statement={'relatant': f'{self.base}{software["BRelatant"]["uri"]}'})

                self._hydrate_relatants(
                    project=project, data=data, prop_keys=SOFTWARE_PROPS['S2B'],
                    spec=_RelatantSpec(
                        question_id_uri=f'{self.base}{self.questions["Benchmark"]["ID"]["uri"]}',
                        question_set_uri=f'{self.base}{self.questions["Benchmark"]["uri"]}',
                        prefix='B',
                        fill_method=partial(self._fill, item_type='Benchmark',
                                            batch_fill_method=self._fill_benchmark_batch),
                        catalog=catalog, visited=visited,
                        batch_fill_method=self._fill_benchmark_batch,
                        section_indices=section_indices,
                    ))

            if 'Publication' in self.questions:
                self._hydrate_publications(project, data.publications, catalog, visited)

    def fill_entity(self, project, text, external_id, question_id,
                    item_type, batch_fill_method, catalog):
        '''Look up the set_index for *external_id* and hydrate the entity via :meth:`_fill`.

        Called from the top-level handlers dispatcher when a relation value is
        saved to the questionnaire.

        Args:
            project:           RDMO project instance.
            text:              Display text for the entity (label + description + source).
            external_id:       External ID string (e.g. ``'mardi:Q42'``).
            question_id:       Full RDMO attribute URI used to locate the entity's
                               set_index in the questionnaire.
            item_type:         Questionnaire item type string (e.g. ``'Task'``).
            batch_fill_method: Bound ``_fill_*_batch`` method for SPARQL hydration.
            catalog:           Current project catalog string.
        '''
        visited    = self._collect_existing_ids(project)
        id_entries = get_id(project, question_id, ['set_index', 'external_id'])
        for set_index, ext_id in id_entries:
            if ext_id == external_id:
                self._fill(
                    project           = project,
                    text              = text,
                    external_id       = external_id,
                    set_index         = set_index,
                    item_type         = item_type,
                    batch_fill_method = batch_fill_method,
                    catalog           = catalog,
                    visited           = visited,
                )
                break

    def _fill(
        self, project, text, external_id, set_index,
        item_type, batch_fill_method, catalog='', visited=None
    ):
        '''Write basic questionnaire fields and delegate SPARQL hydration.

        Skips empty or ``'not found'`` entries, calls :func:`~MaRDMO.adders.add_basics`
        for all entities, then delegates to *batch_fill_method* for MaRDI and
        Wikidata entities.

        Args:
            project:           RDMO project instance.
            text:              Display text for the entity.
            external_id:       External ID string (e.g. ``'mardi:Q42'``).
            set_index:         Questionnaire set index for this entity.
            item_type:         Questionnaire item type string (e.g. ``'Task'``).
            batch_fill_method: Bound ``_fill_*_batch`` method for SPARQL hydration.
            catalog:           Current project catalog string (default ``''``).
            visited:           Mutable set of already-processed external IDs
                               (default ``None``; a new set is created if omitted).
        '''
        if not text or text == 'not found':
            return
        if visited is None:
            visited = set()
        visited.add(external_id)
        add_basics(project=project, text=text, questions=self.questions,
                   item_type=item_type, index=(0, set_index))
        if external_id.split(':')[0] not in ('mardi', 'wikidata'):
            return
        batch_fill_method(project=project, items=[(text, external_id, set_index)],
                          catalog=catalog, visited=visited)
