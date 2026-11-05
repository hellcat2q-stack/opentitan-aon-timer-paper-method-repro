#!/usr/bin/env bash
set -euo pipefail

ROOT=$(realpath "$1")
PHASE=${2:?phase must be preflight, smoke, or full}
WORK="$ROOT/scratch/stage08_vcs_20261104"
PY="$ROOT/.venv/bin/python"
CONFIG="$WORK/aon_timer_vcs_ucb.yaml"
INITIAL="$ROOT/runs/stage06_conversion_20261101T_v10/coverage_bin_by_run.csv"
MAPPING="$WORK/bin_to_cluster.csv"

case "$PHASE" in
  preflight) BUDGET=10; PREFLIGHT_ONLY=1 ;;
  smoke) BUDGET=10; PREFLIGHT_ONLY=0 ;;
  full) BUDGET=1000; PREFLIGHT_ONLY=0 ;;
  *) echo "unknown phase: $PHASE" >&2; exit 2 ;;
esac

"$PY" - "$CONFIG" "$BUDGET" <<'PY'
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
protocol = cfg["protocol"]
budget = int(sys.argv[2])
assert int(protocol["workers"]) == 10
assert int(protocol["logical_batch_size"]) == 10
assert budget in (10, int(protocol["submissions"]))
if budget == int(protocol["submissions"]):
    assert int(protocol["logical_batches"]) == 100
print(f"VCS_CONFIG_OK phase_budget={budget}")
PY

SIMV=$(awk 'NR == 1 {print $1; exit}' "$ROOT/runs/stage05_initial_corpus_20261101T/aon_timer_smoke/0/command.txt")
RESULT="$ROOT/runs/stage08_vcs_${PHASE}_20261104"
export PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1

RUN_ARGS=(
  --author-source "$WORK/source/generic_adaptive_runner_ucb_continuous_refill_norepeat_poolmi.py" \
  --conversion-source "$WORK/source/run_stage06_conversion.py" \
  --corpus-source "$WORK/source/run_aon_timer_initial_corpus.py" \
  --initial-csv "$INITIAL" \
  --mapping "$MAPPING" \
  --simv "$SIMV" \
  --dv-root "$ROOT/src/opentitan/hw/dv" \
  --result-dir "$RESULT" \
  --submissions "$BUDGET" --workers 10 --batch-size 10 --seed 42
)
if (( PREFLIGHT_ONLY )); then
  RUN_ARGS+=(--preflight-only)
fi
exec "$PY" -u "$WORK/run_vcs_ucb.py" "${RUN_ARGS[@]}"
