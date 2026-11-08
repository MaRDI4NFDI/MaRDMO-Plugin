'''Selecting a portal or Wikidata item fills its pages (MaRDMO's handlers), and the preview reads them.

The answers of the portal and Wikidata are recorded (tests/recordings.py);
PAGES are the items the selected item links to on the portal when recorded.
'''
import collections

import pytest
from django.template.loader import render_to_string

from MaRDMO import main
from MaRDMO.constants import BASE_URI
from MaRDMO.getters import get_item_url
from rdmo.options.models import OptionSet
from rdmo.projects.models import Value
from rdmo.projects.signals import value_updated

from tests.db.conftest import select

CASES = {  # recording: (catalog, questions, page, ID, label, description)
    'si_model': ('mardmo-model-catalog', 'model', 'Mathematical Model', 'mardi:Q6675167',
                 'susceptible infectious model',
                 'continuous-time model for the spreading of infectious diseases considering susceptible '
                 'and infectious individuals'),
    'action_potential_model': ('mardmo-model-catalog', 'model', 'Mathematical Model', 'mardi:Q6674954',
                               'action potential propagation model', 'propagation of the action potential'),
    'wikidata_quantity': ('mardmo-model-catalog', 'model', 'Quantity', 'wikidata:Q3686031', 'concentration',
                          'type of physical property; the abundance of a constituent divided by the total '
                          'volume of a mixture'),
    'thomas_algorithm': ('mardmo-algorithm-catalog', 'algorithm', 'Algorithm', 'mardi:Q6825618',
                         'Thomas algorithm (tridiagonal matrix algorithm) for O(n) solution of tridiagonal systems',
                         'Performs a forward sweep eliminating subdiagonal entries followed by back substitution, '
                         'exploiting the tridiagonal pattern for linear-time work and storage. Stable for '
                         'diagonally dominant or SPD problems; otherwise pivoting may be needed.'),
    'publication': ('mardmo-model-catalog', 'publication', 'Publication', 'mardi:Q2643268',
                    'Heroin epidemics, treatment and ODE modelling', 'scientific article; zbMATH DE number 5182347'),
    'workflow': ('mardmo-interdisciplinary-workflow-catalog', 'workflow', 'Workflow', 'mardi:Q6032641',
                 'Logical Data Analysis for Egyptian Objects', 'Do Destruction Patterns Follow Specific Rules?'),
}


# The pages each selection fills: {section: IDs}
PAGES = {
    'si_model': {
        'model': {'mardi:Q6675167'}, 'field': {'mardi:Q6684705'}, 'problem': {'mardi:Q6684648'},
        'formulation': {'mardi:Q6674290', 'mardi:Q6674295', 'mardi:Q6674410'},
        'quantity': {'mardi:Q6673881', 'mardi:Q6673795', 'mardi:Q6673882', 'mardi:Q6673793', 'mardi:Q6534304'},
        'publication': {'mardi:Q1340492', 'mardi:Q2209172'}},
    'action_potential_model': {
        'model': {'mardi:Q6674954'}, 'formulation': {'mardi:Q6674596'}, 'publication': {'mardi:Q6668629'},
        'quantity': {'mardi:Q6674060', 'mardi:Q6674035', 'mardi:Q6674069', 'mardi:Q6673938', 'mardi:Q6534304',
                     'mardi:Q6674117', 'mardi:Q6673702', 'mardi:Q7360709'}},
    'wikidata_quantity': {'quantity': {'wikidata:Q3686031'}},
    'publication': {'publication': {'mardi:Q2643268'}},
    'thomas_algorithm': {
        'algorithm': {'mardi:Q6825618'}, 'problem': {'mardi:Q6825985'},
        'software': {'mardi:Q6825400', 'mardi:Q6825551', 'mardi:Q6825690'},
        'publication': {'mardi:Q1591199', 'mardi:Q3835990', 'mardi:Q6824614', 'mardi:Q6825173'}},
    'workflow': {
        'workflow': {'mardi:Q6032641'}, 'algorithm': {'mardi:Q6032636'}, 'hardware': {'mardi:Q6487066'},
        'software': {'mardi:Q6230812'},
        'dataset': {'mardi:Q6486605', 'mardi:Q6486606', 'mardi:Q6486608', 'mardi:Q6032638', 'mardi:Q6032639',
                    'mardi:Q6486612'},
        'processstep': {'mardi:Q6486604', 'mardi:Q6486607', 'mardi:Q6486609', 'mardi:Q6486610', 'mardi:Q6486611'}},
}


def dump(project):
    return sorted((v.attribute.uri.replace(BASE_URI, ''), v.set_prefix, v.set_index, v.collection_index or 0,
                   v.text or '', v.external_id or '', v.option.uri.rsplit('/', 1)[1] if v.option else '')
                  for v in project.values.filter(snapshot=None).select_related('attribute', 'option'))


def pages(values):
    """{section: [ID of each page]} from the pages' ID answers."""
    result = collections.defaultdict(list)
    for attribute, set_prefix, _, _, _, external_id, _ in values:
        parts = attribute.split('/')
        if set_prefix == '' and len(parts) == 3 and parts[2] == 'id':
            result[parts[1]].append(external_id)
    return result


def preview(project):
    provider = main.MaRDMOExportProvider('wikibase', 'x', 'MaRDMO.main.MaRDMOExportProvider')
    provider.project, provider.snapshot = project, None
    answers, options = provider.get_post_data('preview')
    html = render_to_string(main.CATALOG_TEMPLATE_MAP[project.catalog.uri.rsplit('/', 1)[1]], {
        'answers': answers, 'option': options, 'title': project.title,
        'mardiURI': get_item_url('mardi'), 'wikidataURI': get_item_url('wikidata')})
    return answers, html


@pytest.fixture(params=sorted(CASES))
def hydrated(request, project, portal):
    """The project after selecting the item of the recording, and the recording's name."""
    portal(request.param)
    catalog, qkey, page, external_id, label, description = CASES[request.param]
    model = project(catalog)
    select(model, qkey, page, external_id, f'{label} ({description}) [{external_id.split(":")[0]}]')
    return request.param, model


def test_selection_fills_a_page_for_every_linked_item(hydrated):
    name, model = hydrated
    found = pages(dump(model))
    assert {section: set(ids) for section, ids in found.items()} == PAGES[name]
    assert all(len(ids) == len(set(ids)) for ids in found.values()), 'an item got two pages'


def test_every_page_has_a_name(hydrated):
    _, model = hydrated
    values = dump(model)
    names = collections.Counter(attribute.split('/')[1] for attribute, *_, text, _, _ in values
                                if attribute.count('/') == 2 and attribute.endswith('/name') and text)
    assert names == collections.Counter({section: len(ids) for section, ids in pages(values).items()})


def test_collections_have_no_gaps(hydrated):
    '''References are checkboxes: see test_references_are_at_the_position_of_their_option.'''
    _, model = hydrated
    by_set = collections.defaultdict(list)
    for attribute, set_prefix, set_index, collection_index, *_ in dump(model):
        if not attribute.endswith('/reference'):
            by_set[(attribute, set_prefix, set_index)].append(collection_index)
    assert {key: sorted(indices) for key, indices in by_set.items()
            if sorted(indices) != list(range(len(indices)))} == {}


def test_references_are_at_the_position_of_their_option(hydrated):
    '''RDMO's checkbox widget stores a checked option at its position in the option set.'''
    _, model = hydrated
    references = model.values.filter(attribute__uri__endswith='/reference').select_related('attribute', 'option')
    for value in references:
        section = value.attribute.uri.split('/')[-2]
        optionset = OptionSet.objects.get(uri__endswith=f'/{section}-reference')
        assert value.collection_index == optionset.elements.index(value.option), value.option.uri


def test_publication_name_is_on_the_publication_tab(hydrated):
    '''Like the name of a publication found by its DOI, not below tab 0 (set_prefix "0").'''
    _, model = hydrated
    names = model.values.filter(attribute__uri=f'{BASE_URI}domain/publication/name')
    tabs = model.values.filter(attribute__uri=f'{BASE_URI}domain/publication')
    assert sorted(names.values_list('set_prefix', 'set_index')) == [('', tab.set_index) for tab in tabs]


def test_selecting_again_changes_nothing(hydrated):
    _, model = hydrated
    before = dump(model)
    for value in model.values.filter(attribute__uri__endswith='/id', set_prefix='').exclude(external_id=''):
        if value.attribute.uri.count('/') == 5:  # .../domain/<section>/id
            value_updated.send(sender=Value, instance=value)
    assert dump(model) == before


def test_preview_shows_every_page(hydrated):
    name, model = hydrated
    answers, html = preview(model)
    shown = {section: len(answers.get(section, {})) for section in PAGES[name]}
    assert shown == {section: len(ids) for section, ids in PAGES[name].items()}
    assert CASES[name][4] in html


def test_preview_reads_back_what_it_wrote(hydrated):
    """A second preview finds the project as the first one left it."""
    _, model = hydrated
    first, _ = preview(model)
    values = dump(model)
    second, _ = preview(model)
    assert second == first
    assert dump(model) == values


def test_wikidata_quantity_keeps_its_qudt_id_without_class(project, portal):
    """Concentration (Q3686031) is no instance of quantity or quantity kind on Wikidata (#95)."""
    portal('wikidata_quantity')
    model = project('mardmo-model-catalog')
    *_, label, description = CASES['wikidata_quantity']
    select(model, 'model', 'Quantity', 'wikidata:Q3686031', f'{label} ({description}) [wikidata]')
    reference = model.values.get(attribute__uri=f'{BASE_URI}domain/quantity/reference')
    assert (reference.option.uri.rsplit('/', 1)[1], reference.text) == ('qudt-quantitykind-id', 'Concentration')
    assert not model.values.filter(attribute__uri=f'{BASE_URI}domain/quantity/is-quantity-or-quantity-kind').exists()
