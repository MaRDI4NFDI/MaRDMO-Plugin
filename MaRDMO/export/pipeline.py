'''Everything that has to pass before the export, run by the preview and again by the export (#152).

:func:`run` runs the checks and, when they find nothing, the export's own
checks on the payload (invalid values, statements and symbols on the MaRDI
Portal, the order of the items).  The preview shows what it finds and
offers the export only when nothing is left; the export runs it once more,
since the documentation or the portal may have changed in between.
'''
import copy
from contextlib import nullcontext
from dataclasses import dataclass, field
from typing import Optional

from django.utils.translation import gettext as _, gettext_noop as N_

from .duplicates import PREVIEW_DEADLINE, PREVIEW_RETRY_WAITS
from ..core.config import get_url
from .ordering import cycle_groups, is_cyclic
from .payload import DocumentationProblem, PortalUnavailable
from .problems import Problem
from ..sources.http import check_limits

# The section of the problems the export's own checks find (they have no page)
EXPORT_SECTION = N_('Export')


@dataclass
class Gate:
    '''What :func:`run` found.

    Attributes:
        problems:    :class:`~MaRDMO.export.problems.Problem` of the checks or, when
                     these found nothing, of the export's own checks.
        hints:       What portal items of the documentation could have
                     (:attr:`~MaRDMO.export.problems.Problem.hint`, #167); they do
                     not prevent the export.
        unreachable: The MaRDI Portal did not answer a check (duplicates, TeX
                     check, the statements of existing items); the message.
        duplicates:  Items of the documentation are on the portal already
                     (the preview's list); the export's checks were not run.
        internal:    The export failed for a reason that is MaRDMO's, not the
                     documentation's (shown as a problem too).
        payload:     The payload and the write order, when nothing was found.
    '''
    problems: list = field(default_factory=list)
    hints: list = field(default_factory=list)
    unreachable: Optional[str] = None
    duplicates: bool = False
    internal: bool = False
    payload: Optional[dict] = None
    dependency: Optional[dict] = None

    @property
    def clear(self):
        '''Nothing prevents the export (hints do not).'''
        return not (self.problems or self.unreachable or self.duplicates)

    @property
    def groups(self):
        '''The problems by section and page, in their order: ``[(section, page, [messages])]``.

        *page* is the :class:`~MaRDMO.project.pages.PageRef` (``None`` for the
        export's own checks); the preview links it to the page.
        '''
        return _groups(self.problems)

    @property
    def hint_groups(self):
        '''The hints by section and page, as :attr:`groups`.'''
        return _groups(self.hints)

    @property
    def hint_items(self):
        '''The number of portal items with hints.'''
        return len({(hint.section, hint.page) for hint in self.hints})


def _groups(problems):
    '''*problems* by section and page, in their order: ``[(section, page, [messages])]``.'''
    groups = []
    for problem in problems:
        if groups and groups[-1][:2] == (problem.section, problem.page):
            groups[-1][2].append(problem.message)
        else:
            groups.append((problem.section, problem.page, [problem.message]))
    return groups


def run(project, answers, prepare_class, checks_class, preview=False, duplicates=None):
    '''Run the checks and, if they pass, the export's own checks on a copy of *answers*.

    Args:
        project:       The RDMO project.
        answers:       The answers of ``get_post_data`` (not changed).
        prepare_class: The catalog's worker (``PrepareModel`` ...).
        checks_class:  Its checks (``ModelChecks`` ...).
        preview:       Use the preview's shorter limits for the portal requests.
        duplicates:    The preview's :class:`~MaRDMO.export.duplicates.Report`; with
                       rows, the export's checks are not run.

    Returns:
        :class:`Gate`.
    '''
    checks = checks_class()
    # The statements of portal items with an invalid value are looked up (#167)
    with check_limits(PREVIEW_RETRY_WAITS, PREVIEW_DEADLINE) if preview else nullcontext():
        found = list(checks.run(project=project, data=answers, catalog=str(project.catalog)))
    gate = Gate(problems=[problem for problem in found if not problem.hint],
                hints=[problem for problem in found if problem.hint])
    if checks.unreachable:
        gate.unreachable = checks.unreachable
    if duplicates is not None:
        gate.duplicates = bool(duplicates.rows)
        if duplicates.failed and not gate.unreachable:
            gate.unreachable = _('Could not check which items are on the MaRDI Portal already.')
    if not gate.clear:
        return gate

    limits = check_limits(PREVIEW_RETRY_WAITS, PREVIEW_DEADLINE) if preview else nullcontext()
    try:
        with limits:
            payload, dependency = prepare_class().export(copy.deepcopy(answers), get_url('mardi', 'uri'))
    except DocumentationProblem as problem:
        gate.problems = [Problem(EXPORT_SECTION, None, str(message)) for message in problem.args]
        return gate
    except PortalUnavailable as problem:
        gate.unreachable = str(problem.args[0]) if problem.args else _('The MaRDI Portal did not answer.')
        return gate
    except (ValueError, KeyError) as error:
        gate.internal = True
        gate.problems = [Problem(EXPORT_SECTION, None, str(message)) for message in (error.args or [error])]
        return gate
    if is_cyclic(dependency):
        # The export breaks every cycle (payload.order_items, #164): one left is a bug
        gate.internal = True
        items = [' -> '.join(payload.get(key, {}).get('label') or key for key in group)
                 for group in cycle_groups({key: set(deps) for key, deps in dependency.items()})]
        gate.problems = [Problem(EXPORT_SECTION, None, _(
            'The new items could not be put in an order of creation ({items}); nothing was exported, '
            'please report this to the MaRDMO developers').format(items='; '.join(items) or '?'))]
        return gate
    gate.payload, gate.dependency = payload, dependency
    return gate
