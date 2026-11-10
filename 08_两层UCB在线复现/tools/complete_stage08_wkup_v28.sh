#!/usr/bin/env bash
set -euo pipefail
ROOT=$(realpath "${1:?usage: complete_stage08_wkup_v28.sh REPO_ROOT}")
WORK="$ROOT/scratch/stage08_v28_wkup_cdc_fence_20261111"
TOOLS="$ROOT/08_两层UCB在线复现/tools"
INPUTS="$ROOT/scratch/stage08_v22_inputs_20261110"
PY="$ROOT/.venv/bin/python"
INITIAL="$ROOT/runs/stage08_inputs_xml_20261110_v20_retry1/coverage_bin_by_run.csv"
REPLAY="$ROOT/runs/stage08_wkup_failed_seed_replay_v28_verified_20261111"
SMOKE="$ROOT/runs/stage08_vcs_ucb_smoke30_20261111_v28"
FULL="$ROOT/runs/stage08_vcs_ucb_full1000_20261111_v28"
exec 9>"$WORK/workflow.lock"
flock -n 9 || { echo "Another v28 workflow is active" >&2; exit 2; }
trap 'rc=$?; if [[ $rc -ne 0 ]]; then echo "V28_STOPPED rc=$rc phase=${PHASE:-setup}"; fi' EXIT
phase() { PHASE="$1"; echo "$PHASE" > "$WORK/workflow_phase.txt"; echo "V28_PHASE $PHASE"; }
phase regression
bash "$TOOLS/replay_stage08_wkup_failed_seeds_v28.sh" "$ROOT"
"$PY" - "$REPLAY" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
for seed in (1135891496, 1202340700, 1246806959, 709099176, 1015701649):
    result = json.loads((root / str(seed) / 'verification.json').read_text())
    assert result['status'] == 'pass' and result['simulation_time_ps'] > 0, result
print('V28_FIVE_SEED_GATE_PASS', flush=True)
PY
phase preflight
bash "$TOOLS/launch_stage08_wkup_cdc_fence_v28.sh" "$ROOT" preflight > "$WORK/preflight.log" 2>&1
phase smoke
bash "$TOOLS/launch_stage08_wkup_cdc_fence_v28.sh" "$ROOT" smoke > "$WORK/smoke.log" 2>&1
"$PY" "$INPUTS/audit_stage08.py" --run-dir "$SMOKE" --initial-csv "$INITIAL"
PYTHONPATH="$WORK/tools" "$PY" - "$SMOKE" <<'PY'
import json, sys
from pathlib import Path
from verify_stage08_uvm_replay import inspect_log
run = Path(sys.argv[1])
summary, audit = (json.loads((run / name).read_text()) for name in ('summary.json', 'audit.json'))
assert summary['submitted'] == summary['completed'] == summary['accepted'] == 30, summary
assert summary['failed'] == 0 and audit['status'] == 'pass', (summary, audit)
assert summary['initial_union_bins'] == 508 and summary['bin_count'] == 4507, summary
assert audit['steering_targets'] > 0, audit
assert audit['steering_applied_confirmed'] == audit['steering_targets'], audit
assert audit['steering_target_bin_hits'] >= .9 * audit['steering_targets'], audit
assert len(summary['sequence_usage']) >= 2, summary
for result in json.loads((run / 'run_results.json').read_text()):
    i = result['run_id']
    log = run / 'batches' / f'batch_{i // 10}' / str(i) / 'raw' / result['test_name'] / '0/run.log'
    checked = inspect_log(log.read_text(errors='replace'), result['vcs_return_code'])
    assert checked['status'] == 'pass', (i, checked)
print('V28_SMOKE_GATE_PASS', summary['final_covered_bins'], summary['sequence_usage'], flush=True)
PY
phase smoke_union
"$PY" "$TOOLS/audit_stage08_urg_union_v22.py" --root "$ROOT" --run-dir "$SMOKE" \
  --output-dir "$ROOT/runs/stage08_v28_smoke30_urg_union_20261111"
"$PY" "$INPUTS/export_stage08_improved.py" --run-dir "$SMOKE" \
  --output-dir "$ROOT/evidence/stage08_v28_smoke30_20261111"
cp "$ROOT/runs/stage08_v28_smoke30_urg_union_20261111/union_audit.json" \
  "$ROOT/evidence/stage08_v28_smoke30_20261111/"
phase full
bash "$TOOLS/launch_stage08_wkup_cdc_fence_v28.sh" "$ROOT" full > "$WORK/full.log" 2>&1 &
RUNNER_PID=$!
echo "$RUNNER_PID" > "$WORK/full.pid"
"$PY" "$WORK/tools/finalize_stage08_wkup_v28.py" --root "$ROOT" --runner-pid "$RUNNER_PID"
wait "$RUNNER_PID"
phase complete
echo V28_FULL_AUDITED_COMPLETE
