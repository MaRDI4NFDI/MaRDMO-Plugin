'''MaRDMO's catalogs (MaRDMO.catalogs, #138, #198): each declared by its package, complete, and what it names exists.

A new catalog is a package with its declaration (``catalog.py``) and the rows
of the tables keyed by catalog; these tests name what is missing.
'''
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from django.template.loader import get_template

from MaRDMO.checks.base import ChecksBase
from MaRDMO.catalogs import CATALOG_PACKAGES, SEARCH, catalog_of, catalogs, documenting, registrations
from MaRDMO.constants import BASE_URI
from MaRDMO.model.catalog import CATALOG_MODEL_BASICS_NAME, CATALOG_MODEL_NAME
from MaRDMO.getters import get_questions
from MaRDMO.publication.constants import ROUTING
from tests.conftest import questionnaire  # noqa: F401

DC = '{http://purl.org/dc/elements/1.1/}uri'
PACKAGE = Path(__file__).resolve().parents[2] / 'MaRDMO'


def test_every_catalog_of_the_questionnaire_has_its_entry(questionnaire):  # noqa: F811
    names = {ET.parse(path).getroot().find('catalog').get(DC).rsplit('/', 1)[-1]
             for path in Path(questionnaire.path).glob('mardmo-*-catalog.xml')}
    assert names == set(catalogs())


def test_every_package_declares_its_catalogs_once():
    names = [catalog.name for registration in registrations() for catalog in registration.catalogs]
    assert len(registrations()) == len(CATALOG_PACKAGES) and len(names) == len(set(names))
    for registration in registrations():
        assert registration.catalogs
        for path in registration.questions.values():
            assert (PACKAGE / path).is_file(), path


@pytest.mark.parametrize('name', sorted(catalogs()))
def test_what_an_entry_names_exists(name):
    catalog = catalogs()[name]
    assert catalog.uri == f'{BASE_URI}questions/{name}'
    get_template(catalog.template)
    if catalog.documents:
        assert get_questions(catalog.questions)
        assert hasattr(catalog.prepare_class, 'export')
        assert issubclass(catalog.checks_class, ChecksBase)
    else:
        assert catalog.kind == SEARCH and not catalog.worker


def test_the_tables_keyed_by_catalog_have_a_row_for_each():
    from MaRDMO.builders import (build_post_delete_handler_set, build_post_save_handler_set,
                                 build_presave_validator_map)
    for table in (build_post_save_handler_set(), build_post_delete_handler_set(), build_presave_validator_map(),
                  ROUTING):
        assert set(table) == set(documenting())


def test_a_catalog_is_found_by_project_catalog_or_uri():
    model = catalogs()[CATALOG_MODEL_NAME]
    assert catalog_of(model.uri) is model and catalog_of(CATALOG_MODEL_NAME) is model

    class Project:
        catalog = catalogs()[CATALOG_MODEL_BASICS_NAME].uri
    assert catalog_of(Project()).subset
    assert catalog_of(f'{BASE_URI}questions/another-catalog') is None and catalog_of(None) is None
