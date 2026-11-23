'''The upload's progress page (progress.js) and the result page with its graph (cytoscape) in a browser.

The upload itself is not run: the tests write what its thread writes into
the progress store, and the page polls it as during a real upload.
'''
import re

import pytest
from playwright.sync_api import expect

from MaRDMO.export.store import get_progress_data, set_progress_data
from tests.browser.conftest import screenshot

JOB = 'job-1'
MODEL = ['Mathematical Model', 'MaRDMO test model A', 'Q21993']
FORMULA = ['Formula', 'MaRDMO test formula one', 'Q21989']
# The new model contains the new formula and belongs to an existing community (Q3842)
RESULT = {
    'ids': [MODEL, FORMULA],
    'statements': [
        ['MaRDMO test model A', 'Q21993', 'contains', 'MaRDMO test formula one', 'Q21989', [], '', '', False],
        ['MaRDMO test model A', 'Q21993', 'described by', 'MathModDB', 'Q3842', [], '', '', False],
    ],
}


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user('owner', password='owner')


def progress(**data):
    set_progress_data(JOB, {'done': False, **data})


def test_the_page_follows_the_upload_to_its_result(user, page_as):
    progress(progress=30, phase='items')
    page = page_as(user, jobs=[JOB])
    page.goto(f'/services/progress/{JOB}/')
    status = page.locator('#status')
    expect(status).to_contain_text('Create new Items')
    expect(page.locator('#coloredContainer')).to_have_attribute('style', re.compile(r'width: 30%'))
    screenshot(page, 'progress-items')

    progress(progress=70, phase='relations')
    expect(status).to_contain_text('Create new Statements')
    expect(page.locator('#coloredContainer')).to_have_attribute('style', re.compile(r'width: 70%'))

    set_progress_data(JOB, {'progress': 100, 'phase': 'done', 'done': True,
                            'redirect': f'/services/success/{JOB}/', **RESULT})
    expect(status).to_contain_text('Upload complete!')
    page.wait_for_url(f'**/services/success/{JOB}/')
    expect(page.locator('#view-list')).to_contain_text('MaRDMO test model A')
    screenshot(page, 'result-list', full_page=True)
    # The result page is shown once: the job is gone
    assert get_progress_data(JOB) is None


def test_the_graph_of_the_result(user, page_as):
    set_progress_data(JOB, {'progress': 100, 'phase': 'done', 'done': True, **RESULT})
    page = page_as(user, jobs=[JOB])
    page.goto(f'/services/success/{JOB}/')
    page.locator('#tab-graph-btn').click()
    page.wait_for_function('window.mardmoGraph !== undefined')
    graph = page.evaluate('''() => window.mardmoGraph.nodes().map(node => [node.id(), node.data('node_type')])''')
    assert sorted(graph) == [['Q21989', 'new'], ['Q21993', 'new'], ['Q3842', 'item']]
    assert page.evaluate("() => window.mardmoGraph.edges().length") == 2
    screenshot(page, 'result-graph', full_page=True)

    # The filters hide existing items
    page.locator('#btn-filter-toggle').click()
    page.locator('#flt-existing').uncheck()
    assert page.evaluate("() => window.mardmoGraph.getElementById('Q3842').visible()") is False
    assert page.evaluate("() => window.mardmoGraph.getElementById('Q21993').visible()") is True
    page.locator('#flt-existing').check()
    assert page.evaluate("() => window.mardmoGraph.getElementById('Q3842').visible()") is True

    # Fullscreen and back
    button = page.locator('#btn-fullscreen')
    button.click()
    expect(page.locator('#view-graph')).to_have_css('position', 'fixed')
    expect(button).to_have_attribute('title', 'Exit fullscreen')
    button.click()
    expect(page.locator('#view-graph')).not_to_have_css('position', 'fixed')
    expect(button).to_have_attribute('title', 'Fullscreen')


def test_the_progress_page_in_german(user, page_as):
    progress(progress=30, phase='items')
    page = page_as(user, jobs=[JOB], language='de')
    page.goto(f'/services/progress/{JOB}/')
    expect(page.locator('#status')).to_contain_text('Neue Items anlegen')
    screenshot(page, 'progress-german')


def test_an_error_is_shown_as_text(user, page_as):
    '''The message may contain what the user entered: it must not become HTML.'''
    progress(progress=-1, phase='error', error='<img src=x id=injected> was rejected')
    page = page_as(user, jobs=[JOB])
    page.goto(f'/services/progress/{JOB}/')
    status = page.locator('#status')
    expect(status).to_contain_text('Upload failed')
    expect(status).to_contain_text('<img src=x id=injected> was rejected')
    assert page.locator('#injected').count() == 0


def test_someone_elses_job_is_not_found(user, page_as):
    progress(progress=30, phase='items')
    page = page_as(user)                                    # not this session's job
    assert page.goto(f'/services/progress/{JOB}/').status == 404
    assert page.goto(f'/services/success/{JOB}/').status == 404
    assert page.request.get(f'/services/progress/{JOB}/status/').status == 404
