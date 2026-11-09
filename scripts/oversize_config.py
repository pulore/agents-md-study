# For repos whose root AGENTS.md (or root + nested chain) is over 32 KiB: does a committed .codex/config.toml
# raise project_doc_max_bytes? Writes agg/oversize_config.json (counts only).
# Rerun change (5 Nov 2026): also writes raw/oversize_config_per_repo.json (deleted with raw/) so the per-repo
# labels can carry the result. Only repos whose root AGENTS.md alone is over the limit are checked, as before.
import json, os, sys, re
sys.argv = ['analyze.py', 'quiet']
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
exec(open(os.path.join(HERE, 'analyze.py')).read().split('# ---------------- output ----------------')[0])

ids = [r['id'] for r, s in over]
Q = '''query($ids: [ID!]!) { rateLimit { cost } nodes(ids: $ids) { ... on Repository { id
  cfg: object(expression: "HEAD:.codex/config.toml") { ... on Blob { text } } } } }'''
has_cfg = raised = 0
vals = []
per_repo = {i: {'has_cfg': False, 'raised': False} for i in ids}
for i in range(0, len(ids), 20):
    d = gh_graphql(Q, {'ids': ids[i:i + 20]})
    for n in ((d or {}).get('data') or {}).get('nodes') or []:
        t = ((n or {}).get('cfg') or {}).get('text')
        if t is None:
            continue
        has_cfg += 1; per_repo[n['id']]['has_cfg'] = True
        m = re.search(r'^\s*project_doc_max_bytes\s*=\s*(\d+)', t, re.M)
        if m:
            raised += 1; vals.append(int(m.group(1))); per_repo[n['id']]['raised'] = True
out = {'oversize_root_repos': len(ids), 'with_committed_.codex/config.toml': has_cfg, 'setting_project_doc_max_bytes': raised,
       'values': sorted(vals)}
json.dump(out, open(os.path.join(AGG, 'oversize_config.json'), 'w'), indent=1)
json.dump(per_repo, open(os.path.join(RAW, 'oversize_config_per_repo.json'), 'w'))
print(out)
