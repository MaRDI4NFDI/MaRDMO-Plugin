'''Writes the live check's report (LIVE_REPORT, see test_portal.py).'''
import os


def pytest_sessionfinish(session, exitstatus):
    path = os.environ.get('LIVE_REPORT')
    if not path:
        return
    from tests.live.test_portal import REPORT
    lines = ['## Live check of the MaRDI Portal and Wikidata', '']
    if REPORT['problems']:
        lines += [f'### {len(REPORT["problems"])} answers changed', '', *[f'- {p}' for p in REPORT['problems']], '']
    else:
        lines += ['All answers as recorded.', '']
    if REPORT['notes']:
        lines += ['### Notes', '', *[f'- {n}' for n in REPORT['notes']], '']
    with open(path, 'w', encoding='utf-8') as file:
        file.write('\n'.join(lines))
