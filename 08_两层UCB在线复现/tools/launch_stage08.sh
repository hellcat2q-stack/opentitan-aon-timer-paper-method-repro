#!/usr/bin/env bash
set -euo pipefail
ROOT=$(realpath "$1")
PHASE=${2:?preflight, smoke or full}
WORK="$ROOT/scratch/stage08_v1_20261102"
case "$PHASE" in
  preflight) BUDGET=10; set -- --preflight-only ;;
  smoke) BUDGET=10; set -- ;;
  full) BUDGET=1000; set -- ;;
  *) exit 2 ;;
esac
export PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
SIMV=$("$ROOT/.venv/bin/python" -c 'import shlex,sys; print(shlex.split(open(sys.argv[1]).read())[0])' "$ROOT/runs/stage05_initial_corpus_20261101T/aon_timer_smoke/0/command.txt")
exec "$ROOT/.venv/bin/python" -u "$WORK/run_vcs_ucb.py" \
  --author-source "$WORK/source/generic_adaptive_runner_ucb_continuous_refill_norepeat_poolmi.py" \
  --conversion-source "$WORK/source/run_stage06_conversion.py" \
  --corpus-source "$WORK/source/run_aon_timer_initial_corpus.py" \
  --initial-csv "$ROOT/runs/stage06_conversion_20261101T_v10/coverage_bin_by_run.csv" \
  --mapping "$WORK/bin_to_cluster.csv" --simv "$SIMV" \
  --dv-root "$ROOT/src/opentitan/hw/dv" \
  --result-dir "$ROOT/runs/stage08_${PHASE}_20261102_v1" \
  --submissions "$BUDGET" --workers 10 --batch-size 10 --seed 42 "$@"
