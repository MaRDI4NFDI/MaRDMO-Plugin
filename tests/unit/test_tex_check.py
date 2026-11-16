'''The verdicts of the portal's TeX check (#165): valid, invalid, not reachable, failed.

Only "not reachable" asks to try again; a check that fails on a formula
(e.g. HTTP 500 for valid TeX, which the portal saves and renders) lets the
formula pass as not verified, as trying again would not help.
'''
import pytest
import requests

from MaRDMO import tex_check
from MaRDMO.tex_check import FAILED, UNAVAILABLE

# The portal's answer for b_{\mathrm{B}} (2026-11-16)
CRASH = ('{"message":"Error: exception of type TypeError: MediaWiki\\\\Extension\\\\Math\\\\WikiTexVC\\\\Nodes\\\\'
         'Fun1::getSubs(): Argument #1 ($subs) must be of type array, string given"}')


class Answer:
    def __init__(self, status, body):
        self.status_code, self.text = status, body

    def json(self):
        import json
        return json.loads(self.text)


@pytest.fixture
def portal(monkeypatch):
    '''The checker answers what a test gives it; returns the TeX of every request sent.'''
    sent, answers = [], {}

    def ask(method, url, data=None, **kwargs):
        sent.append(data['q'])
        answer = answers[data['q']]
        if isinstance(answer, Exception):
            raise answer
        return answer
    monkeypatch.setattr(tex_check, 'request_with_retry', ask)
    return answers, sent


@pytest.mark.parametrize('answer, verdict', [
    (Answer(200, '{"success": true, "checked": "x"}'), None),
    (Answer(400, '{"message": "unknown function \\\\foo"}'), 'unknown function \\foo'),
    (Answer(400, '{}'), 'syntax error'),
    (Answer(500, CRASH), FAILED),
    (Answer(200, 'not JSON'), FAILED),
    (Answer(200, '{"success": false}'), FAILED),
    (Answer(503, 'Service Unavailable'), UNAVAILABLE),
    (Answer(429, 'Too Many Requests'), UNAVAILABLE),
    (requests.exceptions.ConnectTimeout('timed out'), UNAVAILABLE),
])
def test_the_verdicts(portal, answer, verdict):
    answers, _ = portal
    answers[r'b_{\mathrm{B}}'] = answer
    assert tex_check.check_formulas([r'b_{\mathrm{B}}']) == {r'b_{\mathrm{B}}': verdict}


@pytest.mark.parametrize('answer, asked_again', [
    (Answer(200, '{"success": true}'), False),          # kept for a week
    (Answer(400, '{"message": "syntax error"}'), False),
    (Answer(500, CRASH), False),                         # kept for a day: asking again does not help
    (Answer(503, 'Service Unavailable'), True),          # not kept: the portal may answer shortly
])
def test_which_verdicts_are_kept(portal, answer, asked_again):
    answers, sent = portal
    answers['x'] = answer
    tex_check.check_formulas(['x'])
    tex_check.check_formulas(['x'])
    assert len(sent) == (2 if asked_again else 1)
