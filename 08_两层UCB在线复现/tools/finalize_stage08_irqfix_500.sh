#!/usr/bin/env bash
set -euo pipefail
ROOT=$(realpath "${1:?usage: finalize_stage08_irqfix_500.sh REPO_ROOT}")
WORK="$ROOT/scratch/stage08_irqfix_build_20261104"
CODEWORK="$ROOT/scratch/stage08_vcs_optimized_20261104"
RUN="$ROOT/runs/stage08_vcs_optimized_full500_irqfix_20261104"
PIDFILE="$WORK/full500_irqfix.pid"
PID=$(cat "$PIDFILE")

while kill -0 "$PID" 2>/dev/null; do
  sleep 60
done

"$ROOT/.venv/bin/python" - "$RUN/summary.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as source:
    summary = json.load(source)
assert summary["status"] == "completed", summary
assert summary["submitted"] == 500 and summary["completed"] == 500, summary
PY

"$ROOT/.venv/bin/python" "$CODEWORK/audit_stage08.py" \
  --run-dir "$RUN" \
  --initial-csv "$ROOT/runs/stage06_conversion_20261101T_v10/coverage_bin_by_run.csv"
"$ROOT/.venv/bin/python" "$CODEWORK/export_stage08_improved.py" \
  --run-dir "$RUN" \
  --output-dir "$ROOT/evidence/stage08_vcs_optimized_full500_irqfix_20261104"
echo STAGE08_VCS_IRQFIX_FULL500_COMPLETE
