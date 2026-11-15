'''What prevents the export: problems of the checks and of the export's own checks (#152).

A :class:`Problem` names its section and page (a :class:`~MaRDMO.pages.PageRef`,
or none for a problem of the whole documentation); as text it reads as the
checks have always reported it: "Formula (Page F4): Missing Short Description".
'''
from dataclasses import dataclass
from typing import Optional

from .pages import PageRef

# First line of the error page of an export that is stopped
HEADER = 'Following aspects prevented the export:'


@dataclass(frozen=True)
class Problem:
    '''A problem of the documentation that prevents the export.

    Attributes:
        section: The section as the user reads it ("Formula"); for a problem
                 of the export's own checks, the check ("MaRDI Portal").
        page:    The page, or ``None``.
        message: What is wrong.
        field:   The answer that is wrong (e.g. ``"Description"``), if known.
    '''
    section: str
    page: Optional[PageRef]
    message: str
    field: Optional[str] = None

    def __str__(self):
        if self.page is None:
            return f'{self.section}: {self.message}'
        return f'{self.section} (Page {self.page.tab}): {self.message}'


def report_lines(problems):
    '''The error page's lines: :data:`HEADER` and every problem as text, or ``[]``.'''
    return [HEADER, *map(str, problems)] if problems else []


def attach(data, problems):
    '''Give every page of *data* its problems: ``page['Problems'] = {field: [message]}``.

    The preview shows them where the page shows the field (template tag
    ``marks``) and the rest at the end of the page (``remaining_marks``), so
    its red marks are the problems of the checks (#152).  Problems without
    page (the export's own checks) are only listed at the top.

    Args:
        data:     Top-level answers dict; mutated in place.
        problems: :class:`Problem` list.

    Returns:
        *data*.
    '''
    for problem in problems:
        page = problem.page
        entry = (data.get(page.section) or {}).get(page.index) if page is not None else None
        if isinstance(entry, dict):
            entry.setdefault('Problems', {}).setdefault(problem.field or '', []).append(problem.message)
    return data
