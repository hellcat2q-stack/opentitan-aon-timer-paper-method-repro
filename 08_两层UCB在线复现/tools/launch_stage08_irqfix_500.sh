#!/usr/bin/env bash
set -euo pipefail
ROOT=$(realpath "${1:?usage: launch_stage08_irqfix_500.sh REPO_ROOT}")
WORK="$ROOT/scratch/stage08_vcs_optimized_20261104"
SIMV="$ROOT/scratch/stage08_irqfix_build_20261104/stage08-irqfix-build/aon_timer-sim-vcs/default/simv"
RESULT="$ROOT/runs/stage08_vcs_optimized_full500_irqfix_20261104"

for path in "$SIMV" "$WORK/run_vcs_ucb_optimized.py" "$ROOT/src/opentitan/hw/dv"; do
  if [[ ! -e "$path" ]]; then
    echo "Required irqfix input is missing: $path" >&2
    exit 2
  fi
done
if [[ -e "$RESULT" ]]; then
  echo "Refusing to overwrite existing result directory: $RESULT" >&2
  exit 2
fi

export PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
exec "$ROOT/.venv/bin/python" -u "$WORK/run_vcs_ucb_optimized.py" \
  --author-source "$WORK/source/generic_adaptive_runner_ucb_continuous_refill_poolmi_global_gain.py" \
  --baseline-source "$WORK/source/generic_adaptive_runner_ucb_continuous_refill_norepeat_poolmi.py" \
  --conversion-source "$WORK/source/run_stage06_conversion.py" \
  --corpus-source "$WORK/source/run_aon_timer_initial_corpus.py" \
  --initial-csv "$ROOT/runs/stage06_conversion_20261101T_v10/coverage_bin_by_run.csv" \
  --mapping "$WORK/bin_to_cluster.csv" --simv "$SIMV" \
  --dv-root "$ROOT/src/opentitan/hw/dv" \
  --result-dir "$RESULT" --submissions 500 --workers 10 --batch-size 10 --seed 42
