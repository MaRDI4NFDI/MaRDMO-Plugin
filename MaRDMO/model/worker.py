'''Background worker for the Model documentation catalog.

Implements the task that collects mathematical model metadata from User, MarDI Portal,
and Wikidata, renders a preview document, and exports the result to the MaRDI
Portal.

Provides:

- :class:`PrepareModel` — orchestrates data collection, preview rendering,
  and portal export for a single model documentation project
'''


from .constants import (
    data_properties_check,
    DEPENDENT_PROPERTIES,
    INDEPENDENT_PROPERTIES,
    preview_relations,
    preview_map_general,
    preview_map_quantity,
    get_relations,
)
from .utils import get_data_properties, map_entity_quantity

from ..getters import get_items, get_mathmoddb, get_properties, get_publication_mapping, get_url
from ..helpers import entity_relations, map_entity, unique_items
from ..payload import GeneratePayload

from ..publication.worker import PublicationExport

class PrepareModel(PublicationExport):
    '''Prepare Mathematical Model answers for preview rendering and MaRDI Portal export.

    Inherits publication export helpers from
    :class:`~MaRDMO.publication.worker.PublicationExport` and extends them
    with model-specific relation mapping, property conflict detection, and
    Wikibase payload generation.
    '''
    def __init__(self):
        '''Initialise with Wikibase vocabulary and the MathModDB ontology registry.'''
        super().__init__()
        self.mathmoddb          = get_mathmoddb()
        self.publication_mapping = get_publication_mapping()

    def preview(self, answers):
        '''Resolve entity cross-references and property checks for the preview page.

        Applies general label/relation mappings, entity-relation links, and
        data-property conflict detection so that the preview template receives
        a fully-resolved answers dict.

        Args:
            answers: Top-level answers dict (mutated in place).

        Returns:
            The mutated *answers* dict.
        '''

        # Prepare General Mappings
        for mapping in preview_map_general:
            map_entity(
                data = answers,
                idx = {
                    'from': mapping[0],
                    'to': mapping[1]
                },
                entity = {
                    'old_name': mapping[2],
                    'new_name': mapping[3],
                    'encryption': mapping[4]
                }
            )

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
                order = {
                    'formulation': relation['formulation'],
                    'task': relation['task']
                },
                assumption = relation['assumption'],
                mapping = (
                    self.publication_mapping if relation.get('mapping') == 'publication'
                    else self.mathmoddb
                )
            )

        # Quantity Type as Label
        for quantity in answers.get("quantity", {}).values():
            if quantity.get("QorQK"):
                quantity['QorQK'] = self.mathmoddb.get(url=quantity["QorQK"])['label']

        # Prepare Quantity Mapping
        for mapping in preview_map_quantity:
            map_entity_quantity(
                data = answers,
                entity_type = mapping
            )

        # Check Data Properties for Preview
        for mathmoddb_class in answers.values():
            for class_item in mathmoddb_class.values():
                properties = class_item.get('Properties')
                if not properties:
                    continue

                present = set(properties.values())
                wrong = set()

                for pair in data_properties_check:
                    opt_a, opt_b = self.mathmoddb.get(key=pair[0])["url"], self.mathmoddb.get(key=pair[1])["url"]
                    if {opt_a, opt_b}.issubset(present):
                        wrong.update([pair[0], pair[1]])
                        present.discard(opt_a)
                        present.discard(opt_b)

                all_prop_keys = {k for k, _ in DEPENDENT_PROPERTIES + INDEPENDENT_PROPERTIES}
                correct = {key for key in all_prop_keys if self.mathmoddb.get(key=key)["url"] in present}

                class_item['Properties_Check'] = [
                    {'label': self.mathmoddb.get(key=k)['label'], 'error': k in wrong}
                    for k in correct | wrong
                ]

        return answers

    def export(self, data, url):
        '''Assemble and return the complete Wikibase payload for a Model documentation export.

        Creates a :class:`~MaRDMO.payload.GeneratePayload` instance, processes
        all unique items, then delegates each entity section (fields, problems,
        models, formulations, quantities, tasks, publications) to dedicated
        helper methods.

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
                'data_properties': get_data_properties,
                'items': get_items(),
                'properties': get_properties(),
                'relations': get_relations()
            }
        )

        # Add / Retrieve Components of Model Item
        payload.process_items()

        # Delegate to helper functions
        self._export_fields(
            payload = payload,
            fields = data.get("field", {}),
        )
        self._export_problems(
            payload = payload,
            problems = data.get("problem", {})
        )
        self._export_models(
            payload = payload,
            models = data.get("model", {})
        )
        self._export_tasks(
            payload = payload,
            tasks = data.get("task", {})
        )
        self._export_formulations(
            payload = payload,
            formulations = data.get("formulation", {})
        )
        self._export_quantities(
            payload = payload,
            quantities = data.get("quantity", {})
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
            relations = [('P2E', 'EntityRelatant')]
        )

        # Construct Item Payloads
        payload.add_item_payload()

        # Mark Relations that already exist on the Portal
        payload.check_existing_relations(
            sparql_endpoint = get_url('mardi', 'sparql'),
            api_url = get_url('mardi', 'api'),
        )
        return payload.get_dictionary(), payload.dependency

    # ---------------------------
    # Shared helper
    # ---------------------------
    # ---------------------------
    # Entity export helpers
    # ---------------------------
    def _export_fields(self, payload, fields: dict):
        for entry in fields.values():
            if not entry.get("ID"):
                continue

            payload.get_item_key(
                value = entry
            )
            payload.set_class('Academic Discipline')

            self._add_common_metadata(
                payload = payload,
                community = self.items["MathModDB"],
                description_long = True,
                qclass =self.items["academic discipline"],
                profile_type = "MaRDI research field profile",
            )

            payload.add_aliases(
                aliases_dict = entry.get('Alias')
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
            payload.set_class('Research Problem')

            self._add_common_metadata(
                payload = payload,
                community = self.items["MathModDB"],
                description_long = True,
                qclass =self.items["research problem"],
                profile_type = "MaRDI research problem profile",
            )

            payload.add_aliases(
                aliases_dict = entry.get('Alias')
            )

            payload.add_single_relation(
                statement = {
                    'relation': self.properties["contains"],
                    'relatant': "RFRelatant"
                },
                reverse = True
            )

            payload.add_multiple_relation(
                statement = {
                    'relation': "IntraClassRelation",
                    'relatant': "IntraClassElement"
                }
            )

    def _export_models(self, payload, models: dict):
        for entry in models.values():
            if not entry.get("ID"):
                continue

            payload.get_item_key(
                value = entry
            )
            payload.set_class('Mathematical Model')

            self._add_common_metadata(
                payload = payload,
                community = self.items["MathModDB"],
                description_long = True,
                qclass =self.items["mathematical model"],
                profile_type = "MaRDI model profile",
            )

            payload.add_aliases(
                aliases_dict = entry.get('Alias')
            )

            payload.add_data_properties(
                item_class = "model"
            )

            payload.add_multiple_relation(
                statement = {
                    'relation': "MM2MF",
                    'relatant': "MFRelatant"
                },
                optional_qualifier = ['series ordinal']
            )

            payload.add_single_relation(
                statement = {
                    'relation': self.properties["modelled by"],
                    'relatant': "RPRelatant"
                },
                reverse = True
            )

            payload.add_single_relation(
                statement = {
                    'relation': self.properties["used by"],
                    'relatant': "TRelatant"
                }
            )

            payload.add_multiple_relation(
                statement = {
                    'relation': "IntraClassRelation",
                    'relatant': "IntraClassElement"
                },
                optional_qualifier = ['assumes']
            )

    def _export_tasks(self, payload, tasks: dict):
        for entry in tasks.values():
            if not entry.get("ID"):
                continue

            payload.get_item_key(
                value = entry
            )
            payload.set_class('Computational Task')

            self._add_common_metadata(
                payload = payload,
                community = self.items["MathModDB"],
                description_long = True,
                qclass =self.items["computational task"],
                profile_type = "MaRDI task profile",
            )

            payload.add_aliases(
                aliases_dict = entry.get('Alias')
            )

            payload.add_data_properties(
                item_class = "task"
            )

            payload.add_multiple_relation(
                statement = {
                    'relation': "T2MF",
                    'relatant': "MFRelatant"
                }
            )

            payload.add_multiple_relation(
                statement = {
                    'relation': "T2Q",
                    'relatant': "QRelatant"
                }
            )

            payload.add_multiple_relation(
                statement = {
                    'relation': "IntraClassRelation",
                    'relatant': "IntraClassElement"
                },
                optional_qualifier = ['assumes', 'series ordinal']
            )

    def _export_formulations(self, payload, formulations: dict):
        for entry in formulations.values():
            if not entry.get("ID"):
                continue

            payload.get_item_key(
                value = entry
            )
            payload.set_class('Formula')

            self._add_common_metadata(
                payload = payload,
                community = self.items["MathModDB"],
                description_long = True,
                qclass =self.items["formula"],
                profile_type = "MaRDI formula profile",
            )

            payload.add_aliases(
                aliases_dict = entry.get('Alias')
            )

            payload.add_data_properties(
                item_class = "equation"
            )

            if entry.get('reference'):
                payload.add_answer(
                    verb = self.properties["comment"],
                    object_and_type = [entry.get('reference'), "string"],
                )

            payload.add_answers(
                mardmo_property = "Formula",
                wikibase_property = "defining formula",
                datatype = "math",
            )

            payload.add_in_defining_formula()

            payload.add_multiple_relation(
                statement = {
                    'relation': "MF2MF",
                    'relatant': "MFRelatant"
                }
            )

            payload.add_multiple_relation(
                statement = {
                    'relation': "IntraClassRelation",
                    'relatant': "IntraClassElement"
                },
                optional_qualifier = ['assumes']
            )

    def _export_quantities(self, payload, quantities: dict):
        for entry in quantities.values():
            if not entry.get("ID"):
                continue

            payload.get_item_key(
                value = entry
            )
            payload.set_class('Quantity')

            if entry.get("QorQK") == self.mathmoddb.get(key='Quantity')['label']:
                self._add_common_metadata(
                    payload = payload,
                    qclass = self.items["quantity"],
                    profile_type = "MaRDI quantity profile",
                )
                qtype = "quantity"

            elif entry.get("QorQK") == self.mathmoddb.get(key='QuantityKind')['label']:
                self._add_common_metadata(
                    payload = payload,
                    qclass = self.items["kind of quantity"],
                    profile_type = "MaRDI quantity profile",
                )
                qtype = "quantity kind"

            else:
                continue

            payload.add_aliases(
                aliases_dict = entry.get('Alias')
            )

            payload.add_data_properties(
                item_class = qtype
            )

            reference = entry.get("reference") or {}

            if qtype == "quantity kind" and reference.get(0):
                payload.add_answer(
                    verb = self.properties["QUDT quantity kind ID"],
                    object_and_type = [reference[0][1], "external-id"],
                )

            if qtype == "quantity" and reference.get(1):
                payload.add_answer(
                    verb = self.properties["QUDT constant ID"],
                    object_and_type = [reference[1][1], "external-id"],
                )

            payload.add_answers(
                mardmo_property = "Formula",
                wikibase_property = "defining formula",
                datatype = "math",
            )

            payload.add_in_defining_formula()

            if qtype == "quantity":
                payload.add_multiple_relation(
                    statement = {
                        'relation': "Q2Q",
                        'relatant': "QRelatant-Q"
                    }
                )

                payload.add_multiple_relation(
                    statement = {
                        'relation': "Q2QK",
                        'relatant': "QKRelatant-Q"
                    }
                )

            else:
                payload.add_multiple_relation(
                    statement = {
                        'relation': "QK2QK",
                        'relatant': "QKRelatant-QK"
                    }
                )

                payload.add_multiple_relation(
                    statement = {
                        'relation': "QK2Q",
                        'relatant': "QRelatant-QK"
                    }
                )
