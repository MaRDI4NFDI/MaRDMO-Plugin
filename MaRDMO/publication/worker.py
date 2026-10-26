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

from .constants import ITEMINFOS, CITATIONINFOS, JOURNALS, AUTHORS, LANGUAGES
from .utils import clean_background_data, get_citation

from ..constants import BASE_URI
from ..getters import get_items, get_options, get_properties, get_questions
from ..helpers import date_precision, find_reference, value_editor


def _single_line(text):
    '''Collapse whitespace (incl. line breaks) in fetched metadata text.

    Crossref/DataCite titles and names occasionally contain line breaks, which
    the MaRDI Portal rejects.  Users cannot edit this background data, so it is
    normalised when stored instead of blocking the export.
    '''
    return ' '.join(text.split()) if isinstance(text, str) else text


class PublicationRetriever:
    '''Retrieve Metadata from MaRDI Portal, Wikidata, and other
       sources like Crossref, DataCite, zbMath, DOI, and ORCid for Workflow,
       Model, and Algorithm documentation.'''

    # Get Publication-related Questions
    questions = get_questions('publication')

    def get_information(self, project, snapshot, answers, options):
        '''Fetch and store citation metadata for all publications in *answers*.

        Iterates over ``answers["publication"]``, skips entries without an ID
        or (for workflow catalogs) entries not flagged for export, then resolves
        each publication via :func:`~.utils.get_citation` and writes the
        resulting metadata fields (title, year, language, journal, authors,
        etc.) back into the questionnaire.

        Args:
            project:  RDMO project instance.
            snapshot: RDMO snapshot (``None`` for the current snapshot).
            answers:  Top-level answers dict (mutated in place with citation data).
            options:  Global RDMO options dict (used for the ``"Yes"`` option check).
        '''

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

            #If User selected a Publication from Wikidata, MathAlgoDB or did not find it...
            if answers['publication'][key]['ID'].startswith(('wikidata','not found')):

                #...check if DOI is available.
                if not answers['publication'][key].get('reference', {}).get(0, ['',''])[1]:
                    continue

                #Get the Citation of several ressource.
                data_all = get_citation(answers['publication'][key]['reference'][0][1].upper())

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
                                'text':
                                    f"{_single_line(data.label)} ({_single_line(data.description)})"
                                    f" [{data.id.split(':')[0]}]",
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

class PublicationExport:
    '''Base class providing author, journal, and publication export helpers.

    Subclassed by :class:`~MaRDMO.model.worker.PrepareModel` and
    :class:`~MaRDMO.algorithm.worker.PrepareAlgorithm`.  Holds the shared
    Wikibase vocabulary and the private ``_export_*`` helpers that build
    publication-related payload entries.
    '''

    def __init__(self):
        '''Initialise with Wikibase properties and items from MaRDMOConfig.'''
        self.properties = get_properties()
        self.items = get_items()

    def _add_common_metadata(self, payload, qclass, profile_type=None, community=None, description_long=False):
        '''Add instance-of and optional community, MaRDI-profile-type, and description statements.

        Args:
            payload:          :class:`~MaRDMO.payload.GeneratePayload` instance.
            qclass:           Wikibase QID for the ``instance of`` target class.
            profile_type:     Label key for the MaRDI profile type item; skipped when ``None``.
            community:        Wikibase QID for the community item; skipped when ``None``.
            description_long: When ``True``, add a ``description`` statement from the item's
                              ``descriptionLong`` field.
        '''
        payload.add_answer(
            verb = self.properties["instance of"],
            object_and_type = [qclass, "wikibase-item"],
        )

        if community is not None:
            payload.add_answer(
                verb = self.properties["community"],
                object_and_type = [community, "wikibase-item"],
            )

        if profile_type is not None:
            payload.add_answer(
                verb = self.properties["MaRDI profile type"],
                object_and_type = [self.items[profile_type], "wikibase-item"],
            )

        if description_long:
            payload.add_answers(
                mardmo_property = "descriptionLong",
                wikibase_property = "description",
            )

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

    def _export_journals(self, payload, publications: dict):
        '''Add journal item entries (instance-of + ISSN) for all publications.

        Args:
            payload:      :class:`~MaRDMO.payload.GeneratePayload` instance.
            publications: Dict of publication answer dicts keyed by index.
        '''
        for publication in publications.values():
            for entry in publication.get('journal', {}).values():
                if not entry.get("ID") or entry.get("ID") == 'no journal found':
                    continue

                payload.get_item_key(value=entry)
                payload.set_class('Journal')

                self._add_common_metadata(
                    payload=payload,
                    qclass=self.items["scientific journal"],
                    profile_type="MaRDI journal profile",
                )

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
                if not entry.get("ID") or entry.get("ID") == 'no author found':
                    continue

                payload.get_item_key(value=entry)
                payload.set_class('Author')

                self._add_common_metadata(
                    payload=payload,
                    qclass=self.items["human"],
                    profile_type="MaRDI person profile",
                )

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

                pclass = (
                    self.items["scholarly article"]
                    if entry.get("entrytype") == "scholarly article"
                    else self.items["publication"]
                )

                self._add_common_metadata(
                    payload=payload,
                    qclass=pclass,
                    profile_type="MaRDI publication profile",
                )

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
