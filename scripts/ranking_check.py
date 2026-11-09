# Are code search's top-ranked CLAUDE.md / AGENTS.md results longer than a random draw? Sizes only; no names kept.
import json, os, sys, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
res = {}
for name in ('CLAUDE.md', 'AGENTS.md'):
    ok, d = gh_rest('search/code', {'q': f'filename:{name}', 'per_page': 100})
    time.sleep(7)
    items = [i for i in d['items'] if i['name'] == name]
    sizes = []
    for j in range(0, len(items), 20):
        ch = items[j:j + 20]
        q = 'query { rateLimit { cost } ' + ' '.join('r%d: repository(owner: %s, name: %s) { object(expression: %s) { ... on Blob { byteSize } } }' % (
            k, json.dumps(i['repository']['owner']['login']), json.dumps(i['repository']['name']), json.dumps('HEAD:' + i['path'])) for k, i in enumerate(ch)) + '}'
        g = gh_graphql(q, {})
        for k in range(len(ch)):
            o = (((g or {}).get('data') or {}).get('r%d' % k) or {}).get('object')
            if o and o.get('byteSize') is not None:
                sizes.append(o['byteSize'])
    res[name] = {'top_results': len(items), 'sized': len(sizes), 'median_bytes': statistics.median(sizes) if sizes else None,
                 'share_under_100_bytes': round(sum(1 for s in sizes if s < 100) / len(sizes), 3) if sizes else None}
    log(name, res[name])
json.dump(res, open(os.path.join(AGG, 'codesearch_ranking_check.json'), 'w'), indent=1)
