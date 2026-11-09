# Print every number the post uses, from the saved aggregates. python3 facts.py
# Rerun change (5 Nov 2026): also prints the run window, the counts that used to come from one-off commands, and API usage.
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import AGG
A = json.load(open(os.path.join(AGG, 'study_aggregates.json')))
M = json.load(open(os.path.join(AGG, 'manual_review.json'))) if os.path.exists(os.path.join(AGG, 'manual_review.json')) else {}
C = json.load(open(os.path.join(AGG, 'codesearch_counts.json')))
R = json.load(open(os.path.join(AGG, 'codesearch_ranking_check.json')))
O = json.load(open(os.path.join(AGG, 'oversize_config.json'))) if os.path.exists(os.path.join(AGG, 'oversize_config.json')) else {}
P = A['pairs']; K = P['kinds']; F = A['frame']; S = A['size']; N = P['n']
k = lambda x: K.get(x, {}).get('k', 0)
pc = lambda a, b: f'{100 * a / b:.1f}%' if b else 'n/a'
print('== meta', json.dumps(A['meta']))
CFG = json.load(open(os.path.join(AGG, 'run_config.json'))) if os.path.exists(os.path.join(AGG, 'run_config.json')) else {}
print('== run config', json.dumps(CFG))
print(f"frame repos {F['repos']:,} | CLAUDE {F['root_CLAUDE.md']['k']} ({F['root_CLAUDE.md']['pct']}%) | AGENTS {F['root_AGENTS.md']['k']} ({F['root_AGENTS.md']['pct']}%) | both {F['both_root']['k']} ({F['both_root']['pct']}%) | either {F['either_root']['pct']}%")
print(f"  P(AGENTS|CLAUDE) {F['AGENTS.md_given_CLAUDE.md']['pct']}% | P(CLAUDE|AGENTS) {F['CLAUDE.md_given_AGENTS.md']['pct']}% | .claude dir {F['has_.claude_dir']['pct']}% | .agents dir {F['has_.agents_dir']['pct']}% | .codex {F['has_.codex_dir']['pct']}%")
print('  by year', json.dumps(F['by_created_year']))
print('  by stars', json.dumps(F['by_star_band']))
print(f"== pairs n={N} (missing text {P['missing_text']})")
imp = k('import-shim') + k('import-plus')
for lab, v in (('import (all)', imp), ('  import shim <=10 lines', k('import-shim')), ('  import + own content', k('import-plus')), ('  exactly one line @AGENTS.md', P['claude_md_exactly_one_import_line']),
               ('symlink', k('symlink')), ('pointer', k('pointer')), ('separate', k('separate')), ('identical', k('identical')), ('near-copy', k('near-copy')),
               ('copies (ident+near)', k('identical') + k('near-copy')), ('symlink-other', k('symlink-other'))):
    print(f'  {lab:32} {v:5} {pc(v, N)}')
print(f"  wired {P['wired']['k']} {P['wired']['pct']}% boot {P['wired']['boot95']} | NOT wired {P['not_wired']['k']} {P['not_wired']['pct']}% boot {P['not_wired']['boot95']} wilson {P['not_wired']['wilson95']}")
print('  symlink dirs', P['symlink_dirs'], '| pointer dirs', P['pointer_dirs'])
print('  broken import in code', P['broken_import_in_code'], '| AGENTS has @CLAUDE.md', P['agents_imports_claude'], '| symlink as text', P['symlink_checked_in_as_text'])
print('  near-miss @AGENTS.md (not an import)', P.get('near_miss_import'), '| looser regex vs Claude Code parser', json.dumps(P.get('loose_regex_vs_parser')))
print('  by stars', json.dumps({b: (v['n'], v['not_wired']['pct']) for b, v in P['by_star_band'].items()}))
print('  .claude/CLAUDE.md + AGENTS.md', P['dot_claude_CLAUDE.md_with_AGENTS.md_no_root_CLAUDE.md'], '| committed CLAUDE.local.md', P['committed_CLAUDE.local.md_any'])
print('  CLAUDE.md sizes', P['claude_md_sizes'], '| ranking check', R)
print('  separate-written jaccard', P['shared_lines_distribution_separate_written'])
print('  small root CLAUDE.md (<100 bytes)', P.get('claude_md_under_100_bytes'), '| not wired, 10-499 stars', P.get('not_wired_10_499_stars'))
print('== omissions', json.dumps(A.get('omissions')))
print('== near copies', json.dumps(A['near_copies']))
print('== manual', json.dumps(M.get('near_copies')), json.dumps(M.get('conflict_flags')))
print('   notes', json.dumps(M.get('notes'), ensure_ascii=False))
print('== conflicts', json.dumps(A['conflicts']))
print('== size', json.dumps({x: S[x] for x in S if x != 'over_32KiB_by_star_band'}))
print('   by stars', json.dumps(S['over_32KiB_by_star_band']))
print('   oversize config', O)
print('== override', json.dumps(A['override']))
print('== skills', json.dumps(A['skills']))
sb = A['skills']['among_both_root_files']; with_sk = sum(v for k, v in sb.items() if k != 'none'); one = sb.get('claude', 0) + sb.get('+agents', 0)
print(f'   both instruction files + a skills folder: {with_sk}; skills where only one agent loads them: {one} ({pc(one, with_sk)})')
print('== code search')
for x, v in C.items():
    print(f"   {x:28} {v['total_count']:>9,}  {v['query']}  ({v['checked_at']})")
U = os.path.join(AGG, 'api_usage_summary.json')
if os.path.exists(U):
    print('== API usage', json.dumps(json.load(open(U))['total']))
