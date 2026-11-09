# Fetch root listings for enumerated days that don't have one yet, newest files first, 2 threads.
import json, os, sys, glob, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
ROOTS_Q = '''query($ids: [ID!]!) {
  rateLimit { cost remaining resetAt }
  nodes(ids: $ids) { ... on Repository {
    id
    root: object(expression: "HEAD:") { ... on Tree { entries { name mode type } } }
  } }
}'''
FR = os.path.join(RAW, 'frame'); RT = os.path.join(RAW, 'roots')
todo = sorted((f for f in glob.glob(os.path.join(FR, '*.json')) if not os.path.exists(f.replace(FR, RT))), key=os.path.getmtime, reverse=True)
log('days without roots', len(todo))
def work(files):
    for f in files:
        out = f.replace(FR, RT)
        if os.path.exists(out):
            continue
        rows = json.load(open(f))['repos']
        if not rows:
            continue
        ids = [r['node_id'] for r in rows]; res = {}
        for i in range(0, len(ids), 50):
            d = gh_graphql(ROOTS_Q, {'ids': ids[i:i + 50]})
            if d is None:
                for j in range(i, min(i + 50, len(ids)), 10):
                    d2 = gh_graphql(ROOTS_Q, {'ids': ids[j:j + 10]})
                    for n in ((d2 or {}).get('data') or {}).get('nodes') or []:
                        if n: res[n['id']] = (n.get('root') or {}).get('entries')
                continue
            for n in d['data']['nodes'] or []:
                if n: res[n['id']] = (n.get('root') or {}).get('entries')
        if not os.path.exists(out):
            json.dump(res, open(out, 'w'))
        log('catchup roots', os.path.basename(f), len(res), 'of', len(ids))
ts = [threading.Thread(target=work, args=(todo[w::2],)) for w in range(2)]
for t in ts: t.start()
for t in ts: t.join()
log('catchup done')
