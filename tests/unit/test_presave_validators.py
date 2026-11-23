'''What the interview refuses while the user types (the pre-save validators, #138).

RDMO saves an answer while it is being typed, so a validator may only refuse
what can never become valid by typing on: ``10.`` and ``https:`` are
accepted, a pasted link instead of a DOI or a comma in a size are not.  Each
validator reacts only to its own options.  The complete rules (preview,
checks, export) are in test_validators.py; that the interview calls these
validators, in tests/db/test_router.py.
'''
from types import SimpleNamespace

import pytest
from rest_framework.exceptions import ValidationError

from MaRDMO.components import validators
from MaRDMO.core.config import get_options

OPTIONS = get_options()


def answer(option, text):
    return SimpleNamespace(option=SimpleNamespace(uri=OPTIONS[option]) if option else None, text=text)


def refused(validator, option, text):
    '''The message *validator* refuses the answer with, or ``None`` if it accepts it.'''
    try:
        validator(answer(option, text))
    except ValidationError as error:
        return str(error.detail['text'][0])
    return None


@pytest.mark.parametrize('text', ['1', '10', '10.', '10.1234', '10.1234/', '10.1234/xyz.5', ' 10.1000/x '])
def test_a_doi_while_it_is_typed(text):
    assert refused(validators.validate_doi, 'DOI', text) is None


@pytest.mark.parametrize('text, message', [
    ('https://doi.org/10.1000/x', 'not the link'),
    ('doi:10.1000/x', 'not the link'),
    ('11.1000/x', 'Invalid DOI'),
    ('10.10 00/x', 'Invalid DOI'),
])
def test_a_doi_that_cannot_become_one(text, message):
    assert message in refused(validators.validate_doi, 'DOI', text)


def test_the_doi_of_a_data_set_to_publish():
    '''"Yes, published with DOI" (YesText) takes a DOI as well.'''
    assert 'Invalid DOI' in refused(validators.validate_doi, 'YesText', 'eleven')


@pytest.mark.parametrize('text', ['h', 'https:', 'https://exa', 'https://example.org/a'])
def test_a_url_while_it_is_typed(text):
    assert refused(validators.validate_url, 'DESCRIPTION_URL', text) is None


@pytest.mark.parametrize('option, text', [
    ('DESCRIPTION_URL', 'ftp://example.org'),          # a web page: http(s) only
    ('URL', 'javascript:alert(1)'),
    ('DESCRIPTION_URL', 'https://exa mple.org'),        # a space inside
    ('SOURCECODE_URL', 'gopher://example.org'),
])
def test_a_url_that_cannot_become_one(option, text):
    assert refused(validators.validate_url, option, text)


def test_a_repository_may_use_git_and_ssh():
    assert refused(validators.validate_url, 'SOURCECODE_URL', 'git://example.org/repo') is None
    assert refused(validators.validate_url, 'DESCRIPTION_URL', 'git://example.org/repo')


@pytest.mark.parametrize('text, accepted', [('12345', True), ('12a', False), ('1.5', False)])
def test_a_swmath_id(text, accepted):
    assert (refused(validators.validate_swmath, 'SWMATH', text) is None) == accepted


@pytest.mark.parametrize('option, text, message', [
    ('items', '250', None), ('items', '0', 'whole number'), ('items', '2.5', 'whole number'),
    ('megabyte', '1.', None), ('megabyte', '12.75', None),
    ('megabyte', '1,5', 'dot as decimal separator'), ('megabyte', '1e3', 'as a number'),
])
def test_a_data_size(option, text, message):
    found = refused(validators.validate_data_size, option, text)
    assert (found is None) if message is None else (message in found)


@pytest.mark.parametrize('text, accepted', [('2', True), ('203', True), ('2030', True), ('20301', False), ('20a', False)])
def test_an_archival_year_while_it_is_typed(text, accepted):
    assert (refused(validators.validate_archive_year, 'YesText', text) is None) == accepted


@pytest.mark.parametrize('text, accepted', [('4', True), ('', True), ('04', False), ('0', False), ('2.5', False)])
def test_a_count(text, accepted):
    assert (refused(validators.validate_count, None, text) is None) == accepted


@pytest.mark.parametrize('validator, option, text', [
    (validators.validate_doi, 'URL', 'not a doi'),            # another option: not a DOI
    (validators.validate_url, 'DOI', 'not a url'),
    (validators.validate_swmath, 'DOI', 'not a number'),
    (validators.validate_archive_year, 'No', 'whenever'),
    (validators.validate_data_size, None, '1,5'),            # no unit chosen yet
    (validators.validate_doi, 'DOI', ''),                    # nothing typed
])
def test_each_validator_reacts_to_its_own_options_only(validator, option, text):
    assert refused(validator, option, text) is None


def test_a_reference_is_checked_by_its_option():
    '''One reference question, several options: DOI, URL and swMATH ID each by its own rule.'''
    assert 'Invalid DOI' in refused(validators.validate_reference, 'DOI', 'eleven')
    assert refused(validators.validate_reference, 'DESCRIPTION_URL', 'ftp://example.org')
    assert refused(validators.validate_reference, 'SWMATH', 'abc')
    assert refused(validators.validate_reference, 'SWMATH', '4384') is None
