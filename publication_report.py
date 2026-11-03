"""Report on the runs of publication_sources.py: fields per source, author/journal matching, preview.

Plain Python, outside RDMO:  python3 publication_report.py [results/publication-sources]

1. Fields per DOI and source configuration (title, year, type, journal, ISSN,
   volume, issue, pages, language, authors with ORCID / zbMATH ID), with the
   fields that differ between the sources that know the DOI.
2. Matching: every ORCID, zbMATH author ID and Wikidata QID of the authors and
   every ISSN of the journals seen in the runs is looked up directly on the
   MaRDI Portal and on Wikidata (read-only, in batches).  From that the
   expected result per author and journal (portal item, Wikidata item, new)
   is compared with the ID MaRDMO assigned in each run.
3. Preview against payload with preview_compare.py for every run.

Writes <results dir>/report.json and prints a summary.
"""
import collections, glob, json, os, re, sys, time
import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import preview_compare

H = {'User-Agent': 'MaRDMO-test (read-only; mailto:reidelbach@zib.de)'}
PORTAL_SPARQL = 'https://query.portal.mardi4nfdi.de/sparql'
WIKIDATA_SPARQL = 'https://query-main.wikidata.org/sparql'
FIELDS = ('Name', 'title', 'date', 'entrytype', 'volume', 'issue', 'page')


def sparql(endpoint, query, attempts=3):
    """Bindings of a query; retried after a pause when the query service answers with an error."""
    for attempt in range(1, attempts + 1):
        time.sleep(1 if attempt == 1 else 15 * attempt)
        try:
            r = requests.post(endpoint, data={'query': query}, timeout=120,
                              headers={**H, 'Accept': 'application/sparql-results+json'})
            r.raise_for_status()
            return r.json()['results']['bindings']
        except requests.exceptions.RequestException:
            if attempt == attempts:
                raise


def lookup(endpoint, prefix, prop, values):
    """{value: [QIDs]} of items holding prop with one of values."""
    found = collections.defaultdict(list)
    values = sorted(values)
    for i in range(0, len(values), 100):
        chunk = ' '.join('"%s"' % v.replace('"', '') for v in values[i:i + 100])
        query = f'PREFIX wdt: <{prefix}/prop/direct/>\nSELECT ?v ?i WHERE {{ VALUES ?v {{ {chunk} }} ?i wdt:{prop} ?v }}'
        for b in sparql(endpoint, query):
            found[b['v']['value']].append(b['i']['value'].rsplit('/', 1)[1])
    return found


def fields(pub):
    """The compared fields of one publication answer."""
    authors = [(a.get('Name', ''), a.get('orcid') or '', a.get('zbmath') or '')
               for _, a in sorted((pub.get('author') or {}).items(), key=lambda kv: int(kv[0]))]
    journal = next(iter((pub.get('journal') or {}).values()), {})
    out = {f: (pub.get(f) or '') for f in FIELDS}
    out['date'] = out['date'][:10]
    out.update({'journal': journal.get('Name', ''), 'issn': journal.get('issn', ''),
                'language': ', '.join(l.get('Name', '') for l in (pub.get('language') or {}).values()),
                'authors': len(authors), 'author names': [a[0] for a in authors],
                'orcids': [a[1] for a in authors if a[1]], 'zbmath ids': [a[2] for a in authors if a[2]]})
    return out


def main(folder):
    props = json.load(open(os.path.join(folder, 'properties.json')))
    runs = collections.defaultdict(dict)
    for path in sorted(glob.glob(os.path.join(folder, '[0-9][0-9]-*.json'))):
        number, config = os.path.basename(path)[:-5].split('-', 1)
        runs[number][config] = (json.load(open(path)), path[:-5] + '.html')

    # identifiers seen in the runs
    orcids, zbmaths, wd_authors, issns = set(), set(), set(), set()
    for configs in runs.values():
        for res, _ in configs.values():
            pub = res.get('publication') or {}
            for a in (pub.get('author') or {}).values():
                orcids.update([a['orcid']] if a.get('orcid') else [])
                # "None" is no zbMATH ID (some portal items carry it as text)
                zbmaths.update([a['zbmath']] if a.get('zbmath') and a['zbmath'] != 'None' else [])
                for ident in (a.get('ID') or '', a.get('wikidata') or ''):
                    if ident.startswith('wikidata:Q'):
                        wd_authors.add(ident.split(':')[1])
            for j in (pub.get('journal') or {}).values():
                issns.update([j['issn']] if j.get('issn') else [])
    portal = 'https://portal.mardi4nfdi.de'
    truth = {
        'portal orcid': lookup(PORTAL_SPARQL, portal, props['ORCID iD'], orcids),
        'portal zbmath': lookup(PORTAL_SPARQL, portal, props['zbMATH author ID'], zbmaths),
        'portal wikidata': lookup(PORTAL_SPARQL, portal, props['Wikidata QID'], wd_authors),
        'portal issn': lookup(PORTAL_SPARQL, portal, props['ISSN'], issns),
        'wikidata orcid': lookup(WIKIDATA_SPARQL, 'http://www.wikidata.org', 'P496', orcids),
        'wikidata zbmath': lookup(WIKIDATA_SPARQL, 'http://www.wikidata.org', 'P1556', zbmaths),
        'wikidata issn': lookup(WIKIDATA_SPARQL, 'http://www.wikidata.org', 'P236', issns),
    }
    # items found on Wikidata may be on the portal through their Wikidata QID
    wd_found = {q for k in ('wikidata orcid', 'wikidata zbmath', 'wikidata issn') for qs in truth[k].values() for q in qs}
    truth['portal wikidata'] = {**truth['portal wikidata'], **lookup(PORTAL_SPARQL, portal, props['Wikidata QID'],
                                                                      wd_found - set(truth['portal wikidata']))}

    def expected_author(a):
        """'mardi:Q…', 'wikidata:Q…', 'new' or 'name only', plus conflicts between identifiers."""
        wd = (a.get('ID') or '').split(':')[1] if (a.get('ID') or '').startswith('wikidata:Q') else \
            (a.get('wikidata') or '').removeprefix('wikidata:') or ''
        zb = a.get('zbmath') if a.get('zbmath') != 'None' else None
        on_wikidata = set(truth['wikidata orcid'].get(a.get('orcid'), [])) | set(truth['wikidata zbmath'].get(zb, [])) \
            | ({wd} if wd else set())
        on_portal = set(truth['portal orcid'].get(a.get('orcid'), [])) | set(truth['portal zbmath'].get(zb, [])) \
            | {q for w in on_wikidata for q in truth['portal wikidata'].get(w, [])}
        conflict = len(on_portal) > 1 or len(on_wikidata) > 1
        if on_portal:
            return 'mardi:' + sorted(on_portal)[0], conflict, sorted(on_portal), sorted(on_wikidata)
        if on_wikidata:
            return 'wikidata:' + sorted(on_wikidata)[0], conflict, [], sorted(on_wikidata)
        return ('new' if a.get('orcid') or a.get('zbmath') else 'name only'), False, [], []

    def actual_author(a):
        ident = a.get('ID') or ''
        if ident.startswith(('mardi:', 'wikidata:')):
            return ident
        return 'new' if a.get('orcid') or a.get('zbmath') else 'name only'

    report = {}
    totals = collections.Counter()
    for number, configs in sorted(runs.items()):
        any_res = next(iter(configs.values()))[0]
        entry = report[number] = {'doi': any_res['doi'], 'group': any_res['group'], 'configs': {}}
        for config, (res, html) in configs.items():
            pub = res.get('publication') or {}
            c = entry['configs'][config] = {'found': [k for k, v in (res.get('found') or {}).items() if v]}
            if res.get('error'):
                c['error'] = res['error'].strip().splitlines()[-1]; totals['error'] += 1
            if res.get('export crash'):
                c['export crash'] = res['export crash'].strip().splitlines()[-1]; totals['export crash'] += 1
            if res.get('export message'):
                c['export message'] = res['export message'][0][:150]
            if not pub.get('title') and not pub.get('author'):
                continue
            c['fields'] = fields(pub)
            # matching of authors and journal
            matching = []
            for a in (pub.get('author') or {}).values():
                exp, conflict, on_portal, on_wd = expected_author(a)
                act = actual_author(a)
                matching.append({'author': a.get('Name'), 'expected': exp, 'MaRDMO': act, 'agrees': act == exp,
                                 'conflict': conflict, 'portal items': on_portal, 'wikidata items': on_wd})
                totals['authors checked'] += 1
                totals['authors agree' if act == exp else 'AUTHORS DIFFER'] += 1
                totals['identifier conflicts'] += conflict
            for j in (pub.get('journal') or {}).values():
                wd_j = truth['wikidata issn'].get(j.get('issn'), []) + \
                    ([j['ID'].split(':')[1]] if (j.get('ID') or '').startswith('wikidata:') else [])
                portal_j = truth['portal issn'].get(j.get('issn'), []) + [q for w in wd_j for q in truth['portal wikidata'].get(w, [])]
                exp_j = ('mardi:' + portal_j[0]) if portal_j else ('wikidata:' + wd_j[0]) if wd_j else 'new'
                if (j.get('ID') or '').startswith('mardi:') and not j.get('issn'):
                    exp_j = j['ID']      # publication from the portal: its journal as the portal links it
                act_j = j.get('ID') if (j.get('ID') or '').startswith(('mardi:', 'wikidata:')) else 'new'
                matching.append({'journal': j.get('Name'), 'expected': exp_j, 'MaRDMO': act_j, 'agrees': act_j == exp_j})
                totals['journals checked'] += 1
                totals['journals agree' if act_j == exp_j else 'JOURNALS DIFFER'] += 1
            c['matching'] = matching
            # preview against payload
            if res.get('payload'):
                _, differences = preview_compare.compare(open(html).read(), res['payload'], props)
                if differences:
                    c['preview differences'] = differences; totals['runs with preview differences'] += 1
        # fields that differ between the sources that know the DOI
        single = {k: v['fields'] for k, v in entry['configs'].items() if k != 'all' and 'fields' in v}
        differ = {}
        for f in ('Name', 'title', 'date', 'entrytype', 'volume', 'issue', 'page', 'journal', 'issn', 'language',
                  'authors', 'author names', 'orcids', 'zbmath ids'):
            values = {k: v[f] for k, v in single.items()}
            if len({json.dumps(x, ensure_ascii=False) for x in values.values()}) > 1:
                differ[f] = values
        entry['differences between sources'] = differ
        totals['DOIs with field differences'] += bool(differ)
    json.dump({'totals': totals, 'truth': {k: dict(v) for k, v in truth.items()}, 'dois': report},
              open(os.path.join(folder, 'report.json'), 'w'), indent=1, ensure_ascii=False)

    print('totals:', dict(totals))
    for number, entry in report.items():
        print(f"\n{number} [{entry['group']}] {entry['doi']}")
        for config, c in entry['configs'].items():
            f = c.get('fields') or {}
            bad = [m for m in c.get('matching', []) if not m['agrees']]
            print(f"   {config:9} found {','.join(c['found']) or '-':24} "
                  f"{(f.get('date') or '')[:4]:4} {f.get('authors', 0):2} auth  journal: {(f.get('journal') or '-')[:28]:28} "
                  f"{'matching ok' if c.get('matching') and not bad else ''}"
                  f"{' MATCHING: ' + '; '.join((m.get('author') or 'journal ' + m.get('journal', ''))[:25] + ' ' + m['MaRDMO'] + ' (expected ' + m['expected'] + ')' for m in bad[:3]) if bad else ''}"
                  f"{' PREVIEW: ' + ', '.join(c['preview differences']) if c.get('preview differences') else ''}"
                  f"{' ERROR ' + c['error'] if c.get('error') else ''}{' CRASH ' + c['export crash'] if c.get('export crash') else ''}")
        for f, values in entry['differences between sources'].items():
            shown = '; '.join(f'{k}: {json.dumps(v, ensure_ascii=False)[:70]}' for k, v in values.items())
            print(f'      differs {f}: {shown}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                             'results', 'publication-sources'))
