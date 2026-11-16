'''Build the synthetic documentations (tools/synthetic) and write them to tests/data/projects.

Opt-in, as it asks the MaRDI Portal, Wikidata and the citation services
(read-only, with a pause before each request)::

    BUILD=1 QUESTIONNAIRE=../MaRDMO-Questionnaire/catalog \\
        pytest tests/db/test_synthetic_build.py --force-enable-socket -s [-k model]

Each documentation is written as the interview writes it, on the test
database with the questionnaire of QUESTIONNAIRE.  Then the preview runs as
the user opens it: items on the MaRDI Portal already are reused ("Use this
item"), and nothing may be left that prevents the export, before it is
written as RDMO XML.  The IDs of new items are
derived from the documentation's name and a counter, so a build of the
same descriptions and portal data writes the same XML.
'''
import importlib
import itertools
import os
import uuid
from pathlib import Path

import pytest
from django.contrib.sites.models import Site
from rdmo.core.exports import prettify_xml
from rdmo.projects.models import Project
from rdmo.projects.renderers import XMLRenderer
from rdmo.projects.serializers.export import ProjectSerializer
from rdmo.questions.models import Catalog as RDMOCatalog

from MaRDMO import main, pipeline
from MaRDMO.duplicates import preview_duplicates, reuse
from MaRDMO.problems import report_lines
from tools.synthetic.catalog import Catalog
from tools.synthetic.writer import SENT, Documentation, polite

pytestmark = pytest.mark.skipif(os.environ.get('BUILD') != '1', reason='builds with BUILD=1 (see the module)')

PROJECTS = Path(__file__).parents[1] / 'data' / 'projects'
BUILDS = {  # name: (catalog, description module)
    'synthetic_model': ('mardmo-model-catalog', 'tools.synthetic.model'),
    'synthetic_model_basics': ('mardmo-model-basics-catalog', 'tools.synthetic.model_basics'),
    'synthetic_algorithm': ('mardmo-algorithm-catalog', 'tools.synthetic.algorithm'),
    'synthetic_workflow': ('mardmo-interdisciplinary-workflow-catalog', 'tools.synthetic.workflow'),
}


def duplicates(project):
    '''Answers stored twice in one place (attribute, set, collection index): the interview never writes these.'''
    seen, twice = {}, []
    for value in project.values.filter(snapshot=None).select_related('attribute').order_by('pk'):
        place = (value.attribute.uri.rsplit('/domain/', 1)[-1], value.set_prefix, value.set_index,
                 value.collection_index)
        if place in seen:
            twice.append((place, seen[place], value.text or value.external_id))
        seen[place] = value.text or value.external_id
    return twice


def preview(project):
    '''What the preview finds, as the user opens it before the export: ``(duplicates, gate)``.

    The preview looks up the citations of new publications (and writes them
    into the documentation), the items that are on the MaRDI Portal already,
    and runs the checks and the export's own checks (``pipeline.run``).
    '''
    provider = main.MaRDMOExportProvider('wikibase', 'x', 'MaRDMO.main.MaRDMOExportProvider')
    provider.project, provider.snapshot = project, None
    answers, _ = provider.get_post_data('preview')
    _, prepare_class, check = main._CATALOG_PREPARE_MAP[str(project.catalog).rsplit('/', 1)[1]]
    found = preview_duplicates(project, answers, prepare_class())
    return found, pipeline.run(project, answers, prepare_class, check, preview=True, duplicates=found)


def use_portal_items(project):
    '''Choose "Use this item" for every item of the preview that is on the MaRDI Portal already, as the user does.

    Items the preview offers no reuse for (another kind of item on the
    portal) stop the build: the description must choose another item.
    '''
    for _ in range(5):
        found, gate = preview(project)
        if not found.rows:
            return gate
        refused = [row for row in found.rows if row.action != 'reuse' or not row.portal_label]
        assert not refused, '\n'.join(f'{row.duplicate.item["Name"]}: {row.action} {row.duplicate.qid} {row.reasons}'
                                       for row in refused)
        for row in found.rows:
            reuse(project, row.duplicate, row.portal_label, row.portal_description)
    raise AssertionError('items on the MaRDI Portal remain after five rounds of "Use this item"')


@pytest.mark.parametrize('name', sorted(BUILDS))
def test_build(name, db, monkeypatch, django_db_setup):
    catalog_name, module = BUILDS[name]
    try:
        describe = importlib.import_module(module).describe
    except ModuleNotFoundError:
        pytest.skip(f'{module} is not written yet')
    counter = itertools.count(1)
    monkeypatch.setattr('MaRDMO.ids.new_user_id',
                        lambda: f'user:{uuid.uuid5(uuid.NAMESPACE_URL, f"mardmo/{name}/{next(counter)}")}')
    polite(monkeypatch)
    SENT.clear()
    project = Project.objects.create(title=name.replace('_', ' '), site=Site.objects.get_current(),
                                     catalog=RDMOCatalog.objects.get(uri__endswith=catalog_name))
    doc = Documentation(project, Catalog.read(os.environ['QUESTIONNAIRE'], catalog_name))
    describe(doc)
    assert not duplicates(project), '\n'.join(map(str, duplicates(project)))
    gate = use_portal_items(project)
    print(f'\n{name}: {project.values.count()} answers, {len(SENT)} requests')
    if gate.problems and os.environ.get('BUILD_PAGES'):
        for section in sorted({problem.page.section for problem in gate.problems if problem.page}):
            for tab in doc.tabs(section):
                print(f'  {section} {tab.index}: {tab.id} {tab.label}')
    assert not gate.unreachable, gate.unreachable
    assert gate.clear, '\n'.join(report_lines(gate.problems))
    xml = prettify_xml(XMLRenderer().render(ProjectSerializer(project).data))
    (PROJECTS / f'{name}.xml').write_text(xml.decode() if isinstance(xml, bytes) else xml, encoding='utf-8')
