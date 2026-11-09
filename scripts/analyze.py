# Phase 3: aggregate analysis. Writes agg/study_aggregates.json (counts only, no repo names).
#   python3 analyze.py            -> aggregates
#   python3 analyze.py review X   -> print anonymised snippets for manual review (X = near|pm|pypm|test|fmt|style|ban|commit|pointer|lock)
# Rerun changes (5 Nov 2026), none of which changes a classification rule:
#   - review IDs are salted (common.anon) instead of sha1(node_id)[:6], and 12 hex characters long
#   - bootstrap clusters are ordered by salted day ID, so the intervals can be recomputed from the kept labels
#   - numbers the original computed in one-off commands are now computed here: 'omissions' (one-sided test and
#     package-manager rules), the share of small CLAUDE.md files that import AGENTS.md, the one-line import count,
#     the 10-499 star band, and the busiest sampled day
# Changes on 9 Nov 2026, which do change classifications:
#   - imports follow Claude Code's own parser (textlib.import_targets, claude_imports.mjs) instead of a regex that
#     also matched "@AGENTS.md.backup", "@AGENTS.md." and "(@AGENTS.md)"; 'loose_regex_vs_parser' counts the difference
#   - the conflict scan also reads import shims whose CLAUDE.md has lines of its own besides the import
#   - skills: per-skill symlinks are followed to their targets, and same-named skill folders are compared by content hash
import json, os, sys, glob, re, random, math, statistics, datetime, collections, hashlib, posixpath
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
from textlib import *

MODE = sys.argv[1] if len(sys.argv) > 1 else 'agg'
WHAT = sys.argv[2] if len(sys.argv) > 2 else None


def load(d):
    out = {}
    for f in glob.glob(os.path.join(RAW, d, '*.json')):
        out[os.path.basename(f)[:-5]] = json.load(open(f))
    return out


frames = {}
for f in glob.glob(os.path.join(RAW, 'frame', '*.json')):
    rec = json.load(open(f))
    rp = f.replace(os.sep + 'frame' + os.sep, os.sep + 'roots' + os.sep)
    roots = json.load(open(rp)) if os.path.exists(rp) else None
    frames[rec['day']] = (rec, roots)
blobs, trees, hist = load('blobs'), load('trees'), load('history')

repos = []   # one dict per frame repo with root entries
for day, (rec, roots) in frames.items():
    if roots is None:
        continue
    for r in rec['repos']:
        e = roots.get(r['node_id'])
        if e is None:
            continue
        ent = {x['name']: x for x in e}
        repos.append({'day': day, 'id': r['node_id'], 'stars': r['stars'], 'created': r['created'][:10], 'lang': r['lang'],
                      'ent': ent, 'b': blobs.get(r['node_id']), 't': trees.get(r['node_id']), 'h': hist.get(r['node_id'])})

days_all = sorted(frames)
days_done = sorted(d for d, (rec, roots) in frames.items() if roots is not None)


def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(100 * (c - h), 1), round(100 * (c + h), 1)]


def boot(items, pred_num, pred_den=lambda r: True, B=2000, seed=7):
    """Cluster bootstrap over creation days. Returns [lo, hi] percent for sum(num)/sum(den)."""
    by = collections.defaultdict(lambda: [0, 0])
    for r in items:
        if pred_den(r):
            by[r['day']][1] += 1
            if pred_num(r):
                by[r['day']][0] += 1
    keys = sorted(days_done, key=day_id)   # salted order: reproducible from the kept labels
    rng = random.Random(seed)
    vals = []
    for _ in range(B):
        s = [by[keys[rng.randrange(len(keys))]] for _ in keys]
        num = sum(x[0] for x in s if x); den = sum(x[1] for x in s if x)
        if den:
            vals.append(num / den)
    vals.sort()
    if not vals:
        return None
    return [round(100 * vals[int(0.025 * len(vals))], 1), round(100 * vals[int(0.975 * len(vals)) - 1], 1)]


def share(k, n):
    return {'k': k, 'n': n, 'pct': round(100 * k / n, 1) if n else None, 'wilson95': wilson(k, n)}


def is_sym(ent, name):
    return name in ent and ent[name]['mode'] == GQL_SYMLINK


def text_of(b, key):
    return ((b or {}).get(key) or {}).get('text')


def star_band(s):
    return '10-49' if s < 50 else ('50-499' if s < 500 else '500+')


A = {'meta': {}, 'frame': {}, 'pairs': {}, 'near_copies': {}, 'conflicts': {}, 'size': {}, 'override': {}, 'skills': {}}

# ---------------- frame ----------------
tot_count = sum((frames[d][0]['total_count'] or 0) for d in days_done)
retrieved = sum(len(frames[d][0]['repos']) for d in days_done)
A['meta'] = {
    'frame_query': FRAME_Q, 'seed': SEED, 'day_range': [str(FIRST_DAY), str(LAST_DAY)],
    'days_drawn': len(days_all), 'days_with_roots': len(days_done),
    'search_total_count_sum': tot_count, 'repos_retrieved': retrieved, 'repos_with_root_listing': len(repos),
    'incomplete_days': sum(1 for d in days_done if frames[d][0]['incomplete']),
    'days_listed_short_of_total_count': sum(1 for d in days_all if (frames[d][0]['total_count'] or 0) > len(frames[d][0]['repos'])),
    'max_repos_on_one_day': max((frames[d][0]['total_count'] or 0) for d in days_all) if days_all else None,
    'days_listed_first_utc': min((frames[d][0].get('listed_at') or '') for d in days_all) if days_all else None,
    'days_listed_last_utc': max((frames[d][0].get('listed_at') or '') for d in days_all) if days_all else None,
    'run_date': RUN_DATE.isoformat(), 'push_window_from': PUSH_FROM.isoformat(),
    'generated_at': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
}
has = lambda r, n: n in r['ent']
SIGNAL = {'CLAUDE.md', 'AGENTS.md', '.claude', '.agents', 'AGENTS.override.md', 'CLAUDE.local.md', '.codex'}   # as in phase2_fetch.py
A['meta']['repos_with_signal_at_root'] = sum(1 for r in repos if SIGNAL & set(r['ent']))
A['meta']['blobs_read'] = sum(1 for r in repos if r['b'] and not r['b'].get('missing'))
A['meta']['history_read'] = sum(1 for r in repos if r['h'] and not r['h'].get('missing'))
A['meta']['trees_fetched'] = sum(1 for r in repos if r['t'] is not None)
nC = sum(has(r, 'CLAUDE.md') for r in repos)
nA = sum(has(r, 'AGENTS.md') for r in repos)
both = [r for r in repos if has(r, 'CLAUDE.md') and has(r, 'AGENTS.md')]
A['frame'] = {
    'repos': len(repos),
    'root_CLAUDE.md': share(nC, len(repos)), 'root_AGENTS.md': share(nA, len(repos)), 'both_root': share(len(both), len(repos)),
    'either_root': share(sum(has(r, 'CLAUDE.md') or has(r, 'AGENTS.md') for r in repos), len(repos)),
    'both_root_boot95': boot(repos, lambda r: has(r, 'CLAUDE.md') and has(r, 'AGENTS.md')),
    'has_.claude_dir': share(sum(has(r, '.claude') for r in repos), len(repos)),
    'has_.agents_dir': share(sum(has(r, '.agents') for r in repos), len(repos)),
    'has_.codex_dir': share(sum(has(r, '.codex') for r in repos), len(repos)),
    'AGENTS.md_given_CLAUDE.md': share(len(both), nC), 'CLAUDE.md_given_AGENTS.md': share(len(both), nA),
}
byyear = collections.defaultdict(lambda: [0, 0, 0, 0])
for r in repos:
    y = int(r['created'][:4]); k = str(y) if y >= 2023 else '2008-2022'
    byyear[k][0] += 1; byyear[k][1] += has(r, 'CLAUDE.md'); byyear[k][2] += has(r, 'AGENTS.md'); byyear[k][3] += has(r, 'CLAUDE.md') and has(r, 'AGENTS.md')
A['frame']['by_created_year'] = {k: {'repos': v[0], 'claude': v[1], 'agents': v[2], 'both': v[3]} for k, v in sorted(byyear.items())}
byband = collections.defaultdict(lambda: [0, 0, 0, 0])
for r in repos:
    k = star_band(r['stars'])
    byband[k][0] += 1; byband[k][1] += has(r, 'CLAUDE.md'); byband[k][2] += has(r, 'AGENTS.md'); byband[k][3] += has(r, 'CLAUDE.md') and has(r, 'AGENTS.md')
A['frame']['by_star_band'] = {k: {'repos': v[0], 'claude': v[1], 'agents': v[2], 'both': v[3]} for k, v in sorted(byband.items())}

# ---------------- pairs ----------------
# one Node call parses every CLAUDE.md, .claude/CLAUDE.md and AGENTS.md read, the way Claude Code parses imports
prime_imports([t for r in repos if r['b'] and not r['b'].get('missing')
               for t in (text_of(r['b'], 'c'), text_of(r['b'], 'a'), (r['b'].get('cc') or {}).get('text')) if t is not None])
pairs = []
missing_blobs = 0
for r in both:
    b = r['b']
    if not b or b.get('missing'):
        missing_blobs += 1; continue
    c_sym, a_sym = is_sym(r['ent'], 'CLAUDE.md'), is_sym(r['ent'], 'AGENTS.md')
    ct, at = text_of(b, 'c'), text_of(b, 'a')
    if ct is None or at is None:
        missing_blobs += 1; continue
    kind, det = classify_pair(c_sym, a_sym, ct, at)
    r['kind'], r['det'], r['ct'], r['at'] = kind, det, ct, at
    pairs.append(r)
kinds = collections.Counter(r['kind'] for r in pairs)
N = len(pairs)
A['pairs']['n'] = N
A['pairs']['missing_text'] = missing_blobs
A['pairs']['kinds'] = {k: dict(share(v, N), boot95=boot(pairs, lambda r, k=k: r['kind'] == k)) for k, v in kinds.most_common()}
wired = lambda r: r['kind'] in ('symlink', 'import-shim', 'import-plus')
A['pairs']['wired'] = dict(share(sum(wired(r) for r in pairs), N), boot95=boot(pairs, wired))
A['pairs']['not_wired'] = dict(share(sum(not wired(r) for r in pairs), N), boot95=boot(pairs, lambda r: not wired(r)))
copies = lambda r: r['kind'] in ('identical', 'near-copy')
A['pairs']['copies'] = dict(share(sum(copies(r) for r in pairs), N), boot95=boot(pairs, copies))
A['pairs']['symlink_dirs'] = dict(collections.Counter(r['det']['dir'] for r in pairs if r['kind'] == 'symlink'))
ptr = [r for r in pairs if r['kind'] == 'pointer']
A['pairs']['pointer_dirs'] = {'claude_mentions_agents_only': sum(r['det']['c_ptr'] and not r['det']['a_ptr'] for r in ptr),
                              'agents_mentions_claude_only': sum(r['det']['a_ptr'] and not r['det']['c_ptr'] for r in ptr),
                              'both_mention': sum(r['det']['c_ptr'] and r['det']['a_ptr'] for r in ptr),
                              'short_claude_pointer_le5_lines': sum(r['det']['c_ptr'] and r['det']['c_lines'] <= 5 for r in ptr)}
A['pairs']['broken_import_in_code'] = sum(1 for r in pairs if r['det'].get('broken_import_in_code'))
A['pairs']['near_miss_import'] = sum(1 for r in pairs if r['det'].get('near_miss_import'))
# pairs a looser regex would call an import and Claude Code's parser doesn't (and the reverse)
A['pairs']['loose_regex_vs_parser'] = {
    'loose_import_parser_not': sum(1 for r in pairs if r['det'].get('loose_regex_import') and not r['kind'].startswith('import')),
    'parser_import_loose_not': sum(1 for r in pairs if r['kind'].startswith('import') and not r['det'].get('loose_regex_import')),
    'parser_not_kinds': dict(collections.Counter(r['kind'] for r in pairs if r['det'].get('loose_regex_import') and not r['kind'].startswith('import')))}
A['pairs']['agents_imports_claude'] = sum(1 for r in pairs if r['det'].get('agents_imports_claude'))
A['pairs']['symlink_checked_in_as_text'] = sum(1 for r in pairs if r['det'].get('symlink_as_text'))
A['pairs']['by_star_band'] = {}
sub_10_499 = [r for r in pairs if r['stars'] < 500]
A['pairs']['not_wired_10_499_stars'] = share(sum(not wired(r) for r in sub_10_499), len(sub_10_499))
for band in ('10-49', '50-499', '500+'):
    sub = [r for r in pairs if star_band(r['stars']) == band]
    A['pairs']['by_star_band'][band] = {'n': len(sub), 'not_wired': share(sum(not wired(r) for r in sub), len(sub)),
                                        'kinds': dict(collections.Counter(r['kind'] for r in sub))}
# .claude/CLAUDE.md + AGENTS.md without a root CLAUDE.md
dotc = [r for r in repos if has(r, 'AGENTS.md') and not has(r, 'CLAUDE.md') and r['b'] and (r['b'].get('cc') or {}).get('text') is not None]
dk = collections.Counter()
for r in dotc:
    cc_text = r['b']['cc']['text']
    a_text = text_of(r['b'], 'a') or ''
    if is_sym(r['ent'], 'AGENTS.md') and link_target(a_text) == '.claude/CLAUDE.md':
        k = 'symlink'
    elif 'AGENTS.md' in import_targets(cc_text, '.claude'):
        k = 'import (@../AGENTS.md)'
    elif '.claude/AGENTS.md' in import_targets(cc_text, '.claude'):
        k = 'import (@AGENTS.md, resolves inside .claude/)'
    else:
        k, _ = classify_pair(False, is_sym(r['ent'], 'AGENTS.md'), cc_text, a_text)
    dk[k] += 1; r['dotc_kind'] = k
A['pairs']['dot_claude_CLAUDE.md_with_AGENTS.md_no_root_CLAUDE.md'] = {'n': len(dotc), 'kinds': dict(dk)}
A['pairs']['committed_CLAUDE.local.md_any'] = sum(1 for r in repos if has(r, 'CLAUDE.local.md'))
A['pairs']['committed_CLAUDE.local.md_with_AGENTS.md'] = sum(1 for r in repos if has(r, 'CLAUDE.local.md') and has(r, 'AGENTS.md'))
A['pairs']['shared_lines_distribution_separate_written'] = None
sim_rows = [r for r in pairs if 'jaccard' in r['det']]
if sim_rows:
    js = sorted(r['det']['jaccard'] for r in sim_rows)
    A['pairs']['shared_lines_distribution_separate_written'] = {
        'n': len(js), 'median_jaccard': statistics.median(js),
        'bins': {b: sum(1 for x in js if lo <= x < hi) for b, lo, hi in (('0', 0, 0.0001), ('0-0.1', 0.0001, 0.1), ('0.1-0.3', 0.1, 0.3), ('0.3-0.5', 0.3, 0.5), ('0.5-0.8', 0.5, 0.8), ('0.8-1', 0.8, 1.0001))}}

# ---------------- near copies and drift ----------------
def last_dates(r):
    h = r['h']
    if not h or h.get('missing'):
        return None, None
    tgt = ((h.get('defaultBranchRef') or {}).get('target') or {})
    hc = (tgt.get('hc') or {}).get('nodes') or []
    ha = (tgt.get('ha') or {}).get('nodes') or []
    return (hc[0]['committedDate'][:10] if hc else None), (ha[0]['committedDate'][:10] if ha else None)


def gap_days(r):
    c, a = last_dates(r)
    if not c or not a:
        return None
    return abs((datetime.date.fromisoformat(c) - datetime.date.fromisoformat(a)).days)


nc = [r for r in pairs if r['kind'] == 'near-copy']
ident = [r for r in pairs if r['kind'] == 'identical']
A['near_copies'] = {
    'identical': len(ident), 'near_copy': len(nc), 'of_pairs': N,
    'near_copy_same_apart_from_tool_names': sum(1 for r in nc if r['det']['jaccard'] >= 0.999),
    'near_copy_lines_only_in_one_file_median': statistics.median([r['det']['only_c'] + r['det']['only_a'] for r in nc]) if nc else None,
    'near_copy_lines_only_in_one_file_range': [min(r['det']['only_c'] + r['det']['only_a'] for r in nc), max(r['det']['only_c'] + r['det']['only_a'] for r in nc)] if nc else None,
}
for label, group in (('near_copy', nc), ('identical', ident), ('separately_written', [r for r in pairs if r['kind'] in ('pointer', 'separate', 'near-copy', 'import-plus')])):
    g = [gap_days(r) for r in group]
    g = [x for x in g if x is not None]
    A['near_copies'][f'last_edit_gap_{label}'] = {'n': len(g), 'same_day': sum(1 for x in g if x == 0), 'over_30_days': sum(1 for x in g if x > 30),
                                                 'median_days': statistics.median(g) if g else None}
nc_newer = collections.Counter()
for r in nc:
    c, a = last_dates(r)
    if c and a:
        nc_newer['claude_newer' if c > a else ('agents_newer' if a > c else 'same_day')] += 1
A['near_copies']['near_copy_which_newer'] = dict(nc_newer)

# ---------------- conflicts ----------------
SEP_KINDS = ('pointer', 'separate', 'near-copy', 'import-plus')
IMPORT_KINDS = ('import-shim', 'import-plus')


def own_claude_text(r):
    # for an import, the CLAUDE.md text minus the @AGENTS.md import(s)
    return IMPORT_TOKEN_A.sub('', r['ct'] or '') if r['kind'] in IMPORT_KINDS else r['ct']


def has_own_lines(r):
    # a line besides the import that isn't only a heading, a rule or an HTML comment
    return any(not re.match(r'^(?:#{1,6}(?:\s|$)|[-*_]{3,}$|<!--.*-->$)', l) for l in norm_lines(own_claude_text(r)))


# 9 Nov: import shims (10 lines or fewer) whose CLAUDE.md says something of its own are scanned too. On 5 Nov they
# weren't, so a two-line file with the import and a rule that contradicts AGENTS.md was never compared.
sep = [r for r in pairs if r['kind'] in SEP_KINDS or (r['kind'] == 'import-shim' and has_own_lines(r))]


flags = {'pm': [], 'pypm': [], 'test': [], 'fmt': [], 'style': [], 'ban': [], 'commit': []}
both_say = collections.Counter()   # pairs where both files state something comparable (the denominators)
one_says = collections.Counter()   # pairs where only one of the two files states it
for r in sep:
    ct, at = own_claude_text(r), r['at']
    for key, table in (('pm', JS_PM), ('pypm', PY_PM)):
        cc, ac = pm_counts(ct, table), pm_counts(at, table)
        dc, da = dominant(cc), dominant(ac)
        if cc and ac:
            both_say[key] += 1; r.setdefault('say', {})[key] = 'both'
        elif cc or ac:
            one_says[key] += 1; r.setdefault('say', {})[key] = 'one'
        if dc and da and dc != da:
            flags[key].append((r, cc, ac))
    tc, ta = test_cmds(ct), test_cmds(at)
    if set(tc) & set(ta):
        both_say['test'] += 1; r.setdefault('say', {})['test'] = 'both'
    elif tc or ta:
        one_says['test'] += 1; r.setdefault('say', {})['test'] = 'one'
    for eco in set(tc) & set(ta):
        if not (tc[eco] & ta[eco]):
            flags['test'].append((r, eco, sorted(tc[eco]), sorted(ta[eco])))
    fc, fa = formatters(ct), formatters(at)
    if set(fc) & set(fa):
        both_say['fmt'] += 1; r.setdefault('say', {})['fmt'] = 'both'
    elif fc or fa:
        one_says['fmt'] += 1; r.setdefault('say', {})['fmt'] = 'one'
    for eco in set(fc) & set(fa):
        if not (fc[eco] & fa[eco]):
            flags['fmt'].append((r, eco, sorted(fc[eco]), sorted(fa[eco])))
    sc, sa = style_values(ct), style_values(at)
    if set(sc) & set(sa):
        both_say['style'] += 1; r.setdefault('say', {})['style'] = 'both'
    elif sc or sa:
        one_says['style'] += 1; r.setdefault('say', {})['style'] = 'one'
    for dim in set(sc) & set(sa):
        if not (sc[dim] & sa[dim]):
            flags['style'].append((r, dim, sorted(sc[dim]), sorted(sa[dim])))
    bc, alc = banned_and_allowed(ct); ba, ala = banned_and_allowed(at)
    if bc or ba:
        both_say['ban_any_side'] += 1; r.setdefault('say', {})['ban_any_side'] = 'both'
    hits = sorted((bc & ala) - ba) + sorted((ba & alc) - bc)
    if hits:
        flags['ban'].append((r, sorted((bc & ala) - ba), sorted((ba & alc) - bc)))
    nc_, pc_ = commit_policy(ct); na_, pa_ = commit_policy(at)
    if (nc_ or pc_) and (na_ or pa_):
        both_say['commit'] += 1; r.setdefault('say', {})['commit'] = 'both'
    elif nc_ or pc_ or na_ or pa_:
        one_says['commit'] += 1; r.setdefault('say', {})['commit'] = 'one'
    if (nc_ and pa_ and not na_) or (na_ and pc_ and not nc_):
        flags['commit'].append((r, (nc_, pc_), (na_, pa_)))
A['conflicts'] = {'pairs_with_separately_written_content': len(sep),
                  'import_shims_with_own_lines_scanned': sum(1 for r in sep if r['kind'] == 'import-shim'),
                  'import_shims_import_only': sum(1 for r in pairs if r['kind'] == 'import-shim' and not has_own_lines(r)),
                  'auto_flags': {k: len(v) for k, v in flags.items()},
                  'both_files_state_it': dict(both_say), 'only_one_file_states_it': dict(one_says)}
# omissions among "two full rule files": both files have 20+ non-empty lines of their own content
full = [r for r in sep if len(norm_lines(own_claude_text(r))) >= 20 and len(norm_lines(r['at'])) >= 20]
om = collections.Counter()
for r in full:
    ct, at = own_claude_text(r), r['at']
    tc, ta = test_cmds(ct), test_cmds(at)
    pc, pa = pm_counts(ct, JS_PM) or pm_counts(ct, PY_PM), pm_counts(at, JS_PM) or pm_counts(at, PY_PM)
    om['test_both'] += bool(tc and ta); om['test_one'] += bool(tc) != bool(ta); om['test_none'] += not tc and not ta
    om['pm_both'] += bool(pc and pa); om['pm_one'] += bool(pc) != bool(pa); om['pm_none'] += not pc and not pa
    om['test_only_claude'] += bool(tc) and not ta; om['test_only_agents'] += bool(ta) and not tc
A['conflicts']['two_full_files'] = dict(n=len(full), **om)
A['conflicts']['two_full_files_kinds'] = dict(collections.Counter(r['kind'] for r in full))
js_full = sorted(similarity(own_claude_text(r), r['at'])[0] for r in full if r['kind'] != 'near-copy')
A['conflicts']['two_full_files_not_copies_median_shared_lines_jaccard'] = statistics.median(js_full) if js_full else None
# one-sided rules among unconnected pairs that are both full rule files (the original's agg/omissions.json)
A['omissions'] = {}
for label, kinds_ in (('not_connected_no_pointer', ('separate', 'near-copy')), ('pointer', ('pointer',)), ('all_unconnected', ('separate', 'near-copy', 'pointer'))):
    sub = [r for r in pairs if r['kind'] in kinds_ and len(norm_lines(r['ct'])) >= 20 and len(norm_lines(r['at'])) >= 20]
    c = collections.Counter()
    for r in sub:
        tc, ta = test_cmds(r['ct']), test_cmds(r['at'])
        pc = pm_counts(r['ct'], JS_PM) or pm_counts(r['ct'], PY_PM); pa = pm_counts(r['at'], JS_PM) or pm_counts(r['at'], PY_PM)
        c['test_one'] += bool(tc) != bool(ta); c['test_both'] += bool(tc and ta); c['pm_one'] += bool(pc) != bool(pa); c['pm_both'] += bool(pc and pa)
    A['omissions'][label] = dict(n=len(sub), **c)
_one = collections.Counter(norm_lines(r['ct'])[0] for r in pairs if r['kind'] == 'import-shim' and len(norm_lines(r['ct'])) == 1)
A['omissions']['one_line_imports'] = {'n': sum(_one.values()), 'exactly_@AGENTS.md': _one.get('@AGENTS.md', 0)}   # counts only, no texts kept

# lockfile / packageManager agreement, per instruction file
LOCK = {'pnpm-lock.yaml': 'pnpm', 'package-lock.json': 'npm', 'yarn.lock': 'yarn', 'bun.lockb': 'bun', 'bun.lock': 'bun'}
lock_rows = []
for r in pairs:
    locks = {pm for f, pm in LOCK.items() if f in r['ent']}
    pmf = (((r['b'] or {}).get('pkg') or {}).get('slim') or {}).get('packageManager')
    truth = None
    if pmf:
        truth = pmf.split('@')[0]
    elif len(locks) == 1:
        truth = next(iter(locks))
    if not truth:
        continue
    for label, t, sym in (('CLAUDE.md', own_claude_text(r), is_sym(r['ent'], 'CLAUDE.md')), ('AGENTS.md', r['at'], is_sym(r['ent'], 'AGENTS.md'))):
        if sym:
            continue
        d = dominant(pm_counts(t, JS_PM))
        if d:
            lock_rows.append((r, label, d, truth))
A['conflicts']['files_naming_js_pm_with_known_repo_pm'] = len(lock_rows)
A['conflicts']['files_whose_dominant_pm_differs_from_repo'] = sum(1 for x in lock_rows if x[2] != x[3])

csz_all = [r['b']['c']['byteSize'] for r in repos if has(r, 'CLAUDE.md') and not is_sym(r['ent'], 'CLAUDE.md')
           and r['b'] and not r['b'].get('missing') and (r['b'].get('c') or {}).get('byteSize') is not None]
csz_pairs = [len((r['ct'] or '').encode()) for r in pairs if not is_sym(r['ent'], 'CLAUDE.md')]
A['pairs']['claude_md_sizes'] = {
    'all_root_regular': {'n': len(csz_all), 'median_bytes': statistics.median(csz_all) if csz_all else None,
                         'share_under_100_bytes': round(sum(1 for s in csz_all if s < 100) / len(csz_all), 3) if csz_all else None},
    'in_pairs_regular': {'n': len(csz_pairs), 'median_bytes': statistics.median(csz_pairs) if csz_pairs else None,
                         'share_under_100_bytes': round(sum(1 for s in csz_pairs if s < 100) / len(csz_pairs), 3) if csz_pairs else None}}
A['pairs']['claude_md_exactly_one_import_line'] = sum(1 for r in pairs if r['kind'] == 'import-shim' and len(norm_lines(r['ct'])) == 1)
# is the one-line @AGENTS.md import the most common root CLAUDE.md text in the whole sample? (counts only, no texts kept)
_ctexts = collections.Counter('\n'.join(norm_lines(r['b']['c'].get('text'))) for r in repos if has(r, 'CLAUDE.md') and not is_sym(r['ent'], 'CLAUDE.md')
                              and r['b'] and not r['b'].get('missing') and (r['b'].get('c') or {}).get('text') is not None)
_top = _ctexts.most_common(2)
A['pairs']['most_common_root_claude_md_text'] = {'regular_root_claude_md_with_text': sum(_ctexts.values()),
                                                 'top_is_exactly_@AGENTS.md': bool(_top) and _top[0][0] == '@AGENTS.md',
                                                 'top_count': _top[0][1] if _top else 0, 'second_count': _top[1][1] if len(_top) > 1 else 0,
                                                 'exactly_@AGENTS.md_any_repo': _ctexts.get('@AGENTS.md', 0)}
# small root CLAUDE.md files (regular files under 100 bytes) and how many of them import AGENTS.md
small_c = [r for r in repos if has(r, 'CLAUDE.md') and not is_sym(r['ent'], 'CLAUDE.md') and r['b'] and not r['b'].get('missing')
           and (r['b'].get('c') or {}).get('byteSize') is not None and r['b']['c']['byteSize'] < 100]
A['pairs']['claude_md_under_100_bytes'] = {'n': len(small_c), 'with_AGENTS.md_import': sum(1 for r in small_c if 'AGENTS.md' in import_targets(r['b']['c'].get('text') or ''))}

# ---------------- size ----------------
size_rows = []
for r in repos:
    if not has(r, 'AGENTS.md') or not r['b'] or r['b'].get('missing'):
        continue
    a = r['b'].get('a') or {}
    if is_sym(r['ent'], 'AGENTS.md'):
        tgt = link_target(a.get('text'))
        if tgt == 'CLAUDE.md' and not is_sym(r['ent'], 'CLAUDE.md'):
            sz = (r['b'].get('c') or {}).get('byteSize')
        else:
            sz = None
    else:
        sz = a.get('byteSize')
    size_rows.append((r, sz))
known = [(r, s) for r, s in size_rows if s is not None]
over = [(r, s) for r, s in known if s > LIMIT]
A['size']['root_AGENTS.md_known_size'] = len(known)
# 9 Nov: why the size denominator is smaller than the count of root AGENTS.md files
A['size']['root_AGENTS.md_read'] = len(size_rows)
A['size']['root_AGENTS.md_size_unknown'] = dict(collections.Counter(
    'symlink, not to a regular root CLAUDE.md' if is_sym(r['ent'], 'AGENTS.md') else 'no size returned' for r, s in size_rows if s is None))
A['size']['root_AGENTS.md_over_32KiB'] = dict(share(len(over), len(known)), boot95=boot([r for r, s in known], lambda r, ids={x[0]['id'] for x in over}: r['id'] in ids))
A['size']['root_AGENTS.md_over_16KiB'] = share(sum(1 for r, s in known if s > 16384), len(known))
A['size']['root_AGENTS.md_median_bytes'] = statistics.median([s for r, s in known]) if known else None
A['size']['root_AGENTS.md_p90_bytes'] = sorted(s for r, s in known)[int(0.9 * len(known))] if known else None
A['size']['root_AGENTS.md_max_bytes'] = max((s for r, s in known), default=None)
BINS = [(0, 1024, 'up to 1 KiB'), (1024, 4096, '1-4 KiB'), (4096, 8192, '4-8 KiB'), (8192, 16384, '8-16 KiB'),
        (16384, 32768, '16-32 KiB'), (32768, 65536, '32-64 KiB'), (65536, 10 ** 12, 'over 64 KiB')]
A['size']['root_AGENTS.md_bins'] = {lab: sum(1 for r, s in known if lo < s <= hi or (lo == 0 and s <= hi)) for lo, hi, lab in BINS}
A['size']['over_32KiB_by_star_band'] ={b: share(sum(1 for r, s in known if star_band(r['stars']) == b and s > LIMIT), sum(1 for r, s in known if star_band(r['stars']) == b)) for b in ('10-49', '50-499', '500+')}

# nested chains (Codex: one file per directory from root to cwd; AGENTS.override.md wins in its directory)
chain_stats = collections.Counter()
nested_repos = 0
over_combined_only = 0
over_any = 0
trees_ok = 0
nested_sym = 0
nested_counts = []
for r, sz in size_rows:
    t = r['t']
    if not t:
        chain_stats['tree_not_fetched'] += 1; r['tree_status'] = 'not_fetched'; continue
    if t.get('error'):
        chain_stats['tree_error'] += 1; r['tree_status'] = 'error'; continue
    if t.get('truncated'):
        chain_stats['tree_truncated'] += 1; r['tree_status'] = 'truncated'; continue
    trees_ok += 1; r['tree_status'] = 'ok'
    per_dir = {}
    for k in t['keep']:
        name = k['path'].rsplit('/', 1)[-1]
        if name not in ('AGENTS.md', 'AGENTS.override.md') or k['type'] != 'blob':
            continue
        d = k['path'].rsplit('/', 1)[0] if '/' in k['path'] else ''
        s = k['size']
        if k['mode'] == '120000':
            nested_sym += 1 if d else 0
            s = sz if d == '' else None
        per_dir.setdefault(d, {})[name] = s
    if '' in per_dir and per_dir[''].get('AGENTS.md') is None and 'AGENTS.override.md' not in per_dir['']:
        per_dir['']['AGENTS.md'] = sz
    nested = [d for d in per_dir if d != '']
    nested_counts.append(len(nested)); r['nested_n'] = len(nested)
    if nested:
        nested_repos += 1

    def eff(d):
        x = per_dir.get(d) or {}
        if 'AGENTS.override.md' in x:
            return x['AGENTS.override.md'] or 0
        return x.get('AGENTS.md') or 0

    worst = 0
    for d in per_dir:
        parts = d.split('/') if d else []
        chain = [''] + ['/'.join(parts[:i + 1]) for i in range(len(parts))]
        worst = max(worst, sum(eff(x) for x in chain))
    root_eff = eff('')
    if worst > LIMIT:
        over_any += 1
        if root_eff <= LIMIT:
            over_combined_only += 1
    r['chain_over'] = worst > LIMIT; r['chain_over_only_combined'] = worst > LIMIT and root_eff <= LIMIT
A['size']['trees_checked'] = trees_ok
A['size']['tree_issues'] = dict(chain_stats)
A['size']['repos_with_nested_AGENTS.md'] = share(nested_repos, trees_ok)
A['size']['nested_AGENTS.md_per_repo_max'] = max(nested_counts) if nested_counts else None
A['size']['nested_symlinks_ignored'] = nested_sym
A['size']['repos_over_32KiB_root_or_combined'] = share(over_any, trees_ok)
A['size']['repos_over_32KiB_only_when_combined'] = share(over_combined_only, trees_ok)

# ---------------- override ----------------
ov_root = sum(1 for r in repos if has(r, 'AGENTS.override.md'))
ov_any = 0
for r, sz in size_rows:
    t = r['t']
    if t and not t.get('error') and any(k['path'].rsplit('/', 1)[-1] == 'AGENTS.override.md' for k in t.get('keep', [])):
        ov_any += 1; r['override_any'] = True
A['override'] = {'root_override_in_frame': share(ov_root, len(repos)), 'root_override_among_root_AGENTS.md': share(ov_root, nA),
                 'any_override_among_tree_checked_AGENTS.md_repos': share(ov_any, trees_ok)}

# ---------------- skills ----------------
def skills_state(r, key, dirkey):
    """'dir', 'symlink:<target>', or None for .claude/skills (key='dcs') or .agents/skills (key='das')."""
    b = r['b'] or {}
    top = b.get(dirkey) or {}
    if top.get('__typename') == 'Blob':
        return 'parent-symlink:' + link_target(top.get('text'))
    x = b.get(key)
    if not x:
        return None
    if x.get('__typename') == 'Blob':
        return 'symlink:' + link_target(x.get('text'))
    return 'dir'


def skill_link_into(e, here, other):
    """A per-skill symlink whose target resolves inside the other agent's skills folder."""
    t = link_target(((e.get('object') or {}).get('text')) or '')
    return bool(t) and posixpath.normpath(posixpath.join(here, t)).startswith(other + '/')


sk = collections.Counter(); sk_detail = collections.Counter(); per_skill_links = 0; both_dirs_rows = []
for r in repos:
    if not r['b'] or r['b'].get('missing'):
        continue
    cs, as_ = skills_state(r, 'dcs', 'dc'), skills_state(r, 'das', 'da')
    if not cs and not as_:
        continue
    if cs and as_:
        if cs.startswith('symlink:') and '.agents/skills' in cs:
            _k = 'both: .claude/skills -> .agents/skills symlink'; sk[_k] += 1; r['skills_state'] = _k
        elif as_.startswith('symlink:') and '.claude/skills' in as_:
            _k = 'both: .agents/skills -> .claude/skills symlink'; sk[_k] += 1; r['skills_state'] = _k
        elif cs.startswith('parent-symlink') or as_.startswith('parent-symlink'):
            # 9 Nov: count it as linked only if .claude points at .agents or the reverse
            _par = lambda st, other: st.startswith('parent-symlink:') and posixpath.normpath(st[len('parent-symlink:'):] or '.') == other
            _k = 'both: parent directory symlinked' if (_par(cs, '.agents') or _par(as_, '.claude')) else 'both: a folder links somewhere else'
            sk[_k] += 1; r['skills_state'] = _k
        elif cs.startswith('symlink:') or as_.startswith('symlink:'):
            # 9 Nov: a skills folder that is a symlink to somewhere other than the other agent's folder. On 5 Nov
            # these fell through to "two real directories" with nothing to compare.
            tc = posixpath.normpath(posixpath.join('.claude', cs[len('symlink:'):])) if cs.startswith('symlink:') else '.claude/skills'
            ta = posixpath.normpath(posixpath.join('.agents', as_[len('symlink:'):])) if as_.startswith('symlink:') else '.agents/skills'
            _k = 'both: both folders link to one third folder' if tc == ta else 'both: a folder links somewhere else'
            sk[_k] += 1; r['skills_state'] = _k
        else:
            ce = [e for e in ((r['b'].get('dcs') or {}).get('entries') or [])]
            ae = [e for e in ((r['b'].get('das') or {}).get('entries') or [])]
            cl, al = [e for e in ce if e['mode'] == GQL_SYMLINK], [e for e in ae if e['mode'] == GQL_SYMLINK]
            links = len(cl) + len(al)
            # 9 Nov: follow each per-skill symlink; on 5 Nov the mode alone was counted, wherever the link pointed
            cross = sum(skill_link_into(e, '.claude/skills', '.agents/skills') for e in cl) + sum(skill_link_into(e, '.agents/skills', '.claude/skills') for e in al)
            cn, an = {e['name'] for e in ce}, {e['name'] for e in ae}
            if links and (all(e['mode'] == GQL_SYMLINK for e in ce) or all(e['mode'] == GQL_SYMLINK for e in ae)):
                _k = 'both: every skill in one dir is a symlink'; sk[_k] += 1; r['skills_state'] = _k
                r['skills_links_into_other'] = 'all' if cross == links else ('some' if cross else 'none')
            elif links:
                _k = 'both: some skills symlinked'; sk[_k] += 1; r['skills_state'] = _k
                r['skills_links_into_other'] = 'all' if cross == links else ('some' if cross else 'none')
            else:
                _k = 'both: two real directories'; sk[_k] += 1; r['skills_state'] = _k
                # 9 Nov: a same-named skill folder counts as a copy only if its git tree hash matches (same files,
                # same contents); on 5 Nov matching names were enough
                co, ao = {e['name']: e.get('oid') for e in ce}, {e['name']: e.get('oid') for e in ae}
                shared = cn & an
                same_content = sum(1 for n in shared if co.get(n) and co.get(n) == ao.get(n))
                both_dirs_rows.append((cn, an, same_content, len(shared)))
                r['skills_two_dirs'] = 'same' if cn == an else ('partial' if cn & an else 'disjoint')
                r['skills_same_name'] = len(shared); r['skills_same_name_identical'] = same_content
    elif cs:
        _k = 'only .claude/skills' + (' (symlink)' if cs.startswith('symlink') else ''); sk[_k] += 1; r['skills_state'] = _k
    else:
        _k = 'only .agents/skills' + (' (symlink)' if as_.startswith('symlink') else ''); sk[_k] += 1; r['skills_state'] = _k
A['skills']['repos_with_any_skills_dir'] = sum(sk.values())
A['skills']['breakdown'] = dict(sk.most_common())
if both_dirs_rows:
    same = sum(1 for cn, an, _, _ in both_dirs_rows if cn == an)
    overlap = sum(1 for cn, an, _, _ in both_dirs_rows if cn != an and cn & an)
    A['skills']['two_real_dirs_same_skill_names'] = same
    A['skills']['two_real_dirs_partial_overlap'] = overlap
    A['skills']['two_real_dirs_disjoint'] = len(both_dirs_rows) - same - overlap
    A['skills']['two_real_dirs_same_names_every_folder_identical'] = sum(1 for cn, an, ident, n in both_dirs_rows if cn == an and n and ident == n)
    A['skills']['two_real_dirs_same_names_some_folder_differs'] = sum(1 for cn, an, ident, n in both_dirs_rows if cn == an and ident < n)
    A['skills']['same_named_skill_folders'] = {'n': sum(n for _, _, _, n in both_dirs_rows), 'identical': sum(i for _, _, i, _ in both_dirs_rows)}
_lk = collections.Counter(r['skills_links_into_other'] for r in repos if r.get('skills_links_into_other'))
A['skills']['symlinked_skills_point_into_other_dir'] = dict(_lk)
A['skills']['denominator_frame_repos'] = len(repos)
A['skills']['among_both_root_files'] = dict(collections.Counter(
    ('claude' if skills_state(r, 'dcs', 'dc') else '') + ('+agents' if skills_state(r, 'das', 'da') else '') or 'none' for r in pairs))

# ---------------- output ----------------
if MODE == 'agg':
    json.dump(A, open(os.path.join(AGG, 'study_aggregates.json'), 'w'), indent=1, default=list)
    print(json.dumps(A, indent=1, default=list)[:20000])


# ---------------- manual review helpers (anonymised) ----------------
# REVIEW_FULL=1 (added 9 Nov 2026) prints whole lines and every differing line, so nothing past the cut is missed
CUT = None if os.environ.get('REVIEW_FULL') else 170
NMAX = None if os.environ.get('REVIEW_FULL') else 10


def show_lines(label, t, pat, n=4):
    hits = [l.strip()[:CUT] for l in (t or '').splitlines() if re.search(pat, l, re.I)][:n]
    for h in hits:
        print(f'      {label}: {h}')


if MODE == 'review':
    if WHAT in ('pm', 'pypm'):
        table = JS_PM if WHAT == 'pm' else PY_PM
        pat = '|'.join(table.values())
        for i, (r, cc, ac) in enumerate(flags[WHAT]):
            locks = {pm for f, pm in LOCK.items() if f in r['ent']}
            pmf = (((r['b'] or {}).get('pkg') or {}).get('slim') or {}).get('packageManager')
            print(f'#{i} [{anon(r["id"])}] kind={r["kind"]} CLAUDE {cc} | AGENTS {ac} | locks {sorted(locks)} pmfield {pmf}')
            show_lines('C', own_claude_text(r), pat); show_lines('A', r['at'], pat)
    elif WHAT == 'test':
        for i, (r, eco, a, b) in enumerate(flags['test']):
            print(f'#{i} [{anon(r["id"])}] kind={r["kind"]} {eco}: CLAUDE {a} | AGENTS {b}')
            pat = '|'.join(p for p, e, c in TEST_RULES if e == eco)
            show_lines('C', own_claude_text(r), pat, 3); show_lines('A', r['at'], pat, 3)
    elif WHAT in ('fmt', 'style'):
        for i, (r, eco, a, b) in enumerate(flags[WHAT]):
            print(f'#{i} [{anon(r["id"])}] kind={r["kind"]} {eco}: CLAUDE {a} | AGENTS {b}')
            pat = '|'.join(a + b) if WHAT == 'fmt' else {'indent': 'indent', 'quotes': 'quot', 'semicolons': 'semi', 'line length': r'line|width|char|column'}[eco]
            show_lines('C', own_claude_text(r), pat, 3); show_lines('A', r['at'], pat, 3)
    elif WHAT == 'ban':
        for i, (r, cb, ab) in enumerate(flags['ban']):
            print(f'#{i} [{anon(r["id"])}] kind={r["kind"]} banned in CLAUDE, allowed in AGENTS: {cb} | banned in AGENTS, allowed in CLAUDE: {ab}')
            def ban_lines(t, cmd):
                out = []
                for l in (t or '').splitlines():
                    for m in re.finditer(r'`([^`\n]{2,80})`', l):
                        if norm_cmd(m.group(1)) == cmd and NEG_CMD.search(l[max(0, m.start() - 60):m.start()]):
                            out.append(l.strip()[:200])
                return out[:2]
            for cmd in cb:
                for x in ban_lines(own_claude_text(r), cmd): print('      C-ban:', x)
                show_lines('A-use', r['at'], re.escape(cmd), 2)
            for cmd in ab:
                for x in ban_lines(r['at'], cmd): print('      A-ban:', x)
                show_lines('C-use', own_claude_text(r), re.escape(cmd), 2)
    elif WHAT == 'commit':
        for i, (r, c, a) in enumerate(flags['commit']):
            print(f'#{i} [{anon(r["id"])}] kind={r["kind"]} CLAUDE neg/pos {c} | AGENTS neg/pos {a}')
            show_lines('C', own_claude_text(r), r'commit|push', 4); show_lines('A', r['at'], r'commit|push', 4)
    elif WHAT == 'near':
        import difflib
        for i, r in enumerate(nc):
            c, a = last_dates(r)
            print(f'#{i} [{anon(r["id"])}] jac={r["det"]["jaccard"]} only_c={r["det"]["only_c"]} only_a={r["det"]["only_a"]} lastC={c} lastA={a}')
            cl = norm_lines(r['ct']); al = norm_lines(r['at'])
            cm = {mask_tools(x) for x in cl}; am = {mask_tools(x) for x in al}
            oc = [x for x in cl if mask_tools(x) not in am][:NMAX]
            oa = [x for x in al if mask_tools(x) not in cm][:NMAX]
            for x in oc: print('      C+', x[:CUT])
            for x in oa: print('      A+', x[:CUT])
    elif WHAT == 'pointer':
        rng = random.Random(3)
        for i, r in enumerate(rng.sample(ptr, min(40, len(ptr)))):
            print(f'#{i} [{anon(r["id"])}] c_ptr={r["det"]["c_ptr"]} a_ptr={r["det"]["a_ptr"]} c_lines={r["det"]["c_lines"]}')
            show_lines('C', r['ct'], r'agents\.md', 2); show_lines('A', r['at'], r'claude\.md', 2)
    elif WHAT == 'lock':
        for i, (r, label, d, truth) in enumerate(x for x in lock_rows if x[2] != x[3]):
            print(f'#{i} [{anon(r["id"])}] {label} says {d}, repo uses {truth}')
            show_lines(label[0], own_claude_text(r) if label == 'CLAUDE.md' else r['at'], '|'.join(JS_PM.values()), 3)
