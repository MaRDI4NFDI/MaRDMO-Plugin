'''MaRDMO's catalog table (MaRDMO.catalogs, #138): complete, and what it names exists.

A new catalog needs its entry and the rows of the tables keyed by catalog;
these tests name what is missing.
'''
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from django.template.loader import get_template

from MaRDMO.catalogs import CATALOGS, DOCUMENTING, SEARCH, catalog_of
from MaRDMO.checks import Checks
from MaRDMO.constants import BASE_URI, CATALOG_MODEL_BASICS_NAME, CATALOG_MODEL_NAME
from MaRDMO.getters import get_questions
from MaRDMO.publication.constants import ROUTING
from tests.conftest import questionnaire  # noqa: F401

DC = '{http://purl.org/dc/elements/1.1/}uri'


def test_every_catalog_of_the_questionnaire_has_its_entry(questionnaire):  # noqa: F811
    names = {ET.parse(path).getroot().find('catalog').get(DC).rsplit('/', 1)[-1]
             for path in Path(questionnaire.path).glob('mardmo-*-catalog.xml')}
    assert names == set(CATALOGS)


@pytest.mark.parametrize('name', sorted(CATALOGS))
def test_what_an_entry_names_exists(name):
    catalog = CATALOGS[name]
    assert catalog.uri == f'{BASE_URI}questions/{name}'
    get_template(catalog.template)
    if catalog.documents:
        assert get_questions(catalog.questions)
        assert hasattr(catalog.prepare_class, 'export')
        assert callable(getattr(Checks(), catalog.check))
    else:
        assert catalog.kind == SEARCH and not catalog.worker


def test_the_tables_keyed_by_catalog_have_a_row_for_each():
    from MaRDMO.builders import (build_post_delete_handler_set, build_post_save_handler_set,
                                 build_presave_validator_map)
    for table in (build_post_save_handler_set(), build_post_delete_handler_set(), build_presave_validator_map(),
                  ROUTING):
        assert set(table) == set(DOCUMENTING)


def test_a_catalog_is_found_by_project_catalog_or_uri():
    model = CATALOGS[CATALOG_MODEL_NAME]
    assert catalog_of(model.uri) is model and catalog_of(CATALOG_MODEL_NAME) is model

    class Project:
        catalog = CATALOGS[CATALOG_MODEL_BASICS_NAME].uri
    assert catalog_of(Project()).subset
    assert catalog_of(f'{BASE_URI}questions/another-catalog') is None and catalog_of(None) is None
