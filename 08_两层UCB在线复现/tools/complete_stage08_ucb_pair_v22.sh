#!/usr/bin/env bash
set -euo pipefail
ROOT=$(realpath "${1:?usage: complete_stage08_ucb_pair_v22.sh REPO_ROOT}")
WORK="$ROOT/scratch/stage08_v22_inputs_20261110"
PY="$ROOT/.venv/bin/python"
INITIAL="$ROOT/runs/stage08_inputs_xml_20261110_v20_retry1/coverage_bin_by_run.csv"
SMOKE="$ROOT/runs/stage08_vcs_ucb_smoke30_20261110_v22"
TREATMENT="$ROOT/runs/stage08_vcs_ucb_full1000_20261110_v22"
CONTROL="$ROOT/runs/stage08_vcs_paper_ucb_full1000_20261110_v20"
exec 9>"$WORK/pair.lock"
flock -n 9 || { echo "Another v22 pair controller is already active" >&2; exit 2; }
trap 'rc=$?; if [[ $rc -ne 0 ]]; then echo "PAIR_STOPPED rc=$rc phase=${PHASE:-setup}"; fi' EXIT
PHASE=parameter_gate
"$PY" - "$ROOT/runs/stage08_v22_parameter_probe_verified_20261110/probe_summary.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
assert data['status'] == 'pass' and len(data['cases']) == 8, data
assert all(case['status'] == 'pass' for case in data['cases']), data
print('V22_PARAMETER_GATE_PASS')
PY
PYTHONPATH="$ROOT/scratch/stage08_v22_20261110/tools" "$PY" "$WORK/audit_stage08_mapping_v22.py" \
  --mapping "$ROOT/runs/stage07_recluster_xml_20261110_v20/bin_to_cluster.csv" --output "$WORK/mapping_validation_v22.json"
PHASE=smoke
bash "$WORK/launch_stage08_paper_ucb_v22.sh" "$ROOT" smoke > "$WORK/smoke.log" 2>&1
"$PY" "$WORK/audit_stage08.py" --run-dir "$SMOKE" --initial-csv "$INITIAL"
"$PY" - "$SMOKE" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
audit = json.loads((root / 'audit.json').read_text())
summary = json.loads((root / 'summary.json').read_text())
assert audit['status'] == 'pass' and summary['completed'] == 30 and summary['failed'] == 0, summary
assert audit['steering_targets'] > 0, audit
assert audit['steering_applied_confirmed'] == audit['steering_targets'], audit
assert audit['steering_target_bin_hits'] >= 0.9 * audit['steering_targets'], audit
assert len(summary['sequence_usage']) >= 2, summary
print('V22_SMOKE_GATE_PASS', summary['final_covered_bins'], summary['sequence_usage'])
PY
"$PY" "$WORK/export_stage08_improved.py" --run-dir "$SMOKE" --output-dir "$ROOT/evidence/stage08_v22_smoke30_20261110"
cp "$WORK/mapping_validation_v22.json" "$ROOT/evidence/stage08_v22_smoke30_20261110/"
cp "$ROOT/runs/stage08_v22_parameter_probe_verified_20261110/probe_summary.json" "$ROOT/evidence/stage08_v22_smoke30_20261110/"
cp "$ROOT/scratch/stage08_v22_20261110/source_sha256.txt" "$ROOT/evidence/stage08_v22_smoke30_20261110/"
PHASE=treatment_full
bash "$WORK/launch_stage08_paper_ucb_v22.sh" "$ROOT" full > "$WORK/treatment_full.log" 2>&1
"$PY" "$WORK/audit_stage08.py" --run-dir "$TREATMENT" --initial-csv "$INITIAL"
"$PY" "$WORK/export_stage08_improved.py" --run-dir "$TREATMENT" --output-dir "$ROOT/evidence/stage08_v22_full1000_20261110"
PHASE=control_full
bash "$ROOT/scratch/stage08_v20_20261110/tools/launch_stage08_paper_ucb_v20.sh" "$ROOT" full > "$WORK/control_full.log" 2>&1
"$PY" "$WORK/audit_stage08.py" --run-dir "$CONTROL" --initial-csv "$INITIAL"
"$PY" "$WORK/export_stage08_improved.py" --run-dir "$CONTROL" --output-dir "$ROOT/evidence/stage08_v20_control_full1000_20261110"
PHASE=compare
"$PY" "$WORK/compare_stage08_ucb_pair_v22.py" --control "$CONTROL" --treatment "$TREATMENT" --output "$WORK/comparison.json"
echo PAIR_V20_V22_COMPLETE
