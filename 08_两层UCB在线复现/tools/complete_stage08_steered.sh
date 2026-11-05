#!/usr/bin/env bash
set -euo pipefail

ROOT=$(realpath "${1:?usage: complete_stage08_steered.sh REPO_ROOT}")
WORK="$ROOT/scratch/stage08_vcs_steered_20261105"
INITIAL="$ROOT/runs/stage06_conversion_20261101T_v10/coverage_bin_by_run.csv"
SMOKE="$ROOT/runs/stage08_vcs_steered_smoke30_v4_20261105"
FULL="$ROOT/runs/stage08_vcs_steered_full500_v4_20261105"
PY="$ROOT/.venv/bin/python"

bash "$WORK/launch_stage08_steered.sh" "$ROOT" smoke > "$WORK/smoke30_v4.log" 2>&1
"$PY" "$WORK/audit_stage08.py" --run-dir "$SMOKE" --initial-csv "$INITIAL"
"$PY" - "$SMOKE/summary.json" "$SMOKE/audit.json" <<'PY'
import json, sys
summary, audit = [json.load(open(path)) for path in sys.argv[1:]]
assert summary["completed"] == 30 and summary["failed"] == 0, summary
assert audit["steering_targets"] > 0, audit
assert audit["steering_applied_confirmed"] > 0, audit
assert audit["steering_target_bin_hits"] > 0, audit
print("STEERED_SMOKE_GATE_PASS")
PY
"$PY" "$WORK/export_stage08_improved.py" --run-dir "$SMOKE" --output-dir "$ROOT/evidence/stage08_vcs_steered_smoke30_v4_20261105"

bash "$WORK/launch_stage08_steered.sh" "$ROOT" full500 > "$WORK/full500_v4.log" 2>&1
"$PY" "$WORK/audit_stage08.py" --run-dir "$FULL" --initial-csv "$INITIAL"
"$PY" "$WORK/export_stage08_improved.py" --run-dir "$FULL" --output-dir "$ROOT/evidence/stage08_vcs_steered_full500_v4_20261105"
echo STAGE08_VCS_STEERED_FULL500_COMPLETE
