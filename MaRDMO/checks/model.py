'''Model Documentation check mixin.'''
from django.utils.translation import gettext as _, gettext_noop as N_

from ..model.constants import (
    data_properties_check,
    SECTION_MAP as SECTION_MAP_MODEL,
)
from ..constants import CATALOG_MODEL, CATALOG_MODEL_BASICS
from ..ids import is_own_item
from .base import without_page
from ..patterns import QUDT_ID_STRICT_RE
from ..tex_check import UNAVAILABLE, check_formulas, collect_formulas, environment_hint, verdict
from ..validators import (
    ELEMENT_SYMBOL_MESSAGES, element_symbol_problems, formula_comment_problem, has_equivalence_sign,
)


class ModelMixin:
    '''Checks for Mathematical Model catalog entries.'''

    # -------------------------------------------------------------------------
    # Model Documentation Checks
    # -------------------------------------------------------------------------

    def _check_formula_syntax(self, ivalue, section, page_name):
        '''Append an error for every formula or symbol the portal's TeX checker rejects.

        Uses the verdicts collected in :meth:`run_model`; formulas the checker
        could not answer are not reported here: ``run_model`` sets
        ``unreachable``, and the export waits until the checker answers.
        '''
        verdicts = getattr(self, '_tex_verdicts', {})
        for number, tex in enumerate((ivalue.get('Formula') or {}).values(), start=1):
            if comment := formula_comment_problem(tex):
                self.err.append(self._error(section, page_name, _('Invalid Formula {number}: {problem}').format(number=number, problem=comment), field='Formula'))
            problem = verdict(verdicts, tex)
            if problem and problem != UNAVAILABLE:
                hint = environment_hint(tex)
                self.err.append(self._error(
                    section, page_name,
                    _('Invalid Formula {number}: rejected by the MaRDI Portal ({problem}), {hint}').format(
                        number=number, problem=problem, hint=hint or _('see the preview for details')),
                    field='Formula'
                ))
        for element in (ivalue.get('element') or {}).values():
            symbol = element.get('symbol') if isinstance(element, dict) else None
            if comment := formula_comment_problem(symbol):
                self.err.append(self._error(section, page_name, _('Invalid Symbol "{symbol}": {problem}').format(symbol=symbol, problem=comment), field='element'))
            problem = verdict(verdicts, symbol)
            if problem and problem != UNAVAILABLE:
                self.err.append(self._error(
                    section, page_name,
                    _('Invalid Symbol "{symbol}": rejected by the MaRDI Portal ({problem})').format(
                        symbol=symbol, problem=problem),
                    field='element'
                ))

    def _check_element_symbols(self, ivalue, section, page_name):
        '''Append an error for every symbol that does not stand for exactly one quantity.

        The symbol table belongs to the item (one formula or one quantity
        definition) and is shared by all of its formula fields.
        '''
        reported = set()
        for key, problem in element_symbol_problems(ivalue.get('element')).items():
            symbol = ivalue['element'][key].get('symbol')
            if (symbol, problem) in reported:
                continue
            reported.add((symbol, problem))
            self.err.append(self._error(
                section, page_name, _('Symbol "{symbol}" {problem}').format(symbol=symbol, problem=_(ELEMENT_SYMBOL_MESSAGES[problem])),
                field='element'
            ))

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
            for ikey, ivalue in ovalue.items():
                page_name = self._page(okey, ikey, ivalue)
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
                            message = _('Inconsistent Properties ({a} and {b})').format(
                                a=_(self.mathmoddb.get(key=url[0])["label"]), b=_(self.mathmoddb.get(key=url[1])["label"])),
                                      field   = 'Properties'
                        )
                    )

    def model(self, project, data, catalog):
        '''Check Mathematical Model documentation completeness and consistency.

        Verifies that each model page has mandatory Research Problem and Task
        links, valid Formula relations, and (for the full
        catalog) consistent specialisation assumptions.

        Args:
            project: RDMO project instance.
            data:    Top-level answers dict.
            catalog: Active catalog URI suffix.
        '''
        for ikey, ivalue in data.get('model', {}).items():
            page_name = self._page('model', ikey, ivalue)
            self._check_static(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationRP',
                from_class = N_('Mathematical Model'),
                to_class   = N_('Research Problem')
            )
            self._check_optional_static(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationT',
                from_class = N_('Mathematical Model'),
                to_class   = N_('Computational Task')
            )
            self._check_flexible(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationMM',
                from_class = N_('Mathematical Model')
            )
            self._check_flexible(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationMF',
                from_class = N_('Mathematical Model'),
                to_class   = N_('Formula'),
                optional   = False
            )

            if catalog == CATALOG_MODEL_BASICS:
                continue

            if any(
                not mval.get('assumption')
                for mval in self._specializations(ivalue.get('RelationMM', {}))
            ):
                self.err.append(
                    self._error(
                        section = N_('Mathematical Model'),
                        page    = page_name,
                        message = _('Missing Assumption (Mathematical Model Specialization)'),
                        field   = 'RelationMM'
                    )
                )

            if any(
                without_page((mval.get('assumption') or {}).values())
                for mval in self._specializations(ivalue.get('RelationMM', {}))
            ):
                self.err.append(
                    self._error(
                        section = N_('Mathematical Model'),
                        page    = page_name,
                        message = _('Selected Formula not found in Section'),
                        field   = 'RelationMM'
                    )
                )

    def task(self, project, data, catalog):
        '''Check Computational Task documentation completeness and consistency.

        Verifies that each task page has mandatory Formula links,
        valid task–task relations, and (for the full catalog) specialisation
        assumptions and Quantity links.

        Args:
            project: RDMO project instance.
            data:    Top-level answers dict.
            catalog: Active catalog URI suffix.
        '''
        for ikey, ivalue in data.get('task', {}).items():
            page_name = self._page('task', ikey, ivalue)
            self._check_flexible(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationT',
                from_class = N_('Computational Task')
            )
            self._check_flexible(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationMF',
                from_class = N_('Computational Task'),
                to_class   = N_('Formula'),
                optional   = False
            )

            if catalog == CATALOG_MODEL_BASICS:
                continue

            if any(
                not tval.get('assumption')
                for tval in self._specializations(ivalue.get('RelationT', {}))
            ):
                self.err.append(
                    self._error(
                        section = N_('Computational Task'),
                        page    = page_name,
                        message = _('Missing Assumption (Computational Task Specialization)'),
                        field   = 'RelationT'
                    )
                )

            if any(
                without_page((tval.get('assumption') or {}).values())
                for tval in self._specializations(ivalue.get('RelationT', {}))
            ):
                self.err.append(
                    self._error(
                        section = N_('Computational Task'),
                        page    = page_name,
                        message = _('Selected Formula not found in Section'),
                        field   = 'RelationT'
                    )
                )

            self._check_flexible(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationQQK',
                from_class = N_('Computational Task'),
                to_class   = N_('Quantity'),
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
        for ikey, ivalue in data.get('formulation', {}).items():
            page_name = self._page('formulation', ikey, ivalue)
            self._check_flexible(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationMF2',
                from_class =N_('Formula')
            )

            if catalog == CATALOG_MODEL_BASICS:
                if is_own_item(ivalue.get('ID')) and not ivalue.get('reference'):
                    self.err.append(
                        self._error(
                            section = N_('Formula'),
                            page    = page_name,
                            message = _('Missing Reference'),
                            field   = 'reference'
                        )
                    )
                continue

            if any(
                not mval.get('assumption')
                for mval in self._specializations(ivalue.get('RelationMF2', {}))
            ):
                self.err.append(
                    self._error(
                        section = N_('Formula'),
                        page    = page_name,
                        message = _('Missing Assumption (Formula Specialization)'), field='RelationMF2'))

            if any(
                without_page((mval.get('assumption') or {}).values())
                for mval in self._specializations(ivalue.get('RelationMF2', {}))
            ):
                self.err.append(
                    self._error(
                        section = N_('Formula'),
                        page    = page_name,
                        message = _('Selected Formula not found in Section'),
                        field   = 'RelationMF2'
                    )
                )

            if not ivalue.get('Formula'):
                self.err.append(
                    self._error(
                        section = N_('Formula'),
                        page    = page_name,
                        message = _('Missing Formula Formula'),
                        field   = 'Formula'
                    )
                )
            self._check_formula_syntax(ivalue, N_('Formula'), page_name)

            if not ivalue.get('element'):
                self.err.append(
                    self._error(
                        section = N_('Formula'),
                        page    = page_name,
                        message = _('Missing Formula Element Information'),
                        field   = 'element'
                    )
                )
            else:
                not_symbol = any(not ev.get('symbol') for ev in ivalue['element'].values())
                not_quantity = any(not ev.get('quantity') for ev in ivalue['element'].values())
                if not_symbol:
                    self.err.append(
                        self._error(
                            section = N_('Formula'),
                            page    = page_name,
                            message = _('Missing Formula Symbol'),
                            field   = 'element'
                        )
                    )
                if not_quantity:
                    self.err.append(
                        self._error(
                            section = N_('Formula'),
                            page    = page_name,
                            message = _('Missing Formula Quantity'),
                            field   = 'element'
                        )
                    )
                self._check_element_symbols(ivalue, N_('Formula'), page_name)

            self._check_flexible(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationMF1',
                from_class = N_('Formula')
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
        for ikey, ivalue in data.get('quantity', {}).items():
            page_name = self._page('quantity', ikey, ivalue)
            if not ivalue.get('QorQK'):
                self.err.append(
                    self._error(
                        section = N_('Quantity [Kind]'),
                        page    = page_name,
                        message = _('Missing Quantity [Kind] Class'),
                        field   = 'QorQK'
                    )
                )

            if ivalue.get('reference'):
                ref = ivalue['reference']
                if ref.get(0) and not ref[0][1]:
                    self.err.append(
                        self._error(
                            section = N_('Quantity [Kind]'),
                            page    = page_name,
                            message = _('QUDT Quantity Kind ID selected, but no ID provided!'),
                            field   = 'reference'
                        )
                    )
                elif ref.get(0) and ref[0][1] and not QUDT_ID_STRICT_RE.match(ref[0][1]):
                    self.err.append(
                        self._error(
                            section = N_('Quantity [Kind]'),
                            page    = page_name,
                            message = _('Invalid QUDT Quantity Kind ID format: "{value}"').format(value=ref[0][1]),
                            field   = 'reference'
                        )
                    )
                if ref.get(1) and not ref[1][1]:
                    self.err.append(
                        self._error(
                            section = N_('Quantity [Kind]'),
                            page    = page_name,
                            message = _('QUDT Constant ID selected, but no ID provided!'),
                            field   = 'reference'
                        )
                    )
                elif ref.get(1) and ref[1][1] and not QUDT_ID_STRICT_RE.match(ref[1][1]):
                    self.err.append(
                        self._error(
                            section = N_('Quantity [Kind]'),
                            page    = page_name,
                            message = _('Invalid QUDT Constant ID format: "{value}"').format(value=ref[1][1]),
                            field   = 'reference'
                        )
                    )
                if ivalue.get('QorQK') == self.mathmoddb.get(key='Quantity')["label"] and ref.get(0):
                    self.err.append(
                        self._error(
                            section = N_('Quantity [Kind]'),
                            page    = page_name,
                            message = _('QUDT Quantity Kind ID limited to Quantity Kinds!'),
                            field   = 'reference'
                        )
                    )
                if (
                    ivalue.get('QorQK') == self.mathmoddb.get(key='QuantityKind')["label"]
                    and ref.get(1)
                ):
                    self.err.append(
                        self._error(
                            section = N_('Quantity [Kind]'),
                            page    = page_name,
                            message = _('QUDT Constant ID limited to Quantities!'),
                            field   = 'reference'
                        )
                    )

            if ivalue.get('Formula'):
                self._check_formula_syntax(ivalue, N_('Quantity [Kind]'), page_name)
                for formula in ivalue['Formula'].values():
                    if not has_equivalence_sign(formula):
                        self.err.append(
                            self._error(
                                section = N_('Quantity [Kind]'),
                                page    = page_name,
                                message = _(r'Inconsistent Quantity Definition (missing \equiv)'),
                                field   = 'Formula'
                            )
                        )
                if not ivalue.get('element'):
                    self.err.append(
                        self._error(
                            section = N_('Quantity [Kind]'),
                            page    = page_name,
                            message = _('Missing Quantity Definition Element Information'),
                            field   = 'element'
                        )
                    )
                else:
                    if any(not ev.get('symbol') for ev in ivalue['element'].values()):
                        self.err.append(
                            self._error(
                                section = N_('Quantity [Kind]'),
                                page    = page_name,
                                message = _('Missing Quantity Definition Symbol'),
                                field   = 'element'
                            )
                        )
                    if any(not ev.get('quantity') for ev in ivalue['element'].values()):
                        self.err.append(
                            self._error(
                                section = N_('Quantity [Kind]'),
                                page    = page_name,
                                message = _('Missing Quantity Definition Quantity'),
                                field   = 'element'
                            )
                        )
                    self._check_element_symbols(ivalue, N_('Quantity [Kind]'), page_name)

            if ivalue.get('QorQK') == self.mathmoddb.get(key='Quantity')["label"]:
                self._check_flexible(
                    data       = ivalue,
                    page_name  = page_name,
                    relation   = 'RelationQQ',
                    from_class = N_('Quantity')
                )
                self._check_flexible(
                    data       = ivalue,
                    page_name  = page_name,
                    relation   = 'RelationQQK',
                    from_class = N_('Quantity')
                )
            elif ivalue.get('QorQK') == self.mathmoddb.get(key='QuantityKind')["label"]:
                self._check_flexible(
                    data       = ivalue,
                    page_name  = page_name,
                    relation   = 'RelationQKQK',
                    from_class = N_('Quantity')
                )
                self._check_flexible(
                    data       = ivalue,
                    page_name  = page_name,
                    relation   = 'RelationQKQ',
                    from_class = N_('Quantity')
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
        for ikey, ivalue in data.get('problem', {}).items():
            page_name = self._page('problem', ikey, ivalue)
            self._check_flexible(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationRP',
                from_class = N_('Research Problem')
            )
            if catalog == CATALOG_MODEL_BASICS:
                continue
            self._check_static(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationRF',
                from_class = N_('Research Problem'),
                to_class   = N_('Academic Discipline')
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
        for ikey, ivalue in data.get('field', {}).items():
            page_name = self._page('field', ikey, ivalue)
            self._check_flexible(
                data       = ivalue,
                page_name  = page_name,
                relation   = 'RelationRF',
                from_class = N_('Academic Discipline')
            )

    # -------------------------------------------------------------------------
    # Run method
    # -------------------------------------------------------------------------

    def run_model(self, project, data, catalog):
        '''Run all model-catalog checks and return the collected error list.

        Executes, in order: ID/Name/Description, single-line text, data properties, model, task,
        formulation, quantity, research problem, academic discipline, and
        publication checks.

        Args:
            project: RDMO project instance.
            data:    Top-level answers dict.
            catalog: Active catalog URI suffix.

        Returns:
            Sorted list of :class:`~MaRDMO.problems.Problem`, empty when
            all checks pass.
        '''
        self._tab_names(project, data)
        # Portal verdicts for all formulas and symbols (only the full catalog has them)
        self._tex_verdicts = (
            check_formulas(collect_formulas(data)) if catalog == CATALOG_MODEL else {}
        )
        if UNAVAILABLE in self._tex_verdicts.values():
            self.unreachable = _('The TeX check of the MaRDI Portal did not answer for some formulas.')
        self.id_name_description(project, data, catalog)
        self.single_line_text(project, data, catalog)
        self.properties(project, data, catalog)
        self.model(project, data, catalog)
        self.task(project, data, catalog)
        self.formulation(project, data, catalog)
        self.quantity(project, data, catalog)
        self.model_problem(project, data, catalog)
        self.field(project, data, catalog)
        self.publication(project, data, catalog)
        return self._finalise()
