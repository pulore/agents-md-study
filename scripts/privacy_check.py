# Before raw/ is deleted: check that nothing we keep names a sampled repo or quotes its instruction files.
#   python3 privacy_check.py DIR [DIR ...]       (every text file under each DIR is scanned)
# Fails (exit 1) on any sampled node ID, any owner/name pair, any github.com/owner/repo URL, or any line of
# 40+ characters copied from a sampled CLAUDE.md, AGENTS.md or .claude/CLAUDE.md. Bare repo names of 8+
# characters are reported as warnings to read by hand, since many are ordinary words.
import glob, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import RAW

node_ids, full_names, bare = set(), set(), set()
for f in glob.glob(os.path.join(RAW, 'frame', '*.json')):
    for r in json.load(open(f))['repos']:
        node_ids.add(r['node_id']); full_names.add(r['full_name'].lower())
        name = r['full_name'].split('/', 1)[1].lower()
        if len(name) >= 8 and re.search(r'[a-z]', name):
            bare.add(name)
lines = set()
for f in glob.glob(os.path.join(RAW, 'blobs', '*.json')):
    b = json.load(open(f))
    for k in ('c', 'a', 'cc'):
        t = ((b.get(k) or {}).get('text')) or ''
        for l in t.splitlines():
            s = re.sub(r'\s+', ' ', l.strip())
            if len(s) >= 40:
                lines.add(s)
print(f'checking against {len(node_ids)} node IDs, {len(full_names)} repo names, {len(lines)} distinct long lines from sampled files')

fail, warn = [], []
files = []
for d in sys.argv[1:]:
    for p in glob.glob(os.path.join(d, '**', '*'), recursive=True):
        if os.path.isfile(p) and not p.endswith(('.png', '.jpeg', '.jpg', '.pyc')):
            files.append(p)
for p in files:
    try:
        text = open(p, encoding='utf-8').read()
    except UnicodeDecodeError:
        continue
    low = text.lower()
    for m in re.finditer(r'\bR_[A-Za-z0-9_-]{12,}|MDEwOlJlcG9zaXRvcnk[A-Za-z0-9=]+', text):
        if m.group(0) in node_ids:
            fail.append((p, 'node ID'))
    for m in re.finditer(r'github\.com/([\w.-]+/[\w.-]+)', low):
        if m.group(1).rstrip('.') in full_names:
            fail.append((p, 'repo URL'))
    for m in re.finditer(r'(?<![\w.-])([\w.-]+/[\w.-]+)(?![\w.-])', low):
        if m.group(1) in full_names:
            fail.append((p, 'owner/name ' + ('(scripts may name a path)' if p.endswith('.py') else '')))
    for l in text.splitlines():
        s = re.sub(r'\s+', ' ', l.strip())
        if len(s) >= 40 and s in lines:
            fail.append((p, 'copied line: ' + s[:60]))
    if p.endswith(('.json', '.txt', '.md', '.csv')):
        for i, l in enumerate(low.splitlines(), 1):
            for w in sorted(set(re.findall(r'[a-z0-9][a-z0-9._-]{7,}', l)) & bare):
                warn.append((p, f'line {i}: {w[:3]}{"*" * (len(w) - 3)}'))   # masked: read the line in the file itself
print(f'scanned {len(files)} files')
for p, why in fail:
    print('FAIL', os.path.relpath(p), why)
for p, w in warn:
    print('WARN bare repo-name match (read by hand)', os.path.relpath(p), w)
print('privacy check', 'FAILED' if fail else 'passed', f'({len(fail)} failures, {len(warn)} warnings)')
sys.exit(1 if fail else 0)
