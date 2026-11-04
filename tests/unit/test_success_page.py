'''The export result page: standard statements on existing items are counted, not listed.

A re-export that only added "community" to existing quantities said
"Export complete - no new items or relations".
'''
import pytest
from django.test import RequestFactory

import MaRDMO.views as views

COMMUNITY = ['MaRDMO test quantity a', 'Q21983', 'community', 'MathModDB', 'Q3842', [], '', '', False]


@pytest.fixture
def page(monkeypatch, db, django_user_model):
    user = django_user_model.objects.create(username='tester')

    def render(job):
        monkeypatch.setattr(views, '_job_belongs_to_session', lambda request, job_id: True)
        monkeypatch.setattr(views, '_unregister_job_for_session', lambda request, job_id: None)
        monkeypatch.setattr(views, 'clear_progress', lambda job_id: None)
        monkeypatch.setattr(views._progress_store, 'get', lambda job_id: job)
        request = RequestFactory().get('/services/success/job/')
        request.user = user
        request.session = {}
        return views.show_success(request, 'job').content.decode()

    return render


def test_only_standard_statements_are_mentioned(page):
    html = page({'ids': [], 'statements': [COMMUNITY, COMMUNITY[:1] + ['Q21984'] + COMMUNITY[2:]]})
    assert 'no new items or relations' in html
    assert '2 standard statements (community, MaRDI profile type) were added to existing items' in html


def test_standard_statements_next_to_relations(page):
    relation = ['MaRDMO test model A', 'Q21993', 'contains', 'MaRDMO test formula one', 'Q21989', [], '', '', False]
    html = page({'ids': [], 'statements': [relation, COMMUNITY]})
    assert 'Relations added to MaRDI Portal!' in html
    assert '1 standard statement (community, MaRDI profile type) was added to existing items' in html


def test_standard_statements_of_new_items_are_not_counted(page):
    html = page({'ids': [['Quantity', 'MaRDMO test quantity a', 'Q21983']], 'statements': [COMMUNITY]})
    assert 'standard statement' not in html
