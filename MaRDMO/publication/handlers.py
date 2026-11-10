'''Module containing handlers for the Publication documentation sub-package.

Listens to RDMO model signals to keep publication-related questionnaire state
consistent.  For example, cleans up dependent ``Value`` objects when a
publication set entry is deleted.

Provides:

- :class:`Information` — signal receiver class with ``citation`` and
  ``publication_delete`` handler methods; routed via ``router.py``
'''

from dataclasses import replace

from ..constants import BASE_URI
from ..getters import (
    get_items,
    get_properties,
    get_publication_mapping,
    get_questions,
    get_sparql_query,
    get_url
)
from ..queries import query_sparql
from ..adders import add_basics, add_references, add_relations_flexible
from ..ids import is_portal_item

from .constants import (
    PROPS,
    ROUTING,
    ITEMINFOS,
    CITATIONINFOS,
    LANGUAGES,
    JOURNALS,
    AUTHORS
)
from .utils import clean_background_data
from .models import Publication

# Publications per citation query
CITATION_BATCH = 50


def _query_citations(source, external_ids):
    '''Return ``{external_id: row}`` with the citation query row of each publication.

    Queries *source* (``mardi`` or ``wikidata``) for :data:`CITATION_BATCH`
    publications at a time.  Publications of a failed query are missing.
    '''
    rows = {}
    for start in range(0, len(external_ids), CITATION_BATCH):
        chunk = external_ids[start:start + CITATION_BATCH]
        query = get_sparql_query(
            f'publication/queries/doi_from_{source}.sparql'
        ).format(
            ' '.join(f'wd:{external_id.split(":")[1]}' for external_id in chunk),
            **get_items(),
            **get_properties()
        )
        for row in query_sparql(query, get_url(source, 'sparql')):
            identifier = row['publication']['value'].rsplit('/', 1)[-1]
            # Several DOIs give several rows; the first one is used
            rows.setdefault(f'{source}:{identifier}', row)
    return rows


def _filter_pub_by_class(data, class_set):
    '''Return a copy of *data* with every relation field filtered to entities in *class_set*.'''
    fields = ['analyzes', 'applies', 'documents', 'invents', 'studies', 'surveys', 'uses']
    return replace(data, **{
        f: [v for v in getattr(data, f) if v.item_class in class_set]
        for f in fields
    })


class Information:
    '''Class containing functions, querying external sources for specific
       entities and integrating the related metadata into the questionnaire.'''

    def __init__(self):
        '''Load publication questions, publication role mapping, and the base URI.'''
        self.questions           = get_questions('publication')
        self.publication_mapping = get_publication_mapping()
        self.base                = BASE_URI

    def citation(self, instance):
        '''Handle a Publication ID-field save: populate citation metadata from the
        MaRDI Portal or Wikidata.

        Extracts project, text, external_id, set_index, catalog, and snapshot
        from *instance* and delegates to :meth:`fill_citation`.

        Args:
            instance: RDMO :class:`~rdmo.projects.models.Value` that was just saved.
        '''
        self.fill_citation(
            project     = instance.project,
            text        = instance.text,
            external_id = instance.external_id,
            set_index   = instance.set_index,
            catalog     = str(getattr(instance.project, 'catalog', '')),
            snapshot    = instance.snapshot,
        )

    def fill_citation(self, project, text, external_id, set_index, catalog='', snapshot=None):
        '''Populate publication citation metadata from the MaRDI Portal or Wikidata.

        Single-publication case of :meth:`fill_citations`.

        Args:
            project:     RDMO project instance.
            text:        Raw ID-field text (``"Label (Description) [source]"``).
            external_id: External ID string in ``"source:id"`` format.
            set_index:   Set-index of the publication page.
            catalog:     Active catalog URI string (used for relation dispatch).
            snapshot:    RDMO snapshot (``None`` for the current snapshot).
        '''
        self.fill_citations(project, [(text, external_id, set_index)], catalog, snapshot)

    def fill_citations(self, project, entries, catalog='', snapshot=None):
        '''Populate citation metadata for several publications at once.

        Cleans any previously stored background data of every entry, then (for
        publications of the MaRDI Portal and Wikidata) adds basic
        label/description, fetches the SPARQL citation data with one query per
        source and :data:`CITATION_BATCH` publications, stores references, and
        writes catalog-specific Publication–Entity / Publication–Algorithm /
        Publication–Benchmark/Software relations.

        Args:
            project:  RDMO project instance.
            entries:  Iterable of ``(text, external_id, set_index)`` tuples.
            catalog:  Active catalog URI string (used for relation dispatch).
            snapshot: RDMO snapshot (``None`` for the current snapshot).
        '''

        publication = self.questions["Publication"]

        by_source = {}
        for text, external_id, set_index in entries:
            clean_background_data(
                key_dict  = ITEMINFOS | CITATIONINFOS | LANGUAGES | JOURNALS | AUTHORS,
                questions = publication,
                project   = project,
                snapshot  = snapshot,
                set_index = set_index
            )

            # Own publications have no citation to query
            if not text or not is_portal_item(external_id):
                continue

            # Add basic Information, on the publication's tab (set_prefix
            # '') as the preview stores it for publications found by DOI
            add_basics(
                project   = project,
                text      = text,
                questions = self.questions,
                item_type = 'Publication',
                index     = (set_index, '')
            )

            source = external_id.split(':')[0]
            by_source.setdefault(source, []).append((external_id, set_index))

        for source, publications in by_source.items():
            rows = _query_citations(source, [external_id for external_id, _ in publications])
            for external_id, set_index in publications:
                if external_id in rows:
                    self._write_citation(project, rows[external_id], source, set_index, catalog)

    def _write_citation(self, project, row, source, set_index, catalog):
        '''Write references and relations of one publication from its query *row*.'''
        publication = self.questions["Publication"]

        # Structure the data
        data = Publication.from_query([row])

        add_references(
            project   = project,
            data      = data,
            uri       = f'{BASE_URI}{publication["Reference"]["uri"]}',
            set_index = set_index
        )

        if source != 'mardi':
            return

        catalog_slug = catalog.rsplit('/', 1)[-1]
        items        = get_items()

        for rule in ROUTING.get(catalog_slug, []):
            class_set = {f"mardi:{items[c]}" for c in rule['classes']}
            add_relations_flexible(
                project   = project,
                data      = _filter_pub_by_class(data, class_set),
                props     = {'keys': PROPS[rule['props']], 'mapping': getattr(self, rule['mapping'])},
                index     = {'set_prefix': set_index},
                statement = {
                    'relation': f'{BASE_URI}{publication[rule["relation"]]["uri"]}',
                    'relatant': f'{BASE_URI}{publication[rule["relatant"]]["uri"]}',
                },
            )


    def publication_delete(self, instance):
        '''Handle Publication set deletion: remove hidden citation background data.

        Called by the post-delete router when a Value for the top-level Publication
        set attribute is deleted.  Removes all background citation fields (item info,
        language, journal, author) for the deleted set index.

        Args:
            instance: RDMO :class:`~rdmo.projects.models.Value` that was just deleted.
        '''
        clean_background_data(
            key_dict  = ITEMINFOS | CITATIONINFOS | LANGUAGES | JOURNALS | AUTHORS,
            questions = self.questions["Publication"],
            project   = instance.project,
            snapshot  = instance.snapshot,
            set_index = instance.set_index
        )
