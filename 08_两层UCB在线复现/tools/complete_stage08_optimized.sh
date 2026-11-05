#!/usr/bin/env bash
set -euo pipefail
ROOT=$(realpath "$1")
WORK="$ROOT/scratch/stage08_vcs_optimized_20261104"
PY="$ROOT/.venv/bin/python"
INITIAL="$ROOT/runs/stage06_conversion_20261101T_v10/coverage_bin_by_run.csv"
SMOKE="$ROOT/runs/stage08_vcs_optimized_smoke_20261104"
FULL="$ROOT/runs/stage08_vcs_optimized_full_20261104"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1

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
print("OPTIMIZED_SMOKE_GATE_PASS")
PY

bash "$WORK/launch_stage08_optimized.sh" "$ROOT" full > "$WORK/full.log" 2>&1
"$PY" "$WORK/audit_stage08.py" --run-dir "$FULL" --initial-csv "$INITIAL"
"$PY" "$WORK/export_stage08_improved.py" --run-dir "$SMOKE" --output-dir "$ROOT/evidence/stage08_vcs_optimized_smoke_20261104"
"$PY" "$WORK/export_stage08_improved.py" --run-dir "$FULL" --output-dir "$ROOT/evidence/stage08_vcs_optimized_full_20261104"
echo STAGE08_VCS_OPTIMIZED_FULL_COMPLETE
