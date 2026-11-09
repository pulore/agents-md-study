# Write the anonymised per-repo labels: one row per sampled repo, keyed by a salted hash.
#   python3 export_labels.py OUTDIR   -> OUTDIR/repo_labels.csv, OUTDIR/day_clusters.json, OUTDIR/columns.json
# Run it after the manual review (raw/review_labels.json) and oversize_config.py, and before raw/ is deleted.
# What the rows hold: labels and coarse bands only. No repo name, owner, node ID, URL, file text, exact date,
# exact star count or exact byte size. The salt lives in raw/salt.bin and is deleted with raw/, so the hashes
# cannot be linked back to repos afterwards, by us or anyone else.
import csv, json, os, sys
OUTDIR = os.path.abspath(sys.argv[1])
sys.argv = ['analyze.py', 'quiet']
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
exec(open(os.path.join(HERE, 'analyze.py')).read().split('# ---------------- output ----------------')[0])

os.makedirs(OUTDIR, exist_ok=True)
L = json.load(open(os.path.join(RAW, 'review_labels.json'))) if os.path.exists(os.path.join(RAW, 'review_labels.json')) else {}
OC = json.load(open(os.path.join(RAW, 'oversize_config_per_repo.json'))) if os.path.exists(os.path.join(RAW, 'oversize_config_per_repo.json')) else {}

COLUMNS = [
    ('repo', 'salted hash of the repo (12 hex). Salt deleted, so it cannot be linked back to a repo'),
    ('day', 'salted hash of the creation day the repo was drawn on (8 hex). The cluster for the day-level bootstrap'),
    ('stars_band', 'stars when listed: 10-49, 50-499 or 500+'),
    ('created_bucket', 'creation year: 2008-2022, 2023, 2024, 2025 or 2026'),
    ('claude_md', 'root CLAUDE.md on the default branch (1/0)'),
    ('agents_md', 'root AGENTS.md (1/0)'),
    ('claude_md_symlink', 'root CLAUDE.md is a symlink, git mode 120000 (1/0)'),
    ('agents_md_symlink', 'root AGENTS.md is a symlink (1/0)'),
    ('dot_claude_dir', 'root .claude entry (1/0)'),
    ('dot_agents_dir', 'root .agents entry (1/0)'),
    ('dot_codex_dir', 'root .codex entry (1/0)'),
    ('root_override', 'root AGENTS.override.md (1/0)'),
    ('root_claude_local', 'committed root CLAUDE.local.md (1/0)'),
    ('dotc_kind', 'repos with AGENTS.md and .claude/CLAUDE.md but no root CLAUDE.md: how the two relate'),
    ('claude_md_lt100', 'regular root CLAUDE.md under 100 bytes (1/0; blank if no regular root CLAUDE.md was read)'),
    ('claude_md_lt100_imports', 'that small CLAUDE.md imports AGENTS.md, by Claude Code\'s own import parser (1/0)'),
    ('pair_kind', 'repos with both root files: import-shim, import-plus, symlink, pointer, separate, identical, near-copy, symlink-other, missing-text'),
    ('pair_symlink_dir', 'symlink pairs: CLAUDE->AGENTS, AGENTS->CLAUDE or both->third'),
    ('pair_ptr_claude', 'pointer pairs: CLAUDE.md names AGENTS.md (1/0)'),
    ('pair_ptr_agents', 'pointer pairs: AGENTS.md names CLAUDE.md (1/0)'),
    ('pair_claude_le5_lines', 'pointer pairs: CLAUDE.md names AGENTS.md and has 5 or fewer non-empty lines (1/0)'),
    ('pair_one_line_import', 'import-shim whose CLAUDE.md is a single non-empty line (1/0)'),
    ('pair_one_line_exact', 'that single line is exactly @AGENTS.md (1/0)'),
    ('pair_broken_import_in_code', '@AGENTS.md written as an import, but only where Claude Code does not read it: in code or HTML (1/0)'),
    ('pair_agents_imports_claude', 'AGENTS.md has an @CLAUDE.md import that Claude Code\'s parser would read (1/0); Codex reads it as text'),
    ('pair_symlink_as_text', 'a regular file whose whole text is the other file name (1/0). It may be a symlink committed as a plain file, or a deliberate one-line pointer'),
    ('pair_near_miss_import', 'not an import: @AGENTS.md runs into other characters ("@AGENTS.md.", "@AGENTS.md.backup") or follows a non-space such as "(" (1/0)'),
    ('pair_loose_regex_import', 'a looser pattern (@AGENTS.md outside code, ending at a word boundary) counts this CLAUDE.md as importing AGENTS.md (1/0); a check on how much the exact import rule matters'),
    ('pair_jaccard', 'shared-line Jaccard after masking tool names (pairs that reached the similarity step)'),
    ('pair_edit_gap_days', 'days between the last commits to the two files'),
    ('pair_near_label', 'manual label for near-copies: cosmetic, content or contradiction'),
    ('pair_sep_written', 'pair compared for conflicts: pointer, separate, near-copy, import-plus, or an import-shim whose CLAUDE.md has lines of its own besides the import (1/0)'),
    ('pair_full', 'separately written pair where both files have 20+ non-empty lines of their own (1/0)'),
    ('pair_full_jaccard', 'full pairs: shared-line Jaccard of the two files own text'),
    ('pair_full_unconnected', 'separate, near-copy or pointer pair where both files have 20+ non-empty lines (1/0)'),
    ('pair_om_test', 'full unconnected pairs: test command in both files, one file or neither (both/one/none)'),
    ('pair_om_pm', 'full unconnected pairs: package manager named in both, one or neither (both/one/none)'),
    ('say_pm', 'separately written pairs: JavaScript package manager stated in both files or one (both/one/blank)'),
    ('say_pypm', 'same for the Python package manager'),
    ('say_test', 'same for a test command'),
    ('say_fmt', 'same for a formatter'),
    ('say_style', 'same for indentation, quotes, semicolons or line length'),
    ('say_commit', 'same for commit and push rules'),
    ('say_ban_any_side', 'either file bans a command (1/0)'),
    ('flag_pm', 'automatic conflict flag, then the manual verdict: confirmed, false-positive or unreviewed (blank if not flagged)'),
    ('flag_pypm', 'same, Python package manager'),
    ('flag_test', 'same, test command'),
    ('flag_fmt', 'same, formatter'),
    ('flag_style', 'same, style values'),
    ('flag_ban', 'same, a command one file bans and the other runs'),
    ('flag_commit', 'same, commit and push rules'),
    ('pair_skills', 'repos with both root files: skills folders present (none, claude, +agents, claude+agents)'),
    ('agents_blob_read', 'root AGENTS.md whose details were read (1/0)'),
    ('agents_size_kib', 'root AGENTS.md size in KiB, rounded to 0.1 (a symlink to CLAUDE.md takes its size)'),
    ('agents_size_bin', 'size bin used in the chart'),
    ('agents_over_32k', 'root AGENTS.md over 32,768 bytes (1/0)'),
    ('agents_over_16k', 'root AGENTS.md over 16,384 bytes (1/0)'),
    ('tree_status', 'full file tree: ok, truncated, error or not_fetched'),
    ('nested_bucket', 'directories below the root with an AGENTS.md or AGENTS.override.md: 0, 1, 2-5, 6-20, 21+'),
    ('chain_over', 'some root-to-directory chain of AGENTS.md files is over 32 KiB (1/0)'),
    ('chain_over_only_combined', 'over only once nested files are added, root alone under (1/0)'),
    ('override_anywhere', 'an AGENTS.override.md anywhere in the tree (1/0)'),
    ('codex_cfg_checked', 'root AGENTS.md over the limit, so .codex/config.toml was checked (1/0)'),
    ('codex_cfg_present', 'committed .codex/config.toml (1/0)'),
    ('codex_cfg_raises_limit', 'that config sets project_doc_max_bytes (1/0)'),
    ('skills_state', 'skills folders: which of .claude/skills and .agents/skills exist and how they link'),
    ('skills_two_dirs', 'two real skills folders: same, partial or disjoint skill names'),
    ('skills_links_into_other', 'per-skill symlinks: all, some or none of them resolve into the other agent\'s skills folder'),
    ('skills_same_name', 'two real skills folders: number of skill folders with the same name in both'),
    ('skills_same_name_identical', 'of those, how many have the same git tree hash: the same files with the same contents'),
]
B = lambda x: '' if x is None else (1 if x else 0)
pair_ids = {r['id'] for r in pairs}
sep_ids = {r['id'] for r in sep}
full_ids = {r['id'] for r in full}
size_of = {r['id']: s for r, s in size_rows}
in_size_rows = set(size_of)
flag_of = {}
for key, items in flags.items():
    for it in items:
        a = anon(it[0]['id'])
        flag_of.setdefault(it[0]['id'], {})[key] = L.get(a, {}).get('flag_' + key) or 'unreviewed'


def bin_of(sz):
    for lo, hi, lab in BINS:
        if lo < sz <= hi or (lo == 0 and sz <= hi):
            return lab
    return ''


def nested_bucket(n):
    return '' if n is None else ('0' if n == 0 else '1' if n == 1 else '2-5' if n <= 5 else '6-20' if n <= 20 else '21+')


rows = []
for r in repos:
    y = int(r['created'][:4])
    row = {'repo': anon(r['id']), 'day': day_id(r['day']), 'stars_band': star_band(r['stars']),
           'created_bucket': str(y) if y >= 2023 else '2008-2022',
           'claude_md': B(has(r, 'CLAUDE.md')), 'agents_md': B(has(r, 'AGENTS.md')),
           'claude_md_symlink': B(is_sym(r['ent'], 'CLAUDE.md')), 'agents_md_symlink': B(is_sym(r['ent'], 'AGENTS.md')),
           'dot_claude_dir': B(has(r, '.claude')), 'dot_agents_dir': B(has(r, '.agents')), 'dot_codex_dir': B(has(r, '.codex')),
           'root_override': B(has(r, 'AGENTS.override.md')), 'root_claude_local': B(has(r, 'CLAUDE.local.md')),
           'dotc_kind': r.get('dotc_kind', '')}
    b = r['b']
    c = (b or {}).get('c') or {}
    if has(r, 'CLAUDE.md') and not is_sym(r['ent'], 'CLAUDE.md') and b and not b.get('missing') and c.get('byteSize') is not None:
        row['claude_md_lt100'] = B(c['byteSize'] < 100)
        if c['byteSize'] < 100:
            row['claude_md_lt100_imports'] = B('AGENTS.md' in import_targets(c.get('text') or ''))
    if has(r, 'CLAUDE.md') and has(r, 'AGENTS.md'):
        if r['id'] not in pair_ids:
            row['pair_kind'] = 'missing-text'
        else:
            k, d = r['kind'], r['det']
            row['pair_kind'] = k
            row['pair_symlink_dir'] = d.get('dir', '') if k == 'symlink' else ''
            if k == 'pointer':
                row['pair_ptr_claude'] = B(d['c_ptr']); row['pair_ptr_agents'] = B(d['a_ptr'])
                row['pair_claude_le5_lines'] = B(d['c_ptr'] and d['c_lines'] <= 5)
            if k == 'import-shim':
                nl = norm_lines(r['ct'])
                row['pair_one_line_import'] = B(len(nl) == 1)
                row['pair_one_line_exact'] = B(len(nl) == 1 and nl[0] == '@AGENTS.md')
            row['pair_broken_import_in_code'] = B(d.get('broken_import_in_code'))
            row['pair_agents_imports_claude'] = B(d.get('agents_imports_claude'))
            row['pair_symlink_as_text'] = B(d.get('symlink_as_text'))
            row['pair_near_miss_import'] = B(d.get('near_miss_import'))
            row['pair_loose_regex_import'] = B(d.get('loose_regex_import'))
            if 'jaccard' in d:
                row['pair_jaccard'] = d['jaccard']
            g = gap_days(r)
            row['pair_edit_gap_days'] = '' if g is None else g
            if k == 'near-copy':
                row['pair_near_label'] = L.get(anon(r['id']), {}).get('near', 'unlabelled')
            row['pair_sep_written'] = B(r['id'] in sep_ids)
            row['pair_full'] = B(r['id'] in full_ids)
            if r['id'] in full_ids and k != 'near-copy':
                row['pair_full_jaccard'] = round(similarity(own_claude_text(r), r['at'])[0], 4)
            fu = k in ('separate', 'near-copy', 'pointer') and len(norm_lines(r['ct'])) >= 20 and len(norm_lines(r['at'])) >= 20
            row['pair_full_unconnected'] = B(fu)
            if fu:
                tc, ta = test_cmds(r['ct']), test_cmds(r['at'])
                pc_ = pm_counts(r['ct'], JS_PM) or pm_counts(r['ct'], PY_PM); pa_ = pm_counts(r['at'], JS_PM) or pm_counts(r['at'], PY_PM)
                row['pair_om_test'] = 'both' if tc and ta else ('one' if bool(tc) != bool(ta) else 'none')
                row['pair_om_pm'] = 'both' if pc_ and pa_ else ('one' if bool(pc_) != bool(pa_) else 'none')
            if r['id'] in sep_ids:
                say = r.get('say', {})
                for key in ('pm', 'pypm', 'test', 'fmt', 'style', 'commit'):
                    row['say_' + key] = say.get(key, '')
                row['say_ban_any_side'] = B(say.get('ban_any_side') == 'both')
                for key, v in flag_of.get(r['id'], {}).items():
                    row['flag_' + key] = v
            row['pair_skills'] = ('claude' if skills_state(r, 'dcs', 'dc') else '') + ('+agents' if skills_state(r, 'das', 'da') else '') or 'none'
    if r['id'] in in_size_rows:
        row['agents_blob_read'] = 1
        sz = size_of[r['id']]
        if sz is not None:
            row['agents_size_kib'] = round(sz / 1024, 1)
            row['agents_size_bin'] = bin_of(sz)
            row['agents_over_32k'] = B(sz > LIMIT); row['agents_over_16k'] = B(sz > 16384)
        row['tree_status'] = r.get('tree_status', '')
        if r.get('tree_status') == 'ok':
            row['nested_bucket'] = nested_bucket(r.get('nested_n'))
            row['chain_over'] = B(r.get('chain_over')); row['chain_over_only_combined'] = B(r.get('chain_over_only_combined'))
        row['override_anywhere'] = B(r.get('override_any', False))
        if r['id'] in OC:
            row['codex_cfg_checked'] = 1
            row['codex_cfg_present'] = B(OC[r['id']]['has_cfg']); row['codex_cfg_raises_limit'] = B(OC[r['id']]['raised'])
    elif has(r, 'AGENTS.md'):
        row['agents_blob_read'] = 0
    if r.get('skills_state'):
        row['skills_state'] = r['skills_state']
        row['skills_two_dirs'] = r.get('skills_two_dirs', '')
        row['skills_links_into_other'] = r.get('skills_links_into_other', '')
        if r.get('skills_two_dirs'):
            row['skills_same_name'] = r.get('skills_same_name', 0); row['skills_same_name_identical'] = r.get('skills_same_name_identical', 0)
    rows.append(row)

# Shuffle-free but name-free order: sort by the salted hash, so row order carries no information.
rows.sort(key=lambda x: x['repo'])
names = [c for c, _ in COLUMNS]
assert len({x['repo'] for x in rows}) == len(rows), 'salted hash collision'
with open(os.path.join(OUTDIR, 'repo_labels.csv'), 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=names, extrasaction='raise')
    w.writeheader()
    for x in rows:
        w.writerow({k: x.get(k, '') for k in names})
json.dump({'days_drawn': len(days_all), 'days_with_repos': len(days_done),
           'day_clusters_in_bootstrap_order': sorted(day_id(d) for d in days_done),
           'bootstrap': {'replicates': 2000, 'seed': 7, 'method': 'resample the day clusters with replacement; ratio of sums; 2.5th and 97.5th percentiles'}},
          open(os.path.join(OUTDIR, 'day_clusters.json'), 'w'), indent=1)
json.dump(dict(COLUMNS), open(os.path.join(OUTDIR, 'columns.json'), 'w'), indent=1)
print('wrote', len(rows), 'rows to', os.path.join(OUTDIR, 'repo_labels.csv'))
