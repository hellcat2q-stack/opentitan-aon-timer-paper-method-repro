#!/usr/bin/env bash
set -euo pipefail

ROOT=$(realpath "$1")
WORK="$ROOT/scratch/stage08_vcs_20261104"
PY="$ROOT/.venv/bin/python"
INITIAL="$ROOT/runs/stage06_conversion_20261101T_v10/coverage_bin_by_run.csv"
SMOKE="$ROOT/runs/stage08_vcs_smoke_20261104"
FULL="$ROOT/runs/stage08_vcs_full_20261104"

"$PY" "$WORK/audit_stage08.py" --run-dir "$SMOKE" --initial-csv "$INITIAL"
"$PY" -c 'import json,sys; rows=json.load(open(sys.argv[1])); assert len(rows)==10; assert all(x["status"]=="success" or (x["status"]=="failed" and x.get("vcs_return_code")==0 and (x.get("uvm_error",0) or x.get("uvm_fatal",0))) for x in rows)' "$SMOKE/run_results.json"
if test ! -d "$ROOT/evidence/stage08_vcs_smoke_20261104"; then
  "$PY" "$WORK/export_stage08.py" --run-dir "$SMOKE" --output-dir "$ROOT/evidence/stage08_vcs_smoke_20261104"
fi

bash "$WORK/launch_stage08_vcs.sh" "$ROOT" full > "$WORK/full.log" 2>&1
"$PY" "$WORK/audit_stage08.py" --run-dir "$FULL" --initial-csv "$INITIAL"
"$PY" "$WORK/export_stage08.py" --run-dir "$FULL" --output-dir "$ROOT/evidence/stage08_vcs_full_20261104"
echo STAGE08_VCS_FULL_COMPLETE
