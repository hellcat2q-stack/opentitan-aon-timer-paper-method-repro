#!/usr/bin/env bash
set -euo pipefail

ROOT=$(realpath "${1:?usage: launch_stage08_steered_v16.sh REPO_ROOT}")
WORK="$ROOT/scratch/stage08_vcs_steered_20261105_v15"
SIMV="$ROOT/scratch/stage08_steered_build_v12_20261105/stage08-steered-build-v12/aon_timer-sim-vcs/default/simv"
RESULT="$ROOT/runs/stage08_vcs_steered_full1000_v16_20261105"

if [[ ! -x "$SIMV" ]]; then
  echo "Verified VCS build is missing: $SIMV" >&2
  exit 2
fi
if [[ -e "$RESULT" ]]; then
  echo "Refusing to overwrite existing run directory: $RESULT" >&2
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
  --result-dir "$RESULT" --submissions 1000 --workers 10 --batch-size 10 --seed 42 \
  --steering \
  --sv-source "$ROOT/src/opentitan/hw/ip/aon_timer/dv/env/seq_lib/aon_timer_base_vseq.sv" \
  --sv-source "$ROOT/src/opentitan/hw/ip/aon_timer/dv/env/seq_lib/aon_timer_prescaler_vseq.sv" \
  --sv-source "$ROOT/src/opentitan/hw/ip/aon_timer/dv/env/seq_lib/aon_timer_jump_vseq.sv" \
  --sv-patch "$WORK/aon_timer_directed_coverage.patch"
