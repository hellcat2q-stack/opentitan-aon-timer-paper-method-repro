#!/usr/bin/env bash
set -euo pipefail

ROOT=$(realpath "${1:?usage: complete_stage08_steered_v15.sh REPO_ROOT}")
WORK="$ROOT/scratch/stage08_vcs_steered_20261105_v15"
PY="$ROOT/.venv/bin/python"
SMOKE="$ROOT/runs/stage08_vcs_steered_smoke30_v15_20261105"
FULL="$ROOT/runs/stage08_vcs_steered_full500_v15_20261105"
INITIAL="$ROOT/runs/stage06_conversion_20261101T_v10/coverage_bin_by_run.csv"

if [[ ! -e "$SMOKE" ]]; then
  "$WORK/launch_stage08_steered_v15.sh" "$ROOT" smoke
fi
"$PY" "$WORK/audit_stage08.py" --run-dir "$SMOKE" --initial-csv "$INITIAL"
"$PY" - "$SMOKE/audit.json" <<'PY'
import json, sys
audit_path = sys.argv[1]
audit = json.load(open(audit_path, encoding="utf-8"))
summary = json.load(open(audit_path.replace("audit.json", "summary.json"), encoding="utf-8"))
assert audit["status"] == "pass" and audit["failed"] == 0, audit
assert audit["steering_targets"] > 0 and audit["steering_target_bin_hits"] > 0, audit
assert summary["sequence_usage"] == {"aon_timer_jump_vseq": 30}, summary["sequence_usage"]
print("SMOKE_GATE_PASS", audit["steering_targets"], audit["steering_target_bin_hits"])
PY

if [[ ! -e "$FULL" ]]; then
  "$WORK/launch_stage08_steered_v15.sh" "$ROOT" full500
fi
"$PY" "$WORK/audit_stage08.py" --run-dir "$FULL" --initial-csv "$INITIAL"
"$PY" - "$FULL/summary.json" <<'PY'
import json, sys
summary = json.load(open(sys.argv[1], encoding="utf-8"))
assert summary["submitted"] == summary["completed"] == 500, summary
assert summary["failed"] == 0, summary
assert summary["sequence_usage"] == {"aon_timer_jump_vseq": 500}, summary["sequence_usage"]
print("FULL500_SEQUENCE_GATE_PASS")
PY
