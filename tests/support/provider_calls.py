'''What each option set provider asks the search for, recorded without network.

The search functions are replaced by recorders, so a provider's answer to a
few search texts shows which query it would send (item class, sources,
"not found", user answers, creation) and from how many characters it
searches.  tests/data/providers.json holds this for every provider key
(see tests/unit/test_providers.py).
'''
import importlib
import inspect
import json
import sys

import MaRDMO.queries as queries

SEARCHES = ('', 'a', 'ab', 'abc')
FUNCTIONS = ('query_sources', 'query_sources_with_user_additions')


def record(class_path, key, monkeypatch):
    '''{search, refresh, calls: {search text: query or None}} of the provider *class_path* under *key*.'''
    module_name, class_name = class_path.rsplit('.', 1)
    module = importlib.import_module(module_name)
    seen = []
    originals = {function: getattr(queries, function) for function in FUNCTIONS}
    # the providers' modules imported the functions; queries itself keeps them
    for loaded in [m for name, m in sys.modules.items()
                   if name.startswith('MaRDMO') and m is not None and m is not queries]:
        for function, real in originals.items():
            current = getattr(loaded, function, None)
            if current is real or getattr(current, 'recorder', False):

                def recorder(*args, _real=real, _name=function, **kwargs):
                    bound = inspect.signature(_real).bind(*args, **kwargs)
                    bound.apply_defaults()
                    arguments = dict(bound.arguments)
                    arguments.pop('project', None)
                    seen.append({'function': _name, **arguments})
                    return []

                recorder.recorder = True
                monkeypatch.setattr(loaded, function, recorder)
    provider = getattr(module, class_name)(key, key, class_path)
    calls = {}
    for search in SEARCHES:
        seen.clear()
        provider.get_options(None, search=search)
        calls[search] = json.loads(json.dumps(seen[0], sort_keys=True)) if seen else None
    return {'search': bool(provider.search), 'refresh': bool(provider.refresh), 'calls': calls}
