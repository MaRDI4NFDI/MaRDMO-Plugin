'''MaRDMO's view for the portal's verdict on a formula typed into the interview (#190).

Only for logged-in users and with the CSRF token (the interview has both):
the URL is no way to the portal's checker for anyone else.  The verdict
itself is tests/unit/test_tex_check.py's; here it is given.
'''
import pytest
from django.test import Client
from django.urls import reverse

import MaRDMO.views as views
from MaRDMO.views import TEX_CHECK_MAX_LENGTH

URL = '/services/tex-check/'


@pytest.fixture
def checked(monkeypatch):
    '''check_formula answers {"state": "valid", ...} and notes what it was asked.'''
    asked = []

    def check_formula(tex):
        asked.append(tex)
        return {'state': 'valid', 'message': '', 'checked': tex}
    monkeypatch.setattr(views, 'check_formula', check_formula)
    return asked


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user('someone', password='someone')


def test_the_url_is_named_and_under_maRDMOs_prefix():
    assert reverse('tex_check') == URL


def test_a_logged_in_user_gets_the_verdict(client, user, checked):
    client.force_login(user)
    response = client.post(URL, {'tex': r'\frac{a}{b}'})
    assert response.status_code == 200
    assert response.json() == {'state': 'valid', 'message': '', 'checked': r'\frac{a}{b}'}
    assert checked == [r'\frac{a}{b}']


def test_nobody_else_gets_it(db, client, checked):
    response = client.post(URL, {'tex': r'\frac{a}{b}'})
    # To the login, as every page of RDMO
    assert response.status_code == 302 and 'login' in response['Location']
    assert checked == []


def test_only_by_post_and_with_the_csrf_token(user, checked):
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    assert client.get(URL, {'tex': 'x'}).status_code == 405
    assert client.post(URL, {'tex': 'x'}).status_code == 403
    assert checked == []


@pytest.mark.parametrize('tex', ['', '   ', 'x' * (TEX_CHECK_MAX_LENGTH + 1)])
def test_no_formula_or_too_long(client, user, checked, tex):
    client.force_login(user)
    assert client.post(URL, {'tex': tex}).status_code == 400
    assert checked == []


def test_the_portals_verdict_through_the_view(client, user, portal):
    '''Recorded answers of the portal's TeX check (``tex_check_view``).'''
    portal('tex_check_view')
    client.force_login(user)
    # A shorthand only the checker knows: valid, with the checker's form to render
    valid = client.post(URL, {'tex': r'x \in \R'}).json()
    assert valid['state'] == 'valid' and r'\mathbb' in valid['checked']
    # An environment it does not support: its message and MaRDMO's explanation
    invalid = client.post(URL, {'tex': r'\begin{gather} a \end{gather}'}).json()
    assert invalid['state'] == 'invalid' and 'gather' in invalid['message']
    assert 'supported environments are aligned' in invalid['message']
