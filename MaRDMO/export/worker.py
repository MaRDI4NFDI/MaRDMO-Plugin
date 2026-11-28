'''The base class of the catalogs' export workers: what they export alike (#198).

:class:`CatalogExport` gives the items of a documentation their class and
markers and exports what several catalogs have: publications with their
authors and journals, algorithms and software (algorithm and workflow
catalogs) and the plain items (:data:`PLAIN_ITEMS`).  The catalogs' workers
(``model/worker.py`` etc.) subclass it.
'''
from ..core.constants import SOFTWARE_REFERENCES
from ..core.config import get_items, get_options, get_properties
from ..core.ids import is_user_id
from ..core.markers import MARKER_PROPERTIES, SECTION_MARKERS, allowed
from ..core.properties import find_reference
from ..core.values import date_precision


# Items entered on a page without a page of their own, exported with their class
# and markers only: {answer key (also the section of the markers): class}
PLAIN_ITEMS = {
    'programminglanguage': 'Programming Language',
    'cpu': 'CPU Model',
    'method': 'Experimental Method',
    'instrument': 'Experimental Equipment',
    'algorithmictask': 'Algorithmic Task',
    'academicdiscipline': 'Academic Discipline',
}


class CatalogExport:
    '''Base class of the export workers of the catalogs: what they export alike.

    Subclassed by :class:`~MaRDMO.model.worker.PrepareModel`,
    :class:`~MaRDMO.algorithm.worker.PrepareAlgorithm` and
    :class:`~MaRDMO.workflow.worker.PrepareWorkflow`.  Holds the shared
    Wikibase vocabulary, the markers, the export of authors, journals and
    publications, and, for the algorithm and workflow catalogs, of
    algorithms, software and the plain items (:data:`PLAIN_ITEMS`).
    '''

    # The worker's key in markers.SECTION_MARKERS
    catalog = None

    def __init__(self):
        '''Initialise with Wikibase properties and items from MaRDMOConfig.'''
        self.properties = get_properties()
        self.items = get_items()

    def _export_plain(self, payload, data, *keys):
        '''Export the plain items of *data* under *keys*, in this order: their class and markers.

        Args:
            payload: :class:`~MaRDMO.export.payload.GeneratePayload` instance.
            data:    Top-level answers dict.
            keys:    Keys of :data:`PLAIN_ITEMS` (e.g. ``'programminglanguage'``,
                     collected from the software pages).
        '''
        for key in keys:
            for entry in data.get(key, {}).values():
                if not entry.get("ID"):
                    continue

                payload.get_item_key(
                    value = entry
                )
                payload.set_class(PLAIN_ITEMS[key])

                self._add_common_metadata(payload, key)

    def _export_algorithms(self, payload, algorithms: dict, intra_class=False):
        '''Export each algorithm item (algorithm and workflow catalogs).

        Sets the class and markers of an algorithm and links it to its
        algorithmic tasks via solved-by (reverse) and to the implementing
        software via implemented-by.

        Args:
            payload:     :class:`~MaRDMO.export.payload.GeneratePayload` instance.
            algorithms:  The ``algorithm`` section of the answers.
            intra_class: Also export the algorithm-to-algorithm relations
                         (the algorithm catalog has them, the workflow catalog not).
        '''
        for entry in algorithms.values():
            if not entry.get("ID"):
                continue

            payload.get_item_key(
                value = entry
            )
            payload.set_class('Algorithm')

            self._add_common_metadata(payload, 'algorithm')

            payload.add_single_relation(
                statement = {
                    'relation': self.properties["solved by"],
                    'relatant': "PRelatant"
                },
                reverse = True
            )

            payload.add_single_relation(
                statement = {
                    'relation': self.properties["implemented by"],
                    'relatant': "SRelatant"
                }
            )

            if intra_class:
                payload.add_multiple_relation(
                    statement = {
                        'relation': "IntraClassRelation",
                        'relatant': "IntraClassElement"
                    }
                )

    def _export_softwares(self, payload, softwares: dict, algo_software_keys: set, tested_by=False):
        '''Export each software item (algorithm and workflow catalogs).

        Software linked to an algorithm via "implemented by" receives community
        MathAlgoDB and the MaRDI software profile; all other software receives
        only the profile.  Then its programming languages, dependencies and
        references.

        Args:
            payload:            :class:`~MaRDMO.export.payload.GeneratePayload` instance.
            softwares:          The ``software`` section of the answers.
            algo_software_keys: The software implementing an algorithm
                                (:meth:`_implementing_software`).
            tested_by:          Also export the benchmarks it is tested by
                                (the algorithm catalog has them, the workflow catalog not).
        '''
        for entry in softwares.values():
            if not entry.get("ID"):
                continue

            payload.get_item_key(
                value = entry
            )
            payload.set_class('Software')

            self._add_common_metadata(payload, self._software_section(entry, algo_software_keys))

            if tested_by:
                payload.add_single_relation(
                    statement = {
                        'relation': self.properties["tested by"],
                        'relatant': "BRelatant"
                    },
                    reverse = True
                )

            payload.add_single_relation(
                statement = {
                    'relation': self.properties["programmed in"],
                    'relatant': "programminglanguage"
                }
            )

            payload.add_single_relation(
                statement = {
                    'relation': self.properties["depends on software"],
                    'relatant': "dependency"
                }
            )

            self._add_references(payload, entry.get('reference'), SOFTWARE_REFERENCES)

    def _add_common_metadata(self, payload, section, description_long=False):
        '''Add the markers of *section* to the current subject, and optionally its long description.

        The markers (class, community, profile type) are those of
        :data:`~MaRDMO.core.markers.SECTION_MARKERS` for the worker's catalog.  A new
        item gets all; an existing portal item only those it lacks and that do
        not contradict its own (:func:`~MaRDMO.core.markers.allowed`, #141); if its
        markers could not be looked up, none.

        Args:
            payload:          :class:`~MaRDMO.export.payload.GeneratePayload` instance.
            section:          Key of the section in ``SECTION_MARKERS[catalog]``.
            description_long: When ``True``, add a ``description`` statement from the item's
                              ``descriptionLong`` field.
        '''
        payload.marked.setdefault(payload.state.subject.get('ID'), set()).add(section)
        portal = payload.subject_markers()
        for kind, qid in SECTION_MARKERS[self.catalog][section].qids().items():
            if qid and (portal is None or (portal is not False and allowed(kind, qid, portal))):
                payload.add_answer(
                    verb = self.properties[MARKER_PROPERTIES[kind]],
                    object_and_type = [qid, "wikibase-item"],
                )

        if description_long:
            payload.add_answers(
                mardmo_property = "descriptionLong",
                wikibase_property = "description",
            )

    def marker_sections(self, data):
        '''The sections whose markers the export gives the items of *data* (preview, #141).

        Returns:
            ``{item ID: set of sections}``, the same as the export's calls of
            :meth:`_add_common_metadata` (``payload.marked``).
        '''
        sections = {}
        for section, entry in self._marked_entries(data):
            if entry.get('ID'):
                sections.setdefault(entry['ID'], set()).add(section)
        return sections

    def _marked_entries(self, data):
        '''``(section, entry)`` of every entry of *data* the export gives markers; per catalog.'''
        raise NotImplementedError

    def _publication_entries(self, data):
        '''``(section, entry)`` of the authors, journals and publications the export gives markers.'''
        for publication in data.get('publication', {}).values():
            for kind in ('author', 'journal'):
                for entry in publication.get(kind, {}).values():
                    # New ones get theirs in the payload, authors only with ORCID iD or zbMATH ID (#118)
                    if kind == 'author' and is_user_id(entry.get('ID')) and not (entry.get('orcid') or entry.get('zbmath')):
                        continue
                    yield kind, entry
            if publication.get('ID') and 'mardi' not in publication['ID']:
                yield self._publication_section(publication), publication

    @staticmethod
    def _implementing_software(data):
        '''Keys (ID, name, description) of the software that implements an algorithm of *data*.'''
        return {
            (item.get('ID', ''), item.get('Name', ''), item.get('Description', ''))
            for algo in data.get('algorithm', {}).values()
            for item in algo.get('SRelatant', {}).values()
        }

    @staticmethod
    def _software_section(entry, implementing):
        '''The section of the markers of the software *entry*; *implementing*: :meth:`_implementing_software`.'''
        key = (entry.get('ID', ''), entry.get('Name', ''), entry.get('Description', ''))
        return 'implementing software' if key in implementing else 'software'

    def _software_entries(self, data):
        '''``(section, entry)`` of the software and programming languages the export gives markers.'''
        implementing = self._implementing_software(data)
        for entry in data.get('software', {}).values():
            yield self._software_section(entry, implementing), entry
        for entry in data.get('programminglanguage', {}).values():
            yield 'programminglanguage', entry

    @staticmethod
    def _publication_section(entry):
        '''The section of the markers of the publication *entry*.'''
        return 'scholarly article' if entry.get('entrytype') == 'scholarly article' else 'publication'

    def _add_references(self, payload, references, mapping):
        '''Add one statement per reference answer (DOI, IDs, URLs) of the current subject.

        Args:
            payload:    :class:`~MaRDMO.export.payload.GeneratePayload` instance.
            references: Reference answers ``{collection_index: [option_uri, text]}``.
            mapping:    Tuples ``(option key, portal property, datatype)``, e.g.
                        :data:`~MaRDMO.core.constants.SOFTWARE_REFERENCES`.
        '''
        options = get_options()
        for option_key, prop, datatype in mapping:
            entry = find_reference(references, options[option_key])
            text = (entry[1] or '').strip() if entry else ''
            if text:
                payload.add_answer(
                    verb = self.properties[prop],
                    object_and_type = [text, datatype],
                )

    @staticmethod
    def _part_exported(payload, entry):
        '''Whether the author or journal *entry* gets its statements here.

        New ones get all of theirs in the payload (#118); those MaRDMO left out
        (:func:`~MaRDMO.export.duplicates._resolve_parts`) none.  Portal items get
        theirs here, also a new one the export found on the portal.
        '''
        if not entry.get("ID"):
            return False
        key = payload.get_item_key(value=entry, role='object')
        if key not in payload.get_dictionary():
            return False
        return not is_user_id(entry["ID"]) or bool(payload.get_dictionary()[key]['id'])

    def _export_journals(self, payload, publications: dict):
        '''Add journal item entries (instance-of + ISSN) for all publications.

        Args:
            payload:      :class:`~MaRDMO.export.payload.GeneratePayload` instance.
            publications: Dict of publication answer dicts keyed by index.
        '''
        for publication in publications.values():
            for entry in publication.get('journal', {}).values():
                if not self._part_exported(payload, entry):
                    continue

                payload.get_item_key(value=entry)
                payload.set_class('Journal')

                self._add_common_metadata(payload, 'journal')

                if entry.get('issn'):
                    payload.add_answer(
                        verb=self.properties["ISSN"],
                        object_and_type=[entry["issn"], "external-id"],
                    )

    def _export_authors(self, payload, publications: dict):
        '''Add author item entries (instance-of, profile type, ORCID, zbMATH) for all publications.

        Args:
            payload:      :class:`~MaRDMO.export.payload.GeneratePayload` instance.
            publications: Dict of publication answer dicts keyed by index.
        '''
        for publication in publications.values():
            for entry in publication.get('author', {}).values():
                if not self._part_exported(payload, entry):
                    continue

                payload.get_item_key(value=entry)
                payload.set_class('Author')

                self._add_common_metadata(payload, 'author')

                if entry.get('orcid'):
                    payload.add_answer(
                        verb = self.properties["ORCID iD"],
                        object_and_type = [
                            entry['orcid'],
                            "external-id"
                        ],
                    )

                if entry.get('zbmath'):
                    payload.add_answer(
                        verb = self.properties["zbMATH author ID"],
                        object_and_type = [
                            entry['zbmath'],
                            "external-id"
                        ],
                    )

    def _export_publications(self, payload, publications: dict, relations: list):
        '''Add publication item entries and their relatant links to the payload.

        Args:
            payload:      :class:`~MaRDMO.export.payload.GeneratePayload` instance.
            publications: Dict of publication answer dicts.
            relations:    List of ``(relation_key, relatant_key)`` pairs that
                          link each publication to its parent entity.
        '''
        for entry in publications.values():
            if not entry.get("ID"):
                continue

            payload.get_item_key(
                value = entry
            )
            payload.set_class('Publication')

            # Only add class, profile, and DOI for non-MaRDI items
            if "mardi" not in entry["ID"]:

                self._add_common_metadata(payload, self._publication_section(entry))

                # Add DOI
                if entry.get("reference", {}).get(0):
                    payload.add_answer(
                        verb = self.properties["DOI"],
                        object_and_type = [
                            entry["reference"][0][1],
                            "external-id"
                        ],
                    )

                # bibliographic data
                if entry.get("title"):
                    payload.add_answer(
                        verb = self.properties["title"],
                        object_and_type = [
                            {"text": entry["title"], "language": "en"},
                            "monolingualtext",
                        ],
                    )

                if entry.get("volume"):
                    payload.add_answer(
                        verb = self.properties["volume"],
                        object_and_type = [entry["volume"], "string"],
                    )

                if entry.get("issue"):
                    payload.add_answer(
                        verb = self.properties["issue"],
                        object_and_type = [entry["issue"], "string"],
                    )

                if entry.get("page"):
                    payload.add_answer(
                        verb = self.properties["page(s)"],
                        object_and_type = [entry["page"], "string"],
                    )

                if entry.get("date"):
                    payload.add_answer(
                        verb = self.properties["publication date"],
                        object_and_type = [
                            {
                                "time": f"+{entry['date']}",
                                "precision": date_precision(
                                    date_str = entry['date']
                                ),
                                "calendarmodel": (
                                    "http://www.wikidata.org/entity/Q1985727"
                                ),
                            },
                            "time",
                        ],
                    )

                # Add Language
                payload.add_single_relation(
                    statement = {
                        'relation': self.properties["language of work or name"],
                        'relatant': "language"
                    }
                )
                # Add Journal
                payload.add_single_relation(
                    statement = {
                        'relation': self.properties["published in"],
                        'relatant': "journal"
                    }
                )
                # Add Authors
                payload.add_single_relation(
                    statement = {
                        'relation': self.properties["author"],
                        'relatant': "author"
                    },
                    alt_statement = {
                        "relation": self.properties["author name string"],
                        "relatant": "Name",
                    },
                )

            # Add caller-supplied relations (P2E, P2A/P2BS, etc.)
            for relation, relatant in relations:
                payload.add_multiple_relation(
                    statement = {
                        'relation': relation,
                        'relatant': relatant
                    },
                    reverse = True,
                )
