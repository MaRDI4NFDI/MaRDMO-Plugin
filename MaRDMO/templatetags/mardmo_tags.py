'''Template tags and filters used by the MaRDMO preview templates.

Load with ``{% load mardmo_tags %}``.  The tags only show; what is wrong
the checks decide (see ``marks`` below).

Provides:

- ``option_name``           — filter: name of an RDMO option URI (e.g. ``"kilobyte"``)
- ``get_item``              — filter: ``dict[key]`` (``None`` if absent)
- ``formula``               — tag: a formula for MathJax, or as raw TeX if the
  MaRDI Portal's TeX checker rejected it
- ``relatant``              — tag: a relation's item (the link to its page)
- ``user_entity``           — tag: one entity as ``Name (Description)`` if
  user-defined, otherwise its portal ID
- ``publication_info``      — tag: citation line, authors and journal of a
  publication, each marked as on the MaRDI Portal, new, or name only
- ``marks``                 — tag: the problems of fields of a page, in red, and
  its hints, in blue
- ``remaining_marks``       — tag: the problems and hints of a page no ``marks`` showed

The red marks of the preview are the problems of the checks
(:func:`~MaRDMO.export.problems.attach`), the blue ones their hints: what a MaRDI
Portal item could have (#167).  A template shows them with ``marks`` where
it shows the field, and ``remaining_marks`` at the end of each page shows
the rest, so every problem and hint is on its page and nothing else is
marked.
'''

from django import template
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _, gettext_noop as N_, ngettext

from ..core.config import get_options
from ..core.properties import find_reference
from ..core.ids import DOI_PREFIX, is_own_item
from ..project.pages import PageRef
from ..components.validators import formula_comment_problem
from ..components.tex_check import FAILED, NOT_VERIFIED, failure_hint

register = template.Library()

# Option names the preview shows ({% translate value|option_name %}): data size units
OPTION_NAMES = (N_('kilobyte'), N_('megabyte'), N_('gigabyte'), N_('terabyte'), N_('items'))

# Fields of a page whose problems a ``marks`` showed; kept on the page (the
# includes have render contexts of their own) until its ``remaining_marks``
_SHOWN = '_marks_shown'


def _mark_list(messages, hints=()):
    '''The *messages* as red marks, then the *hints* as blue ones, one per line.'''
    marks = [('mardmo-error', message) for message in messages] + [('mardmo-hint', hint) for hint in hints]
    return format_html_join(mark_safe('<br>'), '<strong class="{}">{}</strong>', marks)


def _found(page, key, fields):
    '''The messages of *fields* in ``page[key]`` (``'Problems'`` or ``'Hints'``).'''
    return [message for field in fields for message in (page.get(key) or {}).get(field, [])]


@register.simple_tag
def marks(page, *fields, before=''):
    '''The problems of *fields* of *page* (its answers), one red line each.

    Usage: ``{% marks values "Description" %}``; *before* is put in front of
    the marks if there are any (e.g. ``before=" "``).
    '''
    if not isinstance(page, dict):
        return ''
    page.setdefault(_SHOWN, set()).update(fields)
    messages, hints = _found(page, 'Problems', fields), _found(page, 'Hints', fields)
    return format_html('{}{}', before, _mark_list(messages, hints)) if messages or hints else ''


@register.filter
def has_marks(page, field):
    '''Whether the checks found a problem with *field* of *page*, or have a hint for it.

    A block shows "NOT DOCUMENTED" only if not: an answer that is missing
    shows just its mark (``{% if not values|has_marks:field %}``).
    '''
    return isinstance(page, dict) and bool((page.get('Problems') or {}).get(field)
                                           or (page.get('Hints') or {}).get(field))


@register.simple_tag
def relatant(value):
    '''A relation's item: the link to its page, ``-`` if there is none, or its ID.

    An own item without page and a missing item are not marked here: the
    checks report them, and the block's ``marks`` shows it.
    '''
    if isinstance(value, PageRef):
        return value
    if not value or value == 'MISSING OBJECT ITEM':
        return '-'
    if isinstance(value, str) and is_own_item(value):
        return format_html('<span class="mardmo-note">{}</span>', _('item without page'))
    return value


@register.simple_tag
def remaining_marks(page):
    '''The problems and hints of *page* that no :func:`marks` of it showed; put at the end of each page.'''
    if not isinstance(page, dict):
        return ''
    shown = page.pop(_SHOWN, set())
    rest = {key: [message for field, found in (page.get(key) or {}).items() if field not in shown
                  for message in found] for key in ('Problems', 'Hints')}
    if not rest['Problems'] and not rest['Hints']:
        return ''
    return format_html('<p>{}</p>', _mark_list(rest['Problems'], rest['Hints']))


@register.filter
def own_item(identifier):
    '''Return ``True`` if *identifier* is an item of the user's own (``user:`` ID, see :func:`~MaRDMO.core.ids.is_own_item`).

    Usage: ``{% if values.ID|own_item %}``.
    '''
    # A relation resolved to its page is a PageRef, no ID
    return isinstance(identifier, str) and is_own_item(identifier)


@register.filter
def option_name(value):
    '''Return the name of the RDMO option with URI *value*, or ``''``.

    Example: ``{{ values.Size.0|option_name }}`` → ``"kilobyte"``.
    '''
    names = {uri: name for name, uri in get_options().items()}
    return names.get(value, '')


@register.filter
def get_item(mapping, key):
    '''Return ``mapping[key]``, or ``None`` if *mapping* is not a dict or lacks *key*.'''
    return mapping.get(key) if isinstance(mapping, dict) else None


@register.simple_tag
def formula(tex, verdict=None):
    '''Render *tex* for MathJax, or as raw TeX if it is invalid (the checks report why).

    Args:
        tex:     TeX string.
        verdict: Result of :func:`~MaRDMO.components.tex_check.check_formulas` for *tex*:
                 ``None`` (valid), one of :data:`~MaRDMO.components.tex_check.NOT_VERIFIED`
                 (no verdict), or the checker's message.

    Invalid formulas are not handed to MathJax (an unbalanced brace would
    swallow the rest of the line); the browser fills ``mardmo-tex-hint`` with
    MathJax's explanation.  Other formulas are wrapped in ``mardmo-formula``,
    so the browser can show them as raw TeX if MathJax cannot render them.
    Formulas that could not be checked get a note: the portal did not answer,
    or its checker failed on the formula, which is exported unchecked (with
    the likely cause and how to avoid it, :func:`~MaRDMO.components.tex_check.failure_hint`);
    multi-line formulas with a
    ``%`` comment are shown as raw TeX (see
    :func:`~MaRDMO.components.validators.formula_comment_problem`).
    '''
    if formula_comment_problem(tex):
        return format_html('<code class="mardmo-tex">{}</code>', tex)
    if verdict == FAILED:
        hint = failure_hint(tex)
        note = _("the MaRDI Portal's TeX check failed on this formula; it is exported unchecked")
        return format_html(
            '<span class="mardmo-formula" data-tex="{}">\\( {} \\)</span> '
            '<span class="mardmo-note">({}{})</span>', tex, tex, note, f'; {hint}' if hint else ''
        )
    if verdict in NOT_VERIFIED:
        return format_html(
            '<span class="mardmo-formula" data-tex="{}">\\( {} \\)</span> '
            '<span class="mardmo-note">({})</span>', tex, tex, _('not verified by the MaRDI Portal')
        )
    if verdict:
        # Not handed to MathJax; the browser adds MathJax's explanation as a note
        return format_html(
            '<code class="mardmo-tex">{}</code><span class="mardmo-note mardmo-tex-hint" data-tex="{}"></span>',
            tex, tex,
        )
    return format_html('<span class="mardmo-formula" data-tex="{}">\\( {} \\)</span>', tex, tex)


@register.inclusion_tag('MaRDMO/partials/_user_entity.html')
def user_entity(identifier, name, description, entity_class):
    '''Render one entity for relation lists.

    Entities with a portal ID are shown by their ID, user-defined entities
    (``user:`` ID or empty) as ``Name (Description)``; the checks report a
    missing name or short description.

    Usage: ``{% user_entity item.ID item.Name item.Description "SOFTWARE" %}``.
    '''
    return {
        'identifier': identifier if identifier and not is_own_item(identifier) else '',
        'name': name,
        'description': description,
        'entity_class': entity_class,
    }


# Authors shown in the citation line; more are listed below it
_CITATION_AUTHORS = 3


def _portal_status(identifier, creatable=True):
    """``(status, QID)`` of an author or journal as the export treats it.

    ``'portal'`` with its QID if it is on the MaRDI Portal, ``'new'`` if the
    export creates it, ``'name only'`` for authors without any identifier
    (the export adds just their name to the publication).
    """
    identifier = identifier or ''
    if identifier.startswith('mardi:'):
        return 'portal', identifier.split(':', 1)[1]
    return ('new' if creatable else 'name only'), ''


@register.simple_tag
def publication_name(values):
    '''The name of a publication page: that of its citation, else its DOI (``doi:10.…``, #158).

    Usage: ``{% publication_name values as name %}``.  A new publication
    has no name until its citation is found.
    '''
    if values.get('Name'):
        return values['Name']
    doi = find_reference(values.get('reference'), get_options()['DOI'])
    return f'{DOI_PREFIX}{doi[1]}' if doi else ''


@register.simple_tag
def publication_info(values):
    '''Citation line, authors and journal of a publication answer, as the export writes them.

    Usage: ``{% publication_info values as pub %}``.  Every part of the
    citation is optional; missing ones are left out.  Authors and the
    journal carry their status (on the MaRDI Portal, new, name only) and
    identifiers (ORCID, zbMATH, Wikidata, ISSN).
    '''
    authors = []
    for author in (values.get('author') or {}).values():
        if not author.get('Name'):
            continue
        orcid, zbmath = author.get('orcid') or '', author.get('zbmath') or ''
        wikidata = (author.get('wikidata') or '').removeprefix('wikidata:')
        identifier = author.get('ID') or ''
        if identifier.startswith('wikidata:'):
            wikidata = wikidata or identifier.split(':', 1)[1]
        status, qid = _portal_status(identifier, creatable=bool(
            identifier.startswith('wikidata:') or orcid or zbmath))
        authors.append({'name': author['Name'], 'status': status, 'qid': qid,
                        'orcid': orcid, 'zbmath': zbmath, 'wikidata': wikidata})

    journal = None
    for entry in (values.get('journal') or {}).values():
        if entry.get('Name'):
            identifier = entry.get('ID') or ''
            status, qid = _portal_status(identifier)
            journal = {'name': entry['Name'], 'status': status, 'qid': qid, 'issn': entry.get('issn') or '',
                       'wikidata': identifier.split(':', 1)[1] if identifier.startswith('wikidata:') else ''}
            break

    year = (values.get('date') or '')[:4]
    names = [a['name'] for a in authors]
    author_line = ', '.join(names[:_CITATION_AUTHORS]) + (' et al.' if len(names) > _CITATION_AUTHORS else '')
    parts = []
    if author_line:
        parts.append(format_html('{}{}.', author_line, f' ({year})' if year else ''))
    elif year:
        parts.append(format_html('({}).', year))
    if values.get('title'):
        parts.append(format_html('{}.', values['title']))
    if journal:
        issue = f"({values['issue']})" if values.get('issue') else ''
        volume = f" {values.get('volume') or ''}{issue}".rstrip()
        pages = f", {values['page']}" if values.get('page') else ''
        parts.append(format_html('<em>{}</em>{}{}.', journal['name'], volume, pages))
    citation = format_html(' '.join(['{}'] * len(parts)), *parts) if parts else ''

    on_portal = (values.get('ID') or '').startswith('mardi:')
    new = [] if on_portal else [_('publication')]
    if journal and journal['status'] == 'new':
        new.append(_('journal'))
    new_authors = sum(a['status'] == 'new' for a in authors)
    if new_authors:
        new.append(ngettext('{count} author', '{count} authors', new_authors).format(count=new_authors))
    return {
        'citation': citation,
        'on_portal': on_portal,
        'new': new,
        'name_only': sum(a['status'] == 'name only' for a in authors),
        'authors': authors,
        'journal': journal,
        'language': ', '.join(l.get('Name', '') for l in (values.get('language') or {}).values() if l.get('Name')),
    }
