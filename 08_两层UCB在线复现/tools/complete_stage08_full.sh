#!/usr/bin/env bash
# Finite server workflow: audit a completed smoke, run H=1000, audit and export.
set -euo pipefail
ROOT=$(realpath "$1")
WORK="$ROOT/scratch/stage08_v1_20261102"
PY="$ROOT/.venv/bin/python"
INITIAL="$ROOT/runs/stage06_conversion_20261101T_v10/coverage_bin_by_run.csv"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
if test ! -f "$ROOT/runs/stage08_smoke_20261102_v1/summary.json"; then
  SMOKE_PID=${2:?Pass the running smoke PID while awaiting its summary}
  while test ! -f "$ROOT/runs/stage08_smoke_20261102_v1/summary.json"; do
    kill -0 "$SMOKE_PID" || { echo SMOKE_EXITED_WITHOUT_SUMMARY; exit 3; }
    sleep 15
  done
fi
"$PY" "$WORK/audit_stage08.py" --run-dir "$ROOT/runs/stage08_smoke_20261102_v1" --initial-csv "$INITIAL"
# UVM errors are recorded failed submissions under the preregistered rule.
# Infrastructure failures, host timeouts or coverage parse errors block Full.
"$PY" -c 'import json,sys; rows=json.load(open(sys.argv[1])); assert len(rows)==10; assert all(x["status"]=="success" or (x["status"]=="failed" and x.get("vcs_return_code")==0 and (x.get("uvm_error",0) or x.get("uvm_fatal",0))) for x in rows)' "$ROOT/runs/stage08_smoke_20261102_v1/run_results.json"
if test ! -d "$ROOT/evidence/stage08_smoke_20261102_v1"; then
  "$PY" "$WORK/export_stage08.py" --run-dir "$ROOT/runs/stage08_smoke_20261102_v1" --output-dir "$ROOT/evidence/stage08_smoke_20261102_v1"
fi
bash "$WORK/launch_stage08.sh" "$ROOT" full > "$WORK/full.log" 2>&1
"$PY" "$WORK/audit_stage08.py" --run-dir "$ROOT/runs/stage08_full_20261102_v1" --initial-csv "$INITIAL"
"$PY" "$WORK/export_stage08.py" --run-dir "$ROOT/runs/stage08_full_20261102_v1" --output-dir "$ROOT/evidence/stage08_full_20261102_v1"
echo STAGE08_FULL_COMPLETE
