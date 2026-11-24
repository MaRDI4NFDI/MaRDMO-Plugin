'''The synthetic documentation of the model catalog: every question, option and kind of item.

Pages of each section: new items (two or more, so that each relation type
and each pair of exclusive properties is used once), one item of the MaRDI
Portal and one of Wikidata (selected as the page's item, so MaRDMO fills
the page and adds the pages of its relations), and new items typed into a
relation (MaRDMO adds their page, which is then filled here).  Every
relation question gets an item of each source its dropdown offers: the
documentation's own items, the MaRDI Portal, Wikidata, a typed new item.
'''
from .writer import Doi, New, Portal, Typed, Wikidata

# Items of the MaRDI Portal and Wikidata; their dropdowns offer them (the build checks it)
SIS_MODEL = Portal('Q6675171', 'susceptible infectious susceptible model')
BLACK_SCHOLES = Wikidata('Q1338307', 'Black–Scholes model')
KINETIC_SIMULATION = Portal('Q6684556', 'simulation of complex kinetic systems')
PARAMETER_ESTIMATION = Wikidata('Q131147154', 'parameter estimation')
SIS_INFECTIOUS = Portal('Q6674293', 'rate of change of infectious in the SIS model')
STATIONARY_NAVIER_STOKES = Portal('Q6830615', 'stationary Navier-Stokes equations')
WAVE_EQUATION = Wikidata('Q193846', 'wave equation')
# A formula of Wikidata (no twin on the portal) with a long chain of defining formulas (#166:
# its quantities come from the portal where it has them, the others without their formulas)
IDEAL_GAS_LAW = Wikidata('Q191785', 'ideal gas law')
# A quantity whose definition the portal's TeX check fails on (b_{\mathrm{B}}, #165)
MOLALITY = Wikidata('Q172623', 'molality')
FLUID_VELOCITY = Portal('Q7360710', 'fluid velocity')
PARTICLE_VELOCITY = Portal('Q6673873', 'particle velocity')
INTEGER = Portal('Q6673724', 'integer')
NUMBER_OF_INFECTED = Wikidata('Q23696805', 'number of infected')
SPREADING = Portal('Q6684648', 'spreading of infectious diseases')
EPIDEMIC = Wikidata('Q44512', 'epidemic')
EPIDEMIOLOGY = Portal('Q6684705', 'epidemiology')
SCIENTIFIC_WORKFLOWS = Wikidata('Q120970377', 'scientific workflows')
# Publications are selected by their DOI (#158)
HEROIN_EPIDEMICS = Doi('10.1016/J.MBS.2006.10.008', 'mardi:Q2643268')      # Heroin epidemics, treatment and ODE modelling
HEROIN_EPIDEMICS_WIKIDATA = Doi('10.1093/OXFORDJOURNALS.EPIREV.A036186', 'wikidata:Q40923322')  # Heroin epidemics revisited


def synthetic(kind, letter):
    return New(f'MaRDMO synthetic {kind} {letter}', f'synthetic {kind} {letter} of the MaRDMO tests')


def texts(page, kind):
    '''Aliases and long descriptions (several answers each).'''
    page.answer('alias', f'{page.label} alias one', f'{page.label} alias two')
    page.answer('long-description', f'The {kind} {page.label} is made up for the tests of MaRDMO.',
                'It uses every question of its page.')


def describe(doc):
    # --- Academic disciplines ----------------------------------------------------------
    field_a = doc.tab('field', 'AD1', synthetic('academic discipline', 'A'))
    field_b = doc.tab('field', 'AD2', synthetic('academic discipline', 'B'))
    texts(field_a, 'academic discipline')
    doc.tab('field', 'AD3', EPIDEMIOLOGY)
    doc.tab('field', 'AD4', SCIENTIFIC_WORKFLOWS)
    field_a.block('field-to-field', {'field-relation': 'specialized-by', 'field-relatant': [field_b]})
    field_b.block('field-to-field', {'field-relation': 'specializes', 'field-relatant': [field_a, EPIDEMIOLOGY]})
    field_b.block('field-to-field', {'field-relation': 'similar-to', 'field-relatant': [EPIDEMIOLOGY]})

    # --- Research problems -------------------------------------------------------------
    problem_a = doc.tab('problem', 'RP1', synthetic('research problem', 'A'))
    problem_b = doc.tab('problem', 'RP2', synthetic('research problem', 'B'))
    texts(problem_a, 'research problem')
    problem_a.answer('field-relatant', field_a, EPIDEMIOLOGY)
    typed_field = Typed('MaRDMO synthetic academic discipline typed')
    problem_b.answer('field-relatant', SCIENTIFIC_WORKFLOWS, typed_field)
    typed = doc.find('field', typed_field)
    typed.answer('description', 'synthetic academic discipline typed into a relation')
    doc.tab('problem', 'RP3', SPREADING)
    # Wikidata items have no academic discipline in MathModDB: the user adds one
    doc.tab('problem', 'RP4', EPIDEMIC).answer('field-relatant', EPIDEMIOLOGY)
    problem_a.block('problem-to-problem', {'problem-relation': 'specialized-by', 'problem-relatant': [problem_b]})
    problem_b.block('problem-to-problem', {'problem-relation': 'specializes', 'problem-relatant': [problem_a]})
    problem_b.block('problem-to-problem', {'problem-relation': 'similar-to', 'problem-relatant': [SPREADING]})

    # --- Quantities and quantity kinds --------------------------------------------------
    quantity_a = doc.tab('quantity', 'QQK1', synthetic('quantity', 'A'))
    quantity_b = doc.tab('quantity', 'QQK2', synthetic('quantity', 'B'))
    quantity_c = doc.tab('quantity', 'QQK3', synthetic('quantity', 'C'))
    kind_a = doc.tab('quantity', 'QQK4', synthetic('quantity kind', 'A'))
    kind_b = doc.tab('quantity', 'QQK5', synthetic('quantity kind', 'B'))
    for quantity in (quantity_a, quantity_b, quantity_c):
        quantity.answer('is-quantity-or-quantity-kind', 'quantity')
    for kind in (kind_a, kind_b):
        kind.answer('is-quantity-or-quantity-kind', 'quantity-kind')
    texts(quantity_a, 'quantity')
    texts(kind_a, 'quantity kind')
    quantity_a.answer('properties', 'is-physical-constant', 'is-deterministic', 'is-dimensional', 'is-static',
                      'is-space-continuous', 'is-time-continuous')
    quantity_b.answer('properties', 'is-mathematical-constant', 'is-stochastic', 'is-dimensionless', 'is-dynamic',
                      'is-space-discrete', 'is-time-discrete')
    quantity_c.answer('properties', 'is-chemical-constant')
    quantity_a.answer('reference', ('qudt-constant-id', 'SpeedOfLight_Vacuum'))
    kind_a.answer('reference', ('qudt-quantitykind-id', 'Velocity'))
    doc.tab('quantity', 'QQK6', FLUID_VELOCITY)
    doc.tab('quantity', 'QQK7', NUMBER_OF_INFECTED)
    # A defining formula of quantity B, with its symbols
    quantity_b.answer('formula', r'b \equiv \frac{a}{c} + v + n')
    quantity_b.block('element', {'element/symbol': 'b', 'element/quantity': quantity_b})
    quantity_b.block('element', {'element/symbol': 'v', 'element/quantity': FLUID_VELOCITY})
    quantity_b.block('element', {'element/symbol': 'n', 'element/quantity': NUMBER_OF_INFECTED})
    quantity_b.block('element', {'element/symbol': 'a', 'element/quantity': quantity_a})
    quantity_b.block('element', {'element/symbol': 'c', 'element/quantity': quantity_c})
    # Relations between quantities and quantity kinds
    # Quantity B is defined with A: A's relations go to C (and to the portal where they are stored there)
    # A approximates C and is approximated by C: a cycle of new quantities (#164)
    for relation, relatant in (('approximated-by', quantity_c), ('approximates', quantity_c),
                               ('discretized-by', quantity_c), ('discretizes', PARTICLE_VELOCITY),
                               ('nondimensionalized-by', quantity_c), ('nondimensionalizes', PARTICLE_VELOCITY),
                               ('similar-to', PARTICLE_VELOCITY), ('specialized-by', quantity_c),
                               ('specializes', FLUID_VELOCITY)):
        quantity_a.block('quantity-to-quantity', {'quantity-to-quantity/relation': relation,
                                                  'quantity-to-quantity/relatant': [relatant]})
    quantity_a.block('quantity-to-quantity-kind', {'quantity-to-quantity-kind/relation': 'specializes',
                                                   'quantity-to-quantity-kind/relatant': [kind_a, INTEGER]})
    for relation, relatant in (('discretized-by', kind_b), ('discretizes', INTEGER),
                               ('nondimensionalized-by', kind_b), ('nondimensionalizes', INTEGER),
                               ('similar-to', kind_b)):
        kind_a.block('quantity-kind-to-quantity-kind', {'quantity-kind-to-quantity-kind/relation': relation,
                                                        'quantity-kind-to-quantity-kind/relatant': [relatant]})
    kind_b.block('quantity-kind-to-quantity', {'quantity-kind-to-quantity/relation': 'specialized-by',
                                               'quantity-kind-to-quantity/relatant': [quantity_c, PARTICLE_VELOCITY]})

    # --- Formulas -------------------------------------------------------------------------
    formulas = {}
    for letter, tab, properties, tex, symbols in (
        ('A', 'F1', ('is-deterministic', 'is-dimensionless', 'is-dynamic', 'is-linear', 'is-space-continuous',
                     'is-time-continuous', 'is-ordinary-differential-equation'),
         r'\frac{d a}{d t} = - c \, a', (('a', quantity_a), ('c', quantity_c), ('t', kind_a))),
        ('B', 'F2', ('is-stochastic', 'is-dimensional', 'is-static', 'is-not-linear', 'is-space-discrete',
                     'is-time-discrete', 'is-partial-differential-equation'),
         r'\frac{\partial b}{\partial t} = \Delta b + b^2', (('b', quantity_b), ('t', kind_a))),
        ('C', 'F3', ('is-stochastic-differential-equation',),
         r'd a = c \, a \, d t + b \, d W', (('a', quantity_a), ('b', quantity_b), ('c', quantity_c),
                                              ('t', kind_a), ('W', kind_b))),
        # One defining formula per item: D is a system of two equations in one formula
        ('D', 'F4', ('is-integro-differential-equation',),
         r'\begin{align} \frac{d a}{d t} &= \int_0^t c \, a \, d s \\ q &= k + \int_0^t c \, a \, d s \end{align}',
         (('a', quantity_a), ('c', quantity_c), ('t', kind_a), ('s', kind_a))),
    ):
        formula = doc.tab('formulation', tab, synthetic('formula', letter))
        formula.answer('properties', *properties)
        formula.answer('formula', tex)
        for symbol, quantity in symbols:
            formula.block('element', {'element/symbol': symbol, 'element/quantity': quantity})
        formulas[letter] = formula
    texts(formulas['A'], 'formula')
    # A symbol for a new quantity typed in, and one for a quantity of Wikidata
    formulas['D'].block('element', {'element/symbol': 'k', 'element/quantity': NUMBER_OF_INFECTED})
    typed_quantity = Typed('MaRDMO synthetic quantity typed')
    formulas['D'].block('element', {'element/symbol': 'q', 'element/quantity': typed_quantity})
    typed = doc.find('quantity', typed_quantity)
    typed.answer('description', 'synthetic quantity typed into a formula')
    typed.answer('is-quantity-or-quantity-kind', 'quantity')
    doc.tab('formulation', 'F5', SIS_INFECTIOUS)
    doc.tab('formulation', 'F6', IDEAL_GAS_LAW)
    doc.tab('quantity', 'QQK8', MOLALITY)
    # The quantities of the ideal gas law come from Wikidata, or are their twins on the portal
    # (#166), without MathModDB class; Wikidata definitions use "=": the user gives the class
    # (a QUDT quantity kind ID: a quantity kind) and writes the definition with \equiv
    for quantity in doc.tabs('quantity'):
        if quantity.id.startswith('user:'):
            continue
        if not quantity.answered('is-quantity-or-quantity-kind'):
            kind = any(reference for reference in quantity.references() if reference == 'mathmoddb/qudt-quantitykind-id')
            quantity.answer('is-quantity-or-quantity-kind', 'quantity-kind' if kind else 'quantity')
        for index, tex in enumerate(quantity.texts('formula') if quantity.id.startswith('wikidata:') else []):
            if tex and r'\equiv' not in tex:
                quantity.change('formula', tex.replace('=', r'\equiv', 1), collection_index=index)
    # Formulas in formulas (assumptions, boundary conditions, ...)
    typed_formula = Typed('MaRDMO synthetic formula typed')
    for relation, relatants in (('assumes', [formulas['B']]), ('contains', [formulas['C'], IDEAL_GAS_LAW]),
                                ('contains-boundary-condition', [formulas['D']]),
                                ('contains-constraint-condition', [SIS_INFECTIOUS]),
                                ('contains-coupling-condition', [typed_formula]),
                                ('contains-initial-condition', [formulas['B']]),
                                ('contains-final-condition', [formulas['C']])):
        formulas['A'].block('formulation-to-formulation-1', {'formulation-relation-1': relation,
                                                            'formulation-relatant-1': relatants})
    typed = doc.find('formulation', typed_formula)
    typed.answer('description', 'synthetic formula typed into a relation')
    typed.answer('formula', 'a = c')
    typed.block('element', {'element/symbol': 'a', 'element/quantity': quantity_a})
    typed.block('element', {'element/symbol': 'c', 'element/quantity': quantity_c})
    # Formulas related to formulas (approximations, specializations with assumptions, ...)
    # Relations stored on the other item ("approximates" is "approximated by" there) close cycles
    # of new items (#164): A approximated by B, B specialized by C, A approximates C (A, B, C);
    # A approximated by B, A linearizes B (A, B).  The others go to the portal
    for relation, relatant in (('approximated-by', formulas['B']), ('approximates', formulas['C']),
                               ('discretized-by', formulas['B']), ('discretizes', SIS_INFECTIOUS),
                               ('is-weak-formulation-of', SIS_INFECTIOUS), ('has-weak-formulation', formulas['B']),
                               ('linearized-by', formulas['C']), ('linearizes', formulas['B']),
                               ('nondimensionalized-by', formulas['B']), ('nondimensionalizes', SIS_INFECTIOUS),
                               ('similar-to', STATIONARY_NAVIER_STOKES)):
        formulas['A'].block('formulation-to-formulation-2', {'formulation-relation-2': relation,
                                                            'formulation-relatant-2': [relatant]})
    formulas['B'].block('formulation-to-formulation-2', {
        'formulation-relation-2': 'specialized-by', 'formulation-relatant-2': [formulas['C']],
        'formulation-assumption': [formulas['D'], IDEAL_GAS_LAW, SIS_INFECTIOUS]})
    formulas['C'].block('formulation-to-formulation-2', {
        'formulation-relation-2': 'specializes', 'formulation-relatant-2': [SIS_INFECTIOUS],
        'formulation-assumption': [formulas['D']]})

    # --- Computational tasks ------------------------------------------------------------
    task_a = doc.tab('task', 'CT1', synthetic('computational task', 'A'))
    task_b = doc.tab('task', 'CT2', synthetic('computational task', 'B'))
    texts(task_a, 'computational task')
    task_a.answer('properties', 'is-linear', 'is-space-continuous', 'is-time-continuous')
    task_b.answer('properties', 'is-not-linear', 'is-space-discrete', 'is-time-discrete')
    # The portal task lacks formulas and quantities, the Wikidata task has none: the user adds them
    for tab, item in (('CT3', KINETIC_SIMULATION), ('CT4', PARAMETER_ESTIMATION)):
        task = doc.tab('task', tab, item)
        task.block('task-to-formulation', {'formulation-relation': 'contains-governing-equation',
                                           'formulation-relatant': [formulas['B']]})
        task.block('task-to-quantity', {'quantity-relation': 'contains-output', 'quantity-relatant': [quantity_b]})
    formula_relations = ('assumes', 'contains', 'contains-analytical-solution', 'contains-boundary-condition',
                         'contains-computational-domain', 'contains-constraint-condition',
                         'contains-coupling-condition', 'contains-definition', 'contains-initial-condition',
                         'contains-final-condition', 'contains-governing-equation', 'contains-strong-formulation',
                         'contains-weak-formulation')
    relatants = [formulas['A'], formulas['B'], formulas['C'], formulas['D'], SIS_INFECTIOUS, IDEAL_GAS_LAW]
    for number, relation in enumerate(formula_relations):
        task = task_a if number % 2 == 0 else task_b
        task.block('task-to-formulation', {'formulation-relation': relation,
                                           'formulation-relatant': [relatants[number % len(relatants)]]})
    for task in (task_a, task_b):
        for relation, relatant in (('contains-input', quantity_a), ('contains-constant', quantity_c),
                                   ('contains-objective', quantity_b), ('contains-output', kind_a),
                                   ('contains-parameter', FLUID_VELOCITY)):
            task.block('task-to-quantity', {'quantity-relation': relation, 'quantity-relatant': [relatant]})
    task_b.block('task-to-quantity', {'quantity-relation': 'contains-input', 'quantity-relatant': [NUMBER_OF_INFECTED]})
    # A approximates B and is approximated by B: a cycle of new tasks (#164)
    for relation, relatant in (('approximates', task_b), ('approximated-by', task_b), ('contains', task_b),
                               ('contained-in', KINETIC_SIMULATION), ('discretizes', KINETIC_SIMULATION),
                               ('discretized-by', task_b), ('linearizes', KINETIC_SIMULATION), ('linearized-by', task_b),
                               ('similar-to', KINETIC_SIMULATION)):
        task_a.block('task-to-task', {'task-relation': relation, 'task-relatant': [relatant]})
    task_a.block('task-to-task', {'task-relation': 'specializes', 'task-relatant': [KINETIC_SIMULATION],
                                  'task-assumption': [formulas['A']]})
    task_b.block('task-to-task', {'task-relation': 'specialized-by', 'task-relatant': [KINETIC_SIMULATION],
                                  'task-assumption': [formulas['B'], IDEAL_GAS_LAW, SIS_INFECTIOUS]})

    # --- Mathematical models --------------------------------------------------------------
    model_a = doc.tab('model', 'MM1', synthetic('mathematical model', 'A'))
    model_b = doc.tab('model', 'MM2', synthetic('mathematical model', 'B'))
    model_c = doc.tab('model', 'MM3', synthetic('mathematical model', 'C'))
    texts(model_a, 'mathematical model')
    doc.tab('model', 'MM4', SIS_MODEL)
    black_scholes = doc.tab('model', 'MM5', BLACK_SCHOLES)
    black_scholes.answer('problem-relatant', problem_b)
    black_scholes.block('model-to-formulation', {'formulation-relation': 'contains-governing-equation',
                                                  'formulation-relatant': [formulas['A']]})
    model_a.answer('properties', 'is-deterministic', 'is-dimensionless', 'is-dynamic', 'is-linear',
                   'is-space-continuous', 'is-time-continuous')
    model_b.answer('properties', 'is-stochastic', 'is-dimensional', 'is-static', 'is-not-linear',
                   'is-space-discrete', 'is-time-discrete')
    typed_problem = Typed('MaRDMO synthetic research problem typed')
    model_a.answer('problem-relatant', problem_a, typed_problem)
    typed = doc.find('problem', typed_problem)
    typed.answer('description', 'synthetic research problem typed into a relation')
    typed.answer('field-relatant', field_b)
    model_b.answer('problem-relatant', SPREADING)
    model_c.answer('problem-relatant', EPIDEMIC, problem_b)
    typed_task = Typed('MaRDMO synthetic computational task typed')
    model_a.answer('task-relatant', task_a, typed_task)
    typed = doc.find('task', typed_task)
    typed.answer('description', 'synthetic computational task typed into a relation')
    typed.block('task-to-formulation', {'formulation-relation': 'contains', 'formulation-relatant': [formulas['A']]})
    typed.block('task-to-quantity', {'quantity-relation': 'contains-input', 'quantity-relatant': [quantity_a]})
    model_b.answer('task-relatant', KINETIC_SIMULATION, task_b)
    model_c.answer('task-relatant', PARAMETER_ESTIMATION)
    models = (model_a, model_b, model_c)
    for number, relation in enumerate(formula_relations):
        models[number % 3].block('model-to-formulation', {
            'formulation-relation': relation, 'formulation-relatant': [relatants[number % len(relatants)]]})
    # Cycles of new models (#164): A approximates C and is approximated by C; A is the weak
    # formulation of B and has B as weak formulation
    for relation, relatant in (('approximates', model_c), ('approximated-by', model_c), ('contains', model_b),
                               ('contained-in', SIS_MODEL), ('discretizes', SIS_MODEL), ('discretized-by', model_c),
                               ('has-weak-formulation', model_b), ('is-weak-formulation-of', model_b),
                               ('linearizes', SIS_MODEL), ('linearized-by', model_c), ('similar-to', SIS_MODEL)):
        model_a.block('model-to-model', {'model-relation': relation, 'model-relatant': [relatant]})
    model_b.block('model-to-model', {'model-relation': 'specializes', 'model-relatant': [model_a],
                                     'model-assumption': [formulas['C']]})
    model_c.block('model-to-model', {'model-relation': 'specialized-by', 'model-relatant': [SIS_MODEL],
                                     'model-assumption': [formulas['D'], IDEAL_GAS_LAW, SIS_INFECTIOUS]})

    # --- Publications ---------------------------------------------------------------------
    publication = doc.tab('publication', 'P1', HEROIN_EPIDEMICS)
    for relation, relatant in (('documents', model_a), ('invents', formulas['A']), ('studies', problem_a),
                               ('surveys', field_a), ('uses', quantity_a)):
        publication.block('publication-to-entity', {'entity-relation': relation, 'entity-relatant': [relatant]})
    publication.block('publication-to-entity', {'entity-relation': 'uses', 'entity-relatant': [task_a, kind_a]})
    publication = doc.tab('publication', 'P2', HEROIN_EPIDEMICS_WIKIDATA)
    publication.block('publication-to-entity', {'entity-relation': 'documents', 'entity-relatant': [model_b, SIS_MODEL]})
    # Typed by their DOI: the first is on Wikidata only (the dropdown offers the Wikidata
    # item); the second nowhere yet (new, the citation services give the rest: five authors,
    # four with ORCID iD, and its journal)
    publication = doc.tab('publication', 'P3', Doi('10.21105/joss.02404', 'wikidata:Q106245557'))
    publication.block('publication-to-entity', {'entity-relation': 'uses', 'entity-relatant': [quantity_b]})
    publication = doc.tab('publication', 'P4', Doi('10.21105/joss.11112'))
    publication.block('publication-to-entity', {'entity-relation': 'studies', 'entity-relatant': [model_c, task_b]})
