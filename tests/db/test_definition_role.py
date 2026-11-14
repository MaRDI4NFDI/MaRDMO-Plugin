'''Formulas contained in models and tasks as "definition" (#143).'''
import pytest

from MaRDMO import main
from MaRDMO.getters import get_items, get_properties, get_url
from MaRDMO.model.models import MathematicalModel, Task
from MaRDMO.model.worker import PrepareModel
from MaRDMO.queries import PortalItems
from tests.db.conftest import answer, save

DEFINITION = 'mardi:Q7268735'


@pytest.mark.parametrize('entity', [MathematicalModel, Task])
def test_a_formula_with_the_role_definition_is_imported(entity):
    '''Before, a formula with an unknown role was dropped.'''
    data = {'contains_formulation': {'value': f'mardi:Q1 || alpha || a formula || {DEFINITION}'
                                              ' <|> mardi:Q2 || beta || another formula || '}}
    item = entity.from_query_single(data)
    assert [formula.id for formula in item.contains_definition] == ['mardi:Q1']
    assert [formula.id for formula in item.contains_formulation] == ['mardi:Q2']


@pytest.fixture
def model(project):
    '''A model whose formula is its definition.'''
    documentation = project('mardmo-model-catalog')
    save(documentation,
         answer('model', 'MM1', set_index=0),
         answer('model/id', 'new item', external_id='user:model', set_index=0),
         answer('model/name', 'a model', set_prefix='0'),
         answer('model/description', 'a model with a definition', set_prefix='0'),
         answer('model/formulation-relation', option='mathmoddb/contains-definition', set_prefix='0', set_index=0),
         answer('model/formulation-relatant', 'a formula (the definition)', external_id='user:formula',
                set_prefix='0', set_index=0),
         answer('formulation', 'F1', set_index=0),
         answer('formulation/id', 'new item', external_id='user:formula', set_index=0),
         answer('formulation/name', 'a formula', set_prefix='0'),
         answer('formulation/description', 'the definition', set_prefix='0'))
    return documentation


def test_the_export_writes_contains_with_the_role_definition(model, monkeypatch):
    monkeypatch.setattr('MaRDMO.duplicates.find_portal_items', lambda **kwargs: PortalItems())
    monkeypatch.setattr('MaRDMO.model.worker.annotate_formulas', lambda answers: None)
    provider = main.MaRDMOExportProvider('wikibase', 'x', 'MaRDMO.main.MaRDMOExportProvider')
    provider.project, provider.snapshot = model, None
    answers, _ = provider.get_post_data()
    payload, _ = PrepareModel().export(answers, get_url('mardi', 'uri'))
    contains, role = get_properties()['contains'], get_properties()['object has role']
    statements = [statement for entry in payload.values() if isinstance(entry, dict)
                  for statement in entry.get('statements', [])
                  if isinstance(statement, list) and statement and statement[0] == contains]
    assert statements, payload
    assert any(role in str(statement) and get_items()['definition'] in str(statement) for statement in statements), \
        statements
