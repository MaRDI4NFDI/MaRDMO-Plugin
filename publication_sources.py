"""Publications through every citation source: what each one gives, preview against payload.

MaRDMO looks a DOI up on the MaRDI Portal and Wikidata, then on Crossref,
DataCite, zbMATH and doi.org, and uses the first source that knows it
(publication/utils.py).  To compare the sources on the same papers, each DOI
of items.json "publication_sources" runs in these configurations:

- all:        every source, as in the interview
- mardi, wikidata, crossref, datacite, zbmath, doi:
              only this source; the others answer "not known"

The sources are switched off in this process only (query_sparql_pool for the
MaRDI Portal and Wikidata, the get_*_data functions for the others); the
matching of authors and journal with the MaRDI Portal and Wikidata afterwards
stays as it is.  Each run fills a project with a model of the user's own and
the publication (relation "documents"), renders the preview and builds the
payload (nothing is posted).  Per run, results/<OUT>/<number>-<config>.json and
.html hold the sources that knew the DOI, the publication answers, payload
and preview, for preview_compare.py and publication_report.py.

Environment: ITEMS (the list in items.json, default publication_sources),
CONFIGS (comma-separated, default all of them), LIMIT, ONLY (comma-separated
numbers of DOIs), OUT (default results/<ITEMS with - for _>).
"""
import datetime, json, os, sys, traceback
HERE_ = os.path.expanduser(os.environ.get('DEV_TESTS', '~/Work/MaRDMO-Plugin/dev-tests'))
sys.path.insert(0, HERE_)
ITEMS = os.environ.get('ITEMS', 'publication_sources')
os.environ['OUT'] = os.environ.get('OUT') or os.path.join(HERE_, 'results', ITEMS.replace('_', '-'))
from common import *  # noqa: F401,F403
from preview_edits import answer, new_item, own, MARDMO, DOI_OPTION
from preview_payload import preview_and_payload, out
from django.core.cache import cache
import MaRDMO
import MaRDMO.publication.utils as pub_utils
import MaRDMO.publication.worker as pub_worker

TITLE = 'TEMP publication sources'
SPARQL_SOURCES = ('mardi', 'wikidata')
API_SOURCES = {'crossref': 'get_crossref_data', 'datacite': 'get_datacite_data',
               'zbmath': 'get_zbmath_data', 'doi': 'get_doi_data'}
CONFIGS = ['all', *SPARQL_SOURCES, *API_SOURCES]
MODEL = ('Test model for publications', 'model the publication documents')

state = {'config': 'all', 'found': None}
_real_pool = pub_utils.query_sparql_pool
_real_api = {name: getattr(pub_utils, name) for name in API_SOURCES.values()}
_real_get_citation = pub_utils.get_citation


def _pool(queries, *args, **kwargs):
    """Citation lookup on the MaRDI Portal and Wikidata, with switched-off sources answering 'not known'."""
    config = state['config']
    results = _real_pool(queries, *args, **kwargs)
    keep = SPARQL_SOURCES if config == 'all' else (config,)
    return {key: (value if key in keep else []) for key, value in results.items()}


def _api(source):
    def call(doi):
        return _real_api[API_SOURCES[source]](doi) if state['config'] in ('all', source) else None
    return call


def _get_citation(doi):
    """Record which sources knew the DOI (the result the preview uses)."""
    result = _real_get_citation(doi)
    state['found'] = {key: bool(value) for key, value in (result or {}).items() if key != 'orcid'}
    return result


pub_utils.query_sparql_pool = _pool
for source, name in API_SOURCES.items():
    setattr(pub_utils, name, _api(source))
pub_utils.get_citation = _get_citation
pub_worker.get_citation = _get_citation      # imported by name there


if __name__ in ('__main__', 'django.core.management.commands.shell'):
    all_dois = json.load(open(os.path.join(HERE, 'items.json')))[ITEMS]
    dois = list(all_dois)
    if os.environ.get('ONLY'):
        dois = [d for n, d in enumerate(dois, 1) if str(n) in os.environ['ONLY'].split(',')]
    if os.environ.get('LIMIT'):
        dois = dois[:int(os.environ['LIMIT'])]
    configs = os.environ.get('CONFIGS', ','.join(CONFIGS)).split(',')
    print('code from', MaRDMO.__file__, '->', out, f'| {len(dois)} DOIs x {len(configs)} configurations')
    try:
        for entry in dois:
            number = all_dois.index(entry) + 1
            for config in configs:
                state.update(config=config, found=None)
                cache.clear()      # citation cache per DOI
                res = {'doi': entry['doi'], 'group': entry['group'], 'config': config,
                       'time': str(datetime.datetime.now())}
                html = ''
                try:
                    p = new_project('mardmo-model-catalog', TITLE)
                    new_item(p, 'model', 'X', *MODEL)
                    answer(p, 'publication', text='P1', set_index=0)
                    answer(p, 'publication/id', signal=True, text='not found', external_id='not found', set_index=0)
                    answer(p, 'publication/reference', option=DOI_OPTION, text=entry['doi'], set_index=0,
                           collection_index=0)
                    answer(p, 'publication/entity-relation', option=f'{MARDMO}documents', set_prefix='0', set_index=0)
                    answer(p, 'publication/entity-relatant', signal=True, set_prefix='0', set_index=0,
                           collection_index=0, **own(*MODEL))
                    html = preview_and_payload(p, res)
                    res['found'] = state['found']
                    res['publication'] = next(iter((res.get('answers preview') or {}).get('publication', {}).values()), None)
                except Exception:
                    res['error'] = traceback.format_exc()
                finally:
                    Project.objects.filter(title=TITLE).delete()
                name = f'{number:02d}-{config}'
                open(os.path.join(out, f'{name}.html'), 'w').write(html)
                json.dump(res, open(os.path.join(out, f'{name}.json'), 'w'), indent=1, default=str)
                pub = res.get('publication') or {}
                print(f"{name:24} {entry['doi'][:38]:38} found: {','.join(k for k, v in (res.get('found') or {}).items() if v) or '-':28} "
                      f"title: {'yes' if pub.get('title') else '-':3} authors: {len(pub.get('author') or {}):2} "
                      f"journal: {'yes' if pub.get('journal') else '-':3} payload: {len(res['payload']) if 'payload' in res else '-'}"
                      f"{'  export: ' + res['export message'][0][:80] if 'export message' in res else ''}"
                      f"{'  ERROR ' + res['error'].strip().splitlines()[-1] if 'error' in res else ''}", flush=True)
    finally:
        pub_utils.query_sparql_pool = _real_pool
        for name, function in _real_api.items():
            setattr(pub_utils, name, function)
        pub_utils.get_citation = pub_worker.get_citation = _real_get_citation
        Project.objects.filter(title=TITLE).delete()
        print('temporary projects deleted:', not Project.objects.filter(title=TITLE).exists())
