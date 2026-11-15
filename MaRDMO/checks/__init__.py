'''Validation checks for MaRDMO questionnaire data.'''

from .workflow import WorkflowMixin
from .algorithm import AlgorithmMixin
from .model import ModelMixin
from .base import ChecksBase


class Checks(WorkflowMixin, AlgorithmMixin, ModelMixin, ChecksBase):
    '''Validate user answers before transferring documentation to the MaRDI Portal.

    Runs catalog-specific consistency checks (mandatory fields, relations
    to own items without page, projects made before 0.8.0, conflicting data
    properties) and returns what they find as
    :class:`~MaRDMO.problems.Problem` (see :mod:`MaRDMO.pipeline`).
    '''
