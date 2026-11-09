# Phase 1: enumerate every frame repo created on K randomly drawn days, then read each repo's root file list.
# Usage: python3 phase1_frame.py [K]      (K defaults to 420, the study's value)
# Writes raw/frame/<day>.json (repo list per day) and raw/roots/<day>.json (root tree entries per repo),
# and agg/run_config.json (run date, frame query and window, seed, frame size; no repo data).
import json, os, sys, time, threading, queue
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

K = int(sys.argv[1]) if len(sys.argv) > 1 else K_DAYS
FR = os.path.join(RAW, 'frame'); RT = os.path.join(RAW, 'roots')
os.makedirs(FR, exist_ok=True); os.makedirs(RT, exist_ok=True)

ROOTS_Q = '''query($ids: [ID!]!) {
  rateLimit { cost remaining resetAt }
  nodes(ids: $ids) { ... on Repository {
    id
    root: object(expression: "HEAD:") { ... on Tree { entries { name mode type } } }
  } }
}'''

work = queue.Queue()
SEARCH_GAP = 2.3   # seconds between search requests, about 26 a minute (limit 30)

# Record the run once. A later invocation (resume) keeps the first record.
cfg = run_config()
if not cfg:
    ok, d = gh_rest('search/repositories', {'q': FRAME_Q, 'per_page': 1})
    time.sleep(SEARCH_GAP)
    cfg = {'run_date': RUN_DATE.isoformat(), 'frame_query': FRAME_Q,
           'push_window': {'from_utc': PUSH_FROM.isoformat() + 'T00:00:00Z',
                           'to': 'the moment each creation day was listed (see listed_first_utc / listed_last_utc)'},
           'frame_total_count_at_start': d.get('total_count') if ok and isinstance(d, dict) else None,
           'frame_total_count_checked_utc': now_iso(),
           'seed': SEED, 'days_drawn': K, 'day_range': [str(FIRST_DAY), str(LAST_DAY)],
           'phase1_started_utc': now_iso()}
    json.dump(cfg, open(CONFIG_PATH, 'w'), indent=1)
    log('frame', FRAME_Q, 'total_count', cfg['frame_total_count_at_start'])


def search_day(day, attempt=0):
    out = os.path.join(FR, f'{day}.json')
    if os.path.exists(out):
        return json.load(open(out))
    q = f'{FRAME_Q} created:{day}'
    items, total, incomplete = [], None, False
    listed_at = now_iso()
    for page in range(1, 11):
        ok, d = gh_rest('search/repositories', {'q': q, 'per_page': 100, 'page': page})
        time.sleep(SEARCH_GAP)
        if not ok or not isinstance(d, dict):
            incomplete = True; break
        total = d['total_count']; incomplete = incomplete or d.get('incomplete_results', False)
        items += d['items']
        if len(d['items']) < 100 or len(items) >= min(total, 1000):
            break
    seen, rows = set(), []
    for i in items:
        if i['node_id'] in seen or i.get('fork') or i.get('archived'):
            continue
        seen.add(i['node_id'])
        rows.append({'node_id': i['node_id'], 'full_name': i['full_name'], 'stars': i['stargazers_count'],
                     'created': i['created_at'], 'pushed': i['pushed_at'], 'lang': i.get('language'),
                     'size_kb': i.get('size'), 'branch': i.get('default_branch'), 'template': i.get('is_template')})
    # Rerun addition: if search flagged the page set as incomplete, or returned fewer repos than it counted,
    # list the day again (twice at most) instead of keeping a partial day.
    if (incomplete or (total is not None and len(seen) < min(total, 1000))) and attempt < 2:
        log('day', day, 'incomplete listing', len(seen), 'of', total, '-> listing again')
        time.sleep(10)
        return search_day(day, attempt + 1)
    rec = {'day': str(day), 'query': q, 'total_count': total, 'incomplete': incomplete, 'listed_at': listed_at,
           'listing_attempts': attempt + 1, 'repos': rows}
    json.dump(rec, open(out, 'w'))
    return rec


def roots_worker():
    while True:
        item = work.get()
        if item is None:
            return
        day, rows = item
        out = os.path.join(RT, f'{day}.json')
        if os.path.exists(out):
            continue
        res = {}
        ids = [r['node_id'] for r in rows]
        for i in range(0, len(ids), 50):
            chunk = ids[i:i + 50]
            d = gh_graphql(ROOTS_Q, {'ids': chunk})
            if d is None:
                # fall back to smaller batches
                for j in range(0, len(chunk), 10):
                    d2 = gh_graphql(ROOTS_Q, {'ids': chunk[j:j + 10]})
                    for n in ((d2 or {}).get('data') or {}).get('nodes') or []:
                        if n: res[n['id']] = (n.get('root') or {}).get('entries')
                continue
            for n in d['data']['nodes'] or []:
                if n: res[n['id']] = (n.get('root') or {}).get('entries')
        if not os.path.exists(out):
            json.dump(res, open(out, 'w'))
        log('roots', day, len(res), 'of', len(ids))


t = threading.Thread(target=roots_worker, daemon=True); t.start()
days = sampled_days(K)
tot = 0
for n, day in enumerate(days):
    rec = search_day(day)
    tot += len(rec['repos'])
    if rec['total_count'] and rec['total_count'] > 1000:
        log('WARNING day over 1000 results', day, rec['total_count'])
    if rec['repos']:
        work.put((str(day), rec['repos']))
    if n % 10 == 0:
        log('day', n, day, 'repos so far', tot, 'queue', work.qsize())
work.put(None)
t.join()
cfg = run_config()
cfg['phase1_done_utc'] = now_iso()
json.dump(cfg, open(CONFIG_PATH, 'w'), indent=1)
log('done. days', len(days), 'repos', tot)
