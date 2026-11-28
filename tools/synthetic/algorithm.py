'''The synthetic documentation of the algorithm catalog (see tools/synthetic/model.py for the idea).'''
from . import complete
from .writer import Doi, New, Portal, Typed, Wikidata

QUICKSORT = Portal('Q6825489', 'Quicksort')
THOMAS = Portal('Q6825618', 'Thomas algorithm')
CONJUGATE_GRADIENT = Portal('Q6825529', 'Conjugate Gradient (CG) for sparse symmetric positive definite systems')
BAREISS = Wikidata('Q4860404', 'Bareiss algorithm')
SORTING = Portal('Q6825656', 'Sorting items under a total order')
LINEAR_SYSTEM = Portal('Q6825573', 'Linear system of equations')
BIN_PACKING = Wikidata('Q814581', 'bin packing problem')
LAPACK = Portal('Q6825400', 'LAPACK')
SCIPY = Portal('Q6825551', 'SciPy')
MATPLOTLIB_INLINE = Wikidata('Q107380685', 'matplotlib-inline')
HPL = Portal('Q6826014', 'HPL')
MIPLIB = Portal('Q6826034', 'MIPLIB 2017')
# A Wikidata benchmark below the benchmark root (Q816747, #170); MNIST is a data set there
WHETSTONE = Wikidata('Q608140', 'Whetstone')
PYTHON = Portal('Q6230810', 'Python')
FORTRAN = Portal('Q56773', 'Fortran')
FORTRAN_90 = Wikidata('Q20754790', 'Fortran 90')
# Publications are selected by their DOI (#158)
HEROIN_EPIDEMICS = Doi('10.1016/J.MBS.2006.10.008', 'mardi:Q2643268')      # Heroin epidemics, treatment and ODE modelling
SEG1D_WIKIDATA = Doi('10.21105/joss.02404', 'wikidata:Q106245557')       # seg1d, only on Wikidata


def synthetic(kind, letter):
    return New(f'MaRDMO synthetic {kind} {letter}', f'synthetic {kind} {letter} of the MaRDMO tests')


def describe(doc):
    # --- Benchmarks --------------------------------------------------------------------------
    benchmark_a = doc.tab('benchmark', 'B1', synthetic('benchmark', 'A'))
    benchmark_b = doc.tab('benchmark', 'B2', synthetic('benchmark', 'B'))
    benchmark_a.answer('reference', ('doi', '10.5281/zenodo.4011111'), ('morwiki', 'Steel_Profile'),
                       ('described-at-url', 'https://www.mardi4nfdi.de/'),
                       ('source-code-repository-url', 'https://github.com/MaRDI4NFDI/MaRDMO-Plugin'))
    benchmark_b.answer('reference', ('described-at-url', 'https://portal.mardi4nfdi.de/'))
    doc.tab('benchmark', 'B3', HPL)
    doc.tab('benchmark', 'B4', WHETSTONE)

    # --- Software ------------------------------------------------------------------------------
    software_a = doc.tab('software', 'S1', synthetic('software', 'A'))
    software_b = doc.tab('software', 'S2', synthetic('software', 'B'))
    software_a.answer('reference', ('doi', '10.5281/zenodo.4011112'), ('swmath', '4383'),
                      ('described-at-url', 'https://www.mardi4nfdi.de/'),
                      ('source-code-repository-url', 'https://github.com/MaRDI4NFDI/MaRDMO-Plugin'))
    software_b.answer('reference', ('source-code-repository-url', 'https://github.com/MaRDI4NFDI/MaRDMO-Questionnaire'))
    software_a.answer('programming-language-relatant', PYTHON, FORTRAN_90,
                      Typed('MaRDMO synthetic programming language'))
    software_b.answer('programming-language-relatant', FORTRAN)
    # The portal software has no reference yet: the user adds one
    doc.tab('software', 'S3', SCIPY).answer('reference', ('described-at-url', 'https://scipy.org/'))
    doc.tab('software', 'S4', MATPLOTLIB_INLINE)
    typed_software = Typed('MaRDMO synthetic software typed')
    software_a.answer('dependency-relatant', software_b, LAPACK, MATPLOTLIB_INLINE, typed_software)
    typed = doc.find('software', typed_software)
    typed.answer('description', 'synthetic software typed into a relation')
    typed.answer('reference', ('described-at-url', 'https://www.mardi4nfdi.de/'))
    typed_benchmark = Typed('MaRDMO synthetic benchmark typed')
    software_a.answer('benchmark-relatant', benchmark_a, HPL, WHETSTONE, typed_benchmark)
    typed = doc.find('benchmark', typed_benchmark)
    typed.answer('description', 'synthetic benchmark typed into a relation')
    typed.answer('reference', ('morwiki', 'Flow_Meter'))
    software_b.answer('benchmark-relatant', benchmark_b, MIPLIB)

    # --- Algorithmic tasks -------------------------------------------------------------------
    task_a = doc.tab('problem', 'AT1', synthetic('algorithmic task', 'A'))
    task_b = doc.tab('problem', 'AT2', synthetic('algorithmic task', 'B'))
    doc.tab('problem', 'AT3', SORTING)
    doc.tab('problem', 'AT4', BIN_PACKING)
    task_a.answer('benchmark-relatant', benchmark_a, HPL, WHETSTONE, Typed('MaRDMO synthetic benchmark typed again'))
    typed = doc.tabs('benchmark')[-1]
    typed.answer('description', 'synthetic benchmark typed into a relation of an algorithmic task')
    typed.answer('reference', ('described-at-url', 'https://www.mardi4nfdi.de/'))
    task_b.answer('benchmark-relatant', benchmark_b)
    task_a.block('problem-to-problem', {'problem-relation': 'specialized-by', 'problem-relatant': [task_b]})
    task_b.block('problem-to-problem', {'problem-relation': 'specializes', 'problem-relatant': [task_a, SORTING]})

    # --- Algorithms ----------------------------------------------------------------------------
    algorithm_a = doc.tab('algorithm', 'A1', synthetic('algorithm', 'A'))
    algorithm_b = doc.tab('algorithm', 'A2', synthetic('algorithm', 'B'))
    # The portal and Wikidata algorithms lack software or tasks: the user adds them
    portal = doc.tab('algorithm', 'A3', CONJUGATE_GRADIENT)
    wikidata = doc.tab('algorithm', 'A4', BAREISS)
    for page in (portal, wikidata):
        for key, item in (('problem-relatant', task_b), ('software-relatant', software_b)):
            if not page.answered(key):
                page.answer(key, item)
    typed_task = Typed('MaRDMO synthetic algorithmic task typed')
    algorithm_a.answer('problem-relatant', task_a, LINEAR_SYSTEM, BIN_PACKING, typed_task)
    typed = doc.find('problem', typed_task)
    typed.answer('description', 'synthetic algorithmic task typed into a relation')
    algorithm_b.answer('problem-relatant', task_b)
    typed_software = Typed('MaRDMO synthetic software typed again')
    algorithm_a.answer('software-relatant', software_a, SCIPY, MATPLOTLIB_INLINE, typed_software)
    typed = doc.find('software', typed_software)
    typed.answer('description', 'synthetic software typed into a relation of an algorithm')
    typed.answer('reference', ('swmath', '4384'))
    algorithm_b.answer('software-relatant', software_b)
    # A has component B and is component of B: a cycle of new algorithms (#164)
    for relation, relatant in (('has-component', algorithm_b), ('component-of', algorithm_b),
                               ('has-subclass', QUICKSORT), ('subclass-of', algorithm_b),
                               ('related-to', algorithm_b)):
        algorithm_a.block('algorithm-to-algorithm', {'algorithm-relation': relation,
                                                     'algorithm-relatant': [relatant]})

    # --- Publications ------------------------------------------------------------------------
    publication = doc.tab('publication', 'P1', HEROIN_EPIDEMICS)
    for relation, relatant in (('analyzes', algorithm_a), ('applies', THOMAS), ('invents', algorithm_b),
                               ('studies', algorithm_a), ('surveys', QUICKSORT)):
        publication.block('publication-to-algorithm', {'algorithm-relation': relation,
                                                       'algorithm-relatant': [relatant]})
    publication.block('publication-to-benchmark-or-software', {'documents-uses-relation': 'documents',
                                                               'benchmark-or-software-relatant': [software_a, LAPACK]})
    publication.block('publication-to-benchmark-or-software', {'documents-uses-relation': 'uses',
                                                               'benchmark-or-software-relatant': [benchmark_a, HPL]})
    publication = doc.tab('publication', 'P2', SEG1D_WIKIDATA)
    publication.block('publication-to-algorithm', {'algorithm-relation': 'applies', 'algorithm-relatant': [algorithm_b]})
    # Typed by their DOI: one of arXiv, which the MaRDI Portal has already (the dropdown
    # offers the portal item); one nowhere yet (new: two authors with ORCID iD, its journal)
    publication = doc.tab('publication', 'P3', Doi('10.48550/arXiv.2611.17256', 'mardi:Q7433372'))
    publication.block('publication-to-algorithm', {'algorithm-relation': 'invents', 'algorithm-relatant': [algorithm_a]})
    publication = doc.tab('publication', 'P4', Doi('10.21105/joss.10961'))
    publication.block('publication-to-benchmark-or-software', {'documents-uses-relation': 'documents',
                                                               'benchmark-or-software-relatant': [software_b]})
    complete.descriptions(doc, 'algorithm', 'problem', 'software', 'benchmark')
    complete.references(doc, 'software', 'benchmark')
