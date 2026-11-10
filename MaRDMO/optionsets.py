'''The searches of MaRDMO's option set providers, one row per provider key.

The questionnaire names a provider by its key (``provider_key`` of an option
set); RDMO creates the provider as ``Class(key, label, class_name)`` from the
setting ``OPTIONSET_PROVIDERS`` and asks it for options with the search text
only, not with the question.  So one provider class,
:class:`MaRDMO.providers.MaRDMOProvider`, looks up its search here by key.

The RDMO settings import :data:`OPTIONSET_PROVIDERS` while Django starts, so
this module must not import RDMO or MaRDMO models::

    from MaRDMO.optionsets import OPTIONSET_PROVIDERS as MARDMO_OPTIONSET_PROVIDERS
    OPTIONSET_PROVIDERS = MARDMO_OPTIONSET_PROVIDERS

Item classes are names of ``data/items.json`` (a list: several classes);
they are looked up when searching, so the provider's Wikibase is used.
'''
from dataclasses import dataclass
from typing import Optional, Union

from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class Search:
    '''What a provider searches for.

    Attributes:
        label:      Label of the option set provider (RDMO's management pages).
        item_class: Item name(s) of the class-restricted search on the MaRDI Portal.
        answers:    Questionnaire sections whose items of the user's own are
                    offered too (``None``: none).
        answer_class: MathModDB class (``Quantity`` or ``QuantityKind``) the
                    user's own quantities must have; quantities without a
                    class yet are offered too (``None``: all).
        creation:   Offer to create a new item from the search text.
        sources:    Sources to search (``None``: MaRDI Portal and Wikidata).
        not_found:  Offer "new item" (searches without answers and creation).
        refresh:    RDMO reloads the page after a selection (handlers fill it).
        min_search: Characters needed before searching: 1 where one-letter names
                    exist (programming languages and software: C, R), else 3 (a
                    single letter matches hundreds of items and slows the search).
    '''
    label: str
    item_class: Union[str, list]
    answers: Optional[list] = None
    answer_class: Optional[str] = None
    creation: bool = False
    sources: Optional[list] = None
    not_found: bool = True
    refresh: bool = False
    min_search: int = 3

    @property
    def with_answers(self):
        '''Whether the search includes the project's own items (and creation).'''
        return self.answers is not None or self.creation


PROVIDERS = {
    # general
    'Software': Search('Options for Software', 'software', refresh=True, min_search=1),
    'RelatedSoftwareWithCreation': Search('Options for related Software with Creation', 'software', answers=['software'], creation=True, refresh=True, min_search=1),
    # algorithm
    'Algorithm': Search('Options for Algorithms', 'algorithm', refresh=True),
    'RelatedAlgorithmWithoutCreation': Search('Options for related Algorithms without Creation', 'algorithm', answers=['algorithm'], sources=['mardi']),
    'AlgorithmicProblem': Search('Options for Algorithmic Problems', 'algorithmic task', refresh=True),
    'RelatedAlgorithmicProblemWithCreation': Search('Options for related Algorithmic Problems with Creation', 'algorithmic task', answers=['problem'], creation=True),
    'RelatedAlgorithmicProblemWithoutCreation': Search('Options for related Algorithmic Problems without Creation', 'algorithmic task', answers=['problem'], sources=['mardi']),
    'Benchmark': Search('Options for Benchmarks', 'benchmark', refresh=True),
    'RelatedBenchmarkWithCreation': Search('Options for related Benchmarks with Creation', 'benchmark', answers=['benchmark'], creation=True),
    'RelatedBenchmarkOrSoftwareWithoutCreation': Search('Options for related Benchmarks or Software without Creation', ['benchmark', 'software'], answers=['benchmark', 'software'], sources=['mardi'], min_search=1),
    # model
    'ResearchField': Search('Options for Research Fields', ['academic discipline'], refresh=True),
    'RelatedResearchFieldWithCreation': Search('Options for related Research Fields with Creation', 'academic discipline', answers=['field'], creation=True),
    'RelatedResearchFieldWithoutCreation': Search('Options for related Research Fields without Creation', 'academic discipline', answers=['field'], sources=['mardi']),
    'ResearchProblem': Search('Options for Research Problems', 'research problem', refresh=True),
    'RelatedResearchProblemWithCreation': Search('Options for related Research Problems with Creation', 'research problem', answers=['problem'], creation=True),
    'RelatedResearchProblemWithoutCreation': Search('Options for related Research Problems without Creation', 'research problem', answers=['problem'], sources=['mardi']),
    'MathematicalModel': Search('Options for Mathematical Model', 'mathematical model', refresh=True),
    'RelatedMathematicalModelWithoutCreation': Search('Options for related Mathematical Model without Creation', 'mathematical model', answers=['model'], sources=['mardi']),
    'QuantityOrQuantityKind': Search('Options for Quantities and Quantity Kinds', ['quantity', 'kind of quantity'], refresh=True),
    'RelatedQuantityWithoutCreation': Search('Options for related Quantities without Creation', 'quantity', answers=['quantity'], answer_class='Quantity', sources=['mardi']),
    'RelatedQuantityKindWithoutCreation': Search('Options for related Quantity Kinds without Creation', 'kind of quantity', answers=['quantity'], answer_class='QuantityKind', sources=['mardi']),
    'RelatedQuantityOrQuantityKindWithCreation': Search('Options for related Quantities or Quantity Kinds with Creation', ['quantity', 'kind of quantity'], answers=['quantity'], creation=True, refresh=True),
    'MathematicalFormulation': Search('Options for Mathematical Formulation', 'formula', refresh=True),
    'RelatedMathematicalFormulationWithCreation': Search('Options for related Mathematical Formulations with Creation', 'formula', answers=['formulation'], creation=True, refresh=True),
    'RelatedMathematicalFormulationWithoutCreation': Search('Options for related Mathematical Formulations without Creation', 'formula', answers=['formulation'], sources=['mardi']),
    'Task': Search('Options for Task', 'computational task', refresh=True),
    'RelatedTaskWithCreation': Search('Options for related Tasks with Creation', 'computational task', answers=['task'], creation=True),
    'RelatedTaskWithoutCreation': Search('Options for related Tasks without Creation', 'computational task', answers=['task'], sources=['mardi']),
    'RelatedModelEntityWithoutCreation': Search('Options for related Model Entities without Creation', ['academic discipline', 'research problem', 'mathematical model', 'quantity', 'kind of quantity', 'formula', 'computational task'], answers=['field', 'problem', 'model', 'quantity', 'formulation', 'task'], sources=['mardi']),
    # publication
    'Publication': Search('Options for Publication', ['publication', 'scholarly article'], refresh=True),
    # search
    'ResearchFieldMaRDIOnly': Search('Options for Research Fields (MaRDI Only)', ['academic discipline'], sources=['mardi'], not_found=False),
    'MathematicalModelMaRDIOnly': Search('Options for Mathematical Models (MaRDI Only)', ['mathematical model'], sources=['mardi'], not_found=False),
    'AlgorithmMaRDIOnly': Search('Options for Algorithms (MaRDI Only)', ['algorithm'], sources=['mardi'], not_found=False),
    'SoftwareMaRDIOnly': Search('Options for Software (MaRDI Only)', ['software'], sources=['mardi'], not_found=False, min_search=1),
    'HardwareMaRDIOnly': Search('Options for Hardware (MaRDI Only)', ['computer hardware'], sources=['mardi'], not_found=False),
    'MethodMaRDIOnly': Search('Options for Methods (MaRDI Only)', ['method'], sources=['mardi'], not_found=False),
    'InstrumentMaRDIOnly': Search('Options for Instruments (MaRDI Only)', ['research tool'], sources=['mardi'], not_found=False),
    'DataSetMaRDIOnly': Search('Options for Data Sets (MaRDI Only)', ['data set'], sources=['mardi'], not_found=False),
    'ResearchProblemMaRDIOnly': Search('Options for Research Problems (MaRDI Only)', ['research problem'], sources=['mardi'], not_found=False),
    'ComputationalTaskMaRDIOnly': Search('Options for Computational Tasks (MaRDI Only)', ['computational task'], sources=['mardi'], not_found=False),
    'FormulaMaRDIOnly': Search('Options for Formulas (MaRDI Only)', ['formula'], sources=['mardi'], not_found=False),
    'AlgorithmicProblemMaRDIOnly': Search('Options for Algorithmic Problems (MaRDI Only)', ['algorithmic task'], sources=['mardi'], not_found=False),
    'QuantityOrQuantityKindMaRDIOnly': Search('Options for Quantities and Quantity Kinds (MaRDI Only)', ['quantity', 'kind of quantity'], sources=['mardi'], not_found=False),
    # workflow
    'MathematicalModelWorkflow': Search('Options for Mathematical Model (Workflow)', 'mathematical model', sources=['mardi'], not_found=False, refresh=True),
    'RelatedProgrammingLanguageWithCreation': Search('Options for related Programming Languages with Creation', ['programming language'], answers=None, creation=True, min_search=1),
    'RelatedCPUModelWithCreation': Search('Options for related CPU Models with Creation', ['CPU model'], answers=None, creation=True, refresh=True),
    'RelatedMethodWithCreation': Search('Options for related Methods with Creation', ['method'], answers=None, creation=True),
    'RelatedAlgorithmWithCreation': Search('Options for related Algorithms with Creation', ['algorithm'], answers=['algorithm'], creation=True),
    'RelatedStepWithCreation': Search('Options for related Process Steps with Creation', ['process step'], answers=['processstep'], creation=True),
    'TaskWorkflow': Search('Options for Task (Workflow)', 'computational task', sources=['mardi'], not_found=False),
    'Hardware': Search('Options for Hardware', 'computer hardware', refresh=True),
    'RelatedHardwareWithCreation': Search('Options for related Hardware with Creation', ['computer hardware'], answers=['hardware'], creation=True),
    'Workflow': Search('Options for Workflows', 'research workflow', refresh=True),
    'RelatedWorkflowWithoutCreation': Search('Options for related Workflows without Creation', 'research workflow', answers=['workflow'], sources=['mardi']),
    'DataSet': Search('Options for Data Sets', 'data set', refresh=True),
    'RelatedInstrumentWithCreation': Search('Options for related Instruments with Creation', 'research tool', answers=None, creation=True),
    'RelatedDataSetWithCreation': Search('Options for related Data Sets with Creation', 'data set', answers=['dataset'], creation=True),
    'ProcessStep': Search('Options for Process Step', 'process step', refresh=True),
    'RelatedHardwareOrSoftwareWithoutCreation': Search('Options for related Hardware or Software without Creation', ['computer hardware', 'software'], answers=['hardware', 'software'], sources=['mardi'], min_search=1),
    'RelatedWorkflowEntityWithoutCreation': Search('Options for related Workflow Entities without Creation', ['research workflow', 'process step', 'data set'], answers=['workflow', 'processstep', 'dataset'], sources=['mardi']),
}

#: The setting ``OPTIONSET_PROVIDERS`` for every MaRDMO option set.
OPTIONSET_PROVIDERS = [
    (key, _(search.label), 'MaRDMO.providers.MaRDMOProvider') for key, search in PROVIDERS.items()
]
