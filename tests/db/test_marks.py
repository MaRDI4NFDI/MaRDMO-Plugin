'''The red marks of the preview are exactly the problems of the checks (#152), the blue ones their hints (#167).

Every answer of a project of each catalog is deleted (and, if it has text,
blanked) once; then each problem of the checks must be red on its page and
each hint (what a MaRDI Portal item could have) blue, and nothing else may
be marked.  Answers of the same question are mutated once
(the first of them), so the test stays quick; the survey before #152 did all
of them (no difference).  The answers that name a tab are left out: deleting
one is deleting the tab, which RDMO does with all its answers.

The synthetic documentations (tools/synthetic) answer every question of
their catalog, so every question is deleted once.  white_2006 runs once
more in German: the marks are the German problems, and every section of a
problem is in the German catalog.

Offline: recorded portal answers; the TeX checker accepts every formula.
'''
import html
import re

import polib
import pytest
from django.db import transaction
from django.utils import translation
from django.template.loader import render_to_string

from MaRDMO import main
from MaRDMO.checks import Checks
from MaRDMO.constants import BASE_URI, CATALOG_TEMPLATE_MAP
from MaRDMO.problems import attach
from tests.db.conftest import select
from tests.db.test_export import imported
from tests.db.test_hydration import CASES
from tools.messages import CATALOG
from tools.synthetic.catalog import Catalog

MARK = re.compile(r'<strong class="mardmo-error">(.*?)</strong>', re.S)
HINT = re.compile(r'<strong class="mardmo-hint">(.*?)</strong>', re.S)
PROJECTS = [('white_2006', 'import', 'en'), ('si_model', 'select', 'en'), ('thomas_algorithm', 'select', 'en'),
            ('workflow', 'select', 'en'), ('white_2006', 'import', 'de'),
            # Every question of each catalog (tools/synthetic)
            ('synthetic_model', 'import', 'en'), ('synthetic_model_basics', 'import', 'en'),
            ('synthetic_algorithm', 'import', 'en'), ('synthetic_workflow', 'import', 'en')]
# Texts of the German catalog
GERMAN = {entry.msgid for entry in polib.pofile(str(CATALOG)) if entry.msgstr}


class Rollback(Exception):
    pass


def regions(page):
    '''{anchor: HTML of the page} of the rendered preview.'''
    starts = [(match.start(), match.group(1)) for match in re.finditer(r'<h2 id="(page-[^"]+)"', page)]
    ends = [match.start() for match in re.finditer(r'<h2 id="page-|<h1 ', page)]
    result = {}
    for start, anchor in starts:
        end = next((position for position in ends if position > start), len(page))
        result[anchor] = page[start:end]
    return result


def compare(documentation, language='en'):
    '''What is wrong with the marks of the preview of *documentation* in *language*, as a list of strings.'''
    with translation.override(language):
        return _compare(documentation, language)


def _compare(documentation, language):
    provider = main.MaRDMOExportProvider('wikibase', 'x', 'MaRDMO.main.MaRDMOExportProvider')
    provider.project, provider.snapshot = documentation, None
    answers, options = provider.get_post_data()
    slug = str(documentation.catalog).rsplit('/', 1)[1]
    problems = getattr(Checks(), main._CATALOG_PREPARE_MAP[slug][2])(
        project=documentation, data=answers, catalog=str(documentation.catalog))
    attach(answers, problems)
    page = render_to_string(CATALOG_TEMPLATE_MAP[slug], {'answers': answers, 'option': options, 'title': 'x'})
    wrong = []
    for problem in problems:
        if language == 'de' and problem.section not in GERMAN:
            wrong.append(f'section without German: {problem.section}')
    for pattern, colour, hint in ((MARK, 'red', False), (HINT, 'blue', True)):
        found = {anchor: [html.unescape(re.sub(r'<[^>]+>', '', mark)) for mark in pattern.findall(part)]
                 for anchor, part in regions(page).items()}
        expected = {}
        for problem in problems:
            if problem.hint == hint:
                expected.setdefault(problem.page.anchor, []).append(problem.message)
        for anchor in found.keys() | expected.keys():
            missing = sorted(set(expected.get(anchor, [])) - set(found.get(anchor, [])))
            extra = sorted(set(found.get(anchor, [])) - set(expected.get(anchor, [])))
            wrong += [f'{anchor}: not shown in {colour}: {message}' for message in missing]
            wrong += [f'{anchor}: {colour} without a {"hint" if hint else "problem"}: {message}' for message in extra]
        outside = len(pattern.findall(page)) - sum(len(marks) for marks in found.values())
        if outside:
            wrong.append(f'{outside} {colour} marks outside of the pages')
    return wrong


def mutations(documentation, questions):
    '''One answer per question (the first), deleted and, with text, blanked.

    Only answers of questions of the catalog (*questions*: their attribute
    URIs): the user cannot change the others (a publication's authors,
    what MaRDMO stores without a question).
    '''
    sections = {f'{BASE_URI}domain/{section}' for section in ('model', 'formulation', 'quantity', 'task', 'problem',
                'field', 'publication', 'algorithm', 'software', 'benchmark', 'workflow', 'processstep',
                'hardware', 'dataset')}
    seen = set()
    for value in documentation.values.filter(snapshot=None).select_related('attribute').order_by('id'):
        if value.attribute.uri in sections or value.attribute.uri in seen or value.attribute.uri not in questions:
            continue
        seen.add(value.attribute.uri)
        yield value, 'delete'
        if value.text:
            yield value, 'blank'


@pytest.mark.django_db
@pytest.mark.parametrize('name, how, language', PROJECTS)
def test_marks_are_the_problems_of_the_checks(name, how, language, project, portal, monkeypatch, questionnaire):
    monkeypatch.setattr('MaRDMO.tex_check.check_formulas', lambda formulas: {})
    monkeypatch.setattr('MaRDMO.checks.model.check_formulas', lambda formulas: {})
    if how == 'import':
        portal(f'export_{name}')
        documentation = imported(project, name)
    else:
        portal(name, f'export_portal_{name}')
        catalog, qkey, page, external_id, label, description = CASES[name]
        documentation = project(catalog)
        select(documentation, qkey, page, external_id, f'{label} ({description}) [{external_id.split(":")[0]}]')
    assert compare(documentation, language) == []
    wrong = []
    catalog = Catalog.read(questionnaire.path, str(documentation.catalog).rsplit('/', 1)[1])
    questions = {f'{BASE_URI}domain/{question.attribute}' for question in catalog.questions()}
    for value, how in list(mutations(documentation, questions)):
        path = value.attribute.uri.replace(f'{BASE_URI}domain/', '')
        try:
            with transaction.atomic():
                if how == 'delete':
                    value.delete()
                else:
                    value.text = ''
                    value.save()
                wrong += [f'{how} {path}: {line}' for line in compare(documentation, language)]
                raise Rollback
        except Rollback:
            pass
    assert wrong == []
