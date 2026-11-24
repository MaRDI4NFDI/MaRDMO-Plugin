'''MaRDMO's rendering of LaTeX comes into RDMO's interview by a middleware; every other response stays as it is.'''
from types import SimpleNamespace

import pytest
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse, StreamingHttpResponse
from django.test import override_settings

from MaRDMO.middleware import PATH, InterviewMathPreview, check_middleware

PAGE = b'<html><head></head><body><div id="interview"></div></body></html>'


def respond(rf, response, url_name='project_interview', method='get'):
    request = getattr(rf, method)('/projects/1/interview/')
    request.resolver_match = SimpleNamespace(url_name=url_name) if url_name else None
    return InterviewMathPreview(lambda request: response)(request)


def test_the_scripts_come_before_the_end_of_the_interview_page(rf):
    response = HttpResponse(PAGE)
    response['Content-Length'] = str(len(PAGE))
    page = respond(rf, response).content
    assert page.count(b'math-preview.js') == 1
    assert page.index(b'math-preview.js') < page.index(b'</body>')
    assert page.startswith(PAGE[:-len(b'</body></html>')]) and page.endswith(b'</body></html>')
    assert b'data-csrf="' in page and b'data-tex-check="/services/tex-check/"' in page
    assert response['Content-Length'] == str(len(page))


@pytest.mark.parametrize('response, url_name, method', [
    pytest.param(HttpResponse(PAGE), 'project', 'get', id='another page'),
    pytest.param(HttpResponse(PAGE), None, 'get', id='no view'),
    pytest.param(HttpResponse(PAGE), 'project_interview', 'post', id='a POST'),
    pytest.param(HttpResponse(PAGE, status=404), 'project_interview', 'get', id='an error'),
    pytest.param(HttpResponseRedirect('/projects/1/'), 'project_interview', 'get', id='a redirect'),
    pytest.param(JsonResponse({'html': '</body>'}), 'project_interview', 'get', id='JSON'),
    pytest.param(HttpResponse(b'<p>no end</p>'), 'project_interview', 'get', id='no end of body'),
])
def test_every_other_response_stays_as_it_is(rf, response, url_name, method):
    before = response.content
    assert respond(rf, response, url_name, method).content == before


def test_a_compressed_or_streamed_page_stays_as_it_is(rf):
    compressed = HttpResponse(b'\x1f\x8b compressed </body>')
    compressed['Content-Encoding'] = 'gzip'
    assert respond(rf, compressed).content == b'\x1f\x8b compressed </body>'
    streamed = StreamingHttpResponse(iter([PAGE]))
    assert b''.join(respond(rf, streamed).streaming_content) == PAGE


def test_the_check_warns_without_the_middleware():
    with override_settings(MIDDLEWARE=['django.middleware.common.CommonMiddleware']):
        [warning] = check_middleware()
    assert warning.id == 'MaRDMO.W001' and PATH in warning.hint
    with override_settings(MIDDLEWARE=['django.middleware.common.CommonMiddleware', PATH]):
        assert check_middleware() == []
