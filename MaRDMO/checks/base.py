'''Base validation helpers shared across all catalog check modules.'''

from rdmo.domain.models import Attribute

from ..model.constants import SECTION_MAP as SECTION_MAP_MODEL
from ..algorithm.constants import SECTION_MAP as SECTION_MAP_ALGO
from ..workflow.constants import SECTION_MAP as SECTION_MAP_WORKFLOW
from ..constants import (
    BASE_URI, CATALOG_ALGORITHM, CATALOG_MODEL,
    CATALOG_MODEL_BASICS, CATALOG_WORKFLOW,
)
from ..getters import get_mathmoddb, get_mathalgodb
from ..getters import get_options
from ..helpers import find_reference
from ..ids import NOT_FOUND, is_own_item
from ..patterns import LINE_BREAK_RE
from ..validators import doi_problem, short_description_problem, swmath_problem, url_problem, url_schemes

# An item without a real ID: the project was made before MaRDMO 0.8.0, which
# gives every item one (see ids.py); such projects are not supported
OLD_PROJECT = 'Made with MaRDMO before 0.8.0, not supported (enter it in a new project)'


def without_page(values):
    '''Return ``True`` if one of the resolved relations *values* is an own item without page.

    The preview resolves a relation to the page with its ID (e.g. ``"MF3"``);
    one that keeps a ``user:`` ID refers to an own item whose page is not
    there (deleted, or not in this section).
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
    ('SWMATH',          'swMath ID',       'ID'),
    ('DESCRIPTION_URL', 'Description URL', 'URL'),
    ('SOURCECODE_URL',  'Repository URL',  'URL'),
)
BENCHMARK_REFERENCE_CHECKS = (
    ('DOI',             'DOI',             'ID'),
    ('MORWIKI',         'MORwiki ID',      'ID'),
    ('DESCRIPTION_URL', 'Description URL', 'URL'),
    ('SOURCECODE_URL',  'Repository URL',  'URL'),
)

# Workflow textarea answers besides the procedure: answer key -> field label
_WORKFLOW_SINGLE_LINE_FIELDS = {
    'mathematical':     'Mathematical Reproducibility',
    'runtime':          'Runtime Reproducibility',
    'result':           'Reproducibility of Results',
    'originalplatform': 'Reproducibility on original Hardware or Instrument',
    'otherplatform':    'Reproducibility on other Hardware or Instrument',
}


class ChecksBase:
    '''Core infrastructure: registry init, error helpers, shared checks, and publication.'''

    def __init__(self):
        '''Initialise with ontology registries and an empty error list.'''
        self.mathmoddb = get_mathmoddb()
        self.mathalgodb = get_mathalgodb()
        self.err = []

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _error(section, page, message):
        '''Format an error string ``"Section (Page X): message"``.'''
        return f"{section} (Page {page}): {message}"

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
            self.err.append(
                self._error(
                    section = from_class,
                    page    = page_name,
                    message = f'Missing {to_class}'
                )
            )
        elif without_page(data[relation].values()):
            self.err.append(
                self._error(
                    section = from_class,
                    page    = page_name,
                    message = f'Selected {to_class} not found in {to_class} Section'
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
                    message = f'Selected {to_class} not found in {to_class} Section'
                )
            )

    def _check_without_section_items(self, items, parent_page, parent_class, item_class):
        '''Validate name and description for inline items that have no dedicated section.

        Only validates user-defined entries (``user:`` ID); portal-matched
        items are skipped.  Mirrors the checks in ``_name.html`` and
        ``_short_description.html``.

        Args:
            items:        Dict of item dicts (e.g. ``ivalue.get("programminglanguage", {})``)
            parent_page:  Human-readable page label of the parent entity.
            parent_class: Display name of the parent entity (for error section).
            item_class:   Display name of the inline item type (e.g. ``"Programming Language"``).
        '''
        for item in items.values():
            if not is_own_item(item.get('ID')):
                continue
            name = item.get('Name', '')
            desc = item.get('Description', '')
            label = name or '(unnamed)'
            if not name:
                self.err.append(self._error(
                    parent_class, parent_page,
                    f'Missing {item_class} Name ({label})'
                ))
            problem = short_description_problem(desc, name)
            if problem:
                message = {
                    'missing':      f'Missing {item_class} Short Description',
                    'too_long':     f'{item_class} Short Description Too Long',
                    'same_as_name': f'Equal {item_class} Name and Short Description Forbidden',
                }[problem]
                self.err.append(self._error(parent_class, parent_page, f'{message} ({label})'))

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
                self.err.append(self._error(section, page_name, f'{label} selected, but no {noun} provided!'))
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
                    self.err.append(self._error(section, page_name, f'Invalid {label}: {problem}'))

    def _check_doc_entries(self, doc, options, page_name, context_label):
        '''Validate that each selected doc entry has a non-empty text value.

        Args:
            doc:           Dict ``{collection_index: [option_uri, text]}``.
            options:       Options dict from :func:`~MaRDMO.getters.get_options`.
            page_name:     Human-readable page label for error messages.
            context_label: Label prefix for the error (e.g. ``"Software Requirements"``).
        '''
        for entry in doc.values():
            if not entry[1]:
                if entry[0] == options['DOI']:
                    label = 'DOI'
                elif entry[0] == options['URL']:
                    label = 'URL'
                else:
                    label = 'Value'
                self.err.append(self._error(
                    'Process Step', page_name,
                    f'Missing {context_label} {label}'
                ))
            elif entry[0] == options['URL'] and url_problem(entry[1]):
                self.err.append(self._error(
                    'Process Step', page_name,
                    f'Invalid {context_label} URL: {url_problem(entry[1])}'
                ))
            elif entry[0] == options['DOI'] and doi_problem(entry[1]):
                self.err.append(self._error(
                    'Process Step', page_name,
                    f'Invalid {context_label} DOI: {doi_problem(entry[1])}'
                ))

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
            self.err.append(self._error(from_class, page_name, f'Missing {to_class}'))

        if any(v['relation'] is None for v in entries.values()):
            self.err.append(
                self._error(
                    section = from_class,
                    page    = page_name,
                    message = f'Missing Relation Type ({to_class})'
                )
            )

        if any(v['relatant'] == 'MISSING OBJECT ITEM' for v in entries.values()):
            self.err.append(
                self._error(
                    section = from_class,
                    page    = page_name,
                    message = f'Missing Object Item ({to_class})'
                )
            )

        if without_page(v['relatant'] for v in entries.values()):
            self.err.append(
                self._error(
                    section = from_class,
                    page    = page_name,
                    message = f'Selected {to_class} not found in {to_class} Section'
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
            values = project.values.filter(
                snapshot  = None,
                attribute = Attribute.objects.get(uri=f'{BASE_URI}domain/{okey}')
            )
            # Pages with one ID (e.g. a copied tab) are one item, and so are own
            # items with the same name and description ("new" in a relation
            # always makes another page): the export would merge them
            seen, own = {}, {}
            for ikey, ivalue in ovalue.items():
                page_name = values.get(set_index=ikey).text
                if ivalue.get('ID') and seen.setdefault(ivalue['ID'], page_name) != page_name:
                    self.err.append(
                        self._error(
                            section = section_map[okey],
                            page    = page_name,
                            message = f'Same Item as Page {seen[ivalue["ID"]]} (delete one of them)'
                        )
                    )
                elif is_own_item(ivalue.get('ID')) and ivalue.get('Name'):
                    same = own.setdefault((ivalue['Name'], ivalue.get('Description') or ''), page_name)
                    if same != page_name:
                        self.err.append(
                            self._error(
                                section = section_map[okey],
                                page    = page_name,
                                message = f'Same Name and Short Description as Page {same}'
                            )
                        )
                if not ivalue.get('ID'):
                    self.err.append(
                        self._error(
                            section = section_map[okey],
                            page    = page_name,
                            message = 'Missing ID'
                        )
                    )
                if has_old_id(ivalue):
                    self.err.append(
                        self._error(
                            section = section_map[okey],
                            page    = page_name,
                            message = OLD_PROJECT
                        )
                    )
                if not ivalue.get('Name'):
                    self.err.append(
                        self._error(
                            section = section_map[okey],
                            page    = page_name,
                            message = 'Missing Name'
                        )
                    )
                problem = short_description_problem(ivalue.get('Description'), ivalue.get('Name'))
                if problem:
                    self.err.append(
                        self._error(
                            section = section_map[okey],
                            page    = page_name,
                            message = {
                                'missing':      'Missing Short Description',
                                'too_long':     'Short Description Too Long',
                                'same_as_name': 'Equal Name and Short Description Forbidden',
                            }[problem]
                        )
                    )

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
            values = project.values.filter(
                snapshot  = None,
                attribute = Attribute.objects.get(uri=f'{BASE_URI}domain/{okey}')
            )
            for ikey, ivalue in data[okey].items():
                long_label = 'Procedure' if okey == 'workflow' else 'Detailed Description'
                fields = [(long_label, text) for text in ivalue.get('descriptionLong', {}).values()]
                if isinstance(ivalue.get('reference'), str):
                    fields.append(('Reference', ivalue['reference']))
                if okey == 'workflow':
                    for key, label in _WORKFLOW_SINGLE_LINE_FIELDS.items():
                        for answer in ivalue.get(key, {}).values():
                            if answer and len(answer) > 1:
                                fields.append((label, answer[1]))
                flagged = set()
                for label, text in fields:
                    if label in flagged or not (isinstance(text, str) and LINE_BREAK_RE.search(text)):
                        continue
                    flagged.add(label)
                    page = values.filter(set_index=ikey).first()
                    self.err.append(
                        self._error(
                            section = section_map[okey],
                            page    = page.text if page else ikey,
                            message = f'Line Breaks Not Allowed in {label}'
                        )
                    )

    def _pairs(self, mapping, url_0, url_1):
        '''Return a set of the two URL strings for the given MathModDB/MathAlgoDB keys.'''
        return {
            mapping.get(key = url_0)["url"],
            mapping.get(key = url_1)["url"],
        }

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
        values = project.values.filter(
            snapshot  = None,
            attribute = Attribute.objects.get(uri=f'{BASE_URI}domain/publication')
        )
        for ikey, ivalue in data.get('publication', {}).items():
            page_name = values.get(set_index=ikey).text
            if is_own_item(ivalue.get('ID')) and not ivalue.get('reference'):
                self.err.append(
                    self._error(
                        section = 'Publication',
                        page    = page_name,
                        message = 'Missing Publication DOI'
                    )
                )
            doi = find_reference(ivalue.get('reference'), get_options()['DOI'])
            if doi and doi_problem(doi[1]):
                self.err.append(
                    self._error(
                        section = 'Publication',
                        page    = page_name,
                        message = f'Invalid Publication DOI: {doi_problem(doi[1])}'
                    )
                )

            if catalog == CATALOG_ALGORITHM:
                # Algorithm mode: optional links, but at least one required
                if ivalue.get('RelationA') or ivalue.get('RelationBS'):
                    self._check_flexible(
                        data       = ivalue,
                        page_name  = page_name,
                        relation   = 'RelationA',
                        from_class = 'Publication',
                        to_class   = 'Algorithm',
                        optional   = True
                    )
                    self._check_flexible(
                        data       = ivalue,
                        page_name  = page_name,
                        relation   = 'RelationBS',
                        from_class = 'Publication',
                        to_class   = 'Benchmark/Software',
                        optional   = True
                    )
                else:
                    self.err.append(
                        self._error(
                            section = 'Publication',
                            page    = page_name,
                            message = 'Missing Algorithm, Benchmark, or Software'
                        )
                    )
            elif catalog == CATALOG_WORKFLOW:
                # Workflow mode: at least one of Algorithm, Hardware/Software, or Entity required
                if ivalue.get('RelationA') or ivalue.get('RelationHS') or ivalue.get('RelationP'):
                    self._check_flexible(
                        data       = ivalue,
                        page_name  = page_name,
                        relation   = 'RelationA',
                        from_class = 'Publication',
                        to_class   = 'Algorithm',
                        optional   = True
                    )
                    self._check_flexible(
                        data       = ivalue,
                        page_name  = page_name,
                        relation   = 'RelationHS',
                        from_class = 'Publication',
                        to_class   = 'Hardware or Software',
                        optional   = True
                    )
                    self._check_flexible(
                        data       = ivalue,
                        page_name  = page_name,
                        relation   = 'RelationP',
                        from_class = 'Publication',
                        to_class   = 'Interdisciplinary Workflow, Process Step, or Data Set',
                        optional   = True
                    )
                else:
                    self.err.append(
                        self._error(
                            section = 'Publication',
                            page    = page_name,
                            message = 'Missing Algorithm, Hardware/Software, or Workflow Entity'
                        )
                    )
            else:
                # Model mode: mandatory link to a model entity
                self._check_flexible(
                    data       = ivalue,
                    page_name  = page_name,
                    relation   = 'RelationP',
                    from_class = 'Publication',
                    to_class   = 'Mathematical Model Entity',
                    optional   = False
                )

    def _finalise(self):
        '''Sort errors, prepend a header, and return the list.

        Returns:
            ``self.err`` — sorted and with a leading header string when errors
            are present, or an empty list when no issues were found.
        '''
        if self.err:
            self.err.sort()
            self.err.insert(0, "Following aspects prevented the export:")
        return self.err
