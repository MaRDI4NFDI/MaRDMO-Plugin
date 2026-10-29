'''Worker module for Interdisciplinary Workflow preview and export.

Provides :class:`PrepareWorkflow`, which assembles RDMO questionnaire answers
into a :class:`~MaRDMO.payload.GeneratePayload` ready for submission to the
MaRDI Portal Wikibase instance.
'''


from .constants import get_relations, preview_relations, REPRODUCIBILITY, IRREPRODUCIBILITY

from ..constants import SOFTWARE_REFERENCES
from ..getters import (
    get_items,
    get_mathalgodb,
    get_mathmoddb,
    get_options,
    get_properties,
    get_publication_mapping,
    get_url
)
from ..helpers import (
    collect_items_without_section, entity_relations, entity_relations_grouped,
    unique_items,
)
from ..payload import GeneratePayload, quantity_amount

from ..publication.worker import PublicationExport


class PrepareWorkflow(PublicationExport):
    '''Prepare interdisciplinary workflow answers for preview and export.

    Inherits publication export helpers from
    :class:`~MaRDMO.publication.worker.PublicationExport` and extends them
    with workflow-specific relation mapping and Wikibase payload generation.
    '''

    def __init__(self):
        '''Initialise with Wikibase vocabulary and ontology registries.'''
        super().__init__()
        self.mathmoddb           = get_mathmoddb()
        self.mathalgodb          = get_mathalgodb()
        self.publication_mapping = get_publication_mapping()

    def preview(self, answers):
        '''Enrich the answers dict with derived display structures for the preview template.

        First iterates over :data:`~MaRDMO.workflow.constants.preview_relations` and calls
        :func:`~MaRDMO.helpers.entity_relations` for each entry to resolve cross-entity
        relation labels (e.g. Workflow → Process Step) into the ``answers`` dict — the same
        pattern used by the model and algorithm preview workers.

        Then builds ``model_task_pairs`` — an ordered list of dicts with keys ``model``,
        ``tasks``, ``has_model``, and ``has_tasks`` — for every workflow in the project
        and stores it directly on each workflow's sub-dict
        (``answers['workflow'][i]['model_task_pairs']``) so the template can access it as
        ``values.model_task_pairs`` inside the ``{% for values in answers.workflow.values %}``
        loop without integer-key lookups.  Indices from both models *and* tasks are unioned
        so that a task with no matching model (or vice versa) still produces a row with the
        appropriate validation flags set.

        Similarly builds ``algorithm_software_pairs`` and ``method_instrument_pairs`` —
        ordered lists of dicts with generic keys ``primary``, ``qualifier``,
        ``has_primary``, and ``has_qualifier`` — for every process step.  Index *i*
        pairs algorithm *i* with software *i* (and method *i* with instrument *i*);
        a missing partner raises a validation flag rendered as a red warning via the
        ``_relation_block_single_with_qualifier.html`` include.

        Args:
            answers: Top-level answers dict produced by ``get_post_data``.

        Returns:
            The same *answers* dict with relation labels and ``model_task_pairs`` added.
        '''

        # Prepare Relations for Preview
        for relation in preview_relations:
            fn = entity_relations_grouped if relation.get('grouped') else entity_relations
            fn(
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
                    self.mathmoddb           if relation.get('mapping') == 'mathmoddb'
                    else self.publication_mapping if relation.get('mapping') == 'publication'
                    else self.mathalgodb
                )
            )

        for wf_data in answers.get('workflow', {}).values():
            models = wf_data.get('model', {})
            tasks  = wf_data.get('task', {})
            all_indices = sorted(set(models) | set(tasks))
            wf_data['model_task_pairs'] = [
                {
                    'model':     models.get(idx),
                    'tasks':     list(tasks.get(idx, {}).values()),
                    'has_model': bool(models.get(idx)),
                    'has_tasks': bool(tasks.get(idx)),
                }
                for idx in all_indices
            ]

        for ps_data in answers.get('processstep', {}).values():
            # RelationA keys are 'set_index|collection_index' strings;
            # group all algorithms sharing the same set_index into one list.
            algo_by_set = {}
            for key, val in ps_data.get('RelationA', {}).items():
                set_idx = int(str(key).split('|')[0])
                algo_by_set.setdefault(set_idx, []).append(val)
            software = ps_data.get('RelationS', {})
            hardware = ps_data.get('RelationH', {})
            software_doc = ps_data.get('software-documentation', {})
            algo_params = ps_data.get('algorithm-parameter', {})
            all_indices = sorted(
                set(algo_by_set) | set(software) | set(hardware) | set(software_doc)
            )
            ps_data['algorithm_software_pairs'] = [
                {
                    'primary':       algo_by_set.get(idx, []),
                    'qualifier':     software.get(idx),
                    'has_primary':   bool(algo_by_set.get(idx)),
                    'has_qualifier': bool(software.get(idx)),
                    'parameters':    ', '.join(
                        v[1] for v in sorted(algo_params.get(idx, {}).items())
                        if v[1]
                    ),
                    'software_doc':  software_doc.get(idx, {}),
                    'hardware':      hardware.get(idx),
                }
                for idx in all_indices
            ]

            # Use raw MRelatant/IRelatant dicts so the template can display
            # Name (Description) for inline items that have no dedicated section.
            # MRelatant is {set_index: {collection_index: item}}; list the
            # methods of each set in collection order.
            meth_by_set = {
                set_idx: [raw[c] for c in sorted(raw)]
                for set_idx, raw in ps_data.get('MRelatant', {}).items()
            }
            instruments = ps_data.get('IRelatant', {})
            method_doc  = ps_data.get('method-documentation', {})
            meth_params = ps_data.get('method-parameter', {})
            all_indices = sorted(set(meth_by_set) | set(instruments) | set(method_doc))
            ps_data['method_instrument_pairs'] = [
                {
                    'primary':       meth_by_set.get(idx, []),
                    'qualifier':     instruments.get(idx),
                    'has_primary':   bool(meth_by_set.get(idx)),
                    'has_qualifier': bool(instruments.get(idx)),
                    'parameters':    ', '.join(
                        v[1] for v in sorted(meth_params.get(idx, {}).items())
                        if v[1]
                    ),
                    'method_doc':    method_doc.get(idx, {}),
                }
                for idx in all_indices
            ]

        for hw_data in answers.get('hardware', {}).values():
            cpu_dict   = hw_data.get('cpu', {})
            count_dict = hw_data.get('number-of-cpu', {})
            cores_dict = hw_data.get('cores', {})
            all_indices = sorted(set(cpu_dict) | set(count_dict) | set(cores_dict))
            hw_data['cpu_entries'] = [
                {
                    'id':          cpu_dict.get(idx, {}).get('ID'),
                    'name':        cpu_dict.get(idx, {}).get('Name'),
                    'description': cpu_dict.get(idx, {}).get('Description'),
                    'count':       count_dict.get(idx),
                    'cores':       cores_dict.get(idx),
                }
                for idx in all_indices
            ]

        answers['cpu'] = collect_items_without_section(answers, 'hardware', 'cpu')
        answers['programminglanguage'] = collect_items_without_section(
            answers, 'software', 'programminglanguage'
        )
        answers['algorithmictask'] = collect_items_without_section(
            answers, 'algorithm', 'PRelatant'
        )
        answers['academicdiscipline'] = collect_items_without_section(
            answers, 'processstep', 'RFRelatant'
        )
        answers['method'] = collect_items_without_section(
            answers, 'processstep', 'MRelatant', nested=True
        )
        answers['instrument'] = collect_items_without_section(
            answers, 'processstep', 'IRelatant'
        )

        return answers

    def export(self, data, url):
        '''Assemble and return the complete Wikibase payload for a Workflow documentation export.

        Args:
            data: Top-level workflow answers dict produced by ``get_post_data``.
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
                'items':      get_items(),
                'properties': get_properties(),
                'relations':  get_relations(),
            }
        )

        payload.process_items()

        self._export_workflows(
            payload = payload,
            data    = data,
        )
        self._export_processsteps(
            payload      = payload,
            processsteps = data.get('processstep', {}),
        )
        self._export_algorithms(
            payload    = payload,
            algorithms = data.get('algorithm', {}),
        )
        algo_software_keys = {
            (item.get('ID', ''), item.get('Name', ''), item.get('Description', ''))
            for algo in data.get('algorithm', {}).values()
            for item in algo.get('SRelatant', {}).values()
        }
        self._export_softwares(
            payload           = payload,
            softwares         = data.get('software', {}),
            algo_software_keys = algo_software_keys,
        )
        self._export_hardwares(
            payload   = payload,
            hardwares = data.get('hardware', {}),
        )
        self._export_datasets(
            payload  = payload,
            datasets = data.get('dataset', {}),
        )
        self._export_cpus(
            payload = payload,
            cpus    = data.get('cpu', {}),
        )
        self._export_programming_languages(
            payload              = payload,
            programminglanguages = data.get('programminglanguage', {}),
        )
        self._export_methods(
            payload = payload,
            methods = data.get('method', {}),
        )
        self._export_instruments(
            payload     = payload,
            instruments = data.get('instrument', {}),
        )
        self._export_algorithmic_tasks(
            payload           = payload,
            algorithmic_tasks = data.get('algorithmictask', {}),
        )
        self._export_academic_disciplines(
            payload              = payload,
            academic_disciplines = data.get('academicdiscipline', {}),
        )
        self._export_authors(
            payload      = payload,
            publications = data.get('publication', {}),
        )
        self._export_journals(
            payload      = payload,
            publications = data.get('publication', {}),
        )
        self._export_publications(
            payload      = payload,
            publications = data.get('publication', {}),
            relations    = [
                ('P2A', 'ARelatant'), ('P2BS', 'HSRelatant'), ('P2E', 'EntityRelatant'),
            ],
        )

        payload.add_item_payload()

        payload.validate_identifiers()
        payload.check_existing_relations(
            sparql_endpoint = get_url('mardi', 'sparql'),
            api_url         = get_url('mardi', 'api'),
        )

        return payload.get_dictionary(), payload.dependency

    # ------------------------------------------------------------------
    # Entity export helpers
    # ------------------------------------------------------------------

    def _export_workflows(self, payload, data: dict):
        '''Export the top-level research workflow item.

        Creates the workflow item (instance of: research workflow), adds a
        long description, all reproducibility aspects (from REPRODUCIBILITY
        constant) with optional comment qualifiers, and transferability with
        comment qualifiers.  Then links the workflow to its mathematical model
        with computational-task (used-by) qualifiers, contains process steps,
        and workflow-to-workflow intra-class relations.
        '''
        options = get_options()

        for entry in data.get('workflow', {}).values():
            if not entry.get('ID'):
                continue

            payload.get_item_key(value=entry)
            payload.set_class('Workflow')

            self._add_common_metadata(
                payload      = payload,
                qclass       = self.items["research workflow"],
                profile_type = "MaRDI workflow profile",
                description_long = True,
            )

            # Research objective
            if entry.get('objective'):
                payload.add_answer(
                    verb            = self.properties["problem statement"],
                    object_and_type = [entry['objective'], "string"],
                )

            # Reproducibility aspects
            for key in REPRODUCIBILITY:
                for val in entry.get(key, {}).values():
                    if not val:
                        continue
                    if val[0] == options['YesLargeText']:
                        qualifiers = []
                        if val[1]:
                            qualifiers += payload.add_qualifier(
                                self.properties["comment"], "string", val[1]
                            )
                        payload.add_answer(
                            verb            = self.properties["instance of"],
                            object_and_type = [self.items[REPRODUCIBILITY[key]], "wikibase-item"],
                            qualifier       = qualifiers,
                        )
                    elif val[0] == options['No']:
                        payload.add_answer(
                            verb            = self.properties["instance of"],
                            object_and_type = [self.items[IRREPRODUCIBILITY[key]], "wikibase-item"],
                        )

            # Transferability
            transferability = entry.get('transferability', {})
            if transferability:
                qualifiers = []
                for coll_dict in transferability.values():
                    for val in coll_dict.values():
                        if val:
                            qualifiers += payload.add_qualifier(
                                self.properties["comment"], "string", val
                            )
                payload.add_answer(
                    verb            = self.properties["instance of"],
                    object_and_type = [
                        self.items["transferable research workflow"], "wikibase-item",
                    ],
                    qualifier       = qualifiers,
                )

            # Mathematical model → uses, with computational task qualifiers
            for set_idx, model_item in entry.get('model', {}).items():
                if not model_item.get('ID'):
                    continue
                model_key = payload.get_item_key(model_item, 'object')
                if model_key not in payload.get_dictionary():
                    continue
                qualifiers = []
                for task_item in entry.get('task', {}).get(set_idx, {}).values():
                    if not task_item.get('ID'):
                        continue
                    task_key = payload.get_item_key(task_item, 'object')
                    if task_key not in payload.get_dictionary():
                        continue
                    qualifiers += payload.add_qualifier(
                        self.properties["used by"], "wikibase-item", task_key
                    )
                payload.add_answer(
                    verb            = self.properties["uses"],
                    object_and_type = [model_key, "wikibase-item"],
                    qualifier       = qualifiers,
                )

            # Process steps
            payload.add_single_relation(
                statement = {'relation': self.properties["contains"], 'relatant': "PSRelatant"}
            )

            # Workflow–Workflow intra-class relations
            payload.add_multiple_relation(
                statement = {'relation': "IntraClassRelation", 'relatant': "IntraClassElement"}
            )

    def _export_processsteps(self, payload, processsteps: dict):
        '''Export each process step item.

        Sets instance of: process step, then adds input/output data-set
        relations, applied methods with parameter qualifiers, software
        environment (platform relation with object-has-role: software
        qualifier) and instrument environment (platform relation with
        object-has-role: research tool qualifier), and field-of-work using
        a Wikibase item for each discipline.
        '''
        options = get_options()

        for entry in processsteps.values():
            if not entry.get("ID"):
                continue

            payload.get_item_key(value=entry)
            payload.set_class('Process Step')

            payload.add_answer(
                verb = self.properties["instance of"],
                object_and_type = [self.items["process step"], "wikibase-item"],
            )

            payload.add_single_relation(
                statement = {
                    'relation': self.properties["input data set"], 'relatant': "IDSRelatant",
                }
            )
            payload.add_single_relation(
                statement = {
                    'relation': self.properties["output data set"], 'relatant': "ODSRelatant",
                }
            )

            # Algorithms: one 'uses' statement per (set_idx, collection_idx)
            for set_idx, algo_items in entry.get('ARelatant', {}).items():
                qualifiers = []

                sw = entry.get('SRelatant', {}).get(set_idx)
                if sw and sw.get('ID'):
                    sw_key = payload.get_item_key(sw, 'object')
                    if sw_key in payload.get_dictionary():
                        qualifiers += payload.add_qualifier(
                            self.properties["platform"], "wikibase-item", sw_key
                        )

                hw = entry.get('HRelatant', {}).get(set_idx)
                if hw and hw.get('ID'):
                    hw_key = payload.get_item_key(hw, 'object')
                    if hw_key in payload.get_dictionary():
                        qualifiers += payload.add_qualifier(
                            self.properties["platform"], "wikibase-item", hw_key
                        )

                for param in entry.get('algorithm-parameter', {}).get(set_idx, {}).values():
                    if param:
                        qualifiers += payload.add_qualifier(
                            self.properties["comment"], "string", param
                        )

                for doc in entry.get('software-documentation', {}).get(set_idx, {}).values():
                    text = (doc[1] or '').strip() if doc and len(doc) > 1 else ''
                    if text:
                        if doc[0] == options['DOI']:
                            qualifiers += payload.add_qualifier(
                                self.properties["DOI"], "external-id", text
                            )
                        elif doc[0] == options['URL']:
                            qualifiers += payload.add_qualifier(
                                self.properties["URL"], "url", text
                            )

                for algo_item in algo_items.values():
                    if not algo_item.get('ID'):
                        continue
                    algo_key = payload.get_item_key(algo_item, 'object')
                    if algo_key not in payload.get_dictionary():
                        continue
                    payload.add_answer(
                        verb = self.properties["uses"],
                        object_and_type = [algo_key, "wikibase-item"],
                        qualifier = qualifiers,
                    )

            # Methods: one 'uses' statement per (set_idx, collection_idx)
            for set_idx, meth_items in entry.get('MRelatant', {}).items():
                qualifiers = []

                instr = entry.get('IRelatant', {}).get(set_idx)
                if instr and instr.get('ID'):
                    instr_key = payload.get_item_key(instr, 'object')
                    if instr_key in payload.get_dictionary():
                        qualifiers += payload.add_qualifier(
                            self.properties["platform"], "wikibase-item", instr_key
                        )

                for param in entry.get('method-parameter', {}).get(set_idx, {}).values():
                    if param:
                        qualifiers += payload.add_qualifier(
                            self.properties["comment"], "string", param
                        )

                for doc in entry.get('method-documentation', {}).get(set_idx, {}).values():
                    text = (doc[1] or '').strip() if doc and len(doc) > 1 else ''
                    if text:
                        if doc[0] == options['DOI']:
                            qualifiers += payload.add_qualifier(
                                self.properties["DOI"], "external-id", text
                            )
                        elif doc[0] == options['URL']:
                            qualifiers += payload.add_qualifier(
                                self.properties["URL"], "url", text
                            )

                for meth_item in meth_items.values():
                    if not meth_item.get('ID'):
                        continue
                    meth_key = payload.get_item_key(meth_item, 'object')
                    if meth_key not in payload.get_dictionary():
                        continue
                    payload.add_answer(
                        verb = self.properties["uses"],
                        object_and_type = [meth_key, "wikibase-item"],
                        qualifier = qualifiers,
                    )

            payload.add_single_relation(
                statement = {'relation': self.properties["field of work"], 'relatant': "RFRelatant"}
            )

    def _export_algorithms(self, payload, algorithms: dict):
        '''Export each algorithm item.

        Sets instance of: algorithm (community: MathAlgoDB, profile: MaRDI
        algorithm profile), links to its algorithmic tasks via solved-by
        (reverse) and to implementing software via implemented-by.
        No algorithm-to-algorithm intra-class relations are exported for the
        workflow catalog.
        '''
        for entry in algorithms.values():
            if not entry.get("ID"):
                continue

            payload.get_item_key(value=entry)
            payload.set_class('Algorithm')

            self._add_common_metadata(
                payload      = payload,
                community    = self.items["MathAlgoDB"],
                qclass       = self.items["algorithm"],
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

    def _export_softwares(self, payload, softwares: dict, algo_software_keys: set):
        '''Export each software item.

        Software linked to an algorithm via "implemented by" receives community
        MathAlgoDB and the MaRDI software profile; all other software receives
        only the profile.  No benchmark (tested-by) relation is exported for
        the workflow catalog.
        '''
        for entry in softwares.values():
            if not entry.get("ID"):
                continue

            payload.get_item_key(value=entry)
            payload.set_class('Software')

            entry_key = (entry.get('ID', ''), entry.get('Name', ''), entry.get('Description', ''))
            if entry_key in algo_software_keys:
                self._add_common_metadata(
                    payload      = payload,
                    community    = self.items["MathAlgoDB"],
                    qclass       = self.items["software"],
                    profile_type = "MaRDI software profile",
                )
            else:
                self._add_common_metadata(
                    payload      = payload,
                    qclass       = self.items["software"],
                    profile_type = "MaRDI software profile",
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

    def _export_hardwares(self, payload, hardwares: dict):
        '''Export each hardware item.

        Sets instance of: computer hardware, adds CPU relation, number-of-
        compute-nodes (has-part: compute node with quantity qualifier), and
        number-of-processor-cores (quantity).
        '''
        for entry in hardwares.values():
            if not entry.get("ID"):
                continue

            payload.get_item_key(value=entry)
            payload.set_class('Hardware')

            self._add_common_metadata(
                payload = payload,
                qclass  = self.items["computer hardware"],
            )

            nodes = str(entry.get('nodes') or '').strip()
            if nodes:
                payload.add_answer(
                    verb = self.properties["number of compute nodes"],
                    object_and_type = [
                        {"amount": quantity_amount(nodes), "unit": "1"},
                        "quantity",
                    ],
                )

            for idx, cpu_entry in entry.get('cpu', {}).items():
                if not cpu_entry.get('ID'):
                    continue

                # Add number of processor cores as a statement on the CPU item
                cores = str(entry.get('cores', {}).get(idx) or '').strip()
                if cores:
                    payload.get_item_key(cpu_entry)
                    payload.add_answer(
                        verb = self.properties["number of processor cores"],
                        object_and_type = [
                            {"amount": quantity_amount(cores), "unit": "1"},
                            "quantity",
                        ],
                    )
                    payload.get_item_key(value=entry)

                # Add CPU relation with count qualifier on the hardware item
                cpu_item = payload.get_item_key(cpu_entry, 'object')
                if cpu_item not in payload.get_dictionary():
                    continue
                qualifiers = []
                count = str(entry.get('number-of-cpu', {}).get(idx) or '').strip()
                if count:
                    qualifiers += payload.add_qualifier(
                        self.properties["quantity_property"],
                        "quantity",
                        {"amount": quantity_amount(count), "unit": "1"},
                    )
                payload.add_answer(
                    verb = self.properties["CPU"],
                    object_and_type = [cpu_item, "wikibase-item"],
                    qualifier = qualifiers,
                )

    def _export_datasets(self, payload, datasets: dict):
        '''Export each data set item.

        Sets instance of: data set, adds data-size (with unit from
        kilobyte/megabyte/gigabyte/terabyte options) or number-of-records,
        file-extension, binary/text classification, proprietary/open-data
        classification, data-publishing mandate (with optional DOI and URL),
        and research-data-archiving mandate (with optional end-time qualifier).
        '''
        options = get_options()

        for entry in datasets.values():
            if not entry.get("ID"):
                continue

            payload.get_item_key(value=entry)
            payload.set_class('Dataset')

            self._add_common_metadata(
                payload      = payload,
                qclass       = self.items["data set"],
                profile_type = "MaRDI data set profile",
            )

            if entry.get("Size"):
                unit_map = {
                    options["kilobyte"]: self.items["kilobyte"],
                    options["megabyte"]: self.items["megabyte"],
                    options["gigabyte"]: self.items["gigabyte"],
                    options["terabyte"]: self.items["terabyte"],
                }
                size_unit = entry["Size"][0]
                size_val  = quantity_amount(entry["Size"][1] if len(entry["Size"]) > 1 else '')
                if size_unit in unit_map:
                    payload.add_answer(
                        verb = self.properties["data size"],
                        object_and_type = [
                            {
                                "amount": size_val,
                                "unit": (
                                    f"{get_url('mardi', 'entity_uri')}"
                                    f"/entity/{unit_map[size_unit]}"
                                ),
                            },
                            "quantity",
                        ],
                    )
                elif size_unit == options["items"]:
                    payload.add_answer(
                        verb = self.properties["number of records"],
                        object_and_type = [
                            {"amount": size_val, "unit": "1"},
                            "quantity",
                        ],
                    )

            if entry.get("FileFormat"):
                payload.add_answer(
                    verb = self.properties["file extension"],
                    object_and_type = [entry["FileFormat"], "string"],
                )

            if entry.get("BinaryText"):
                if entry["BinaryText"] == options["binary"]:
                    payload.add_answer(
                        verb = self.properties["instance of"],
                        object_and_type = [self.items["binary data"], "wikibase-item"],
                    )
                elif entry["BinaryText"] == options["text"]:
                    payload.add_answer(
                        verb = self.properties["instance of"],
                        object_and_type = [self.items["text data"], "wikibase-item"],
                    )

            if entry.get("Proprietary"):
                if entry["Proprietary"] == options["Yes"]:
                    payload.add_answer(
                        verb = self.properties["instance of"],
                        object_and_type = [self.items["proprietary information"], "wikibase-item"],
                    )
                elif entry["Proprietary"] == options["No"]:
                    payload.add_answer(
                        verb = self.properties["instance of"],
                        object_and_type = [self.items["open data"], "wikibase-item"],
                    )

            if entry.get("ToPublish"):
                if entry["ToPublish"][0] == options["YesText"]:
                    payload.add_answer(
                        verb = self.properties["mandates"],
                        object_and_type = [self.items["data publishing"], "wikibase-item"],
                    )
                    val = (entry["ToPublish"][1] or "").strip() if len(entry["ToPublish"]) > 1 else ""
                    if val:
                        payload.add_answer(
                            verb = self.properties["DOI"],
                            object_and_type = [val, "external-id"],
                        )

            if entry.get("ToArchive"):
                if entry["ToArchive"][0] == options["YesText"]:
                    qualifier = []
                    year = str(entry["ToArchive"][1] or "").strip()
                    if year:
                        qualifier = payload.add_qualifier(
                            self.properties["end time"],
                            "time",
                            {
                                "time": f"+{year}-00-00T00:00:00Z",
                                "precision": 9,
                                "calendarmodel": "http://www.wikidata.org/entity/Q1985727",
                            },
                        )
                    payload.add_answer(
                        verb = self.properties["mandates"],
                        object_and_type = [self.items["research data archiving"], "wikibase-item"],
                        qualifier = qualifier,
                    )

    def _export_cpus(self, payload, cpus: dict):
        '''Export each CPU item collected from hardware sections.'''
        for entry in cpus.values():
            if not entry.get("ID"):
                continue

            payload.get_item_key(
                value = entry
            )
            payload.set_class('CPU Model')

            payload.add_answer(
                verb = self.properties["instance of"],
                object_and_type = [self.items["CPU model"], "wikibase-item"],
            )

    def _export_programming_languages(self, payload, programminglanguages: dict):
        '''Export each programming language item collected from software sections.'''
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

    def _export_methods(self, payload, methods: dict):
        '''Export each experimental method item collected from process-step sections.'''
        for entry in methods.values():
            if not entry.get("ID"):
                continue

            payload.get_item_key(
                value = entry
            )
            payload.set_class('Experimental Method')

            payload.add_answer(
                verb = self.properties["instance of"],
                object_and_type = [self.items["method"], "wikibase-item"],
            )

    def _export_instruments(self, payload, instruments: dict):
        '''Export each instrument item collected from process-step sections.'''
        for entry in instruments.values():
            if not entry.get("ID"):
                continue

            payload.get_item_key(
                value = entry
            )
            payload.set_class('Experimental Equipment')

            payload.add_answer(
                verb = self.properties["instance of"],
                object_and_type = [self.items["research tool"], "wikibase-item"],
            )

    def _export_algorithmic_tasks(self, payload, algorithmic_tasks: dict):
        '''Export each algorithmic task item collected from algorithm sections.'''
        for entry in algorithmic_tasks.values():
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

    def _export_academic_disciplines(self, payload, academic_disciplines: dict):
        '''Export each academic discipline item collected from process-step sections.'''
        for entry in academic_disciplines.values():
            if not entry.get("ID"):
                continue

            payload.get_item_key(
                value = entry
            )
            payload.set_class('Academic Discipline')

            payload.add_answer(
                verb = self.properties["instance of"],
                object_and_type = [self.items["academic discipline"], "wikibase-item"],
            )
