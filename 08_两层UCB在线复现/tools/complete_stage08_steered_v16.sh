#!/usr/bin/env bash
set -euo pipefail

ROOT=$(realpath "${1:?usage: complete_stage08_steered_v16.sh REPO_ROOT}")
FULL="$ROOT/runs/stage08_vcs_steered_full1000_v16_20261105"
INITIAL="$ROOT/runs/stage06_conversion_20261101T_v10/coverage_bin_by_run.csv"
PY="$ROOT/.venv/bin/python"
WORK="$ROOT/scratch/stage08_vcs_steered_20261105_v15"
EXPORT="$ROOT/evidence/stage08_vcs_steered_full1000_v16_20261105"

if [[ -e "$FULL" ]]; then
  echo "Refusing to reuse an existing run directory; inspect it before proceeding: $FULL" >&2
  exit 2
fi
bash "$ROOT/08_两层UCB在线复现/tools/launch_stage08_steered_v16.sh" "$ROOT"
"$PY" "$WORK/audit_stage08.py" --run-dir "$FULL" --initial-csv "$INITIAL"
"$PY" - "$FULL/audit.json" "$FULL/summary.json" <<'PY'
import json, sys
audit = json.load(open(sys.argv[1], encoding="utf-8"))
summary = json.load(open(sys.argv[2], encoding="utf-8"))
assert audit["status"] == "pass", audit
assert audit["completed"] == 1000 and audit["failed"] == 0, audit
assert summary["submitted"] == summary["completed"] == 1000, summary
assert summary["failed"] == 0 and summary["retried"] == 0, summary
assert summary["sequence_usage"] == {"aon_timer_jump_vseq": 1000}, summary["sequence_usage"]
print("FULL1000_AUDIT_AND_SEQUENCE_GATE_PASS", audit["final_covered_bins"])
PY
"$PY" "$WORK/export_stage08_improved.py" --run-dir "$FULL" --output-dir "$EXPORT"
