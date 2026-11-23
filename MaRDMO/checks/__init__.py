'''Validation checks for MaRDMO questionnaire data.

The shared checks are :class:`~MaRDMO.checks.base.ChecksBase`; each catalog
has its own subclass (``model/checks.py``, ``algorithm/checks.py``,
``workflow/checks.py``), which its :class:`~MaRDMO.core.catalogs.Catalog` names.
They return what they find as :class:`~MaRDMO.problems.Problem` (see
:mod:`MaRDMO.pipeline`).
'''
