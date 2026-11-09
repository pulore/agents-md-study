# How many frame repos could not be drawn because they were created outside the day range?
# Two repository-search counts, written into agg/run_config.json.  python3 frame_coverage.py
import json, os, sys, time, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

cfg = run_config()
out = {'checked_utc': now_iso()}
for key, q in (('created_after_last_day', f'{FRAME_Q} created:>{LAST_DAY.isoformat()}'),
               ('created_before_first_day', f'{FRAME_Q} created:<{FIRST_DAY.isoformat()}')):
    ok, d = gh_rest('search/repositories', {'q': q, 'per_page': 1})
    out[key] = d.get('total_count') if ok and isinstance(d, dict) else None
    out[key + '_query'] = q
    time.sleep(2.3)
total = cfg.get('frame_total_count_at_start')
if total and out['created_after_last_day'] is not None and out['created_before_first_day'] is not None:
    out['share_of_frame_outside_range_pct'] = round(100 * (out['created_after_last_day'] + out['created_before_first_day']) / total, 3)
cfg['frame_outside_day_range'] = out
json.dump(cfg, open(CONFIG_PATH, 'w'), indent=1)
print(json.dumps(out))
