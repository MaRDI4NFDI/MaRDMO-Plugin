'''Background workers for collecting and exporting publication metadata.

Two worker classes handle different phases of publication documentation:
retrieval (fetching bibliographic data from external APIs) and export
(formatting and pushing data to the MaRDI Portal).

Provides:

- :class:`PublicationRetriever` — fetches citation metadata for a DOI and
  writes the results into the questionnaire via the adders module
- :class:`PublicationExport`    — base class for catalog-specific export
  workers that package questionnaire answers for portal submission
'''

import html
import re
from multiprocessing.pool import ThreadPool

from .constants import ITEMINFOS, CITATIONINFOS, JOURNALS, AUTHORS, LANGUAGES
from .utils import clean_background_data, get_citation

from ..constants import BASE_URI
from ..getters import get_items, get_options, get_properties, get_questions
from ..helpers import commit_writes, date_precision, find_reference, value_editor
from ..markers import MARKER_PROPERTIES, SECTION_MARKERS, allowed
from ..ids import is_user_id, item_text

# Publications whose citation data is looked up at the same time
CITATION_LOOKUPS_IN_PARALLEL = 3


# Formatting tags in fetched titles (Crossref, DataCite, ...); only these are
# removed, so a title like "a < b and c > d" keeps its text
_FORMATTING_TAG_RE = re.compile(
    r'</?(?:i|b|u|em|strong|sup|sub|scp|tt|sc|span|jats:[a-z-]+|mml:[a-z]+)(?:\s[^<>]*)?/?>',
    re.IGNORECASE,
)


def _single_line(text):
    '''Collapse whitespace (incl. line breaks), remove formatting tags and decode HTML entities in fetched metadata text.

    Crossref/DataCite titles and names occasionally contain line breaks, which
    the MaRDI Portal rejects, formatting tags (``<i>``, ``<sup>``) and HTML
    entities (``&amp;``), which would end up literally in labels.  Users
    cannot edit this background data, so it is normalised when stored instead
    of blocking the export.
    '''
    if not isinstance(text, str):
        return text
    return ' '.join(html.unescape(_FORMATTING_TAG_RE.sub('', text)).split())


class PublicationRetriever:
    '''Retrieve Metadata from MaRDI Portal, Wikidata, and other
       sources like Crossref, DataCite, zbMath, DOI, and ORCid for Workflow,
       Model, and Algorithm documentation.'''

    # Get Publication-related Questions
    questions = get_questions('publication')

    def get_information(self, project, snapshot, answers):
        '''Fetch and store citation metadata for all publications in *answers*.

        Iterates over ``answers["publication"]``, skips entries without an ID,
        then resolves
        each publication via :func:`~.utils.get_citation` and writes the
        resulting metadata fields (title, year, language, journal, authors,
        etc.) back into the questionnaire.

        Args:
            project:  RDMO project instance.
            snapshot: RDMO snapshot (``None`` for the current snapshot).
            answers:  Top-level answers dict (mutated in place with citation data).
        '''

        citations = self._lookup_citations(answers)

        for key in answers.get('publication', {}):

            # If ID is missing (not answered or deleted)
            if not answers['publication'][key].get('ID'):
                continue

            #Clean potential old data...
            clean_background_data(
                key_dict = CITATIONINFOS | LANGUAGES | JOURNALS | AUTHORS,
                questions = self.questions["Publication"],
                project = project,
                snapshot = snapshot,
                set_index = key
            )

            #If User selected a Publication from Wikidata or entered an own one...
            if answers['publication'][key]['ID'].startswith(('wikidata', 'user:')):

                #...check if DOI is available.
                if not answers['publication'][key].get('reference', {}).get(0, ['',''])[1]:
                    continue

                #Get the Citation of several ressource.
                data_all = citations[key]

                #If Publication available at MaRDI, Wikidata, Crossref, Datacite, zbMath or DOI...
                if any(
                    data_all.get(k)
                    for k in ("mardi", "wikidata", "crossref", "datacite", "zbmath", "doi")
                ):

                    data = (
                        data_all.get('mardi')
                        or data_all.get("wikidata")
                        or data_all.get("crossref")
                        or data_all.get("datacite")
                        or data_all.get("zbmath")
                        or data_all.get("doi")
                    )

                    #...add data to Questionnaire and...
                    if data_all.get('mardi') or data_all.get('wikidata'):
                        value_editor(
                            project = project,
                            uri = f'{BASE_URI}{self.questions["Publication"]["ID"]["uri"]}',
                            info = {
                                'text': item_text(_single_line(data.label), _single_line(data.description)),
                                'external_id': data.id,
                                'set_index': key
                            }
                        )

                    for uri, data_key in (ITEMINFOS|CITATIONINFOS).items():
                        value_editor(
                            project = project,
                            uri = f'{BASE_URI}{self.questions["Publication"][uri]["uri"]}',
                            info = {
                                'text': _single_line(getattr(data, data_key)),
                                'set_index': key
                            }
                        )
                    for idx, language in enumerate(data.language):
                        for uri, data_key in LANGUAGES.items():
                            value_editor(
                                project = project,
                                uri = f'{BASE_URI}{self.questions["Publication"][uri]["uri"]}',
                                info = {
                                    'text': _single_line(getattr(language, data_key)),
                                    'collection_index': idx, 
                                    'set_index': key
                                }
                            )
                    for idx, journal in enumerate(data.journal):
                        for uri, data_key in JOURNALS.items():
                            value_editor(
                                project = project,
                                uri = f'{BASE_URI}{self.questions["Publication"][uri]["uri"]}',
                                info = {
                                    'text': _single_line(getattr(journal, data_key)),
                                    'collection_index': idx, 
                                    'set_index': key
                                }
                            )
                    for idx, author in enumerate(data.authors):
                        for uri, data_key in AUTHORS.items():
                            value_editor(
                                project = project,
                                uri = f'{BASE_URI}{self.questions["Publication"][uri]["uri"]}',
                                info = {
                                    'text': _single_line(getattr(author, data_key)),
                                    'collection_index': idx, 
                                    'set_index': key
                                }
                            )

                    #...output dictionary.
                    if data_all.get('mardi') or data_all.get('wikidata'):
                        answers['publication'][key]['ID'] = data.id
                    answers['publication'][key]['Name'] = _single_line(data.label)
                    answers['publication'][key]['Description'] = _single_line(data.description)

        return answers

    @staticmethod
    def _lookup_citations(answers):
        '''Look up the citation data of all publications that need it, in parallel.

        These are the publications from Wikidata or entered by the user
        (``user:`` ID) that have a DOI.

        Returns:
            Dict mapping the publication's set index to the result of
            :func:`~.utils.get_citation`.
        '''
        dois = {
            key: publication['reference'][0][1].upper()
            for key, publication in answers.get('publication', {}).items()
            if (publication.get('ID') or '').startswith(('wikidata', 'user:'))
            and publication.get('reference', {}).get(0, ['', ''])[1]
        }
        if not dois:
            return {}
        commit_writes()
        with ThreadPool(min(CITATION_LOOKUPS_IN_PARALLEL, len(dois))) as pool:
            results = pool.map(get_citation, dois.values())
        return dict(zip(dois, results))

class PublicationExport:
    '''Base class providing author, journal, and publication export helpers.

    Subclassed by :class:`~MaRDMO.model.worker.PrepareModel`,
    :class:`~MaRDMO.algorithm.worker.PrepareAlgorithm` and
    :class:`~MaRDMO.workflow.worker.PrepareWorkflow`.  Holds the shared
    Wikibase vocabulary and the private ``_export_*`` helpers that build
    publication-related payload entries, and the export of programming
    languages (algorithm and workflow catalogs).
    '''

    # The worker's key in markers.SECTION_MARKERS
    catalog = None

    def __init__(self):
        '''Initialise with Wikibase properties and items from MaRDMOConfig.'''
        self.properties = get_properties()
        self.items = get_items()

    def _export_programming_languages(self, payload, programminglanguages: dict):
        '''Export each programming language item collected from software sections.'''
        for entry in programminglanguages.values():
            if not entry.get("ID"):
                continue

            payload.get_item_key(
                value = entry
            )
            payload.set_class('Programming Language')

            self._add_common_metadata(payload, 'programminglanguage')

    def _add_common_metadata(self, payload, section, description_long=False):
        '''Add the markers of *section* to the current subject, and optionally its long description.

        The markers (class, community, profile type) are those of
        :data:`~MaRDMO.markers.SECTION_MARKERS` for the worker's catalog.  A new
        item gets all; an existing portal item only those it lacks and that do
        not contradict its own (:func:`~MaRDMO.markers.allowed`, #141); if its
        markers could not be looked up, none.

        Args:
            payload:          :class:`~MaRDMO.payload.GeneratePayload` instance.
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
            payload:    :class:`~MaRDMO.payload.GeneratePayload` instance.
            references: Reference answers ``{collection_index: [option_uri, text]}``.
            mapping:    Tuples ``(option key, portal property, datatype)``, e.g.
                        :data:`~MaRDMO.constants.SOFTWARE_REFERENCES`.
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
        (:func:`~MaRDMO.duplicates._resolve_parts`) none.  Portal items get
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
            payload:      :class:`~MaRDMO.payload.GeneratePayload` instance.
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
            payload:      :class:`~MaRDMO.payload.GeneratePayload` instance.
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
            payload:      :class:`~MaRDMO.payload.GeneratePayload` instance.
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
                            entry["reference"][0][1].upper(),
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
