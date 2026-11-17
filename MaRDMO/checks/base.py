'''Base validation helpers shared across all catalog check modules.

Three kinds of findings (#167): what a page lacks (:meth:`ChecksBase._missing`),
an invalid value (:meth:`ChecksBase._invalid`) and a broken structure
(:meth:`ChecksBase._error`: a relation without type or target, an item
without page, the same item twice).  The export creates own items and
Wikidata items: every finding of theirs prevents it.  A MaRDI Portal item
is not created: what it lacks, and an invalid value it has already, are
hints the preview offers to complete; only what MaRDMO would write must be
valid, and the structure always.

The messages are translated when the checks run (the language of the
request); sections and class names stay English in the problems and are
marked with ``N_`` so that the catalog has them (see :mod:`MaRDMO.problems`).
'''
from django.utils.translation import gettext as _, gettext_noop as N_

from ..model.constants import SECTION_MAP as SECTION_MAP_MODEL
from ..algorithm.constants import SECTION_MAP as SECTION_MAP_ALGO
from ..workflow.constants import SECTION_MAP as SECTION_MAP_WORKFLOW
from ..constants import (
    CATALOG_ALGORITHM, CATALOG_MODEL,
    CATALOG_MODEL_BASICS, CATALOG_WORKFLOW,
)
from ..getters import get_mathmoddb, get_mathalgodb
from ..getters import get_options
from ..helpers import find_reference
from ..ids import NOT_FOUND, is_own_item
from ..pages import add_tab_names, page_ref
from ..patterns import LINE_BREAK_RE
from ..problems import Problem
from ..validators import doi_problem, short_description_problem, swmath_problem, url_problem, url_schemes

# An item without a real ID: the project was made before MaRDMO 0.8.0, which
# gives every item one (see ids.py); such projects are not supported
OLD_PROJECT = N_('Made with MaRDMO before 0.8.0, not supported (enter it in a new project)')


def without_page(values):
    '''Return ``True`` if one of the resolved relations *values* is an own item without page.

    The preview resolves a relation to the page with its ID (a
    :class:`~MaRDMO.pages.PageRef`); one that keeps a ``user:`` ID refers to
    an own item whose page is not there (deleted, or not in this section).
    '''
    return any(isinstance(value, str) and is_own_item(value) for value in values)


# IDs of answers saved before 0.8.0: own items, and new authors and journals of
# publications (#118)
_OLD_IDS = (NOT_FOUND, 'no author found', 'no journal found')


def has_old_id(entry):
    '''Return ``True`` if *entry* or an answer in it has an ID of before 0.8.0 ("not found").'''
    if not isinstance(entry, dict):
        return False
    return entry.get('ID') in _OLD_IDS or any(has_old_id(value) for value in entry.values())

# Reference answers to check: (option key, label in messages, noun for "no ... provided")
SOFTWARE_REFERENCE_CHECKS = (
    ('DOI',             'DOI',             'ID'),
    ('SWMATH',          N_('swMath ID'),       'ID'),
    ('DESCRIPTION_URL', N_('Description URL'), 'URL'),
    ('SOURCECODE_URL',  N_('Repository URL'),  'URL'),
)
BENCHMARK_REFERENCE_CHECKS = (
    ('DOI',             'DOI',             'ID'),
    ('MORWIKI',         N_('MORwiki ID'),      'ID'),
    ('DESCRIPTION_URL', N_('Description URL'), 'URL'),
    ('SOURCECODE_URL',  N_('Repository URL'),  'URL'),
)

# Workflow textarea answers besides the procedure: answer key -> field label
_WORKFLOW_SINGLE_LINE_FIELDS = {
    'mathematical':     N_('Mathematical Reproducibility'),
    'runtime':          N_('Runtime Reproducibility'),
    'result':           N_('Reproducibility of Results'),
    'originalplatform': N_('Reproducibility on original Hardware or Instrument'),
    'otherplatform':    N_('Reproducibility on other Hardware or Instrument'),
}


def _normalized(value):
    '''*value* as the statements of the portal have it: text without surrounding spaces and leading "+".'''
    return str(value).strip().lstrip('+')


def _snak_texts(snak):
    '''The texts of a portal snak's value: string, monolingual text, amount, time (and its year), item.'''
    value = (snak.get('datavalue') or {}).get('value')
    if isinstance(value, str):
        return {_normalized(value)}
    if not isinstance(value, dict):
        return set()
    if 'text' in value:
        return {_normalized(value['text'])}
    if 'amount' in value:
        return {_normalized(value['amount'])}
    if 'time' in value:
        time = _normalized(value['time'])
        return {time, time.split('-', 1)[0]}
    if 'id' in value:
        return {value['id']}
    return set()


class ChecksBase:
    '''Core infrastructure: registry init, error helpers, shared checks, and publication.'''

    def __init__(self):
        '''Initialise with ontology registries and an empty error list.'''
        self.mathmoddb = get_mathmoddb()
        self.mathalgodb = get_mathalgodb()
        self.err = []
        # Set when the MaRDI Portal did not answer a check (the TeX check): what it is
        self.unreachable = None
        # Statements of portal items, looked up for their invalid values (_invalid)
        self._claims = {}

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _error(section, page, message, field=None):
        '''The :class:`~MaRDMO.problems.Problem` *message* of *page* in *section*.

        As text it reads ``"Section (Page <tab>): message"``.
        '''
        return Problem(section, page, message, field)

    def _missing(self, section, page, message, field=None):
        '''Report what *page* lacks: a problem, or a hint on the page of a MaRDI Portal item (#167).

        The export does not create a portal item, so what it lacks does not
        prevent the export; the preview offers to complete it.
        '''
        self.err.append(Problem(section, page, message, field, hint=bool(page is not None and page.portal)))

    def _invalid(self, section, page, message, field=None, values=()):
        '''Report the invalid *values* of *page*: a problem, or a hint if its MaRDI Portal item has them (#167).

        MaRDMO writes to a portal item only what it does not have, so an
        invalid value of the portal item itself is not written and does not
        prevent the export; one the user added does.  The statements of the
        portal item are looked up only for such a value
        (:meth:`_portal_values`).
        '''
        hint = False
        values = [value for value in values if value not in (None, '')]
        if page is not None and page.portal and values:
            known = self._portal_values(page.item)
            hint = known is None or all(_normalized(value) in known for value in values)
        self.err.append(Problem(section, page, message, field, hint=hint))

    def _portal_values(self, item):
        '''The values of the statements of the portal item *item* (``mardi:Q…``) as text, or ``None``.

        Main values and qualifiers, normalized as :func:`_normalized`.  If the
        portal does not answer, ``None``: the finding stays a hint, and
        :attr:`unreachable` keeps the export waiting.
        '''
        # pylint: disable=import-outside-toplevel
        from ..getters import get_url
        from ..payload import PortalUnavailable, fetch_claims
        from ..queries import check_deadline
        qid = item.split(':', 1)[1]
        try:
            claims = fetch_claims([qid], get_url('mardi', 'api'), check_deadline(), 'statements', self._claims)
        except PortalUnavailable as problem:
            self.unreachable = self.unreachable or str(problem.args[0])
            return None
        found = set()
        for statements in claims.get(qid, {}).values():
            for statement in statements:
                snaks = [statement.get('mainsnak', {})] + [
                    snak for qualifiers in statement.get('qualifiers', {}).values() for snak in qualifiers]
                for snak in snaks:
                    found |= _snak_texts(snak)
        return found

    @staticmethod
    def _tab_names(project, data):
        '''Give the pages of *data* their tab names, if the answers do not have them yet.

        ``get_post_data`` writes them (:func:`~MaRDMO.pages.add_tab_names`);
        the checks name the pages by them.
        '''
        if any(isinstance(entry, dict) and 'Tab' not in entry
               for pages in data.values() if isinstance(pages, dict) for entry in pages.values()):
            add_tab_names(project, data)

    @staticmethod
    def _page(section, index, entry):
        '''The :class:`~MaRDMO.pages.PageRef` of page *index* of *section* (answers *entry*).'''
        return page_ref(section, index, entry)

    def _check_static(self, data, page_name, relation, from_class, to_class):
        '''Append an error if a mandatory single-value relation is missing or its item has no page.

        Args:
            data:       Entity answer dict.
            page_name:  Human-readable page label used in the error message.
            relation:   Key in *data* for the relation (e.g. ``"RelationRP"``).
            from_class: Display name of the source entity (for the error message).
            to_class:   Display name of the expected target entity.
        '''
        if not data.get(relation):
            self._missing(from_class, page_name, _('Missing {item}').format(item=_(to_class)), relation)
        elif without_page(data[relation].values()):
            self.err.append(
                self._error(
                    section = from_class,
                    page    = page_name,
                    message = _('Selected {item} not found in {item} Section').format(item=_(to_class)),
                    field   = relation
                )
            )

    def _check_optional_static(self, data, page_name, relation, from_class, to_class):
        '''Append an error if an optional single-value relation is selected but its item has no page.

        Unlike :meth:`_check_static`, a missing relation is not an error.

        Args:
            data:       Entity answer dict.
            page_name:  Human-readable page label used in the error message.
            relation:   Key in *data* for the relation.
            from_class: Display name of the source entity.
            to_class:   Display name of the expected target entity.
        '''
        if data.get(relation) and without_page(data[relation].values()):
            self.err.append(
                self._error(
                    section = from_class,
                    page    = page_name,
                    message = _('Selected {item} not found in {item} Section').format(item=_(to_class)),
                    field   = relation
                )
            )

    def _check_without_section_items(self, items, parent_page, parent_class, item_class, items_field=None):
        '''Validate name and description for inline items that have no dedicated section.

        Only validates user-defined entries (``user:`` ID); portal-matched
        items are skipped.  Mirrors the checks in ``_name.html`` and
        ``_short_description.html``.

        Args:
            items:        Dict of item dicts (e.g. ``ivalue.get("programminglanguage", {})``)
            parent_page:  Human-readable page label of the parent entity.
            parent_class: Display name of the parent entity (for error section).
            item_class:   Display name of the inline item type (e.g. ``"Programming Language"``).
            items_field:  The answer the preview shows the items with (the problems' field).
        '''
        for item in items.values():
            if not is_own_item(item.get('ID')):
                continue
            name = item.get('Name', '')
            desc = item.get('Description', '')
            label = name or _('(unnamed)')
            if not name:
                self.err.append(self._error(
                    parent_class, parent_page,
                    _('Missing {item} Name ({label})').format(item=_(item_class), label=label),
                    field=items_field
                ))
            problem = short_description_problem(desc, name)
            if problem:
                message = {
                    'missing':      _('Missing {item} Short Description'),
                    'too_long':     _('{item} Short Description Too Long'),
                    'same_as_name': _('Equal {item} Name and Short Description Forbidden'),
                }[problem].format(item=_(item_class))
                self.err.append(self._error(parent_class, parent_page, f'{message} ({label})', field=items_field))

    def _check_references(self, references, section, page_name, checks):
        '''Check selected reference options: value present; DOI, swMATH ID and URLs valid.

        References are looked up by option, not by position (see
        :func:`~MaRDMO.helpers.find_reference`).

        Args:
            references: Reference answers ``{collection_index: [option_uri, text]}``.
            section:    Section name for error messages (e.g. ``"Software"``).
            page_name:  Human-readable page label for error messages.
            checks:     Tuples ``(option key, label, noun)``, e.g.
                        :data:`SOFTWARE_REFERENCE_CHECKS`.
        '''
        options = get_options()
        for option_key, label, noun in checks:
            entry = find_reference(references, options[option_key])
            if not entry:
                continue
            if not entry[1]:
                self._missing(section, page_name,
                              _('{label} selected, but no {noun} provided!').format(label=_(label), noun=noun),
                              'reference')
            else:
                if noun == 'URL':
                    problem = url_problem(entry[1], url_schemes(options[option_key]))
                elif option_key == 'DOI':
                    problem = doi_problem(entry[1])
                elif option_key == 'SWMATH':
                    problem = swmath_problem(entry[1])
                else:
                    problem = None
                if problem:
                    self._invalid(section, page_name, _('Invalid {label}: {problem}').format(label=_(label), problem=problem),
                                  'reference', [entry[1]])

    def _check_doc_entries(self, doc, options, page_name, context_label, doc_field=None):
        '''Validate that each selected doc entry has a non-empty text value.

        Args:
            doc:           Dict ``{collection_index: [option_uri, text]}``.
            options:       Options dict from :func:`~MaRDMO.getters.get_options`.
            page_name:     Human-readable page label for error messages.
            context_label: Label prefix for the error (e.g. ``"Software Requirements"``).
            doc_field:     The answer the preview shows the entries with (the problems' field).
        '''
        for entry in doc.values():
            if not entry[1]:
                if entry[0] == options['DOI']:
                    label = 'DOI'
                elif entry[0] == options['URL']:
                    label = 'URL'
                else:
                    label = N_('Value')
                self._missing(N_('Process Step'), page_name,
                              _('Missing {item} {label}').format(item=_(context_label), label=_(label)), doc_field)
            elif entry[0] == options['URL'] and url_problem(entry[1]):
                self._invalid(N_('Process Step'), page_name,
                              _('Invalid {item} URL: {problem}').format(item=_(context_label), problem=url_problem(entry[1])),
                              doc_field, [entry[1]])
            elif entry[0] == options['DOI'] and doi_problem(entry[1]):
                self._invalid(N_('Process Step'), page_name,
                              _('Invalid {item} DOI: {problem}').format(item=_(context_label), problem=doi_problem(entry[1])),
                              doc_field, [entry[1]])

    def _check_flexible(
        self, data, page_name, relation, from_class, to_class=None, optional=True
    ):
        '''Append errors for a typed multi-value relation block.

        Checks for: missing block (when *optional* is ``False``), entries
        with no relation type, entries pointing to ``"MISSING OBJECT ITEM"``,
        and entries pointing to own items without page.

        Args:
            data:       Entity answer dict.
            page_name:  Human-readable page label for error messages.
            relation:   Key in *data* for the relation block.
            from_class: Display name of the source entity.
            to_class:   Display name of the target entity; defaults to
                        *from_class* when omitted.
            optional:   If ``False``, an empty relation block is also an error.
        '''
        to_class = to_class or from_class
        entries = data.get(relation, {})

        if not optional and not entries:
            self._missing(from_class, page_name, _('Missing {item}').format(item=_(to_class)), relation)

        if any(v['relation'] is None for v in entries.values()):
            self.err.append(
                self._error(
                    section = from_class,
                    page    = page_name,
                    message = _('Missing Relation Type ({item})').format(item=_(to_class)),
                    field   = relation
                )
            )

        if any(v['relatant'] == 'MISSING OBJECT ITEM' for v in entries.values()):
            self.err.append(
                self._error(
                    section = from_class,
                    page    = page_name,
                    message = _('Missing Object Item ({item})').format(item=_(to_class)),
                    field   = relation
                )
            )

        if without_page(v['relatant'] for v in entries.values()):
            self.err.append(
                self._error(
                    section = from_class,
                    page    = page_name,
                    message = _('Selected {item} not found in {item} Section').format(item=_(to_class)),
                    field   = relation
                )
            )

    def id_name_description(self, project, data, catalog):
        '''Check that every entity page has a non-empty ID, Name, and Description.

        Also flags equal Name/Description pairs and overlong descriptions
        (rules from :func:`~MaRDMO.validators.short_description_problem`).
        Skips entity types not relevant to *catalog*.

        Args:
            project: RDMO project instance (used to look up page labels).
            data:    Top-level answers dict.
            catalog: Active catalog URI suffix.
        '''
        if catalog == CATALOG_ALGORITHM:
            section_map = SECTION_MAP_ALGO
            okeys = ('algorithm', 'problem', 'software', 'benchmark', 'publication')
        elif catalog in (CATALOG_MODEL, CATALOG_MODEL_BASICS):
            section_map = SECTION_MAP_MODEL
            okeys = (
                'model', 'formulation', 'quantity', 'task',
                'problem', 'field', 'publication'
            )
        elif catalog == CATALOG_WORKFLOW:
            section_map = SECTION_MAP_WORKFLOW
            okeys = (
                'workflow', 'processstep', 'algorithm', 'software',
                'hardware', 'dataset', 'publication'
            )
        else:
            return

        for okey, ovalue in data.items():
            if okey not in okeys:
                continue
            # Pages with one ID (e.g. a copied tab) are one item, and so are own
            # items with the same name and description ("new" in a relation
            # always makes another page): the export would merge them
            seen, own = {}, {}
            for ikey, ivalue in ovalue.items():
                page_name = self._page(okey, ikey, ivalue)
                if ivalue.get('ID') and seen.setdefault(ivalue['ID'], page_name) != page_name:
                    self.err.append(
                        self._error(
                            section = section_map[okey],
                            page    = page_name,
                            message = _('Same Item as Page {tab} (delete one of them)').format(tab=seen[ivalue["ID"]].tab),
                            field   = 'Name'
                        )
                    )
                elif is_own_item(ivalue.get('ID')) and ivalue.get('Name'):
                    same = own.setdefault((ivalue['Name'], ivalue.get('Description') or ''), page_name)
                    if same != page_name:
                        self.err.append(
                            self._error(
                                section = section_map[okey],
                                page    = page_name,
                                message = _('Same Name and Short Description as Page {tab}').format(tab=same.tab),
                                field   = 'Name'
                            )
                        )
                if not ivalue.get('ID'):
                    self.err.append(
                        self._error(
                            section = section_map[okey],
                            page    = page_name,
                            message = _('Missing ID'),
                            field   = 'ID'
                        )
                    )
                if has_old_id(ivalue):
                    self.err.append(
                        self._error(
                            section = section_map[okey],
                            page    = page_name,
                            message = _(OLD_PROJECT),
                            field   = 'ID'
                        )
                    )
                # The export does not change the name and description of a
                # portal item: what is wrong with them is a hint there
                if not ivalue.get('Name'):
                    self._missing(section_map[okey], page_name, _('Missing Name'), 'Name')
                problem = short_description_problem(ivalue.get('Description'), ivalue.get('Name'))
                if problem:
                    self._missing(section_map[okey], page_name, {
                        'missing':      _('Missing Short Description'),
                        'too_long':     _('Short Description Too Long'),
                        'same_as_name': _('Equal Name and Short Description Forbidden'),
                    }[problem], 'Description')

    def single_line_text(self, project, data, catalog):
        '''Flag textarea answers containing line breaks, which the MaRDI Portal rejects.

        Covers the detailed descriptions (workflow: procedure), the formula
        reference, and the workflow reproducibility comments.  Values saved
        before the pre-save validator existed, imported projects, and API
        writes are only caught here.

        Args:
            project: RDMO project instance (used to look up page labels).
            data:    Top-level answers dict.
            catalog: Active catalog URI suffix.
        '''
        if catalog in (CATALOG_MODEL, CATALOG_MODEL_BASICS):
            section_map = SECTION_MAP_MODEL
            okeys = ('field', 'problem', 'model', 'formulation', 'quantity', 'task')
        elif catalog == CATALOG_WORKFLOW:
            section_map = SECTION_MAP_WORKFLOW
            okeys = ('workflow',)
        else:
            return
        for okey in okeys:
            if not data.get(okey):
                continue
            for ikey, ivalue in data[okey].items():
                long_label = N_('Procedure') if okey == 'workflow' else N_('Detailed Description')
                fields = [(long_label, text, 'descriptionLong') for text in ivalue.get('descriptionLong', {}).values()]
                if isinstance(ivalue.get('reference'), str):
                    fields.append((N_('Reference'), ivalue['reference'], 'reference'))
                if okey == 'workflow':
                    for key, label in _WORKFLOW_SINGLE_LINE_FIELDS.items():
                        for answer in ivalue.get(key, {}).values():
                            if answer and len(answer) > 1:
                                fields.append((label, answer[1], key))
                flagged = set()
                for label, text, line_field in fields:
                    if label in flagged or not (isinstance(text, str) and LINE_BREAK_RE.search(text)):
                        continue
                    flagged.add(label)
                    self._invalid(section_map[okey], self._page(okey, ikey, ivalue),
                                  _('Line Breaks Not Allowed in {field}').format(field=_(label)), line_field, [text])

    def _pairs(self, mapping, url_0, url_1):
        '''Return a set of the two URL strings for the given MathModDB/MathAlgoDB keys.'''
        return {
            mapping.get(key = url_0)["url"],
            mapping.get(key = url_1)["url"],
        }

    def _specializations(self, relations):
        '''The rows of *relations* whose relation type is "specializes" or "specialized by".

        A row without relation type is none of them; ``_check_flexible``
        reports it as "Missing Relation Type".
        '''
        pair = self._pairs(self.mathmoddb, 'specializes', 'specialized_by')
        return [row for row in relations.values() if (row.get('relation') or {}).get('url') in pair]

    # -------------------------------------------------------------------------
    # Publication Check (shared, behaviour differs by mode)
    # -------------------------------------------------------------------------

    def publication(self, project, data, catalog):
        '''Check Publication documentation completeness.

        Flags user-defined publications that have no DOI reference.  In
        algorithm mode, at least one Algorithm or Benchmark/Software link is
        required; in model mode, a Mathematical Model Entity link is mandatory.

        Args:
            project: RDMO project instance.
            data:    Top-level answers dict.
            catalog: Active catalog URI suffix.
        '''
        for ikey, ivalue in data.get('publication', {}).items():
            page_name = self._page('publication', ikey, ivalue)
            if is_own_item(ivalue.get('ID')) and not ivalue.get('reference'):
                self.err.append(
                    self._error(
                        section = N_('Publication'),
                        page    = page_name,
                        message = _('Missing Publication DOI'),
                        field   = 'reference'
                    )
                )
            doi = find_reference(ivalue.get('reference'), get_options()['DOI'])
            if doi and doi_problem(doi[1]):
                self._invalid(N_('Publication'), page_name,
                              _('Invalid Publication DOI: {problem}').format(problem=doi_problem(doi[1])),
                              'reference', [doi[1]])

            if catalog == CATALOG_ALGORITHM:
                # Algorithm mode: optional links, but at least one required
                if ivalue.get('RelationA') or ivalue.get('RelationBS'):
                    self._check_flexible(
                        data       = ivalue,
                        page_name  = page_name,
                        relation   = 'RelationA',
                        from_class = N_('Publication'),
                        to_class   = N_('Algorithm'),
                        optional   = True
                    )
                    self._check_flexible(
                        data       = ivalue,
                        page_name  = page_name,
                        relation   = 'RelationBS',
                        from_class = N_('Publication'),
                        to_class   = N_('Benchmark/Software'),
                        optional   = True
                    )
                else:
                    self._missing(N_('Publication'), page_name, _('Missing Algorithm, Benchmark, or Software'),
                                  'RelationA')
            elif catalog == CATALOG_WORKFLOW:
                # Workflow mode: at least one of Algorithm, Hardware/Software, or Entity required
                if ivalue.get('RelationA') or ivalue.get('RelationHS') or ivalue.get('RelationP'):
                    self._check_flexible(
                        data       = ivalue,
                        page_name  = page_name,
                        relation   = 'RelationA',
                        from_class = N_('Publication'),
                        to_class   = N_('Algorithm'),
                        optional   = True
                    )
                    self._check_flexible(
                        data       = ivalue,
                        page_name  = page_name,
                        relation   = 'RelationHS',
                        from_class = N_('Publication'),
                        to_class   = N_('Hardware or Software'),
                        optional   = True
                    )
                    self._check_flexible(
                        data       = ivalue,
                        page_name  = page_name,
                        relation   = 'RelationP',
                        from_class = N_('Publication'),
                        to_class   = N_('Interdisciplinary Workflow, Process Step, or Data Set'),
                        optional   = True
                    )
                else:
                    self._missing(N_('Publication'), page_name,
                                  _('Missing Algorithm, Hardware/Software, or Workflow Entity'), 'RelationA')
            else:
                # Model mode: mandatory link to a model entity
                self._check_flexible(
                    data       = ivalue,
                    page_name  = page_name,
                    relation   = 'RelationP',
                    from_class = N_('Publication'),
                    to_class   = N_('Mathematical Model Entity'),
                    optional   = False
                )

    def _finalise(self):
        '''Return the problems, sorted by their text (the order of the error page).

        Returns:
            ``self.err``: a list of :class:`~MaRDMO.problems.Problem`, empty when
            no issues were found.  :func:`~MaRDMO.problems.report_lines` gives
            the error page's lines.
        '''
        self.err.sort(key=str)
        return self.err
