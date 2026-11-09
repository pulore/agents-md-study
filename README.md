# CLAUDE.md and AGENTS.md in public GitHub repos: code and data

The code and data behind [CLAUDE.md and AGENTS.md: How 1,292 Public Repos Link Them](https://pulore.com/blog/agents-md-claude-md-study), from the run on 9 November 2026. Nothing here names a repo or quotes its files.

In a random sample of 19,776 public repos with 10 or more stars and a push in the 30 days to 9 November 2026, 1,292 have both a root CLAUDE.md and a root AGENTS.md whose text could be read. In 508 of them, 39.3% (95% interval 35.6% to 42.6%), there is no import or symlink between the two files: CLAUDE.md doesn't import AGENTS.md the way Claude Code reads imports, and neither file is a symlink to the other. That measures automatic loading, not whether the two files' rules agree or what the agents do in a session.

| Path | What it holds |
| --- | --- |
| `scripts/` | The pipeline: the Python 3 standard library, the authenticated `gh` CLI, and Node.js with marked 18.1.1 (pinned in `package.json` and `package-lock.json`) for Claude Code's import rule. `run_all.sh` runs it in order. |
| `labels/repo_labels.csv` | One row of labels per sampled repo (19,776 rows), keyed by a salted hash. `columns.json` explains every column. `day_clusters.json` lists the creation-day clusters in the order the bootstrap uses. |
| `aggregates/study_aggregates.json` | Every count, share, Wilson interval and day-bootstrap interval the analysis produced. |
| `aggregates/manual_review.json` | Totals of the manual review: near-copy labels and the verdict on every automatic conflict flag, with paraphrased notes for contradictions and confirmed conflicts. |
| `aggregates/codesearch_counts.json`, `codesearch_ranking_check.json` | GitHub code search totals (all of GitHub, estimates) and the size check on code search's top results. |
| `aggregates/oversize_config.json` | For root AGENTS.md files over 32 KiB: committed `.codex/config.toml` files and whether they raise `project_doc_max_bytes`. |
| `aggregates/run_config.json` | Run date, frame query, push window, seed, frame size. |
| `aggregates/api_usage_summary.json` | Requests sent, by API and by script. |
| `aggregates/facts.txt` | Every number the post uses, printed by `scripts/facts.py`. |
| `aggregates/verify_from_labels.txt` | Every count and interval recomputed from `labels/` alone and checked against the aggregates: 128 checks, 0 differences. |
| `aggregates/claude_import_rule_check.txt` | Output of `scripts/check_claude_import_rule.py`: Claude Code's import rule in builds 2.1.220, 2.1.309 and 2.1.317, compared piece by piece with the one `claude_imports.mjs` copies. |
| `aggregates/privacy_check.txt` | Result of `scripts/privacy_check.py` on everything kept, run before the raw data was deleted. |
| `charts/chart_data.json` | Every value drawn in the post's two charts. `relationship.html` and `size.html` are the chart sources. |

## Check the numbers without any API call

```sh
python3 scripts/verify_from_labels.py labels aggregates
```

It recomputes every count and interval from `labels/` and compares them with `aggregates/`.

## Sample

- **Seed** `20261103`. The day list is the 6,881 days from 1 January 2008 to 2 November 2026; `random.Random(20261103).shuffle` orders them and the first 420 are drawn (`scripts/common.py`).
- **Frame.** Repository search `stars:>=10 pushed:>=2026-10-10 archived:false is:public`. Forks are excluded by default, so this is public repos with 10 or more stars, not forks, not archived, with a push between 10 October 2026 00:00 UTC and the moment their creation day was listed. Search counted 317,587 such repos at 06:22 UTC.
- **Listing.** Every frame repo created on a drawn day was listed, between 06:22 and 06:57 UTC on 9 November 2026. Search returns at most 1,000 results per query and the busiest drawn day had 888, so no day was cut off. 19,776 repos. 23 of the 420 days had no repo in the frame.
- **Coverage.** Every frame repo created from 1 January 2008 to 2 November 2026 had the same chance of being drawn, 420 in 6,881 (6.1%). Repos created before 2008 or after 2 November 2026 could not be drawn: 2,448 frame repos were created after 2 November 2026 and 0 before 2008 when checked at 06:58 UTC, 0.771% of the frame.
- **Why the day range ends on 2 November.** It is fixed together with the seed. Ending it on the run date would reshuffle every day and draw a different sample, so a rerun on another date draws the same 420 days and only the push window moves.

## How a pair is classified

- **Symlinks** come from git file modes, and each link is followed to its target.
- **Imports** follow Claude Code's own rule, in `scripts/claude_imports.mjs`. It is copied from the function that collects a CLAUDE.md file's imports in Claude Code 2.1.220 and run on marked's tokens in CommonMark mode, the way Claude Code calls it. Code blocks and inline code are skipped, an HTML block is read only after its comments are removed, the `@` must start the text or follow whitespace, and the path runs to the next unescaped whitespace with any `#fragment` cut. So `@AGENTS.md.` at the end of a sentence names a file called `AGENTS.md.`, and `(@AGENTS.md)` isn't an import. `scripts/check_claude_import_rule.py` compares any Claude Code build with that rule: 2.1.309 and 2.1.317 have the same scanner, token walk and CommonMark lexer, with a broader check that skips special paths such as device files (`aggregates/claude_import_rule_check.txt`).
- **How much the exact rule matters.** A looser pattern, `@AGENTS.md` outside code ending at a word boundary, would count 4 more pairs as imports; all 4 are pointers here (`pair_loose_regex_import` in the labels). 6 pairs write `@AGENTS.md` in a way Claude Code doesn't import (`pair_near_miss_import`).
- **Near-copies.** The Jaccard similarity of the two files' sets of distinct lines, after trimming, collapsing whitespace and masking tool and file names, is 0.5 or more. A Claude Code agent read each diff in full and labelled it by the definitions under Rerun; the diffs were deleted with the raw data.
- **Conflicts.** Scripted checks for seven kinds of clash run over every pair whose files say things separately: pointers, separate files, near-copies, and imports whose CLAUDE.md has lines of its own besides the import. The same agent read and labelled every flag. The checks only catch what their patterns describe.
- **Skills.** Same-named skill folders in `.claude/skills` and `.agents/skills` count as identical only if their git tree hashes match.

## Rerun

From the repo root, with `gh auth status` showing a logged-in account and Node.js on the path. A rerun reads today's GitHub, so its counts will differ from the ones published here.

```sh
npm ci --ignore-scripts --prefix scripts      # marked, for the import rule
export STUDY_EVIDENCE="$PWD/rerun"           # where finish writes its labels/, aggregates/ and charts/
bash scripts/run_all.sh fetch                # sample and read: about an hour
bash scripts/run_all.sh analyze              # counts; lists what needs a manual verdict
REVIEW_FULL=1 bash scripts/run_all.sh review near   # then pm, pypm, test, fmt, style, ban, commit
python3 scripts/label.py ID near content "paraphrase, no names"   # one per item
bash scripts/run_all.sh finish               # totals, charts, labels, checks
bash scripts/run_all.sh purge                # /bin/rm the raw data and confirm it's gone
```

Raw data goes to `.claude/work/agents-md-study/pipeline/raw/`, which `.gitignore` keeps out of git; set `STUDY_WORK` to move it. `fetch` uses today's date for the push window unless `STUDY_RUN_DATE=YYYY-MM-DD` is set. marked can also come from `STUDY_NODE_MODULES`. The optional PNG render needs Google Chrome.

The manual review is the one step a script can't do. In the published run a Claude Code agent did it. `review` prints anonymized snippets: for near-copies, the lines only one file has; for each conflict flag, the lines that triggered it. `REVIEW_FULL=1` prints whole lines and every differing line; without it, lines are cut at 170 characters. The labels used:

- near-copies: `cosmetic` (only a title, the tool's name, a generated-file banner or a line rewritten for each tool differs), `content` (rules, commands or facts only one file has), `contradiction` (the two files disagree)
- conflict flags: `confirmed` (the instructions really conflict) or `false-positive`

## API cost of the 9 November 2026 run

| Step | Repo search | Code search | REST | GraphQL requests | GraphQL points | Busy time (min) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `phase1_frame` (1 run) | 489 | 0 | 0 | 647 | 647 | 36.2 |
| `frame_coverage` (1 run) | 2 | 0 | 0 | 0 | 0 | 0.1 |
| `codesearch_counts` (1 run) | 0 | 16 | 24 | 0 | 0 | 2.6 |
| `ranking_check` (1 run) | 0 | 2 | 0 | 10 | 10 | 0.6 |
| `phase2_fetch-blobs` (1 run) | 0 | 0 | 0 | 566 | 561 | 15.2 |
| `phase2_fetch-history` (1 run) | 0 | 0 | 0 | 65 | 65 | 1.6 |
| `phase2_fetch-trees` (1 run) | 0 | 0 | 3,109 | 0 | 0 | 22.6 |
| `oversize_config` (1 run) | 0 | 0 | 0 | 9 | 9 | 0.6 |
| **Total** | 491 | 18 | 3,133 | 1,297 | 1,292 | 59 for the fetch |

Retries are included. There were no rate-limit pauses, and 1 request, in the blob step, failed for good. Requests ran from 06:22 to 07:40 UTC. One token's limits are 30 repository searches and 10 code searches a minute, 5,000 REST requests an hour and 5,000 GraphQL points an hour. The run stayed inside them, so the fetch time is set by the gap between search requests.

## Privacy

- Repo names, node IDs and file texts existed only in the raw folder while counting. `privacy_check.py` then checked every file kept here against them: no node ID, no owner/name pair, no repo URL and no line of 40 or more characters copied from a sampled instruction file (0 failures; the warnings were ordinary words such as "agents.md", "directory" or "pipeline" that are also the names of some sampled repos, checked one by one).
- The labels are keyed by HMAC-SHA256 with a random 32-byte salt. The salt was deleted with the raw data on 9 November 2026, so the keys can't be turned back into repo names.
- Rows hold bands rather than exact values: star band, creation-year bucket, AGENTS.md size rounded to 0.1 KiB. There are no dates, exact star counts or exact byte sizes.
- The seed and code are here, so anyone can redraw the same days from public data. What isn't here is the list of repos we drew or what their files said.

## Method notes

- The classification rules, regexes and thresholds are in `scripts/textlib.py`, `scripts/analyze.py` and `scripts/claude_imports.mjs`.
- The blob query reads CLAUDE.md, AGENTS.md, .claude/CLAUDE.md, AGENTS.override.md and the .claude, .agents, .claude/skills and .agents/skills listings, with each skills entry's git object ID and, for a symlink, its target. Root listings come from GraphQL `HEAD:` trees, last-commit dates from `history(first: 1, path:)`, nested AGENTS.md files from the REST recursive tree, and `.codex/config.toml` only for repos whose root AGENTS.md is over 32 KiB.
- Root AGENTS.md counts differ by step: 3,107 repos have one, 3,084 have a size (23 are symlinks to something other than a plain root CLAUDE.md), and 3,092 file trees were listed in full (15 were too large for the API).
- Intervals: 2,000 bootstrap replicates over creation days (seed 7), percentile method, because repos created on the same day were drawn together.
- Code search totals are GitHub's estimates for all of GitHub, count files rather than repos, and move between queries.

## License

Apache License 2.0, for the code and the data. See `LICENSE` and `NOTICE`.
