'''Model Documentation check mixin.'''

from rdmo.domain.models import Attribute

from ..model.constants import (
    data_properties_check,
    SECTION_MAP as SECTION_MAP_MODEL,
)
from ..constants import BASE_URI, CATALOG_MODEL, CATALOG_MODEL_BASICS
from ..patterns import QUDT_ID_STRICT_RE


class ModelMixin:
    '''Checks for Mathematical Model catalog entries.'''

    # -------------------------------------------------------------------------
    # Model Documentation Checks
    # -------------------------------------------------------------------------

    def properties(self, project, data, catalog):
        '''Check for mutually exclusive (conflicting) data-property combinations.

        Uses ``data_properties_check`` pairs to detect invalid co-occurrences
        (e.g. *linear* and *nonlinear* both selected for the same entity).

        Args:
            project: RDMO project instance.
            data:    Top-level answers dict.
            catalog: Active catalog URI suffix.
        '''
        section_map = SECTION_MAP_MODEL

        if catalog == CATALOG_MODEL_BASICS:
            okeys = ('model', 'formulation', 'task')
        elif catalog == CATALOG_MODEL:
            okeys = ('model', 'formulation', 'quantity', 'task')
        else:
            return

        for okey, ovalue in data.items():
            if okey not in okeys:
                continue
            values = project.values.filter(
                snapshot  = None,
                attribute = Attribute.objects.get(uri=f'{BASE_URI}domain/{okey}')
            )
            for ikey, ivalue in ovalue.items():
                page_name = values.get(set_index=ikey).text
                if not ivalue.get('Properties'):
                    continue
                properties = ivalue['Properties'].values()
                for url in data_properties_check:
                    if not self._pairs(self.mathmoddb, url[0], url[1]).issubset(properties):
                        continue
                    self.err.append(
                        self._error(
                            section = section_map[okey],
                            page = page_name,
                            message = f'Inconsistent Properties ({self.mathmoddb.get(key=url[0])["label"]}'
                                      f' and {self.mathmoddb.get(key=url[1])["label"]})'
                        )
                    )

    def model(self, project, data, catalog):
        '''Check Mathematical Model documentation completeness and consistency.

        Verifies that each model page has mandatory Research Problem and Task
        links, valid Formula relations, and (for the full
        catalog) consistent specialisation assumptions and expression ordering.

        Args:
            project: RDMO project instance.
            data:    Top-level answers dict.
            catalog: Active catalog URI suffix.
        '''
        values = project.values.filter(
            snapshot  = None,
            attribute = Attribute.objects.get(uri=f'{BASE_URI}domain/model')
        )
        for ikey, ivalue in data.get('model', {}).items():
            page_name = values.get(set_index=ikey).text
            self._check_static(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationRP',
                from_class = 'Mathematical Model',
                to_class   = 'Research Problem'
            )
            self._check_optional_static(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationT',
                from_class = 'Mathematical Model',
                to_class   = 'Computational Task'
            )
            self._check_flexible(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationMM',
                from_class = 'Mathematical Model'
            )
            self._check_flexible(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationMF',
                from_class = 'Mathematical Model',
                to_class   = 'Formula',
                optional   = False
            )

            if catalog == CATALOG_MODEL_BASICS:
                return

            if any(
                mval['relation']['url'] in self._pairs(
                    self.mathmoddb, 'specializes', 'specialized_by'
                )
                and not mval.get('assumption')
                for mval in ivalue.get('RelationMM', {}).values()
            ):
                self.err.append(
                    self._error(
                        section = 'Mathematical Model',
                        page    = page_name,
                        message = 'Missing Assumption (Mathematical Model Specialization)'
                    )
                )

            if any(
                mval['relation']['url'] in self._pairs(
                    self.mathmoddb, 'specializes', 'specialized_by'
                )
                and 'not found' in mval.get('assumption', {}).values()
                for mval in ivalue.get('RelationMM', {}).values()
            ):
                self.err.append(
                    self._error(
                        section = 'Mathematical Model',
                        page    = page_name,
                        message = 'Selected Formula not found in Section'
                    )
                )

            relation_mf = ivalue.get('RelationMF', {})
            if relation_mf:
                orders = [val.get('order') for val in relation_mf.values()]
                if any(order is not None for order in orders):
                    if not all(order is not None for order in orders):
                        self.err.append(
                            self._error(
                                section = 'Mathematical Model',
                                page    = page_name,
                                message = 'Missing Order Number (Formula)'
                            )
                        )
                    else:
                        order_numbers = set(int(order) for order in orders)
                        if order_numbers != set(range(1, len(relation_mf) + 1)):
                            self.err.append(
                                self._error(
                                    section = 'Mathematical Model',
                                    page    = page_name,
                                    message = 'Incorrect Order Number (Formula)'
                                )
                            )

    def task(self, project, data, catalog):
        '''Check Computational Task documentation completeness and consistency.

        Verifies that each task page has mandatory Formula links,
        valid task–task relations, and (for the full catalog) specialisation
        assumptions, containment order numbers, and Quantity links.

        Args:
            project: RDMO project instance.
            data:    Top-level answers dict.
            catalog: Active catalog URI suffix.
        '''
        values = project.values.filter(
            snapshot  = None,
            attribute = Attribute.objects.get(uri=f'{BASE_URI}domain/task')
        )
        for ikey, ivalue in data.get('task', {}).items():
            page_name = values.get(set_index=ikey).text
            self._check_flexible(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationT',
                from_class = 'Computational Task'
            )
            self._check_flexible(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationMF',
                from_class = 'Computational Task',
                to_class   = 'Formula',
                optional   = False
            )

            if catalog == CATALOG_MODEL_BASICS:
                return

            if any(
                tval['relation']['url'] in self._pairs(
                    self.mathmoddb, 'specializes', 'specialized_by'
                )
                and not tval.get('assumption')
                for tval in ivalue.get('RelationT', {}).values()
            ):
                self.err.append(
                    self._error(
                        section = 'Computational Task',
                        page    = page_name,
                        message = 'Missing Assumption (Mathematical Model Specialization)'
                    )
                )

            if any(
                tval['relation']['url'] in self._pairs(
                    self.mathmoddb, 'specializes', 'specialized_by'
                )
                and 'not found' in tval.get('assumption', {}).values()
                for tval in ivalue.get('RelationT', {}).values()
            ):
                self.err.append(
                    self._error(
                        section = 'Computational Task',
                        page    = page_name,
                        message = 'Selected Formula not found in Section'
                    )
                )

            if any(
                tval['relation']['url'] in self._pairs(
                    self.mathmoddb, 'contains_task', 'contained_in_task'
                )
                and not tval.get('order')
                for tval in ivalue.get('RelationT', {}).values()
            ):
                self.err.append(
                    self._error(
                        section = 'Computational Task',
                        page    = page_name,
                        message = 'Missing Order Number (Computational Task Containment)'
                    )
                )

            self._check_flexible(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationQQK',
                from_class = 'Computational Task',
                to_class   = 'Quantity',
                optional   = False
            )

    def formulation(self, project, data, catalog):
        '''Check Formula documentation completeness and consistency.

        For the basics catalog, flags missing references on user-defined entries.
        For the full catalog, also verifies specialisation assumptions, the
        presence of a formula, and that every element has a symbol and quantity.

        Args:
            project: RDMO project instance.
            data:    Top-level answers dict.
            catalog: Active catalog URI suffix.
        '''
        values = project.values.filter(
            snapshot  = None,
            attribute = Attribute.objects.get(uri=f'{BASE_URI}domain/formulation')
        )
        for ikey, ivalue in data.get('formulation', {}).items():
            page_name = values.get(set_index=ikey).text
            self._check_flexible(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationMF2',
                from_class ='Formula'
            )

            if catalog == CATALOG_MODEL_BASICS:
                if ivalue.get('ID') == 'not found' and not ivalue.get('reference'):
                    self.err.append(
                        self._error(
                            section = 'Formula',
                            page    = page_name,
                            message = 'Missing Reference'
                        )
                    )
                return

            if any(
                mval['relation']['url'] in self._pairs(
                    self.mathmoddb, 'specializes', 'specialized_by'
                )
                and not mval.get('assumption')
                for mval in ivalue.get('RelationMF2', {}).values()
            ):
                self.err.append(
                    self._error(
                        section = 'Formula',
                        page    = page_name,
                        message = 'Missing Assumption (Formula Specialization)'))

            if any(
                mval['relation']['url'] in self._pairs(
                    self.mathmoddb, 'specializes', 'specialized_by'
                )
                and 'not found' in mval.get('assumption', {}).values()
                for mval in ivalue.get('RelationMF2', {}).values()
            ):
                self.err.append(
                    self._error(
                        section = 'Formula',
                        page    = page_name,
                        message = 'Selected Formula not found in Section'
                    )
                )

            if not ivalue.get('Formula'):
                self.err.append(
                    self._error(
                        section = 'Formula',
                        page    = page_name,
                        message = 'Missing Formula Formula'
                    )
                )

            if not ivalue.get('element'):
                self.err.append(
                    self._error(
                        section = 'Formula',
                        page    = page_name,
                        message = 'Missing Formula Element Information'
                    )
                )
            else:
                not_symbol = any(not ev.get('symbol') for ev in ivalue['element'].values())
                not_quantity = any(not ev.get('quantity') for ev in ivalue['element'].values())
                if not_symbol:
                    self.err.append(
                        self._error(
                            section = 'Formula',
                            page    = page_name,
                            message = 'Missing Formula Symbol'
                        )
                    )
                if not_quantity:
                    self.err.append(
                        self._error(
                            section = 'Formula',
                            page    = page_name,
                            message = 'Missing Formula Quantity'
                        )
                    )

            self._check_flexible(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationMF1',
                from_class = 'Formula'
            )

    def quantity(self, project, data, catalog):
        '''Check Quantity [Kind] documentation completeness and consistency.

        Skipped entirely for the basics catalog.  Validates the Quantity/QuantityKind
        class selection, QUDT reference ID presence, formula ``\\equiv`` sign, formula
        element completeness, and relation blocks for Quantity and QuantityKind pages.

        Args:
            project: RDMO project instance.
            data:    Top-level answers dict.
            catalog: Active catalog URI suffix.
        '''
        if catalog == CATALOG_MODEL_BASICS:
            return
        values = project.values.filter(
            snapshot  = None,
            attribute = Attribute.objects.get(uri=f'{BASE_URI}domain/quantity')
        )
        for ikey, ivalue in data.get('quantity', {}).items():
            page_name = values.get(set_index=ikey).text
            if not ivalue.get('QorQK'):
                self.err.append(
                    self._error(
                        section = 'Quantity [Kind]',
                        page    = page_name,
                        message = 'Missing Quantity [Kind] Class'
                    )
                )

            if ivalue.get('reference'):
                ref = ivalue['reference']
                if ref.get(0) and not ref[0][1]:
                    self.err.append(
                        self._error(
                            section = 'Quantity [Kind]',
                            page    = page_name,
                            message = 'QUDT Quantity Kind ID selected, but no ID provided!'
                        )
                    )
                elif ref.get(0) and ref[0][1] and not QUDT_ID_STRICT_RE.match(ref[0][1]):
                    self.err.append(
                        self._error(
                            section = 'Quantity [Kind]',
                            page    = page_name,
                            message = f'Invalid QUDT Quantity Kind ID format: "{ref[0][1]}"'
                        )
                    )
                if ref.get(1) and not ref[1][1]:
                    self.err.append(
                        self._error(
                            section = 'Quantity [Kind]',
                            page    = page_name,
                            message = 'QUDT Constant ID selected, but no ID provided!'
                        )
                    )
                elif ref.get(1) and ref[1][1] and not QUDT_ID_STRICT_RE.match(ref[1][1]):
                    self.err.append(
                        self._error(
                            section = 'Quantity [Kind]',
                            page    = page_name,
                            message = f'Invalid QUDT Constant ID format: "{ref[1][1]}"'
                        )
                    )
                if ivalue.get('QorQK') == self.mathmoddb.get(key='Quantity')["label"] and ref.get(0):
                    self.err.append(
                        self._error(
                            section = 'Quantity [Kind]',
                            page    = page_name,
                            message = 'QUDT Quantity Kind ID limited to Quantity Kinds!'
                        )
                    )
                if (
                    ivalue.get('QorQK') == self.mathmoddb.get(key='QuantityKind')["label"]
                    and ref.get(1)
                ):
                    self.err.append(
                        self._error(
                            section = 'Quantity [Kind]',
                            page    = page_name,
                            message = 'QUDT Constant ID limited to Quantities!'
                        )
                    )

            if ivalue.get('Formula'):
                equiv_sign_encodings = ('>≡</', '>&#x2261;</', '>&equiv;</', '\\equiv', '\\Equiv')
                for formula in ivalue['Formula'].values():
                    if not any(equiv in formula for equiv in equiv_sign_encodings):
                        self.err.append(
                            self._error(
                                section = 'Quantity [Kind]',
                                page    = page_name,
                                message = r'Inconsistent Quantity Definition (missing \equiv)'
                            )
                        )
                if not ivalue.get('element'):
                    self.err.append(
                        self._error(
                            section = 'Quantity [Kind]',
                            page    = page_name,
                            message = 'Missing Quantity Definition Element Information'
                        )
                    )
                else:
                    if any(not ev.get('symbol') for ev in ivalue['element'].values()):
                        self.err.append(
                            self._error(
                                section = 'Quantity [Kind]',
                                page    = page_name,
                                message = 'Missing Quantity Definition Symbol'
                            )
                        )
                    if any(not ev.get('quantity') for ev in ivalue['element'].values()):
                        self.err.append(
                            self._error(
                                section = 'Quantity [Kind]',
                                page    = page_name,
                                message = 'Missing Quantity Definition Quantity'
                            )
                        )

            if ivalue.get('QorQK') == self.mathmoddb.get(key='Quantity')["label"]:
                self._check_flexible(
                    data       = ivalue,
                    page_name  = page_name,
                    relation   = 'RelationQQ',
                    from_class = 'Quantity'
                )
                self._check_flexible(
                    data       = ivalue,
                    page_name  = page_name,
                    relation   = 'RelationQQK',
                    from_class = 'Quantity'
                )
            elif ivalue.get('QorQK') == self.mathmoddb.get(key='QuantityKind')["label"]:
                self._check_flexible(
                    data       = ivalue,
                    page_name  = page_name,
                    relation   = 'RelationQKQK',
                    from_class = 'Quantity'
                )
                self._check_flexible(
                    data       = ivalue,
                    page_name  = page_name,
                    relation   = 'RelationQKQ',
                    from_class = 'Quantity'
                )

    def model_problem(self, project, data, catalog):
        '''Check Research Problem documentation completeness.

        Verifies that each problem page has valid Research Problem relations and,
        for the full catalog, a mandatory Academic Discipline link.

        Args:
            project: RDMO project instance.
            data:    Top-level answers dict.
            catalog: Active catalog URI suffix.
        '''
        values = project.values.filter(
            snapshot  = None,
            attribute = Attribute.objects.get(uri=f'{BASE_URI}domain/problem')
        )
        for ikey, ivalue in data.get('problem', {}).items():
            page_name = values.get(set_index=ikey).text
            self._check_flexible(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationRP',
                from_class = 'Research Problem'
            )
            if catalog == CATALOG_MODEL_BASICS:
                return
            self._check_static(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationRF',
                from_class = 'Research Problem',
                to_class   = 'Academic Discipline'
            )

    def field(self, project, data, catalog):
        '''Check Academic Discipline relation completeness.

        Skipped for the basics catalog.  Verifies that each discipline page
        has valid Academic Discipline–to–discipline relations.

        Args:
            project: RDMO project instance.
            data:    Top-level answers dict.
            catalog: Active catalog URI suffix.
        '''
        if catalog == CATALOG_MODEL_BASICS:
            return
        values = project.values.filter(
            snapshot  = None,
            attribute = Attribute.objects.get(uri=f'{BASE_URI}domain/field')
        )
        for ikey, ivalue in data.get('field', {}).items():
            page_name = values.get(set_index=ikey).text
            self._check_flexible(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationRF',
                from_class = 'Academic Discipline'
            )

    # -------------------------------------------------------------------------
    # Run method
    # -------------------------------------------------------------------------

    def run_model(self, project, data, catalog):
        '''Run all model-catalog checks and return the collected error list.

        Executes, in order: ID/Name/Description, data properties, model, task,
        formulation, quantity, research problem, academic discipline, and
        publication checks.

        Args:
            project: RDMO project instance.
            data:    Top-level answers dict.
            catalog: Active catalog URI suffix.

        Returns:
            List of human-readable error strings, or an empty list when all
            checks pass.
        '''
        self.id_name_description(project, data, catalog)
        self.properties(project, data, catalog)
        self.model(project, data, catalog)
        self.task(project, data, catalog)
        self.formulation(project, data, catalog)
        self.quantity(project, data, catalog)
        self.model_problem(project, data, catalog)
        self.field(project, data, catalog)
        self.publication(project, data, catalog)
        return self._finalise()
