'''The synthetic documentation of the model basics catalog (see tools/synthetic/model.py).

The basics catalog has no quantities, academic disciplines and notation;
a formula is described in words (its reference).  The same kinds of items
as the full catalog: new ones, of the MaRDI Portal, of Wikidata, typed
into a relation.
'''
from .model import (
    EPIDEMIC, HEROIN_EPIDEMICS, HEROIN_EPIDEMICS_WIKIDATA, KINETIC_SIMULATION, BLACK_SCHOLES, PARAMETER_ESTIMATION,
    SIS_INFECTIOUS, SIS_MODEL, SPREADING, STATIONARY_NAVIER_STOKES, WAVE_EQUATION, synthetic,
)
from .writer import Doi, Typed

FORMULA_RELATIONS = ('assumes', 'contains', 'contains-analytical-solution', 'contains-boundary-condition',
                     'contains-computational-domain', 'contains-constraint-condition',
                     'contains-coupling-condition', 'contains-definition', 'contains-initial-condition',
                     'contains-final-condition', 'contains-governing-equation', 'contains-strong-formulation',
                     'contains-weak-formulation')


def describe(doc):
    # --- Research problems ---------------------------------------------------------------
    problem_a = doc.tab('problem', 'RP1', synthetic('research problem', 'A'))
    problem_b = doc.tab('problem', 'RP2', synthetic('research problem', 'B'))
    doc.tab('problem', 'RP3', SPREADING)
    doc.tab('problem', 'RP4', EPIDEMIC)
    problem_a.block('problem-to-problem', {'problem-relation': 'specialized-by', 'problem-relatant': [problem_b]})
    problem_b.block('problem-to-problem', {'problem-relation': 'specializes', 'problem-relatant': [problem_a]})
    problem_b.block('problem-to-problem', {'problem-relation': 'similar-to', 'problem-relatant': [SPREADING]})

    # --- Formulas, described in words ------------------------------------------------------
    formulas = {}
    for letter, tab, properties in (
        ('A', 'F1', ('is-deterministic', 'is-dimensionless', 'is-dynamic', 'is-linear', 'is-space-continuous',
                     'is-time-continuous', 'is-ordinary-differential-equation')),
        ('B', 'F2', ('is-stochastic', 'is-dimensional', 'is-static', 'is-not-linear', 'is-space-discrete',
                     'is-time-discrete', 'is-partial-differential-equation')),
        ('C', 'F3', ('is-stochastic-differential-equation',)),
        ('D', 'F4', ('is-integro-differential-equation',)),
    ):
        formula = doc.tab('formulation', tab, synthetic('formula', letter))
        formula.answer('properties', *properties)
        formula.answer('reference', f'The rate of change of a is proportional to a, in variant {letter}.')
        formulas[letter] = formula
    doc.tab('formulation', 'F5', SIS_INFECTIOUS)
    wave = doc.tab('formulation', 'F6', WAVE_EQUATION)
    if not wave.answered('reference'):
        wave.answer('reference', 'The second time derivative equals the squared speed times the Laplacian.')
    # Formulas in formulas (assumptions, boundary conditions, ...): one block with the relations below (#213)
    for relation, relatants in (('assumes', [formulas['B']]), ('contains', [formulas['C'], SIS_INFECTIOUS]),
                                ('contains-boundary-condition', [formulas['D']]),
                                ('contains-constraint-condition', [SIS_INFECTIOUS]),
                                ('contains-coupling-condition', [formulas['D']]),
                                ('contains-initial-condition', [formulas['B']]),
                                ('contains-final-condition', [formulas['C']])):
        formulas['A'].block('formulation-to-formulation', {'formulation-relation': relation,
                                                          'formulation-relatant': relatants})
    # Relations stored on the other item ("approximates" is "approximated by" there) close cycles
    # of new items (#164): A approximated by B, B specialized by C, A approximates C (A, B, C);
    # A approximated by B, A linearizes B (A, B).  The others go to the portal
    for relation, relatant in (('approximated-by', formulas['B']), ('approximates', formulas['C']),
                               ('discretized-by', formulas['B']), ('discretizes', SIS_INFECTIOUS),
                               ('is-weak-formulation-of', SIS_INFECTIOUS), ('has-weak-formulation', formulas['B']),
                               ('linearized-by', formulas['C']), ('linearizes', formulas['B']),
                               ('nondimensionalized-by', formulas['B']), ('nondimensionalizes', SIS_INFECTIOUS),
                               ('similar-to', STATIONARY_NAVIER_STOKES)):
        formulas['A'].block('formulation-to-formulation', {'formulation-relation': relation,
                                                                 'formulation-relatant': [relatant]})
    typed_formula = Typed('MaRDMO synthetic formula typed')
    formulas['B'].block('formulation-to-formulation', {
        'formulation-relation': 'specialized-by', 'formulation-relatant': [formulas['C']],
        'formulation-assumption': [formulas['D'], WAVE_EQUATION, SIS_INFECTIOUS, typed_formula]})
    typed = doc.find('formulation', typed_formula)
    typed.answer('description', 'synthetic formula typed into a relation')
    typed.answer('reference', 'a equals c')
    formulas['C'].block('formulation-to-formulation', {
        'formulation-relation': 'specializes', 'formulation-relatant': [SIS_INFECTIOUS],
        'formulation-assumption': [formulas['D']]})

    # --- Computational tasks ---------------------------------------------------------------
    task_a = doc.tab('task', 'CT1', synthetic('computational task', 'A'))
    task_b = doc.tab('task', 'CT2', synthetic('computational task', 'B'))
    task_a.answer('properties', 'is-linear', 'is-space-continuous', 'is-time-continuous')
    task_b.answer('properties', 'is-not-linear', 'is-space-discrete', 'is-time-discrete')
    for tab, item in (('CT3', KINETIC_SIMULATION), ('CT4', PARAMETER_ESTIMATION)):
        task = doc.tab('task', tab, item)
        task.block('task-to-formulation', {'formulation-relation': 'contains-governing-equation',
                                           'formulation-relatant': [formulas['B']]})
    relatants = [formulas['A'], formulas['B'], formulas['C'], formulas['D'], SIS_INFECTIOUS, WAVE_EQUATION]
    for number, relation in enumerate(FORMULA_RELATIONS):
        task = task_a if number % 2 == 0 else task_b
        task.block('task-to-formulation', {'formulation-relation': relation,
                                           'formulation-relatant': [relatants[number % len(relatants)]]})
    # A approximates B and is approximated by B: a cycle of new tasks (#164)
    for relation, relatant in (('approximates', task_b), ('approximated-by', task_b), ('contains', task_b),
                               ('contained-in', KINETIC_SIMULATION), ('discretizes', KINETIC_SIMULATION),
                               ('discretized-by', task_b), ('linearizes', KINETIC_SIMULATION), ('linearized-by', task_b),
                               ('similar-to', KINETIC_SIMULATION)):
        task_a.block('task-to-task', {'task-relation': relation, 'task-relatant': [relatant]})
    task_a.block('task-to-task', {'task-relation': 'specializes', 'task-relatant': [KINETIC_SIMULATION],
                                  'task-assumption': [formulas['A'], SIS_INFECTIOUS]})
    task_b.block('task-to-task', {'task-relation': 'specialized-by', 'task-relatant': [KINETIC_SIMULATION],
                                  'task-assumption': [formulas['B'], WAVE_EQUATION]})

    # --- Mathematical models -----------------------------------------------------------------
    model_a = doc.tab('model', 'MM1', synthetic('mathematical model', 'A'))
    model_b = doc.tab('model', 'MM2', synthetic('mathematical model', 'B'))
    model_c = doc.tab('model', 'MM3', synthetic('mathematical model', 'C'))
    doc.tab('model', 'MM4', SIS_MODEL)
    black_scholes = doc.tab('model', 'MM5', BLACK_SCHOLES)
    black_scholes.answer('problem-relatant', problem_b)
    black_scholes.block('model-to-formulation-basics', {'formulation-relation': 'contains-governing-equation',
                                                         'formulation-relatant': [formulas['A']]})
    model_a.answer('properties', 'is-deterministic', 'is-dimensionless', 'is-dynamic', 'is-linear',
                   'is-space-continuous', 'is-time-continuous')
    model_b.answer('properties', 'is-stochastic', 'is-dimensional', 'is-static', 'is-not-linear',
                   'is-space-discrete', 'is-time-discrete')
    typed_problem = Typed('MaRDMO synthetic research problem typed')
    model_a.answer('problem-relatant', problem_a, typed_problem)
    doc.find('problem', typed_problem).answer('description', 'synthetic research problem typed into a relation')
    model_b.answer('problem-relatant', SPREADING)
    model_c.answer('problem-relatant', EPIDEMIC, problem_b)
    typed_task = Typed('MaRDMO synthetic computational task typed')
    model_a.answer('task-relatant', task_a, typed_task)
    typed = doc.find('task', typed_task)
    typed.answer('description', 'synthetic computational task typed into a relation')
    typed.block('task-to-formulation', {'formulation-relation': 'contains', 'formulation-relatant': [formulas['A']]})
    model_b.answer('task-relatant', KINETIC_SIMULATION, task_b)
    model_c.answer('task-relatant', PARAMETER_ESTIMATION)
    models = (model_a, model_b, model_c)
    for number, relation in enumerate(FORMULA_RELATIONS):
        models[number % 3].block('model-to-formulation-basics', {
            'formulation-relation': relation, 'formulation-relatant': [relatants[number % len(relatants)]]})
    # Cycles of new models (#164): A approximates C and is approximated by C; A is the weak
    # formulation of B and has B as weak formulation
    for relation, relatant in (('approximates', model_c), ('approximated-by', model_c), ('contains', model_b),
                               ('contained-in', SIS_MODEL), ('discretizes', SIS_MODEL), ('discretized-by', model_c),
                               ('has-weak-formulation', model_b), ('is-weak-formulation-of', model_b),
                               ('linearizes', SIS_MODEL), ('linearized-by', model_c), ('similar-to', SIS_MODEL)):
        model_a.block('model-to-model', {'model-relation': relation, 'model-relatant': [relatant]})
    model_b.block('model-to-model', {'model-relation': 'specializes', 'model-relatant': [model_a],
                                     'model-assumption': [formulas['C'], SIS_INFECTIOUS]})
    model_c.block('model-to-model', {'model-relation': 'specialized-by', 'model-relatant': [SIS_MODEL],
                                     'model-assumption': [formulas['D'], WAVE_EQUATION]})

    # --- Publications --------------------------------------------------------------------------
    publication = doc.tab('publication', 'P1', HEROIN_EPIDEMICS)
    for relation, relatant in (('documents', model_a), ('invents', formulas['A']), ('studies', problem_a),
                               ('surveys', task_b), ('uses', SIS_INFECTIOUS)):
        publication.block('publication-to-entity', {'entity-relation': relation, 'entity-relatant': [relatant]})
    publication = doc.tab('publication', 'P2', HEROIN_EPIDEMICS_WIKIDATA)
    publication.block('publication-to-entity', {'entity-relation': 'documents', 'entity-relatant': [model_b, SIS_MODEL]})
    publication = doc.tab('publication', 'P3', Doi('10.21105/joss.11112'))         # KIM, new
    publication.block('publication-to-entity', {'entity-relation': 'uses', 'entity-relatant': [task_a]})
