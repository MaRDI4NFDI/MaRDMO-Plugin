'''A relation of an item to another of its kind without relation type (#152).

The checks crashed on it (``None['url']``) instead of reporting it.
'''
import pytest

from MaRDMO import main
from MaRDMO.checks import Checks
from tests.db.conftest import answer, save


def page(section, index, identifier, name):
    return [answer(section, f'{section} {index + 1}', set_index=index),
            answer(f'{section}/id', 'new item', external_id=identifier, set_index=index),
            answer(f'{section}/name', name, set_prefix=str(index)),
            answer(f'{section}/description', f'a {name}', set_prefix=str(index))]


@pytest.mark.parametrize('section, relatant, name', [
    ('model', 'model/model-relatant', 'Mathematical Model'),
    ('task', 'task/task-relatant', 'Computational Task'),
    ('formulation', 'formulation/formulation-relatant-2', 'Formula'),
])
def test_a_missing_relation_type_is_reported(project, monkeypatch, section, relatant, name):
    monkeypatch.setattr('MaRDMO.model.worker.annotate_formulas', lambda answers: None)
    monkeypatch.setattr('MaRDMO.checks.model.check_formulas', lambda formulas: {})
    documentation = project('mardmo-model-catalog')
    save(documentation, *page(section, 0, 'user:general', 'general'), *page(section, 1, 'user:special', 'special'),
         answer(relatant, 'special (a special)', external_id='user:special', set_prefix='0'))
    provider = main.MaRDMOExportProvider('wikibase', 'x', 'MaRDMO.main.MaRDMOExportProvider')
    provider.project, provider.snapshot = documentation, None
    answers, _ = provider.get_post_data()
    messages = [str(m) for m in Checks().run_model(project=documentation, data=answers,
                                                   catalog=str(documentation.catalog))]
    assert f'{name} (Page {section} 1): Missing Relation Type ({name})' in messages, messages
