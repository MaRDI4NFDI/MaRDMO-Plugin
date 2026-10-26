'''Background worker for the Algorithm documentation catalog.

Implements the task that collects algorithm metadata from User,
MaRDI Portal, and Wikidata, renders a preview document, and
exports the result to the MaRDI Portal.

Provides:

- :class:`PrepareAlgorithm` — orchestrates data collection, preview rendering,
  and portal export for a single algorithm documentation project
'''


from .constants import get_relations, preview_relations

from ..constants import BENCHMARK_REFERENCES, SOFTWARE_REFERENCES
from ..getters import get_items, get_mathalgodb, get_properties, get_publication_mapping, get_url
from ..helpers import collect_items_without_section, entity_relations, unique_items
from ..payload import GeneratePayload

from ..publication.worker import PublicationExport

class PrepareAlgorithm(PublicationExport):
    '''Prepare Algorithm documentation answers for preview rendering and MaRDI Portal export.

    Inherits publication export helpers from
    :class:`~MaRDMO.publication.worker.PublicationExport` and extends them
    with algorithm-specific relation mapping and Wikibase payload generation.
    '''
    def __init__(self):
        '''Initialise with Wikibase vocabulary and the MathAlgoDB ontology registry.'''
        super().__init__()
        self.mathalgodb          = get_mathalgodb()
        self.publication_mapping = get_publication_mapping()

    def preview(self, answers):
        '''Resolve entity cross-references for the Algorithm documentation preview page.

        Applies algorithm-specific relation mappings so that the preview
        template receives a fully-resolved answers dict.

        Args:
            answers: Top-level answers dict (mutated in place).

        Returns:
            The mutated *answers* dict.
        '''

        # Prepare Relations for Preview
        for relation in preview_relations:
            entity_relations(
                data = answers,
                idx = {
                    'from': relation['from_idx'],
                    'to': relation['to_idx']
                },
                entity = {
                    'relation': relation['relation'],
                    'old_name': relation['old_name'],
                    'new_name': relation['new_name'],
                    'encryption': relation['encryption']
                },
                assumption = False,
                mapping = (
                    self.publication_mapping if relation.get('mapping') == 'publication'
                    else self.mathalgodb
                )
            )

        # Collect inline items that have no dedicated questionnaire section
        answers['programminglanguage'] = collect_items_without_section(
            answers, 'software', 'programminglanguage'
        )

        return answers

    def export(self, data, url):
        '''Assemble and return the complete Wikibase payload for an Algorithm documentation export.

        Creates a :class:`~MaRDMO.payload.GeneratePayload` instance, processes
        all unique items, then delegates each entity section (algorithms, problems,
        software, benchmarks, publications) to dedicated helper methods.

        Args:
            data: Top-level answers dict produced by ``get_post_data``.
            url:  Target Wikibase API URL for the upload.

        Returns:
            Tuple ``(payload_dict, dependency_order)`` ready for
            :meth:`~MaRDMO.oauth2.OauthProviderMixin.post`.
        '''

        items, dependency = unique_items(data)

        payload = GeneratePayload(
            dependency = dependency,
            user_items = items,
            url = url,
            wikibase = {
                'items': get_items(),
                'properties': get_properties(),
                'relations': get_relations()
            }
        )

        # Add / Retrieve Components of Model Item
        payload.process_items()

        # Delegate to helper functions
        self._export_algorithms(
            payload = payload,
            algorithms = data.get("algorithm", {}),
        )
        self._export_problems(
            payload = payload,
            problems = data.get("problem", {})
        )
        algo_software_keys = {
            (item.get('ID', ''), item.get('Name', ''), item.get('Description', ''))
            for algo in data.get('algorithm', {}).values()
            for item in algo.get('SRelatant', {}).values()
        }
        self._export_softwares(
            payload = payload,
            softwares = data.get("software", {}),
            algo_software_keys = algo_software_keys,
        )
        self._export_benchmarks(
            payload = payload,
            benchmarks = data.get("benchmark", {})
        )
        self._export_programming_languages(
            payload = payload,
            programminglanguages = data.get("programminglanguage", {})
        )
        self._export_authors(
            payload = payload,
            publications = data.get("publication", {})
        )
        self._export_journals(
            payload = payload,
            publications = data.get("publication", {})
        )
        self._export_publications(
            payload = payload,
            publications = data.get("publication", {}),
            relations = [('P2A', 'ARelatant'), ('P2BS', 'BSRelatant')]
        )

        # Construct Item Payloads
        payload.add_item_payload()

        # Reject malformed URLs/DOIs/swMATH IDs, then mark existing Relations
        payload.validate_identifiers()
        payload.check_existing_relations(
            sparql_endpoint = get_url('mardi', 'sparql'),
            api_url = get_url('mardi', 'api'),
        )
        return payload.get_dictionary(), payload.dependency

    # ---------------------------
    # Entity export helpers
    # ---------------------------
    def _export_algorithms(self, payload, algorithms: dict):
        for entry in algorithms.values():
            if not entry.get("ID"):
                continue

            payload.get_item_key(
                value = entry
            )
            payload.set_class('Algorithm')

            self._add_common_metadata(
                payload = payload,
                community = self.items["MathAlgoDB"],
                qclass =self.items["algorithm"],
                profile_type = "MaRDI algorithm profile",
            )

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

            payload.add_multiple_relation(
                statement = {
                    'relation': "IntraClassRelation",
                    'relatant': "IntraClassElement"
                }
            )

    def _export_problems(self, payload, problems: dict):
        for entry in problems.values():
            if not entry.get("ID"):
                continue

            payload.get_item_key(
                value = entry
            )
            payload.set_class('Algorithmic Task')

            self._add_common_metadata(
                payload = payload,
                community = self.items["MathAlgoDB"],
                qclass =self.items["algorithmic task"],
                profile_type = "MaRDI task profile",
            )

            payload.add_single_relation(
                statement = {
                    'relation': self.properties["manifestation of"],
                    'relatant': "BRelatant"
                },
                reverse = True
            )

            payload.add_multiple_relation(
                statement = {
                    'relation': "IntraClassRelation",
                    'relatant': "IntraClassElement"
                }
            )

    def _export_softwares(self, payload, softwares: dict, algo_software_keys: set):
        for entry in softwares.values():
            if not entry.get("ID"):
                continue

            payload.get_item_key(
                value = entry
            )
            payload.set_class('Software')

            entry_key = (entry.get('ID', ''), entry.get('Name', ''), entry.get('Description', ''))
            if entry_key in algo_software_keys:
                self._add_common_metadata(
                    payload = payload,
                    community = self.items["MathAlgoDB"],
                    qclass = self.items["software"],
                    profile_type = "MaRDI software profile",
                )
            else:
                self._add_common_metadata(
                    payload = payload,
                    qclass = self.items["software"],
                    profile_type = "MaRDI software profile",
                )

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

    def _export_benchmarks(self, payload, benchmarks: dict):
        for entry in benchmarks.values():
            if not entry.get("ID"):
                continue

            payload.get_item_key(
                value = entry
            )
            payload.set_class('Benchmark')

            self._add_common_metadata(
                payload = payload,
                community = self.items["MathAlgoDB"],
                qclass = self.items["benchmark"],
            )

            self._add_references(payload, entry.get('reference'), BENCHMARK_REFERENCES)

    def _export_programming_languages(self, payload, programminglanguages: dict):
        for entry in programminglanguages.values():
            if not entry.get("ID"):
                continue

            payload.get_item_key(
                value = entry
            )
            payload.set_class('Programming Language')

            payload.add_answer(
                verb = self.properties["instance of"],
                object_and_type = [self.items["programming language"], "wikibase-item"],
            )
