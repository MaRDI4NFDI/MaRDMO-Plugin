"""How the export classifies statements whose qualifiers were changed in the interview.

Real portal items are filled, then a few relations are added or extended
the way a user would do it.  For each case the export payload (nothing is
posted) is searched for the statement concerned and its existence check
result is reported:

- exists:   the statement with exactly these qualifiers is on the portal
- partial:  the statement is on the portal, only qualifiers are added to it
- new:      a statement of its own is written

A statement is the same if subject, property, object and the qualifiers
that define its meaning match (role, symbol represents, platform, also
when there is none); all other qualifiers (assumptions, comments,
documentation, ...) are added to an existing statement.

Cases (expected after the qualifier merge):

  C1  contains F (no role) on portal, user adds F as initial condition   new
  C2  F as initial condition on portal, user adds F as boundary cond.    new
  C3  F as initial condition on portal, user enters it again             exists
  C4  F as initial condition on portal, user adds plain "contains F"     new
  C5  as C4, but no statement of the export has a role                   new
      (a hand-built payload: a whole model brings its roles along)
  A1  specialization without assumption, user adds assumption q          partial
  A2  specialization with assumption q1, user adds q2                    partial
  A3  specialization with assumption q1, user enters q1 again            exists
  A4  specialization, assumption is a formula of the user's own          partial
  A5  four specializations in one block, user adds an assumption         partial (all four)
  W1  process step uses algorithm with platform, user adds a parameter   partial
  W2  same algorithm with another software                               new
  P1  publication invents the model, user adds "uses"                    new

Environment: OUT (default results/qualifier-merge-<date>).
"""
import collections, datetime, json, os, sys, traceback
HERE_ = os.path.expanduser(os.environ.get('DEV_TESTS', '~/Work/MaRDMO-Plugin/dev-tests'))
sys.path.insert(0, HERE_)
os.environ['OUT'] = os.environ.get('OUT') or os.path.join(HERE_, 'results', f'qualifier-merge-{datetime.date.today()}')
from common import *  # noqa: F401,F403
from preview_edits import answer, new_item, own, portal, TEXTS, MATHMODDB, MARDMO
from preview_payload import preview_and_payload, out
from preview_compare import parse_payload
from MaRDMO.getters import get_items, get_properties, get_url
from MaRDMO.payload import GeneratePayload

TITLE = 'TEMP qualifier merge'
PROPS = get_properties()
ROLE = {'initial condition': 'Q6534264', 'boundary condition': 'Q6534259', 'invents': 'Q6672344', 'uses': 'Q6480405'}


def next_index(project, path, prefix):
    """Next free set index of a nested question set (relation block) below set_prefix."""
    return max(project.values.filter(snapshot=None, attribute__uri=f'{BASE_URI}domain/{path}', set_prefix=prefix)
               .values_list('set_index', flat=True), default=-1) + 1


def relation(project, kind, option, relatant, prefix, assumptions=()):
    """A new relation block: relation type, one relatant and optional assumptions."""
    rel, item, assumption = {'formula': ('model/formulation-relation', 'model/formulation-relatant', None),
                             'model': ('model/model-relation', 'model/model-relatant', 'model/model-assumption'),
                             'publication': ('publication/entity-relation', 'publication/entity-relatant', None)}[kind]
    k = next_index(project, rel, prefix)
    answer(project, rel, option=option, set_prefix=prefix, set_index=k)
    answer(project, item, signal=True, set_prefix=prefix, set_index=k, collection_index=0, **relatant)
    for c, a in enumerate(assumptions):
        answer(project, assumption, signal=True, set_prefix=prefix, set_index=k, collection_index=c, **a)


def existing(project, path, prefix, set_index):
    """The relatants already in a block, as stored by the interview."""
    return [{'text': v.text, 'external_id': v.external_id} for v in project.values.filter(
        snapshot=None, attribute__uri=f'{BASE_URI}domain/{path}', set_prefix=prefix, set_index=set_index)
        .order_by('collection_index')]


# case: (subject, property, object, all qualifiers of the statement after the edit, expected)
# items are portal QIDs or ('own', label); qualifier lists are (property, item or text)
def edit_q6675425(p):
    """uni uni reaction model: contains with roles, specialization with assumption, publication."""
    f = 'Q6674426'   # initial product concentration, contained as initial condition
    relation(p, 'formula', f'{MATHMODDB}contains-boundary-condition', portal(f), '0|0')
    relation(p, 'formula', f'{MATHMODDB}contains-initial-condition', portal(f), '0|0')
    relation(p, 'formula', f'{MATHMODDB}contains', portal(f), '0|0')
    q1 = existing(p, 'model/model-assumption', '0', 0)          # assumption of "specializes Q6675446"
    q1_qid = q1[0]['external_id'].split(':')[1]
    answer(p, 'model/model-assumption', signal=True, set_prefix='0', set_index=0, collection_index=len(q1),
           **portal('Q6674155'))
    relation(p, 'model', f'{MATHMODDB}specializes', portal('Q6675446'), '0', assumptions=q1)
    relation(p, 'publication', f'{MARDMO}uses', portal('Q6675425'), '1')
    role = PROPS['object has role']
    assumes = PROPS['assumes']
    return [
        ('C2', 'Q6675425', 'contains', f, [(role, ROLE['boundary condition'])], 'new'),
        ('C3', 'Q6675425', 'contains', f, [(role, ROLE['initial condition'])], 'exists'),
        ('C4', 'Q6675425', 'contains', f, [], 'new'),
        ('A2', 'Q6675446', 'specialized by', 'Q6675425', [(assumes, q1_qid), (assumes, 'Q6674155')], 'partial'),
        ('A3', 'Q6675446', 'specialized by', 'Q6675425', [(assumes, q1_qid)], 'exists'),
        ('P1', 'Q6675425', 'described by source', 'Q6672237', [(role, ROLE['uses'])], 'new'),
    ]


def edit_q6775746(p):
    """Kriging model: plain contains, four specializations without assumption in one block."""
    relation(p, 'formula', f'{MATHMODDB}contains-initial-condition', portal('Q6775747'), '0|0')
    relation(p, 'model', f'{MATHMODDB}specialized-by', portal('Q6775758'), '0', assumptions=[portal('Q6775753')])
    predictor = ('Kriging predictor', 'best linear unbiased predictor of the Kriging model')
    new_item(p, 'formulation', 'F', *predictor)
    relation(p, 'model', f'{MATHMODDB}specialized-by', portal('Q6775785'), '0', assumptions=[own(*predictor)])
    answer(p, 'model/model-assumption', signal=True, set_prefix='0', set_index=0, collection_index=0,
           **portal('Q6775747'))
    role, assumes = PROPS['object has role'], PROPS['assumes']
    return [
        ('C1', 'Q6775746', 'contains', 'Q6775747', [(role, ROLE['initial condition'])], 'new'),
        ('A1', 'Q6775746', 'specialized by', 'Q6775758', [(assumes, 'Q6775753')], 'partial'),
        ('A4', 'Q6775746', 'specialized by', 'Q6775785', [(assumes, ('own', predictor[0]))], 'partial'),
    ] + [('A5', 'Q6775746', 'specialized by', o, [(assumes, 'Q6775747')], 'partial')
         for o in ('Q6775758', 'Q6775785', 'Q6775787', 'Q6822189')]


def edit_q6032641(p):
    """Workflow: the real usage "RAP Algorithm on Jupyter Notebook / Lenovo IdeaPad" of a process step."""
    step = p.values.get(snapshot=None, attribute__uri=f'{BASE_URI}domain/processstep/id',
                        external_id='mardi:Q6486610').set_index
    prefix = f'{step}|0'
    usage = p.values.filter(snapshot=None, attribute__uri=f'{BASE_URI}domain/processstep/algorithm-relatant',
                            set_prefix=prefix, external_id='mardi:Q6032636').first().set_index
    answer(p, 'processstep/algorithm-parameter', text='threshold = 0.5', set_prefix=prefix, set_index=usage,
           collection_index=0)
    k = next_index(p, 'processstep/algorithm-relatant', prefix)
    answer(p, 'processstep/algorithm-relatant', signal=True, set_prefix=prefix, set_index=k, collection_index=0,
           **portal('Q6032636'))
    answer(p, 'processstep/software-relatant', signal=True, set_prefix=prefix, set_index=k, **portal('Q6825400'))
    platform, comment = PROPS['platform'], PROPS['comment']
    return [
        ('W1', 'Q6486610', 'uses', 'Q6032636',
         [(platform, 'Q6230812'), (platform, 'Q6487066'), (comment, 'threshold = 0.5')], 'partial'),
        ('W2', 'Q6486610', 'uses', 'Q6032636', [(platform, 'Q6825400')], 'new'),
    ]


PROJECTS = [('model', 'Q6675425', edit_q6675425), ('model', 'Q6775746', edit_q6775746),
            ('workflow', 'Q6032641', edit_q6032641)]
LABELS = ['Q6674426', 'Q6674155', 'Q6675446', 'Q6675425', 'Q6775747', 'Q6775753', 'Q6775758', 'Q6775785',
          'Q6032636', 'Q6825400']


def plain_contains_only():
    """C5: only "Q6675425 contains Q6674426", which the portal holds as initial condition.

    The export of a whole model also writes its other "contains" statements,
    some with a role; here the payload holds nothing else.  Runs the real
    existence check (one SPARQL query, one wbgetentities request).
    """
    payload = GeneratePayload(url=get_url('mardi', 'uri'), dependency={},
                              wikibase={'items': get_items(), 'properties': PROPS, 'relations': {}})
    payload.state.dictionary = {
        'Item0000000001': {'id': 'Q6675425', 'label': TEXTS['Q6675425'], 'description': ''},
        'Item0000000002': {'id': 'Q6674426', 'label': TEXTS['Q6674426'], 'description': ''},
    }
    payload.add_answer(PROPS['contains'], ['Item0000000002', 'wikibase-item'], subject='Item0000000001')
    payload.check_existing_relations(get_url('mardi', 'sparql'), get_url('mardi', 'api'))
    found = payload._claims.get('Q6675425', {}).get(PROPS['contains'], [])
    on_portal = [sorted((q, s['datavalue']['value'].get('id')) for q, snaks in c.get('qualifiers', {}).items()
                        for s in snaks if 'datavalue' in s and isinstance(s['datavalue']['value'], dict))
                 for c in found if c['mainsnak'].get('datavalue', {}).get('value', {}).get('id') == 'Q6674426']
    exists = payload.state.dictionary['RELATION0']['exists']
    return {'case': 'C5', 'statement': 'Q6675425 contains Q6674426', 'qualifiers': [],
            'result': {'true': 'exists', 'partial': 'partial'}.get(exists, 'new'), 'expected': 'new',
            'on the portal (item qualifiers)': on_portal}


def classify(payload, cases):
    """Find each case's statement in the payload and report its existence check result."""
    pname = {v: k for k, v in PROPS.items()}
    items, statements, _ = parse_payload(payload)

    def ident(value):
        """Payload value -> QID, ('own', label) for new items, or the literal."""
        if isinstance(value, str) and value in items:
            e = items[value]
            return e['id'] if e.get('id') else ('own', e.get('label'))
        return value

    rows = []
    for case, s, prop, o, quals, expected in cases:
        same_spo = [(sorted(map(str, [(q, ident(v)) for q, v in st[4]])), st[5]) for st in statements
                    if ident(st[0]) == s and pname.get(st[1]) == prop and ident(st[3]) == o]
        want = sorted(map(str, quals))
        match = [ex for q, ex in same_spo if q == want]
        result = ('exists' if match[0] == 'true' else 'partial' if match[0] == 'partial' else 'new') if match \
            else 'NOT IN PAYLOAD'
        rows.append({'case': case, 'statement': f'{s} {prop} {o}', 'qualifiers': quals, 'result': result,
                     'expected': expected, 'same subject/property/object in payload': same_spo})
    return rows


if __name__ in ('__main__', 'django.core.management.commands.shell'):
    TEXTS.update(labels('mardi', LABELS))
    report = {'started': str(datetime.datetime.now()), 'cases': []}
    try:
        for kind, qid, edit in PROJECTS:
            source, slug, qkey, item_type = TYPES[kind]
            res = {'qid': f'{kind}-{qid}'}
            try:
                p = new_project(slug, TITLE)
                TEXTS.update(labels(source, [qid]))
                select(p, qkey, item_type, f'{source}:{qid}', TEXTS[qid], 0)
                cases = edit(p)
                html = preview_and_payload(p, res)
                open(os.path.join(out, f"{res['qid']}.html"), 'w').write(html)
                json.dump(res, open(os.path.join(out, f"{res['qid']}.json"), 'w'), indent=1, default=str)
                if 'payload' not in res:
                    print(qid, 'NO PAYLOAD:', res.get('export message') or res.get('export crash', '')[-300:])
                    continue
                for row in classify(res['payload'], cases):
                    report['cases'].append(row)
                    print(f"{row['case']:3} {row['statement']:44} {row['result']:15} expected {row['expected']:8}"
                          f"{'' if row['result'] == row['expected'] else '   <-- differs'}", flush=True)
            except Exception:
                print(qid, 'ERROR', traceback.format_exc())
            finally:
                Project.objects.filter(title=TITLE).delete()
        row = plain_contains_only()
        report['cases'].append(row)
        print(f"{row['case']:3} {row['statement']:44} {row['result']:15} expected {row['expected']:8}"
              f"{'' if row['result'] == row['expected'] else '   <-- differs'}", flush=True)
    finally:
        Project.objects.filter(title=TITLE).delete()
        json.dump(report, open(os.path.join(out, 'report.json'), 'w'), indent=1, default=str)
        print('\nresults:', out)
        print('temporary projects deleted:', not Project.objects.filter(title=TITLE).exists())
