#!/usr/bin/env bash
set -euo pipefail

ROOT=$(realpath "${1:?usage: launch_stage08_wkup_cdc_fence_v28.sh REPO_ROOT preflight|smoke|full}")
PHASE=${2:?phase must be preflight, smoke or full}
V28_ROOT="$ROOT/scratch/stage08_v28_wkup_cdc_fence_20261111"
V20_ROOT="$ROOT/scratch/stage08_v20_20261110"
V19_ROOT="$ROOT/scratch/stage08_vcs_paper_ucb_20261109_v19"
SIMV="$V28_ROOT/build_scratch/stage08-ucb-v28/aon_timer-sim-vcs/default/simv"
INITIAL="$ROOT/runs/stage08_inputs_xml_20261110_v20_retry1/coverage_bin_by_run.csv"
MAPPING="$ROOT/runs/stage07_recluster_xml_20261110_v20/bin_to_cluster.csv"
CANONICAL_REPORT="$ROOT/runs/stage06_conversion_20261101T_v10/reports/original_g0"
case "$PHASE" in
  preflight) BUDGET=10; RESULT="$ROOT/runs/stage08_vcs_ucb_preflight_20261111_v28" ;;
  smoke) BUDGET=30; RESULT="$ROOT/runs/stage08_vcs_ucb_smoke30_20261111_v28" ;;
  full) BUDGET=1000; RESULT="$ROOT/runs/stage08_vcs_ucb_full1000_20261111_v28" ;;
  *) echo "unknown phase: $PHASE" >&2; exit 2 ;;
esac
if [[ ! -x "$SIMV" || ! -f "$INITIAL" || ! -f "$MAPPING" ]]; then
  echo "v28 build or frozen inputs are missing" >&2
  exit 2
fi
if [[ -e "$RESULT" ]]; then
  echo "Refusing to overwrite existing result directory: $RESULT" >&2
  exit 2
fi
export PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
RUN_ARGS=(
  --author-source "$V19_ROOT/source/generic_adaptive_runner_ucb_continuous_refill_paper_ucb_v17.py"
  --baseline-source "$V19_ROOT/source/generic_adaptive_runner_ucb_continuous_refill_norepeat_poolmi.py"
  --conversion-source "$V20_ROOT/tools/run_stage06_conversion_stable.py"
  --corpus-source "$V19_ROOT/source/run_aon_timer_initial_corpus.py"
  --initial-csv "$INITIAL"
  --mapping "$MAPPING" --simv "$SIMV"
  --canonical-report "$CANONICAL_REPORT"
  --dv-root "$V28_ROOT/source/opentitan/hw/dv" --result-dir "$RESULT"
  --submissions "$BUDGET" --workers 10 --batch-size 10 --seed 42 --steering
  --sv-source "$V28_ROOT/source/opentitan/hw/ip/aon_timer/dv/env/seq_lib/aon_timer_base_vseq.sv"
  --sv-source "$V28_ROOT/source/opentitan/hw/ip/aon_timer/dv/env/seq_lib/aon_timer_prescaler_vseq.sv"
  --sv-source "$V28_ROOT/source/opentitan/hw/ip/aon_timer/dv/env/seq_lib/aon_timer_jump_vseq.sv"
  --sv-patch "$V28_ROOT/tools/aon_timer_directed_coverage.patch"
)
if [[ "$PHASE" == preflight ]]; then RUN_ARGS+=(--preflight-only); fi
exec "$ROOT/.venv/bin/python" -u "$V28_ROOT/tools/run_vcs_ucb_paper_ucb_v22.py" "${RUN_ARGS[@]}"
