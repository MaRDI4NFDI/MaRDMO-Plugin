'''The synthetic documentation of the interdisciplinary workflow catalog (see tools/synthetic/model.py).'''
from . import complete
from .writer import Doi, New, Portal, Typed, Wikidata

EGYPTIAN_OBJECTS = Portal('Q6032641', 'Logical Data Analysis for Egyptian Objects')
# The only Wikidata item below the research workflow root (Q115682347, #170); found by the start of its label
REPRODUCIBILITY_PROTOCOL = Wikidata('Q115706422', 'A reproducibility protocol and dataset on the biomedical sentence similarity v3')
EXTRACT_RULES = Portal('Q6486610', 'Extract logical Rules from encoded Subset of Objects from the Cachette de Karnak')
LENOVO = Portal('Q6487066', 'Lenovo IdeaPad Flex 5 14ARE05')
RASPBERRY_PI = Wikidata('Q65015606', 'Raspberry Pi 4 Model B')
MNIST_784 = Portal('Q6033287', 'mnist_784', search='MNIST')
MNIST = Wikidata('Q17069496', 'MNIST database')
RYZEN = Portal('Q6487068', 'AMD Ryzen 7 4700U')
XEON = Wikidata('Q66730546', 'Xeon E5-4650L')
EXHAUSTION = Portal('Q7278483', 'method of exhaustion')
# An experimental method below the method roots (#170); the Galerkin method is a numerical one
MASS_SPECTROMETRY = Wikidata('Q180809', 'mass spectrometry')
MICROSCOPE = Wikidata('Q196538', 'microscope')
SIS_MODEL = Portal('Q6675171', 'susceptible infectious susceptible model')
KINETIC_SIMULATION = Portal('Q6684556', 'simulation of complex kinetic systems')
THOMAS = Portal('Q6825618', 'Thomas algorithm')
BAREISS = Wikidata('Q4860404', 'Bareiss algorithm')
LAPACK = Portal('Q6825400', 'LAPACK')
MATPLOTLIB_INLINE = Wikidata('Q107380685', 'matplotlib-inline')
PYTHON = Portal('Q6230810', 'Python')
FORTRAN_90 = Wikidata('Q20754790', 'Fortran 90')
SORTING = Portal('Q6825656', 'Sorting items under a total order')
BIN_PACKING = Wikidata('Q814581', 'bin packing problem')
EPIDEMIOLOGY = Portal('Q6684705', 'epidemiology')
SCIENTIFIC_WORKFLOWS = Wikidata('Q120970377', 'scientific workflows')
# Publications are selected by their DOI (#158)
HEROIN_EPIDEMICS = Doi('10.1016/J.MBS.2006.10.008', 'mardi:Q2643268')      # Heroin epidemics, treatment and ODE modelling
SEG1D_WIKIDATA = Doi('10.21105/joss.02404', 'wikidata:Q106245557')       # seg1d, only on Wikidata

REPRODUCIBILITY = ('mathematical', 'result', 'runtime', 'original-platform', 'other-platform')


def synthetic(kind, letter):
    return New(f'MaRDMO synthetic {kind} {letter}', f'synthetic {kind} {letter} of the MaRDMO tests')


def describe(doc):
    # --- Data sets: every format, size and archiving answer ---------------------------------
    datasets = {letter: doc.tab('dataset', f'DS{number}', synthetic('data set', letter))
                for number, letter in enumerate('ABCDE', start=1)}
    for (letter, dataset), (binary, proprietary, size, publish, archive) in zip(datasets.items(), (
            ('binary', 'yes', ('kilobyte', '12'), ('yes', '10.5281/zenodo.4011113'), ('yes', '2030')),
            ('text', 'no', ('megabyte', '3.5'), ('no', ''), ('no', '')),
            ('binary', 'no', ('gigabyte', '7'), ('no', ''), ('no', '')),
            ('text', 'yes', ('terabyte', '1'), ('no', ''), ('yes', '2040')),
            ('text', 'no', ('items', '60000'), ('no', ''), ('no', '')))):
        dataset.answer('binary-or-text', binary)
        dataset.answer('proprietary', proprietary)
        dataset.answer('file-format', 'CSV' if binary == 'text' else 'HDF5')
        dataset.answer('size', size)
        dataset.answer('to-publish', publish if publish[1] else publish[0])
        dataset.answer('to-archive', archive if archive[1] else archive[0])
    doc.tab('dataset', 'DS6', MNIST_784)
    doc.tab('dataset', 'DS7', MNIST)

    # --- Hardware -----------------------------------------------------------------------------
    hardware_a = doc.tab('hardware', 'HW1', synthetic('hardware', 'A'))
    hardware_b = doc.tab('hardware', 'HW2', synthetic('hardware', 'B'))
    hardware_a.answer('nodes', '4')
    hardware_a.block('cpu-specification', {'cpu': RYZEN, 'number-of-cpu': '2', 'cores': '8'})
    hardware_a.block('cpu-specification', {'cpu': XEON, 'number-of-cpu': '1', 'cores': '8'})
    hardware_b.answer('nodes', '1')
    hardware_b.block('cpu-specification', {'cpu': Typed('MaRDMO synthetic CPU model'), 'number-of-cpu': '1',
                                           'cores': '4'})
    doc.tab('hardware', 'HW3', LENOVO)
    doc.tab('hardware', 'HW4', RASPBERRY_PI)

    # --- Software -------------------------------------------------------------------------------
    software_a = doc.tab('software', 'S1', synthetic('software', 'A'))
    software_b = doc.tab('software', 'S2', synthetic('software', 'B'))
    software_a.answer('reference', ('doi', '10.5281/zenodo.4011112'), ('swmath', '4383'),
                      ('described-at-url', 'https://www.mardi4nfdi.de/'),
                      ('source-code-repository-url', 'https://github.com/MaRDI4NFDI/MaRDMO-Plugin'))
    software_b.answer('reference', ('described-at-url', 'https://portal.mardi4nfdi.de/'))
    software_a.answer('programming-language-relatant', PYTHON, FORTRAN_90,
                      Typed('MaRDMO synthetic programming language'))
    doc.tab('software', 'S3', MATPLOTLIB_INLINE)
    typed_software = Typed('MaRDMO synthetic software typed')
    software_a.answer('dependency-relatant', software_b, LAPACK, MATPLOTLIB_INLINE, typed_software)
    typed = doc.find('software', typed_software)
    typed.answer('description', 'synthetic software typed into a relation')

    # --- Algorithms -----------------------------------------------------------------------------
    algorithm_a = doc.tab('algorithm', 'A1', synthetic('algorithm', 'A'))
    algorithm_b = doc.tab('algorithm', 'A2', synthetic('algorithm', 'B'))
    typed_task = Typed('MaRDMO synthetic algorithmic task typed')
    algorithm_a.answer('problem-relatant', SORTING, BIN_PACKING, typed_task)
    algorithm_b.answer('problem-relatant', typed_task)
    algorithm_a.answer('software-relatant', software_a, LAPACK, MATPLOTLIB_INLINE)
    algorithm_b.answer('software-relatant', software_b)
    doc.tab('algorithm', 'A3', BAREISS)

    # --- Process steps: computational and experimental ---------------------------------------
    step_a = doc.tab('processstep', 'PS1', synthetic('process step', 'A'))
    step_b = doc.tab('processstep', 'PS2', synthetic('process step', 'B'))
    step_a.answer('input-data-set-relatant', datasets['A'], MNIST_784, MNIST)
    step_a.answer('output-data-set-relatant', datasets['B'], Typed('MaRDMO synthetic data set typed'))
    step_a.block('computational', {'algorithm-relatant': [algorithm_a, THOMAS, BAREISS,
                                                          Typed('MaRDMO synthetic algorithm typed')],
                                   'algorithm-parameter': ['tolerance 1e-8', 'maximal 100 iterations'],
                                   'software-relatant': software_a,
                                   'software-documentation': [('doi', '10.5281/zenodo.4011112'),
                                                              ('url', 'https://www.mardi4nfdi.de/')],
                                   'hardware-relatant': hardware_a})
    step_a.block('computational', {'algorithm-relatant': [algorithm_b], 'software-relatant': LAPACK,
                                   'software-documentation': [('url', 'https://netlib.org/lapack/')],
                                   'hardware-relatant': LENOVO})
    step_a.block('computational', {'algorithm-relatant': [algorithm_a], 'software-relatant': MATPLOTLIB_INLINE,
                                   'software-documentation': [('url', 'https://numpy.org/')],
                                   'hardware-relatant': RASPBERRY_PI})
    step_a.block('computational', {'algorithm-relatant': [algorithm_b],
                                   'software-relatant': Typed('MaRDMO synthetic software typed again'),
                                   'software-documentation': [('url', 'https://www.mardi4nfdi.de/')],
                                   'hardware-relatant': Typed('MaRDMO synthetic hardware typed')})
    step_a.answer('field-relatant', EPIDEMIOLOGY, SCIENTIFIC_WORKFLOWS, Typed('MaRDMO synthetic academic discipline typed'))
    step_b.answer('input-data-set-relatant', datasets['C'])
    step_b.answer('output-data-set-relatant', datasets['D'], datasets['E'], MNIST)
    step_b.block('experimental', {'method-relatant': [EXHAUSTION, MASS_SPECTROMETRY,
                                                      Typed('MaRDMO synthetic method')],
                                  'method-parameter': ['magnification 400x'],
                                  'method-documentation': [('doi', '10.5281/zenodo.4011114'),
                                                           ('url', 'https://www.mardi4nfdi.de/')],
                                  'instrument-relatant': MICROSCOPE})
    step_b.block('experimental', {'method-relatant': [MASS_SPECTROMETRY],
                                  'method-documentation': [('url', 'https://www.mardi4nfdi.de/')],
                                  'instrument-relatant': Typed('MaRDMO synthetic instrument')})
    step_b.answer('field-relatant', EPIDEMIOLOGY)
    doc.tab('processstep', 'PS3', EXTRACT_RULES)
    # no process step from Wikidata: it is not searched there (NO_WIKIDATA, #170)

    # --- Workflows: every answer of the reproducibility questions ----------------------------
    workflow_a = doc.tab('workflow', 'WF1', synthetic('workflow', 'A'))
    workflow_b = doc.tab('workflow', 'WF2', synthetic('workflow', 'B'))
    workflow_c = doc.tab('workflow', 'WF3', synthetic('workflow', 'C'))
    for workflow, answer in ((workflow_a, ('yes', 'Reproduced by a second run of the synthetic tests.')),
                             (workflow_b, 'no'), (workflow_c, 'not_relevant')):
        workflow.answer('objective', f'Test every question of the workflow catalog ({workflow.label}).')
        for question in REPRODUCIBILITY:
            workflow.answer(f'reproducibility/{question}', answer)
    workflow_a.answer('long-description', 'A synthetic workflow made up for the tests of MaRDMO.',
                      'It uses every question of its page.')
    workflow_a.answer('transferability', 'other data sets of handwritten digits', 'other sorting tasks')
    workflow_a.block('workflow-to-model', {'model': SIS_MODEL, 'task': [KINETIC_SIMULATION]})
    typed_step = Typed('MaRDMO synthetic process step typed')
    workflow_a.answer('step-relatant', step_a, step_b, EXTRACT_RULES, typed_step)
    workflow_b.answer('step-relatant', step_b)
    workflow_c.answer('step-relatant', step_a)
    workflow_a.block('workflow-to-workflow', {'workflow-relation': 'contains', 'workflow-relatant': [workflow_b]})
    workflow_b.block('workflow-to-workflow', {'workflow-relation': 'contained-in',
                                              'workflow-relatant': [workflow_a, EGYPTIAN_OBJECTS]})
    doc.tab('workflow', 'WF4', EGYPTIAN_OBJECTS)
    doc.tab('workflow', 'WF5', REPRODUCIBILITY_PROTOCOL)

    # --- Publications -------------------------------------------------------------------------
    publication = doc.tab('publication', 'P1', HEROIN_EPIDEMICS)
    publication.block('publication-to-hardware-or-software', {'documents-uses-relation': 'documents',
                                                              'hardware-or-software-relatant': [software_a, LAPACK]})
    publication.block('publication-to-hardware-or-software', {'documents-uses-relation': 'uses',
                                                              'hardware-or-software-relatant': [hardware_a, LENOVO]})
    for relation, relatant in (('analyzes', algorithm_a), ('applies', THOMAS), ('invents', algorithm_b),
                               ('studies', algorithm_a), ('surveys', THOMAS)):
        publication.block('publication-to-algorithm', {'algorithm-relation': relation, 'algorithm-relatant': [relatant]})
    for relation, relatant in (('analyzes', workflow_a), ('applies', step_a), ('documents', datasets['A']),
                               ('invents', workflow_b), ('studies', EGYPTIAN_OBJECTS), ('surveys', step_b),
                               ('uses', MNIST_784)):
        publication.block('publication-to-remaining-workflow-entities', {
            'remaining-workflow-entity-relation': relation, 'remaining-workflow-entity-relatant': [relatant]})
    publication = doc.tab('publication', 'P2', SEG1D_WIKIDATA)
    publication.block('publication-to-algorithm', {'algorithm-relation': 'applies', 'algorithm-relatant': [algorithm_b]})
    publication = doc.tab('publication', 'P3', Doi('10.21105/joss.10797'))         # GeoRacoon, new
    publication.block('publication-to-remaining-workflow-entities', {
        'remaining-workflow-entity-relation': 'documents', 'remaining-workflow-entity-relatant': [datasets['B']]})

    # --- What the pages MaRDMO filled or added still need ---------------------------------
    complete.descriptions(doc, 'workflow', 'processstep', 'algorithm', 'software', 'hardware', 'dataset')
    complete.references(doc, 'software')
    for page in doc.tabs('dataset'):
        complete.missing(page, {'binary-or-text': 'text', 'proprietary': 'no', 'file-format': 'CSV',
                                'size': ('items', '100'), 'to-publish': 'no', 'to-archive': 'no'})
    for page in doc.tabs('hardware'):
        complete.missing(page, {'nodes': '1'})
        blocks = page.blocks('cpu-specification')
        if not blocks and complete.created(page):
            page.block('cpu-specification', {'cpu': RYZEN, 'number-of-cpu': '1', 'cores': '8'})
        for block in blocks:
            complete.missing(page, {'cpu': RYZEN, 'number-of-cpu': '1', 'cores': '8'}, within=(block,))
    for page in doc.tabs('algorithm'):
        complete.missing(page, {'problem-relatant': SORTING, 'software-relatant': LAPACK})
    for page in doc.tabs('processstep'):
        complete.missing(page, {'input-data-set-relatant': datasets['C'], 'output-data-set-relatant': datasets['D'],
                                'field-relatant': EPIDEMIOLOGY})
        for block in page.blocks('computational'):
            complete.missing(page, {'software-relatant': LAPACK, 'hardware-relatant': hardware_b,
                                    'software-documentation': [('url', 'https://netlib.org/lapack/')]},
                             within=(block,))
    for page in doc.tabs('workflow'):
        complete.missing(page, {'objective': f'Objective of {page.label} (completed for the MaRDMO tests)',
                                'step-relatant': step_b,
                                **{f'reproducibility/{question}': 'not_relevant' for question in REPRODUCIBILITY}})
