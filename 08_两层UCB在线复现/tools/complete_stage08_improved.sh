#!/usr/bin/env bash
# Audit the 30-submit smoke, enforce the failure gate, then run/audit/export H=1000.
set -euo pipefail
ROOT=$(realpath "$1")
WORK="$ROOT/scratch/stage08_improved_v3_20261103"
PY="$ROOT/.venv/bin/python"
INITIAL="$ROOT/runs/stage06_conversion_20261101T_v10/coverage_bin_by_run.csv"
SMOKE="$ROOT/runs/stage08_improved_smoke_20261103_v3"
FULL="$ROOT/runs/stage08_improved_full_20261103_v3"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
if test ! -f "$SMOKE/summary.json"; then
  SMOKE_PID=${2:?Pass the smoke PID while waiting for its summary}
  while test ! -f "$SMOKE/summary.json"; do
    kill -0 "$SMOKE_PID" || { echo SMOKE_EXITED_WITHOUT_SUMMARY; exit 3; }
    sleep 15
  done
fi
"$PY" "$WORK/audit_stage08.py" --run-dir "$SMOKE" --initial-csv "$INITIAL"
"$PY" - "$SMOKE/run_results.json" <<'PY'
import json, sys
rows = json.load(open(sys.argv[1]))
assert len(rows) == 30, f"expected 30 smoke submissions, got {len(rows)}"
for row in rows:
    if row["status"] == "success":
        continue
    assert (row["status"] == "failed" and row.get("vcs_return_code") == 0
            and (row.get("uvm_error", 0) or row.get("uvm_fatal", 0))), row
print("IMPROVED_SMOKE_GATE_PASS")
PY
bash "$WORK/launch_stage08_improved.sh" "$ROOT" full > "$WORK/full.log" 2>&1
"$PY" "$WORK/audit_stage08.py" --run-dir "$FULL" --initial-csv "$INITIAL"
"$PY" "$WORK/export_stage08_improved.py" --run-dir "$SMOKE" --output-dir "$ROOT/evidence/stage08_improved_smoke_20261103_v3"
"$PY" "$WORK/export_stage08_improved.py" --run-dir "$FULL" --output-dir "$ROOT/evidence/stage08_improved_full_20261103_v3"
echo STAGE08_IMPROVED_FULL_COMPLETE