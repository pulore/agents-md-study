# Recompute the study's counts and bootstrap intervals from the kept per-repo labels alone, and check them
# against the aggregates the analysis wrote from the raw data.
#   python3 verify_from_labels.py LABELS_DIR AGGREGATES_DIR
# Needs only repo_labels.csv, day_clusters.json and the aggregate JSON files: no API calls, no raw data.
# Prints one line per check and exits 1 if any recomputed number differs.
import collections, csv, json, os, random, statistics, sys

LAB, AGGD = sys.argv[1], sys.argv[2]
rows = list(csv.DictReader(open(os.path.join(LAB, 'repo_labels.csv'))))
D = json.load(open(os.path.join(LAB, 'day_clusters.json')))
A = json.load(open(os.path.join(AGGD, 'study_aggregates.json')))
M = json.load(open(os.path.join(AGGD, 'manual_review.json')))
O = json.load(open(os.path.join(AGGD, 'oversize_config.json')))
KEYS = D['day_clusters_in_bootstrap_order']
one = lambda r, c: r[c] == '1'
bad = []


def boot(items, num, den=lambda r: True, B=2000, seed=7):
    by = collections.defaultdict(lambda: [0, 0])
    for r in items:
        if den(r):
            by[r['day']][1] += 1
            if num(r):
                by[r['day']][0] += 1
    rng = random.Random(seed); vals = []
    for _ in range(B):
        s = [by[KEYS[rng.randrange(len(KEYS))]] for _ in KEYS]
        n_ = sum(x[0] for x in s); d_ = sum(x[1] for x in s)
        if d_:
            vals.append(n_ / d_)
    vals.sort()
    return [round(100 * vals[int(0.025 * len(vals))], 1), round(100 * vals[int(0.975 * len(vals)) - 1], 1)]


def check(name, got, want):
    ok = got == want
    if not ok:
        bad.append(name)
    print(f"{'OK  ' if ok else 'DIFF'} {name}: labels {got} | aggregates {want}")


F = A['frame']
check('frame repos', len(rows), F['repos'])
for col, key in (('claude_md', 'root_CLAUDE.md'), ('agents_md', 'root_AGENTS.md'), ('dot_claude_dir', 'has_.claude_dir'),
                 ('dot_agents_dir', 'has_.agents_dir'), ('dot_codex_dir', 'has_.codex_dir')):
    check(f'frame {key}', sum(one(r, col) for r in rows), F[key]['k'])
both = lambda r: one(r, 'claude_md') and one(r, 'agents_md')
check('frame both_root', sum(both(r) for r in rows), F['both_root']['k'])
check('frame both_root 95% interval', boot(rows, both), F['both_root_boot95'])
for band, v in F['by_star_band'].items():
    sub = [r for r in rows if r['stars_band'] == band]
    check(f'frame stars {band}', {'repos': len(sub), 'claude': sum(one(r, 'claude_md') for r in sub), 'agents': sum(one(r, 'agents_md') for r in sub), 'both': sum(both(r) for r in sub)}, v)
for yb, v in F['by_created_year'].items():
    sub = [r for r in rows if r['created_bucket'] == yb]
    check(f'frame created {yb}', {'repos': len(sub), 'claude': sum(one(r, 'claude_md') for r in sub), 'agents': sum(one(r, 'agents_md') for r in sub), 'both': sum(both(r) for r in sub)}, v)

P = A['pairs']
pairs = [r for r in rows if r['pair_kind'] not in ('', 'missing-text')]
check('pairs n', len(pairs), P['n'])
check('pairs missing text', sum(r['pair_kind'] == 'missing-text' for r in rows), P['missing_text'])
for k, v in P['kinds'].items():
    check(f'kind {k}', sum(r['pair_kind'] == k for r in pairs), v['k'])
    check(f'kind {k} 95% interval', boot(pairs, lambda r, k=k: r['pair_kind'] == k), v['boot95'])
wired = lambda r: r['pair_kind'] in ('symlink', 'import-shim', 'import-plus')
check('connected', sum(wired(r) for r in pairs), P['wired']['k'])
check('not connected', sum(not wired(r) for r in pairs), P['not_wired']['k'])
check('not connected 95% interval', boot(pairs, lambda r: not wired(r)), P['not_wired']['boot95'])
check('connected 95% interval', boot(pairs, wired), P['wired']['boot95'])
copies = lambda r: r['pair_kind'] in ('identical', 'near-copy')
check('copies', sum(copies(r) for r in pairs), P['copies']['k'])
check('copies 95% interval', boot(pairs, copies), P['copies']['boot95'])
check('symlink directions', dict(collections.Counter(r['pair_symlink_dir'] for r in pairs if r['pair_kind'] == 'symlink')), P['symlink_dirs'])
ptr = [r for r in pairs if r['pair_kind'] == 'pointer']
check('pointer directions', {'claude_mentions_agents_only': sum(one(r, 'pair_ptr_claude') and not one(r, 'pair_ptr_agents') for r in ptr),
                             'agents_mentions_claude_only': sum(one(r, 'pair_ptr_agents') and not one(r, 'pair_ptr_claude') for r in ptr),
                             'both_mention': sum(one(r, 'pair_ptr_claude') and one(r, 'pair_ptr_agents') for r in ptr),
                             'short_claude_pointer_le5_lines': sum(one(r, 'pair_claude_le5_lines') for r in ptr)}, P['pointer_dirs'])
check('broken import in code', sum(one(r, 'pair_broken_import_in_code') for r in pairs), P['broken_import_in_code'])
check('AGENTS.md with @CLAUDE.md', sum(one(r, 'pair_agents_imports_claude') for r in pairs), P['agents_imports_claude'])
check('symlink checked in as text', sum(one(r, 'pair_symlink_as_text') for r in pairs), P['symlink_checked_in_as_text'])
check('near-miss imports', sum(one(r, 'pair_near_miss_import') for r in pairs), P['near_miss_import'])
check('looser regex says import, parser says no', sum(one(r, 'pair_loose_regex_import') and not r['pair_kind'].startswith('import') for r in pairs), P['loose_regex_vs_parser']['loose_import_parser_not'])
check('parser says import, looser regex says no', sum(r['pair_kind'].startswith('import') and not one(r, 'pair_loose_regex_import') for r in pairs), P['loose_regex_vs_parser']['parser_import_loose_not'])
check('one-line import CLAUDE.md', sum(one(r, 'pair_one_line_import') for r in pairs), P['claude_md_exactly_one_import_line'])
check('one line exactly @AGENTS.md', sum(one(r, 'pair_one_line_exact') for r in pairs), A['omissions']['one_line_imports']['exactly_@AGENTS.md'])
for band, v in P['by_star_band'].items():
    sub = [r for r in pairs if r['stars_band'] == band]
    check(f'not connected, stars {band}', [sum(not wired(r) for r in sub), len(sub)], [v['not_wired']['k'], v['not_wired']['n']])
sub = [r for r in pairs if r['stars_band'] in ('10-49', '50-499')]
check('not connected, 10-499 stars', [sum(not wired(r) for r in sub), len(sub)], [P['not_wired_10_499_stars']['k'], P['not_wired_10_499_stars']['n']])
check('.claude/CLAUDE.md kinds', dict(collections.Counter(r['dotc_kind'] for r in rows if r['dotc_kind'])), P['dot_claude_CLAUDE.md_with_AGENTS.md_no_root_CLAUDE.md']['kinds'])
check('committed CLAUDE.local.md', sum(one(r, 'root_claude_local') for r in rows), P['committed_CLAUDE.local.md_any'])
reg = [r for r in rows if r['claude_md_lt100'] != '']
check('regular root CLAUDE.md read', len(reg), P['claude_md_sizes']['all_root_regular']['n'])
check('share of those under 100 bytes', round(sum(one(r, 'claude_md_lt100') for r in reg) / len(reg), 3) if reg else None, P['claude_md_sizes']['all_root_regular']['share_under_100_bytes'])
check('small CLAUDE.md that import', [sum(one(r, 'claude_md_lt100') for r in reg), sum(one(r, 'claude_md_lt100_imports') for r in reg)],
      [P['claude_md_under_100_bytes']['n'], P['claude_md_under_100_bytes']['with_AGENTS.md_import']])
js = sorted(float(r['pair_jaccard']) for r in pairs if r['pair_jaccard'] != '')
check('separately written median shared lines', statistics.median(js) if js else None, (P['shared_lines_distribution_separate_written'] or {}).get('median_jaccard'))

NC = A['near_copies']
check('identical pairs', sum(r['pair_kind'] == 'identical' for r in pairs), NC['identical'])
check('near-copy pairs', sum(r['pair_kind'] == 'near-copy' for r in pairs), NC['near_copy'])
for label, kinds_ in (('near_copy', ('near-copy',)), ('identical', ('identical',)), ('separately_written', ('pointer', 'separate', 'near-copy', 'import-plus'))):
    g = [int(r['pair_edit_gap_days']) for r in pairs if r['pair_kind'] in kinds_ and r['pair_edit_gap_days'] != '']
    check(f'last-edit gap {label}', {'n': len(g), 'same_day': sum(1 for x in g if x == 0), 'over_30_days': sum(1 for x in g if x > 30),
                                     'median_days': statistics.median(g) if g else None}, NC[f'last_edit_gap_{label}'])
check('near-copy manual labels', dict(collections.Counter(r['pair_near_label'] for r in pairs if r['pair_kind'] == 'near-copy' and r['pair_near_label'] != 'unlabelled')), M['near_copies']['labels'])
for lab_, v in M['near_copies']['last_edit_gap_days_by_label'].items():
    g = [int(r['pair_edit_gap_days']) for r in pairs if r['pair_near_label'] == lab_ and r['pair_edit_gap_days'] != '']
    check(f'near-copy {lab_}: edited on different days', [len(g), sum(1 for x in g if x > 0)], [v['n'], v['different_day']])

C = A['conflicts']
check('separately written pairs', sum(one(r, 'pair_sep_written') for r in pairs), C['pairs_with_separately_written_content'])
for key in ('pm', 'pypm', 'test', 'fmt', 'style', 'commit'):
    check(f'both files state {key}', sum(r['say_' + key] == 'both' for r in pairs), C['both_files_state_it'].get(key, 0))
    check(f'one file states {key}', sum(r['say_' + key] == 'one' for r in pairs), C['only_one_file_states_it'].get(key, 0))
check('either file bans a command', sum(one(r, 'say_ban_any_side') for r in pairs), C['both_files_state_it'].get('ban_any_side', 0))
for key, n in C['auto_flags'].items():
    check(f'automatic flags {key}', sum(r['flag_' + key] != '' for r in pairs), n)
    check(f'manual verdicts {key}', dict(collections.Counter(r['flag_' + key] for r in pairs if r['flag_' + key] != '')), M['conflict_flags'].get(key, {}))
full = [r for r in pairs if one(r, 'pair_full')]
check('two full files', len(full), C['two_full_files']['n'])
fj = sorted(float(r['pair_full_jaccard']) for r in full if r['pair_full_jaccard'] != '')
want = C['two_full_files_not_copies_median_shared_lines_jaccard']
check('two full files, not copies: median shared lines (4 dp)', round(statistics.median(fj), 4) if fj else None, round(want, 4) if want is not None else None)
for label, kinds_ in (('not_connected_no_pointer', ('separate', 'near-copy')), ('pointer', ('pointer',)), ('all_unconnected', ('separate', 'near-copy', 'pointer'))):
    sub = [r for r in pairs if one(r, 'pair_full_unconnected') and r['pair_kind'] in kinds_]
    got = {'n': len(sub), 'test_one': sum(r['pair_om_test'] == 'one' for r in sub), 'test_both': sum(r['pair_om_test'] == 'both' for r in sub),
           'pm_one': sum(r['pair_om_pm'] == 'one' for r in sub), 'pm_both': sum(r['pair_om_pm'] == 'both' for r in sub)}
    check(f'one-sided rules, {label}', got, {k: A['omissions'][label].get(k, 0) for k in got})

S = A['size']
known = [r for r in rows if r['agents_size_kib'] != '']
check('root AGENTS.md with known size', len(known), S['root_AGENTS.md_known_size'])
check('over 32 KiB', sum(one(r, 'agents_over_32k') for r in known), S['root_AGENTS.md_over_32KiB']['k'])
check('over 32 KiB 95% interval', boot(known, lambda r: one(r, 'agents_over_32k')), S['root_AGENTS.md_over_32KiB']['boot95'])
check('over 16 KiB', sum(one(r, 'agents_over_16k') for r in known), S['root_AGENTS.md_over_16KiB']['k'])
check('median root AGENTS.md (KiB, 1 dp, from rounded sizes)', round(statistics.median(float(r['agents_size_kib']) for r in known), 1) if known else None,
      round(S['root_AGENTS.md_median_bytes'] / 1024, 1) if S['root_AGENTS.md_median_bytes'] else None)
check('size bins', dict(collections.Counter(r['agents_size_bin'] for r in known)), {k: v for k, v in S['root_AGENTS.md_bins'].items() if v})
for band, v in S['over_32KiB_by_star_band'].items():
    sub = [r for r in known if r['stars_band'] == band]
    check(f'over 32 KiB, stars {band}', [sum(one(r, 'agents_over_32k') for r in sub), len(sub)], [v['k'], v['n']])
ok_t = [r for r in rows if r['tree_status'] == 'ok']
check('trees listed in full', len(ok_t), S['trees_checked'])
check('tree issues', dict(collections.Counter('tree_' + r['tree_status'] for r in rows if r['tree_status'] not in ('', 'ok'))), S['tree_issues'])
check('repos with nested AGENTS.md', sum(r['nested_bucket'] != '0' for r in ok_t), S['repos_with_nested_AGENTS.md']['k'])
check('over 32 KiB root or combined', sum(one(r, 'chain_over') for r in ok_t), S['repos_over_32KiB_root_or_combined']['k'])
check('over 32 KiB only when combined', sum(one(r, 'chain_over_only_combined') for r in ok_t), S['repos_over_32KiB_only_when_combined']['k'])
OV = A['override']
check('root AGENTS.override.md', sum(one(r, 'root_override') for r in rows), OV['root_override_in_frame']['k'])
check('AGENTS.override.md anywhere in listed trees', sum(one(r, 'override_anywhere') for r in rows), OV['any_override_among_tree_checked_AGENTS.md_repos']['k'])
check('oversize repos checked for .codex/config.toml', sum(one(r, 'codex_cfg_checked') for r in rows), O['oversize_root_repos'])
check('with a committed .codex/config.toml', sum(one(r, 'codex_cfg_present') for r in rows), O['with_committed_.codex/config.toml'])
check('raising project_doc_max_bytes', sum(one(r, 'codex_cfg_raises_limit') for r in rows), O['setting_project_doc_max_bytes'])

SK = A['skills']
check('repos with a skills folder', sum(r['skills_state'] != '' for r in rows), SK['repos_with_any_skills_dir'])
check('skills breakdown', dict(collections.Counter(r['skills_state'] for r in rows if r['skills_state'])), SK['breakdown'])
if 'two_real_dirs_same_skill_names' in SK:
    check('two real skills folders by names', dict(collections.Counter(r['skills_two_dirs'] for r in rows if r['skills_two_dirs'])),
          {k: v for k, v in (('same', SK['two_real_dirs_same_skill_names']), ('partial', SK['two_real_dirs_partial_overlap']), ('disjoint', SK['two_real_dirs_disjoint'])) if v})
check('skills among repos with both files', dict(collections.Counter(r['pair_skills'] for r in pairs)), SK['among_both_root_files'])
# 9 Nov 2026: where per-skill symlinks point, and which same-named skill folders are really the same
check('per-skill symlinks into the other folder', dict(collections.Counter(r['skills_links_into_other'] for r in rows if r.get('skills_links_into_other'))), SK.get('symlinked_skills_point_into_other_dir', {}))
_two = [r for r in rows if r.get('skills_two_dirs')]
if _two and 'same_named_skill_folders' in SK:
    _n = lambda r, c: int(r[c] or 0)
    check('two real folders, same names, every folder identical', sum(r['skills_two_dirs'] == 'same' and _n(r, 'skills_same_name') > 0 and _n(r, 'skills_same_name_identical') == _n(r, 'skills_same_name') for r in _two), SK['two_real_dirs_same_names_every_folder_identical'])
    check('same-named skill folders, identical', {'n': sum(_n(r, 'skills_same_name') for r in _two), 'identical': sum(_n(r, 'skills_same_name_identical') for r in _two)}, SK['same_named_skill_folders'])

print(f'\n{len(bad)} difference(s)' + (': ' + '; '.join(bad) if bad else ''))
sys.exit(1 if bad else 0)
