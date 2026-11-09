# Sum the per-script API usage records in agg/api_usage/ into agg/api_usage_summary.json.  python3 api_usage.py
import glob, json, os, sys, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import AGG

KEYS = ['search_repositories_requests', 'search_code_requests', 'rest_core_requests', 'graphql_requests',
        'graphql_cost_points', 'rate_limit_sleeps', 'failed_requests']
recs = [json.load(open(f)) for f in sorted(glob.glob(os.path.join(AGG, 'api_usage', '*.json')))]
by = {}
for r in recs:
    b = by.setdefault(r['script'], dict({k: 0 for k in KEYS}, runs=0, first_start_utc=r['started_utc'], last_end_utc=r['ended_utc'], busy_seconds=0))
    for k in KEYS:
        b[k] += r.get(k, 0)
    b['runs'] += 1
    b['first_start_utc'] = min(b['first_start_utc'], r['started_utc']); b['last_end_utc'] = max(b['last_end_utc'], r['ended_utc'])
    t = lambda s: datetime.datetime.strptime(s, '%Y-%m-%dT%H:%M:%SZ')
    b['busy_seconds'] += int((t(r['ended_utc']) - t(r['started_utc'])).total_seconds())
tot = {k: sum(b[k] for b in by.values()) for k in KEYS}
tot['first_start_utc'] = min((b['first_start_utc'] for b in by.values()), default=None)
tot['last_end_utc'] = max((b['last_end_utc'] for b in by.values()), default=None)
tot['script_busy_seconds_summed'] = sum(b['busy_seconds'] for b in by.values())
out = {'note': 'Requests this pipeline sent, counted in code (retries included). GraphQL cost is the rateLimit.cost GitHub '
               'reported per query. Limits for one token: search 30/min, code search 10/min, REST 5,000/h, GraphQL 5,000 points/h.',
       'by_script': by, 'total': tot}
json.dump(out, open(os.path.join(AGG, 'api_usage_summary.json'), 'w'), indent=1)
print(json.dumps(out['total'], indent=1))
