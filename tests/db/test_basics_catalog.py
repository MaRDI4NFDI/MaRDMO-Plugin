'''The model basics catalog reads and writes only what it asks (#168).

It shares the questions of the model catalog but has no quantities,
academic disciplines and formula notation.  Hydration does not write them
(a selected formula brings no notation and no quantity pages), and answers
to them that a documentation has (e.g. from an older MaRDMO) are not read:
they neither block the export nor reach the portal.
'''
from rdmo.questions.models import Catalog

from MaRDMO import main
from MaRDMO.model.catalog import CATALOG_MODEL_BASICS_NAME, CATALOG_MODEL_NAME
from MaRDMO.core.config import catalog_questions, get_questions
from MaRDMO.model import models
from MaRDMO.model.handlers import Information
from tests.db.conftest import answer, save

QUESTIONS = get_questions('model') | get_questions('publication')


def keys(questions):
    return {(section, key) for section, entries in questions.items() for key in entries if key != 'uri'}


def test_the_basics_catalog_has_no_quantities_disciplines_or_notation(db):
    basics = catalog_questions(QUESTIONS, Catalog.objects.get(uri__endswith=CATALOG_MODEL_BASICS_NAME))
    assert 'Quantity' not in basics and 'Research Field' not in basics
    assert not {key for section, key in keys(basics) if section == 'Mathematical Formulation'} & {
        'Formula', 'Element Symbol', 'Element Quantity'}
    assert ('Research Problem', 'RFRelatant') not in keys(basics)
    # What it asks stays, and the citation data of publications too
    assert {('Mathematical Model', 'Name'), ('Mathematical Formulation', 'Reference')} <= keys(basics)
    assert basics['Publication'] == QUESTIONS['Publication']


def test_the_full_catalog_keeps_everything(db):
    full = catalog_questions(QUESTIONS, Catalog.objects.get(uri__endswith=CATALOG_MODEL_NAME))
    assert {'Quantity', 'Research Field'} <= set(full)
    assert ('Mathematical Formulation', 'Element Quantity') in keys(full)


def test_a_formula_brings_no_notation_in_the_basics_catalog(project, monkeypatch):
    asked = []
    monkeypatch.setattr('MaRDMO.model.handlers._fetch_by_source',
                        lambda items, *args: {external_id: models.MathematicalFormulation() for _, external_id, _ in items})
    monkeypatch.setattr(models, 'fetch_formula_data', lambda qids: asked.append(('mardi', qids)) or {})
    monkeypatch.setattr(models, 'fetch_formula_data_wikidata', lambda qids: asked.append(('wikidata', qids)) or {})
    documentation = project(CATALOG_MODEL_BASICS_NAME)
    Information()._fill_formulation_batch(documentation, [('x (y)', 'mardi:Q1', 0), ('z (w)', 'wikidata:Q2', 1)],
                                          CATALOG_MODEL_BASICS_NAME, set())
    assert asked == [('mardi', []), ('wikidata', [])]


def test_leftover_answers_are_not_read(project):
    '''A basics documentation with a quantity page and a formula notation (as MaRDMO wrote before).'''
    documentation = project(CATALOG_MODEL_BASICS_NAME)
    save(documentation,
         answer('formulation', 'F1', set_index=0),
         answer('formulation/id', 'new item', external_id='user:f', set_index=0),
         answer('formulation/name', 'f', set_prefix='0'),
         answer('formulation/formula', 'a = b', set_prefix='0|0'),
         answer('formulation/element/symbol', 'a', set_prefix='0|0|0'),
         answer('quantity', 'QQK1', set_index=0),
         answer('quantity/id', 'new item', external_id='user:q', set_index=0),
         answer('quantity/name', 'q', set_prefix='0'))
    provider = main.MaRDMOExportProvider('wikibase', 'x', 'MaRDMO.main.MaRDMOExportProvider')
    provider.project, provider.snapshot = documentation, None
    answers, _ = provider.get_post_data()
    assert 'quantity' not in answers
    formula = answers['formulation'][0]
    assert formula['Name'] == 'f' and not formula.get('Formula') and not formula.get('element')
