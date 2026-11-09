# Population-level file counts from REST code search (legacy engine). Totals are estimates.
# Paced at one request every 7 s (limit: 10 a minute). Saves totals plus anonymous checks on the
# first page of results (share at repo root, and blob sizes for the size-filtered queries).
import json, os, sys, time, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

QUERIES = [
    ('agents_all', 'filename:AGENTS.md'),
    ('claude_all', 'filename:CLAUDE.md'),
    ('agents_root', 'filename:AGENTS.md path:/'),
    ('claude_root', 'filename:CLAUDE.md path:/'),
    ('agents_gt32k', 'filename:AGENTS.md size:>32768'),
    ('agents_root_gt32k', 'filename:AGENTS.md path:/ size:>32768'),
    ('agents_gt16k', 'filename:AGENTS.md size:>16384'),
    ('override_all', 'filename:AGENTS.override.md'),
    ('claude_imports_agents', 'filename:CLAUDE.md "@AGENTS.md"'),
    ('claude_mentions_agents', 'filename:CLAUDE.md AGENTS.md'),
    ('agents_mentions_claude', 'filename:AGENTS.md CLAUDE.md'),
    ('skill_claude', 'filename:SKILL.md path:.claude/skills'),
    ('skill_agents', 'filename:SKILL.md path:.agents/skills'),
    ('agents_imports_claude', 'filename:AGENTS.md "@CLAUDE.md"'),
    ('override_root', 'filename:AGENTS.override.md path:/'),
    ('claude_root_imports_agents', 'filename:CLAUDE.md path:/ "@AGENTS.md"'),
]
only = set(sys.argv[1:])
out_path = os.path.join(AGG, 'codesearch_counts.json')
res = json.load(open(out_path)) if os.path.exists(out_path) else {}
for key, q in QUERIES:
    if only and key not in only:
        continue
    ok, d = gh_rest('search/code', {'q': q, 'per_page': 100})
    when = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    if not ok or not isinstance(d, dict):
        log('failed', key, str(d)[:200]); time.sleep(7); continue
    items = d.get('items', [])
    at_root = sum(1 for i in items if '/' not in i['path'])
    name_ok = sum(1 for i in items if i['name'] == q.split()[0].split(':')[1])
    path_ok = None
    if 'path:.' in q:
        want = q.split('path:')[1].split()[0]
        path_ok = sum(1 for i in items if i['path'].startswith(want + '/') or ('/' + want + '/') in i['path'])
    rec = {'query': q, 'total_count': d['total_count'], 'incomplete_results': d.get('incomplete_results'),
           'checked_at': when, 'first_page_items': len(items), 'first_page_at_repo_root': at_root,
           'first_page_exact_name': name_ok, 'first_page_path_match': path_ok}
    # blob-size check on size-filtered queries: sizes of the first 8 results (anonymous)
    if 'size:>' in q:
        lim = int(q.split('size:>')[1].split()[0])
        sizes = []
        for i in items[:8]:
            ok2, b = gh_rest(f"repos/{i['repository']['full_name']}/git/blobs/{i['sha']}")
            if ok2 and isinstance(b, dict):
                sizes.append(b.get('size'))
        rec['first8_blob_sizes'] = sizes
        rec['first8_over_limit'] = sum(1 for s in sizes if s and s > lim)
    res[key] = rec
    json.dump(res, open(out_path, 'w'), indent=1)
    log(key, d['total_count'], 'root', at_root, '/', len(items), 'path_ok', path_ok, rec.get('first8_blob_sizes'))
    time.sleep(7)
