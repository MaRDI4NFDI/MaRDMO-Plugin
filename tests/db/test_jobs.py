'''The progress and result pages of an export: only for the session that started it (#138).

A job is in the cache (store.py); the session remembers the jobs it
started.  The result page shows what was created and added, and forgets the
job afterwards.  The jobs are written here as the upload writes them.
'''
import pytest

from MaRDMO.store import SESSION_JOBS_KEY, _progress_store
from tests.support.html import text

RESULT = {
    'progress': 100, 'done': True, 'phase': 'done', 'error': None, 'redirect': '/services/success/job/',
    'ids': [['mathematical model', 'flux model (model of the tests)', 'Q901'],
            ['unusual class', 'odd item (item of no listed class)', 'Q903']],
    'statements': [
        # On the new model: a relation to a portal item, a literal with a link, an amount with unit
        ['flux model', 'Q901', 'contains', 'Laplace equation', 'Q77', [], '', '', False],
        ['flux model', 'Q901', 'DOI', '10.1000/x', '', [], '', '', False],
        ['flux model', 'Q901', 'described at URL', 'https://example.org/flux', '', [], '', '', False],
        # Markers of new items are not listed; on portal items they are counted
        ['flux model', 'Q901', 'community', 'MathModDB', 'Q6534265', [], '', '', False],
        ['heat equation', 'Q55', 'community', 'MathModDB', 'Q6534265', [], '', '', False],
        # On a portal item: a new statement, and qualifiers added to one it had
        ['heat equation', 'Q55', 'specialized by', 'flux model', 'Q901',
         [{'prop': 'assumes', 'obj': 'Fourier law', 'obj_qid': 'Q78'}], '', '', False],
        ['heat equation', 'Q55', 'contains', 'flux', 'Q79',
         [{'prop': 'object has role', 'obj': 'boundary condition', 'obj_qid': 'Q80'}], '', '', True],
    ],
    'counts': {'items_created': 2, 'items_planned': 2, 'relations_created': 2, 'relations_planned': 2},
}


@pytest.fixture
def user_client(client, django_user_model, db):
    client.force_login(django_user_model.objects.create_user('owner', password='owner'))
    return client


def started(client, job, data=None):
    if data is not None:
        _progress_store[job] = data
    session = client.session
    session[SESSION_JOBS_KEY] = session.get(SESSION_JOBS_KEY, []) + [job]
    session.save()


@pytest.mark.parametrize('url', ['/services/progress/job/', '/services/progress/job/status/',
                                 '/services/success/job/'])
def test_someone_elses_job_is_not_found(user_client, url):
    _progress_store['job'] = RESULT
    assert user_client.get(url).status_code == 404


def test_a_job_without_progress_yet(user_client):
    started(user_client, 'job')
    assert user_client.get('/services/progress/job/status/').json() == {'progress': 0, 'done': False}
    page = text(user_client.get('/services/success/job/').content.decode())
    assert 'Not ready' in page and 'Job not found' in page


def test_the_result_page_and_then_the_job_is_gone(user_client):
    started(user_client, 'job', RESULT)
    page = text(user_client.get('/services/success/job/').content.decode())
    assert 'flux model' in page and 'odd item' in page
    # Literals with an identifier become links; markers of new items are not listed
    assert '10.1000/x' in page and 'https://example.org/flux' in page
    assert user_client.get('/services/success/job/').status_code == 404
    assert _progress_store.get('job') is None


def test_the_result_page_lists_what_portal_items_got(user_client):
    started(user_client, 'job', RESULT)
    response = user_client.get('/services/success/job/')
    html = response.content.decode()
    assert 'href="https://doi.org/10.1000/x"' in html
    page = text(html)
    assert 'heat equation' in page and 'Fourier law' in page and 'boundary condition' in page


def test_login_is_required(client, db):
    response = client.get('/services/progress/job/status/')
    assert response.status_code == 302 and 'login' in response['Location']
