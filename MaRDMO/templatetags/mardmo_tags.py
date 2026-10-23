'''Template filters used by the MaRDMO preview templates.

Load with ``{% load mardmo_tags %}``.

Provides:

- ``has_line_break`` — ``True`` if a text contains line breaks, which the
  MaRDI Portal rejects in text values
'''

from django import template

from ..patterns import LINE_BREAK_RE

register = template.Library()


@register.filter
def has_line_break(value):
    '''Return ``True`` if *value* is a string containing line breaks.'''
    return isinstance(value, str) and bool(LINE_BREAK_RE.search(value))
