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
from ..ids import unique_items
from ..relations import collect_items_without_section, resolve_relations
from ..payload import GeneratePayload

from ..publication.worker import PublicationExport

class PrepareAlgorithm(PublicationExport):
    '''Prepare Algorithm documentation answers for preview rendering and MaRDI Portal export.

    Inherits publication export helpers from
    :class:`~MaRDMO.publication.worker.PublicationExport` and extends them
    with algorithm-specific relation mapping and Wikibase payload generation.
    '''
    catalog = 'algorithm'

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
        resolve_relations(answers, preview_relations, {'publication': self.publication_mapping}, self.mathalgodb)

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
        algo_software_keys = self._implementing_software(data)
        self._export_softwares(
            payload = payload,
            softwares = data.get("software", {}),
            algo_software_keys = algo_software_keys,
        )
        self._export_benchmarks(
            payload = payload,
            benchmarks = data.get("benchmark", {})
        )
        self._export_plain(payload, data, 'programminglanguage')
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

        # Invalid values, existing statements and symbols: all problems at once
        payload.final_checks(get_url('mardi', 'api'))
        return payload.get_dictionary(), payload.dependency

    # ---------------------------
    # Entity export helpers
    # ---------------------------
    def _marked_entries(self, data):
        for section in ('algorithm', 'problem', 'benchmark'):
            for entry in data.get(section, {}).values():
                yield section, entry
        yield from self._software_entries(data)
        yield from self._publication_entries(data)

    def _export_algorithms(self, payload, algorithms: dict):
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

            self._add_common_metadata(payload, 'problem')

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

            self._add_common_metadata(payload, self._software_section(entry, algo_software_keys))

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

            self._add_common_metadata(payload, 'benchmark')

            self._add_references(payload, entry.get('reference'), BENCHMARK_REFERENCES)
