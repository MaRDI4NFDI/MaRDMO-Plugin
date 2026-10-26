'''Template tags and filters used by the MaRDMO preview templates.

Load with ``{% load mardmo_tags %}``.  The validation rules come from
:mod:`~MaRDMO.validators`, the same functions the documentation checker uses,
so the preview and the export check always agree.

Provides:

- ``has_line_break``        — filter: text contains line breaks (rejected by the portal)
- ``has_equivalence_sign``  — filter: defining formula contains ``\\equiv`` / ``≡``
- ``option_name``           — filter: name of an RDMO option URI (e.g. ``"kilobyte"``)
- ``url_problem``           — filter: what is wrong with a URL, or ``''``
- ``doi_problem``           — filter: what is wrong with a DOI, or ``''``
- ``swmath_problem``        — filter: what is wrong with a swMATH ID, or ``''``
- ``description_error``     — tag: error text for a short description, or ``''``
- ``user_entity``           — tag: one entity as ``Name (Description)`` with
  error markers if user-defined, otherwise its portal ID
'''

from django import template

from ..getters import get_options
from ..patterns import LINE_BREAK_RE
from ..validators import has_equivalence_sign as _has_equivalence_sign
from ..validators import short_description_problem
from ..validators import doi_problem as _doi_problem
from ..validators import swmath_problem as _swmath_problem
from ..validators import url_problem as _url_problem
from ..validators import url_schemes

register = template.Library()


@register.filter
def has_line_break(value):
    '''Return ``True`` if *value* is a string containing line breaks.'''
    return isinstance(value, str) and bool(LINE_BREAK_RE.search(value))


@register.filter
def has_equivalence_sign(value):
    '''Return ``True`` if the defining formula *value* contains an equivalence sign.'''
    return _has_equivalence_sign(value)


@register.filter
def option_name(value):
    '''Return the name of the RDMO option with URI *value*, or ``''``.

    Example: ``{{ values.Size.0|option_name }}`` → ``"kilobyte"``.
    '''
    names = {uri: name for name, uri in get_options().items()}
    return names.get(value, '')


@register.filter
def url_problem(url, option_uri=None):
    '''Return what is wrong with *url* (strict rule, same as checks and export), or ``''``.

    *option_uri* selects the allowed schemes (source code repositories may also
    use ``git://`` etc.).  Usage: ``{{ reference.1|url_problem:reference.0 }}``.
    '''
    return _url_problem(url, url_schemes(option_uri)) or ''


@register.filter
def doi_problem(doi):
    '''Return what is wrong with *doi* (same rule as checks and export), or ``''``.'''
    return _doi_problem(doi) or ''


@register.filter
def swmath_problem(swmath_id):
    '''Return what is wrong with a swMATH work ID (same rule everywhere), or ``''``.'''
    return _swmath_problem(swmath_id) or ''


@register.simple_tag
def description_error(description, name, entity_class=''):
    '''Return the error text for a short description, or ``''`` if it is fine.

    Usage: ``{% description_error description name "SOFTWARE" as error %}``.
    '''
    problem = short_description_problem(description, name)
    if problem == 'missing':
        return ' '.join(f'MISSING {entity_class} SHORT DESCRIPTION'.split())
    if problem == 'too_long':
        return 'SHORT DESCRIPTION TOO LONG'
    if problem == 'same_as_name':
        return 'NAME AND SHORT DESCRIPTION MUST BE DIFFERENT'
    return ''


@register.inclusion_tag('MaRDMO/partials/_user_entity.html')
def user_entity(identifier, name, description, entity_class):
    '''Render one entity for relation lists.

    Entities with a portal ID are shown by their ID.  User-defined entities
    (ID ``'not found'`` or empty) are shown as ``Name (Description)`` with an
    error marker for a missing name or a problematic short description.

    Usage: ``{% user_entity item.ID item.Name item.Description "SOFTWARE" %}``.
    '''
    return {
        'identifier': identifier if identifier and identifier != 'not found' else '',
        'name': name,
        'description': description,
        'entity_class': entity_class,
        'error': description_error(description, name, entity_class),
        'description_missing': short_description_problem(description, name) == 'missing',
    }
