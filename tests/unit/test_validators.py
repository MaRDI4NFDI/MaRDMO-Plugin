'''The checks behind the validators and the documentation check.'''
import pytest

from MaRDMO import validators as v


@pytest.mark.parametrize('doi, problem', [
    ('10.1000/xyz123', None),
    ('', None),
    ('https://doi.org/10.1000/xyz', 'not the link'),
    ('doi:10.1000/xyz', 'not the link'),
    ('abc', 'must have the form'),
    ('10.1000/ x', 'must have the form'),
])
def test_doi(doi, problem):
    assert (v.doi_problem(doi) is None) if problem is None else (problem in v.doi_problem(doi))


@pytest.mark.parametrize('url, problem', [
    ('https://example.org', None),
    ('example.org', 'must start with'),
    ('ftp://example.org', 'must start with'),
    ('javascript:alert(1)', 'must start with'),
    ('http://', 'needs a domain'),
    ('https://ex ample.org', 'spaces'),
])
def test_url(url, problem):
    assert (v.url_problem(url) is None) if problem is None else (problem in v.url_problem(url))


def test_repository_urls_may_use_other_schemes():
    assert v.url_problem('git://example.org/repo', schemes=v.REPOSITORY_URL_SCHEMES) is None


@pytest.mark.parametrize('value, problem', [('7554', None), (' 12 ', None), ('abc', 'must be a number')])
def test_swmath(value, problem):
    assert (v.swmath_problem(value) is None) if problem is None else (problem in v.swmath_problem(value))


@pytest.mark.parametrize('value, problem', [('2030', None), ('', None), ('20a0', '4-digit year')])
def test_archive_year(value, problem):
    assert (v.archive_year_problem(value) is None) if problem is None else (problem in v.archive_year_problem(value))


@pytest.mark.parametrize('value, problem', [
    ('3', None), ('', None), ('0', 'at least 1'), ('-1', 'whole number'), ('2.5', 'whole number'), ('x', 'whole number'),
])
def test_count(value, problem):
    assert (v.count_problem(value) is None) if problem is None else (problem in v.count_problem(value))


@pytest.mark.parametrize('value, integer, problem', [
    ('1.5', False, None), ('1.5', True, 'whole number'), ('-2', False, 'must be a number'),
])
def test_size(value, integer, problem):
    result = v.size_problem(value, integer=integer)
    assert (result is None) if problem is None else (problem in result)


@pytest.mark.parametrize('description, problem', [
    ('a model of traffic', None),
    ('', 'missing'),
    ('x' * (v.SHORT_DESCRIPTION_MAX_LENGTH + 1), 'too_long'),
    ('Traffic Model', 'same_as_name'),
])
def test_short_description(description, problem):
    assert v.short_description_problem(description, 'Traffic Model') == problem


@pytest.mark.parametrize('tex, problem', [
    ('a + b', False),
    ('a % comment', False),          # one line: the comment hides nothing
    ('a \\% b\n+ c', False),         # a percent sign
    ('a % comment\n+ b', True),      # joined for the export, "+ b" would be commented out
])
def test_formula_comment(tex, problem):
    assert (v.formula_comment_problem(tex) is not None) == problem


def test_formula_is_put_on_one_line():
    assert v.normalize_formula('  a\n+ b  ') == 'a + b'


@pytest.mark.parametrize('formula, expected', [
    ('a \\equiv b', True), ('<mo>≡</mo>', True), ('<mo>&#x2261;</mo>', True), ('a = b', False),
])
def test_equivalence_sign(formula, expected):
    assert v.has_equivalence_sign(formula) is expected
