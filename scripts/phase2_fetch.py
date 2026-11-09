# Phase 2: details for frame repos with any agent-config signal at the root.
# Rerun change (9 Nov 2026): each .claude/skills and .agents/skills entry now brings its oid (a skill folder's
# content hash, so two folders can be compared without reading them) and, for a symlink, its target.
# Rerun change (5 Nov 2026): the blob query no longer reads package.json or CLAUDE.local.md. Neither fed a
# published number (package.json only fed an unpublished lockfile check), and the method reads only what it needs.
#   python3 phase2_fetch.py blobs    -> raw/blobs/<node_id>.json  (file texts, .claude/.agents listings, package.json)
#   python3 phase2_fetch.py trees    -> raw/trees/<node_id>.json  (relevant paths from the recursive tree; root AGENTS.md repos)
#   python3 phase2_fetch.py history  -> raw/history/<node_id>.json (last commit date touching each root file; repos with both)
import json, os, sys, time, glob, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

SIGNAL = {'CLAUDE.md', 'AGENTS.md', '.claude', '.agents', 'AGENTS.override.md', 'CLAUDE.local.md', '.codex'}
SYMLINK = '120000'


def frame_index():
    """node_id -> (repo row, root entries) for every enumerated frame repo."""
    idx = {}
    for f in glob.glob(os.path.join(RAW, 'frame', '*.json')):
        rec = json.load(open(f))
        rp = f.replace(os.sep + 'frame' + os.sep, os.sep + 'roots' + os.sep)
        roots = json.load(open(rp)) if os.path.exists(rp) else {}
        for r in rec['repos']:
            idx[r['node_id']] = (r, roots.get(r['node_id']))
    return idx


BLOB_FIELDS = '''
    id
    c: object(expression: "HEAD:CLAUDE.md") { ... on Blob { text byteSize isTruncated isBinary } }
    a: object(expression: "HEAD:AGENTS.md") { ... on Blob { text byteSize isTruncated isBinary } }
    cc: object(expression: "HEAD:.claude/CLAUDE.md") { ... on Blob { text byteSize isTruncated } }
    ao: object(expression: "HEAD:AGENTS.override.md") { ... on Blob { text byteSize } }
    dc: object(expression: "HEAD:.claude") { __typename ... on Tree { entries { name mode type } } ... on Blob { text } }
    da: object(expression: "HEAD:.agents") { __typename ... on Tree { entries { name mode type } } ... on Blob { text } }
    dcs: object(expression: "HEAD:.claude/skills") { __typename ... on Tree { entries { name mode type oid object { ... on Blob { text } } } } ... on Blob { text } }
    das: object(expression: "HEAD:.agents/skills") { __typename ... on Tree { entries { name mode type oid object { ... on Blob { text } } } } ... on Blob { text } }
'''
BLOB_Q = 'query($ids: [ID!]!) { rateLimit { cost remaining } nodes(ids: $ids) { ... on Repository {' + BLOB_FIELDS + '} } }'

HIST_Q = '''query($ids: [ID!]!) { rateLimit { cost remaining } nodes(ids: $ids) { ... on Repository {
  id
  defaultBranchRef { target { ... on Commit {
    hc: history(first: 1, path: "CLAUDE.md") { nodes { committedDate } }
    ha: history(first: 1, path: "AGENTS.md") { nodes { committedDate } }
  } } }
} } }'''

KEEP_NAMES = {'AGENTS.md', 'AGENTS.override.md', 'CLAUDE.md', 'CLAUDE.local.md', 'SKILL.md'}


def slim_pkg(text):
    try:
        p = json.loads(text)
    except Exception:
        return None
    if not isinstance(p, dict):
        return None
    scripts = p.get('scripts') if isinstance(p.get('scripts'), dict) else {}
    return {'packageManager': p.get('packageManager'), 'scripts': {k: v for k, v in scripts.items() if isinstance(v, str) and ('test' in k or k in ('lint', 'format', 'fmt', 'build', 'check', 'typecheck'))},
            'workspaces': bool(p.get('workspaces'))}


def run_graphql_batches(ids, query, outdir, batch, post=None, workers=2):
    os.makedirs(outdir, exist_ok=True)
    todo = [i for i in ids if not os.path.exists(os.path.join(outdir, i.replace('/', '_') + '.json'))]
    log('to fetch', len(todo), 'of', len(ids))
    chunks = [todo[i:i + batch] for i in range(0, len(todo), batch)]
    lock = threading.Lock(); done = [0]

    def handle(chunk):
        d = gh_graphql(query, {'ids': chunk})
        if d is None and len(chunk) > 1:
            for one in chunk:
                handle([one])
            return
        nodes = ((d or {}).get('data') or {}).get('nodes') or []
        got = {n['id']: n for n in nodes if n}
        for i in chunk:
            n = got.get(i)
            if n is None:
                n = {'id': i, 'missing': True}
            if post:
                n = post(n)
            json.dump(n, open(os.path.join(outdir, i.replace('/', '_') + '.json'), 'w'))
        with lock:
            done[0] += 1
            if done[0] % 20 == 0:
                log('batches', done[0], 'of', len(chunks), (d or {}).get('data', {}).get('rateLimit'))

    def worker(my):
        for ch in my:
            handle(ch)

    ts = [threading.Thread(target=worker, args=(chunks[w::workers],)) for w in range(workers)]
    for t in ts: t.start()
    for t in ts: t.join()


def post_blobs(n):
    if n.get('pkg') and n['pkg'].get('text'):
        n['pkg'] = {'byteSize': n['pkg'].get('byteSize'), 'slim': slim_pkg(n['pkg']['text'])}
    return n


def cmd_blobs():
    idx = frame_index()
    ids = [k for k, (r, e) in idx.items() if e and SIGNAL & {x['name'] for x in e}]
    log('frame repos', len(idx), 'with a signal at root', len(ids))
    run_graphql_batches(sorted(ids), BLOB_Q, os.path.join(RAW, 'blobs'), batch=8, post=post_blobs, workers=int(sys.argv[2]) if len(sys.argv) > 2 else 2)


def cmd_history():
    idx = frame_index()
    ids = [k for k, (r, e) in idx.items() if e and {'CLAUDE.md', 'AGENTS.md'} <= {x['name'] for x in e}]
    log('repos with both root files', len(ids))
    run_graphql_batches(sorted(ids), HIST_Q, os.path.join(RAW, 'history'), batch=20, workers=int(sys.argv[2]) if len(sys.argv) > 2 else 2)


def cmd_trees():
    idx = frame_index()
    ids = [k for k, (r, e) in idx.items() if e and 'AGENTS.md' in {x['name'] for x in e}]
    outdir = os.path.join(RAW, 'trees'); os.makedirs(outdir, exist_ok=True)
    todo = [i for i in sorted(ids, reverse=os.environ.get('REVERSE') == '1') if not os.path.exists(os.path.join(outdir, i + '.json'))]
    log('root AGENTS.md repos', len(ids), 'to fetch', len(todo))
    lock = threading.Lock(); done = [0]

    def one(nid):
        r, _ = idx[nid]
        ok, d = gh_rest(f"repos/{r['full_name']}/git/trees/{r['branch']}", {'recursive': 1})
        if not ok or not isinstance(d, dict):
            rec = {'error': str(d)[:120]}
        else:
            tree = d.get('tree') or []
            keep = [{'path': t['path'], 'mode': t['mode'], 'type': t['type'], 'size': t.get('size')} for t in tree
                    if t['path'].rsplit('/', 1)[-1] in KEEP_NAMES
                    or t['path'].split('/')[0] in ('.claude', '.agents', '.codex') and t['path'].count('/') <= 2]
            rec = {'truncated': d.get('truncated'), 'n_entries': len(tree), 'keep': keep}
        json.dump(rec, open(os.path.join(outdir, nid + '.json'), 'w'))
        with lock:
            done[0] += 1
            if done[0] % 100 == 0:
                log('trees', done[0], 'of', len(todo))

    def worker(my):
        for nid in my:
            if not os.path.exists(os.path.join(outdir, nid + '.json')):
                one(nid); time.sleep(0.4)

    W = 3
    ts = [threading.Thread(target=worker, args=(todo[w::W],)) for w in range(W)]
    for t in ts: t.start()
    for t in ts: t.join()
    log('trees done')


if __name__ == '__main__':
    {'blobs': cmd_blobs, 'trees': cmd_trees, 'history': cmd_history}[sys.argv[1]]()
