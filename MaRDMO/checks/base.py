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
from ..helpers import is_valid_url
from ..patterns import LINE_BREAK_RE

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
        '''Append an error if a mandatory single-value relation is missing or ``"not found"``.

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
        elif 'not found' in data[relation].values():
            self.err.append(
                self._error(
                    section = from_class,
                    page    = page_name,
                    message = f'Selected {to_class} not found in {to_class} Section'
                )
            )

    def _check_optional_static(self, data, page_name, relation, from_class, to_class):
        '''Append an error if an optional single-value relation is selected but ``"not found"``.

        Unlike :meth:`_check_static`, a missing relation is not an error.

        Args:
            data:       Entity answer dict.
            page_name:  Human-readable page label used in the error message.
            relation:   Key in *data* for the relation.
            from_class: Display name of the source entity.
            to_class:   Display name of the expected target entity.
        '''
        if data.get(relation) and 'not found' in data[relation].values():
            self.err.append(
                self._error(
                    section = from_class,
                    page    = page_name,
                    message = f'Selected {to_class} not found in {to_class} Section'
                )
            )

    def _check_without_section_items(self, items, parent_page, parent_class, item_class):
        '''Validate name and description for inline items that have no dedicated section.

        Only validates user-defined entries (``ID == "not found"``); portal-matched
        items are skipped.  Mirrors the checks in ``_name.html`` and
        ``_short_description.html``.

        Args:
            items:        Dict of item dicts (e.g. ``ivalue.get("programminglanguage", {})``)
            parent_page:  Human-readable page label of the parent entity.
            parent_class: Display name of the parent entity (for error section).
            item_class:   Display name of the inline item type (e.g. ``"Programming Language"``).
        '''
        for item in items.values():
            if item.get('ID') != 'not found':
                continue
            name = item.get('Name', '')
            desc = item.get('Description', '')
            label = name or '(unnamed)'
            if not name:
                self.err.append(self._error(
                    parent_class, parent_page,
                    f'Missing {item_class} Name ({label})'
                ))
            if not desc:
                self.err.append(self._error(
                    parent_class, parent_page,
                    f'Missing {item_class} Short Description ({label})'
                ))
            elif len(desc) > 2000:
                self.err.append(self._error(
                    parent_class, parent_page,
                    f'{item_class} Short Description Too Long ({label})'
                ))
            elif desc == name:
                self.err.append(self._error(
                    parent_class, parent_page,
                    f'Equal {item_class} Name and Short Description Forbidden ({label})'
                ))

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
            elif entry[0] == options['URL'] and not is_valid_url(entry[1]):
                self.err.append(self._error(
                    'Process Step', page_name,
                    f'Invalid {context_label} URL: must start with http:// or https://'
                ))

    def _check_flexible(
        self, data, page_name, relation, from_class, to_class=None, optional=True
    ):
        '''Append errors for a typed multi-value relation block.

        Checks for: missing block (when *optional* is ``False``), entries
        with no relation type, entries pointing to ``"MISSING OBJECT ITEM"``,
        and entries pointing to ``"not found"`` items.

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

        if any(v['relatant'] == 'not found' for v in entries.values()):
            self.err.append(
                self._error(
                    section = from_class,
                    page    = page_name,
                    message = f'Selected {to_class} not found in {to_class} Section'
                )
            )

    def id_name_description(self, project, data, catalog):
        '''Check that every entity page has a non-empty ID, Name, and Description.

        Also flags equal Name/Description pairs and descriptions exceeding
        2000 characters.  Skips entity types not relevant to *catalog*.

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
            for ikey, ivalue in ovalue.items():
                page_name = values.get(set_index=ikey).text
                if not ivalue.get('ID'):
                    self.err.append(
                        self._error(
                            section = section_map[okey],
                            page    = page_name,
                            message = 'Missing ID'
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
                if not ivalue.get('Description'):
                    self.err.append(
                        self._error(
                            section = section_map[okey],
                            page    = page_name,
                            message = 'Missing Short Description'
                        )
                    )
                if ivalue.get('Name') == ivalue.get('Description'):
                    self.err.append(
                        self._error(
                            section = section_map[okey],
                            page    = page_name,
                            message = 'Equal Name and Short Description Forbidden'
                        )
                    )
                if ivalue.get('Description') and len(ivalue['Description']) > 2000:
                    self.err.append(
                        self._error(
                            section = section_map[okey],
                            page    = page_name,
                            message = 'Short Description Too Long'
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
            if ivalue.get('ID') == 'not found' and not ivalue.get('reference'):
                self.err.append(
                    self._error(
                        section = 'Publication',
                        page    = page_name,
                        message = 'Missing Publication DOI'
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
