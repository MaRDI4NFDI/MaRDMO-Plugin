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
Wikidata hits are filtered by the classes of :data:`WIKIDATA_ROOTS` (#170).
'''
from dataclasses import dataclass
from typing import Optional, Union

from django.utils.translation import gettext_lazy as _

# The Wikidata classes of each item class (#170): a dropdown offers only the
# Wikidata items that are an instance or subclass of something at or below
# them.  They are Wikidata's, the same for every portal.  Mathematical
# operators are quantities in MathModDB, so the quantity providers offer them.
QUANTITY_ROOTS = [
    'Q309314',     # quantity
    'Q110653654',  # kind of quantity
    'Q131030',     # operator
    'Q1058681',    # differential operator
    'Q186509',     # mathematical constant
    'Q719375',     # operand
    'Q200726',     # probability distribution
    'Q11348',      # function
]
WIKIDATA_ROOTS = {
    'mathematical model': ['Q486902'],                         # mathematical model
    'formula': [
        'Q976981',     # formula
        'Q6498784',    # mathematical expression
        'Q11345',      # equation
        'Q214070',     # physical law
        'Q408891',     # scientific law
        'Q18382796',   # boundary condition
        'Q1339342',    # empirical relationship
    ],
    'quantity': QUANTITY_ROOTS,
    'kind of quantity': QUANTITY_ROOTS,
    'academic discipline': ['Q1047113'],                       # field of study
    'computational task': ['Q140136486'],                      # computational task
    'algorithm': ['Q8366'],                                    # algorithm
    'algorithmic task': ['Q3435924'],                          # computational problem
    'benchmark': ['Q816747'],                                  # benchmark
    'software': ['Q7397'],                                     # software
    'programming language': ['Q9143'],                         # programming language
    'computer hardware': ['Q3966', 'Q68'],                     # computer hardware, computer
    'CPU model': ['Q122967152', 'Q5297'],                      # CPU model, microprocessor
    'data set': ['Q1172284'],                                  # data set
    'method': [                                                # experimental and measuring methods
        'Q1924397',    # measurement technique
        'Q4751159',    # analytical chemical technique
        'Q3247516',    # lab technique
        'Q3331334',    # experimentation
    ],
    'research tool': [
        'Q110994345',  # research tool
        'Q3099911',    # scientific instrument
        'Q2041172',    # measuring instrument
        'Q1751850',    # optical instrument
    ],
    'research workflow': ['Q115682347'],                       # research workflow
}
# Item classes Wikidata has nothing for: their providers search the portal only
NO_WIKIDATA = {'process step'}
# Item classes no Wikidata class fits (research problems are phenomena,
# processes, …): their Wikidata hits are filtered by WIKIDATA_NOISE instead
NOISE_FILTERED = {'research problem'}
# What is never a research problem: an item that is an instance of one of
# these classes or of a subclass is left out.  Deliberately narrow classes
# (a broad one like "work" or "concept" would leave out real ones); measured
# against the research problems' Wikidata twins on the portal, none of which
# is left out (dev-tests/spikes/wikidata_noise.py)
WIKIDATA_NOISE = [
    # people and names
    'Q5',          # human
    'Q202444',     # given name
    'Q101352',     # family name
    'Q28640',      # profession
    'Q12737077',   # occupation
    # living things and molecules
    'Q16521',      # taxon
    'Q7187',       # gene
    'Q8054',       # protein
    # writings
    'Q47461344',   # written work
    'Q13442814',   # scholarly article
    'Q7725634',    # literary work
    'Q571',        # book
    'Q1980247',    # chapter
    'Q3331189',    # version, edition or translation
    'Q1266946',    # thesis
    'Q13433827',   # encyclopedia article
    'Q212971',     # Request for Comments
    'Q10870555',   # report
    'Q1002697',    # periodical
    'Q5633421',    # scientific journal
    'Q737498',     # academic journal
    'Q41298',      # magazine
    'Q253623',     # patent
    'Q43305660',   # United States patent
    'Q30612',      # clinical trial
    # works of art and media
    'Q11424',      # film
    'Q5398426',    # television series
    'Q21191270',   # television series episode
    'Q2431196',    # audiovisual work
    'Q482994',     # album
    'Q134556',     # single
    'Q7366',       # song
    'Q7302866',    # audio track
    'Q7889',       # video game
    'Q7397',       # software
    'Q35127',      # website
    'Q3305213',    # painting
    'Q860861',     # sculpture
    'Q2668072',    # collection
    # places and things
    'Q486972',     # human settlement
    'Q79007',      # street
    'Q41176',      # building
    'Q13226383',   # facility
    'Q4022',       # river
    'Q8502',       # mountain
    'Q3863',       # asteroid
    'Q11446',      # ship
    # organizations and events
    'Q43229',      # organization
    'Q4830453',    # business
    'Q31855',      # research institute
    'Q3918',       # university
    'Q2020153',    # academic conference
    'Q618779',     # award
    # Wikimedia pages
    'Q4167410',    # Wikimedia disambiguation page
    'Q4167836',    # Wikimedia category
    'Q13406463',   # Wikimedia list article
]


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
        by_identifier: Search by an identifier with its prefix instead of the
                    label (publications: ``doi:10.…``, #158).
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
    by_identifier: bool = False

    @property
    def with_answers(self):
        '''Whether the search includes the project's own items (and creation).'''
        return self.answers is not None or self.creation

    @property
    def classes(self):
        '''The item class names, as a list.'''
        return [self.item_class] if isinstance(self.item_class, str) else list(self.item_class)

    @property
    def search_sources(self):
        '''The sources searched: without Wikidata if it has nothing for any of the classes.'''
        if all(name in NO_WIKIDATA for name in self.classes):
            return [source for source in (self.sources or ['mardi', 'wikidata']) if source != 'wikidata']
        return self.sources

    @property
    def noise_filtered(self):
        '''Whether the Wikidata hits are filtered by :data:`WIKIDATA_NOISE` instead of roots.

        No row has a class filtered by noise together with one that has roots
        (tests/unit/test_wikidata_roots.py); such a row would be filtered by noise.
        '''
        return any(name in NOISE_FILTERED for name in self.classes)

    @property
    def wikidata_roots(self):
        '''The Wikidata classes the hits must be at or below (sorted); ``None``: no roots.

        The roots of all classes of the row; a class Wikidata has nothing for
        adds none.  None where the hits are filtered by noise.
        '''
        if self.noise_filtered:
            return None
        roots = {root for name in self.classes if name not in NO_WIKIDATA for root in WIKIDATA_ROOTS[name]}
        return sorted(roots) or None

    @property
    def wikidata_noise(self):
        '''The Wikidata classes the hits must not be instances of; ``None``: not filtered by noise.'''
        return WIKIDATA_NOISE if self.noise_filtered else None


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
    'Publication': Search('Options for Publication', ['publication', 'scholarly article'], refresh=True,
                          by_identifier=True),
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
