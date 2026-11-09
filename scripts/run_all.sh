#!/usr/bin/env bash
# CLAUDE.md / AGENTS.md study: the whole pipeline, in order.
#
#   bash run_all.sh fetch      # sample the frame and read the files (about an hour of API time)
#   bash run_all.sh analyze    # classify and count; prints what the manual review has to read
#   bash run_all.sh review near|pm|pypm|test|fmt|style|ban|commit   # print anonymised snippets to review
#   python3 label.py ID KEY VALUE "note"                            # record each verdict (see label.py)
#   bash run_all.sh finish     # manual-review totals, .codex check, facts, charts, labels, checks, evidence copy
#   bash run_all.sh purge      # delete raw/ with /bin/rm and confirm it is gone
#
# Needs: python3 (3.10+), an authenticated gh CLI, and Google Chrome only for the optional PNG render.
# Every API call is a read of public data. Raw per-repo data stays in $STUDY_WORK/raw until purge.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(git -C "$HERE" rev-parse --show-toplevel)"
export STUDY_WORK="${STUDY_WORK:-$ROOT/.claude/work/agents-md-study/pipeline}"
EVIDENCE="${STUDY_EVIDENCE:-$ROOT/docs/growth/research/agents-md-study}"
RAW="$STUDY_WORK/raw"; AGG="$STUDY_WORK/agg"; LOGS="$RAW/logs"
mkdir -p "$AGG" "$LOGS"
PY="python3 -I"   # isolated mode: never import modules from the current directory
case "${1:-}" in
  fetch)
    # The run date fixes the push window (30 days to the run date). Set it once; later steps read agg/run_config.json.
    export STUDY_RUN_DATE="${STUDY_RUN_DATE:-$(date -u +%F)}"
    $PY "$HERE/phase1_frame.py" 420 > "$LOGS/phase1.log" 2>&1 &
    P1=$!
    $PY "$HERE/codesearch_counts.py" > "$LOGS/codesearch.log" 2>&1     # code search has its own rate limit
    $PY "$HERE/ranking_check.py" > "$LOGS/ranking.log" 2>&1
    wait $P1
    $PY "$HERE/frame_coverage.py" > "$LOGS/frame_coverage.log" 2>&1    # frame repos created outside the day range (2 searches)
    $PY "$HERE/roots_catchup.py" > "$LOGS/roots_catchup.log" 2>&1      # no-op unless a day's root listing is missing
    $PY "$HERE/phase2_fetch.py" trees > "$LOGS/trees.log" 2>&1 &       # REST, in parallel with the GraphQL reads
    P2=$!
    $PY "$HERE/phase2_fetch.py" blobs 2 > "$LOGS/blobs.log" 2>&1
    $PY "$HERE/phase2_fetch.py" history 2 > "$LOGS/history.log" 2>&1
    wait $P2
    tail -n 2 "$LOGS"/*.log
    ;;
  analyze)
    $PY "$HERE/analyze.py" agg > /dev/null
    $PY -c "import json; A=json.load(open('$AGG/study_aggregates.json')); print('to review: near-copies', A['near_copies']['near_copy'], '| flags', A['conflicts']['auto_flags'])"
    ;;
  review)
    $PY "$HERE/analyze.py" review "$2"
    ;;
  finish)
    $PY "$HERE/analyze.py" agg > /dev/null
    $PY "$HERE/labels_agg.py" > "$LOGS/labels_agg.log"
    $PY "$HERE/oversize_config.py" > "$LOGS/oversize.log"
    $PY "$HERE/charts.py"
    if [ -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ]; then
      $PY "$HERE/render.py" "$STUDY_WORK/charts/relationship.html" "$STUDY_WORK/charts/relationship.png" 1200 675 2
      $PY "$HERE/render.py" "$STUDY_WORK/charts/size.html" "$STUDY_WORK/charts/size.png" 1200 675 2
    fi
    $PY "$HERE/api_usage.py" > /dev/null
    $PY "$HERE/facts.py" > "$AGG/facts.txt"
    mkdir -p "$EVIDENCE/labels" "$EVIDENCE/aggregates" "$EVIDENCE/charts"
    $PY "$HERE/export_labels.py" "$EVIDENCE/labels"
    for f in study_aggregates.json manual_review.json codesearch_counts.json codesearch_ranking_check.json oversize_config.json \
             run_config.json api_usage_summary.json facts.txt; do cp "$AGG/$f" "$EVIDENCE/aggregates/$f"; done
    cp "$AGG/chart_data.json" "$EVIDENCE/charts/chart_data.json"
    cp "$STUDY_WORK/charts/relationship.html" "$STUDY_WORK/charts/size.html" "$EVIDENCE/charts/"
    $PY "$HERE/verify_from_labels.py" "$EVIDENCE/labels" "$EVIDENCE/aggregates" | tee "$EVIDENCE/aggregates/verify_from_labels.txt" | tail -n 1
    $PY "$HERE/privacy_check.py" "$EVIDENCE" "$AGG" "$STUDY_WORK/charts" > "$LOGS/privacy_check.txt"
    tail -n 1 "$LOGS/privacy_check.txt" | tee "$EVIDENCE/aggregates/privacy_check.txt"
    ;;
  purge)
    /bin/rm -rf "$RAW" "$STUDY_WORK/chrome-profile"
    if [ -e "$RAW" ]; then echo "raw data still present at $RAW"; exit 1; fi
    echo "deleted $RAW (and the Chrome scratch profile) with /bin/rm; nothing went to the Trash"
    ;;
  *)
    sed -n '2,12p' "$0"; exit 2
    ;;
esac
