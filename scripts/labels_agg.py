# Merge the manual review labels (raw/review_labels.json, keyed by an anonymous hash) into agg/manual_review.json.
# Only items present in the current analysis are counted. Notes are paraphrased and name no repo.
# Review IDs are the salted ones from common.anon (rerun change); the original used sha1(node_id)[:6].
import json, os, sys, collections, statistics
sys.argv = ['analyze.py', 'quiet']
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
src = open(os.path.join(HERE, 'analyze.py')).read().split('# ---------------- output ----------------')[0]
exec(src)

LP = os.path.join(RAW, 'review_labels.json')
L = json.load(open(LP)) if os.path.exists(LP) else {}   # rerun change: no labels yet is not an error
out = {'near_copies': {}, 'conflict_flags': {}, 'notes': {}}

nc_ids = {anon(r['id']): r for r in nc}
lab = collections.Counter(); missing = []
gaps = collections.defaultdict(list)
for a, r in nc_ids.items():
    x = L.get(a, {}).get('near')
    if not x:
        missing.append(a); continue
    lab[x] += 1
    g = gap_days(r)
    if g is not None:
        gaps[x].append(g)
out['near_copies'] = {'n': len(nc_ids), 'labelled': sum(lab.values()), 'unlabelled': len(missing), 'labels': dict(lab),
                      'last_edit_gap_days_by_label': {k: {'n': len(v), 'median': statistics.median(v), 'different_day': sum(1 for d in v if d > 0)} for k, v in gaps.items()}}
out['notes']['near_copy_contradictions'] = [L[a]['near_note'] for a in nc_ids if L.get(a, {}).get('near') == 'contradiction']

for key, items in flags.items():
    c = collections.Counter(); notes = []
    for it in items:
        a = anon(it[0]['id'])
        x = L.get(a, {}).get('flag_' + key)
        c[x or 'unreviewed'] += 1
        if x == 'confirmed':
            notes.append(L[a].get('flag_' + key + '_note'))
    out['conflict_flags'][key] = dict(c)
    if notes:
        out['notes']['confirmed_' + key] = notes
lk = collections.Counter()
for (r, label, d, truth) in [x for x in lock_rows if x[2] != x[3]]:
    lk[L.get(anon(r['id']), {}).get('flag_lock_' + label) or 'unreviewed'] += 1
out['conflict_flags']['file_vs_lockfile'] = dict(lk)
json.dump(out, open(os.path.join(AGG, 'manual_review.json'), 'w'), indent=1)
print(json.dumps(out, indent=1))
if missing:
    print('UNLABELLED near-copies:', missing)
