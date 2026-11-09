#!/usr/bin/env bash
set -euo pipefail
ROOT=$(realpath "${1:?usage: complete_stage08_paper_ucb_v18.sh REPO_ROOT smoke|full}")
PHASE=${2:?phase must be smoke or full}
WORK="$ROOT/scratch/stage08_vcs_paper_ucb_20261109_v18"
PY="$ROOT/.venv/bin/python"
INITIAL="$ROOT/runs/stage06_conversion_20261101T_v10/coverage_bin_by_run.csv"
case "$PHASE" in
  smoke) RUN="$ROOT/runs/stage08_vcs_paper_ucb_smoke30_20261109_v18"; EXPORT="$ROOT/evidence/stage08_vcs_paper_ucb_smoke30_20261109_v18" ;;
  full) RUN="$ROOT/runs/stage08_vcs_paper_ucb_full1000_20261109_v18"; EXPORT="$ROOT/evidence/stage08_vcs_paper_ucb_full1000_20261109_v18" ;;
  *) echo "unknown phase: $PHASE" >&2; exit 2 ;;
esac
if [[ -e "$RUN" ]]; then echo "Refusing to reuse existing run directory: $RUN" >&2; exit 2; fi
bash "$WORK/launch_stage08_paper_ucb_v18.sh" "$ROOT" "$PHASE"
"$PY" "$WORK/audit_stage08.py" --run-dir "$RUN" --initial-csv "$INITIAL"
"$PY" - "$RUN/audit.json" "$RUN/summary.json" "$PHASE" <<'PY'
import json, sys
from collections import Counter
audit=json.load(open(sys.argv[1],encoding='utf-8'))
summary=json.load(open(sys.argv[2],encoding='utf-8'))
phase=sys.argv[3]
assert audit['status']=='pass', audit
assert audit['completed']==(30 if phase=='smoke' else 1000), audit
assert summary['submitted']==summary['completed'], summary
assert set(summary['sequence_usage']).issubset({'aon_timer_jump_vseq','aon_timer_prescaler_vseq','aon_timer_smoke_vseq','aon_timer_stress_all_vseq'}), summary['sequence_usage']
assert len(summary['sequence_usage']) >= 2, summary['sequence_usage']
print('PAPER_UCB_V18_AUDIT_PASS', summary['final_covered_bins'], summary['sequence_usage'])
PY
"$PY" "$WORK/export_stage08_improved.py" --run-dir "$RUN" --output-dir "$EXPORT"

