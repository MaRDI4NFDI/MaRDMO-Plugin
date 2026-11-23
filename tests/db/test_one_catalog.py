'''MaRDMO with one catalog only: the others are not needed (#198).

The catalogs register themselves (MaRDMO.core.catalogs); lint-imports
checks that no catalog imports another.  These tests check it at run time:
with only one catalog package registered, as an installation with only that
catalog would have it, the app's questions, the router's tables, the checks
and the export know that catalog only, and every documentation of it
exports exactly as with all catalogs (the golden files of
tests/db/test_export.py).  The other catalogs' modules are never imported
anew; they stay loaded in the test run, which is what lint-imports covers.
'''
from importlib import import_module

import pytest
from django.apps import apps
from rdmo.core.xml import get_ns_map, get_uri, read_xml_file
from rdmo.projects.models import Value
from rdmo.projects.signals import value_created

from MaRDMO import router
from MaRDMO.sources import http
from MaRDMO.builders import build_post_delete_handler_set, build_post_save_handler_set, build_presave_validator_map
from MaRDMO.core import catalogs as registry
from MaRDMO.core.catalogs import CATALOG_PACKAGES, catalogs, documenting, registrations
from MaRDMO.core.config import get_questions
from MaRDMO.core.constants import BASE_URI
from MaRDMO.project.writes import value_editor
from tests.db.test_export import DATA, DOCUMENTATIONS, compare, export, imported


def package_of(catalog_name):
    '''The catalog package whose catalog.py declares the catalog *catalog_name*.'''
    return next(package for package in CATALOG_PACKAGES
                if any(catalog.name == catalog_name
                       for catalog in import_module(f'MaRDMO.{package}.catalog').REGISTRATION.catalogs))


def catalog_of_documentation(name):
    '''The catalog of the RDMO project export tests/data/projects/<name>.xml.'''
    root = read_xml_file(DATA / 'projects' / f'{name}.xml')
    return get_uri(root.find('catalog'), get_ns_map(root)).rsplit('/', 1)[1]


@pytest.fixture
def only(monkeypatch):
    '''Register the catalog package *package* only: ``only('model')``.

    As an installation with only that catalog: the registry, the questions
    of the app (MaRDMOConfig.load_questions) and the router's tables are
    built anew from it.  Afterwards all catalogs are registered again.
    '''
    config = apps.get_app_config('MaRDMO')

    def register(package):
        monkeypatch.setattr(registry, 'CATALOG_PACKAGES', (package,))
        registrations.cache_clear()
        monkeypatch.setattr(config, 'questions', config.load_questions())
        monkeypatch.setattr(router, 'HANDLER_MAP', build_post_save_handler_set())
        monkeypatch.setattr(router, 'DELETE_HANDLER_MAP', build_post_delete_handler_set())
        monkeypatch.setattr(router, 'PRESAVE_VALIDATOR_MAP', build_presave_validator_map())
    yield register
    registrations.cache_clear()


@pytest.mark.parametrize('package', CATALOG_PACKAGES)
def test_only_the_registered_catalog_is_known(package, only):
    only(package)
    own = {catalog.name for catalog in import_module(f'MaRDMO.{package}.catalog').REGISTRATION.catalogs}
    question_sets = {name for registration in registrations() for name in registration.questions}
    assert set(catalogs()) == own
    assert set(apps.get_app_config('MaRDMO').questions) == {'publication'} | question_sets
    for table in (router.HANDLER_MAP, router.DELETE_HANDLER_MAP, router.PRESAVE_VALIDATOR_MAP):
        assert set(table) <= set(documenting())


@pytest.mark.parametrize('name', DOCUMENTATIONS)
def test_a_documentation_exports_as_with_all_catalogs(name, only, project, portal):
    only(package_of(catalog_of_documentation(name)))
    portal(f'export_{name}')
    compare(name, export(imported(project, name)))


def test_an_answer_of_another_catalog_is_left_alone(only, project, monkeypatch):
    '''Selecting a portal algorithm in an algorithm documentation runs no handler: nothing is asked or filled in.'''
    # The questions of the algorithm, read before: with the model only, MaRDMO does not know them
    questions = get_questions('algorithm')['Algorithm']
    only('model')

    def no_request():
        raise AssertionError('a handler sent a request')
    monkeypatch.setattr(http, 'http_session', no_request)
    documentation = project('mardmo-algorithm-catalog')
    value_editor(project=documentation, uri=f'{BASE_URI}{questions["uri"]}', info={'text': 'Algorithm 1'})
    value, _ = value_editor(project=documentation, uri=f'{BASE_URI}{questions["ID"]["uri"]}',
                            info={'text': 'Thomas algorithm (algorithm)', 'external_id': 'mardi:Q6825618'})
    value_created.send(sender=Value, instance=value)
    assert documentation.values.count() == 2              # the page and its ID: nothing filled in
