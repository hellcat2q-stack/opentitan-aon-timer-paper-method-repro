#!/usr/bin/env bash
set -euo pipefail
ROOT=$(realpath "${1:?usage: replay_stage08_wkup_failed_seeds_v28.sh REPO_ROOT}")
WORK="$ROOT/scratch/stage08_v28_wkup_cdc_fence_20261111"
SRC="$WORK/source/opentitan"
SIMV="$WORK/build_scratch/stage08-ucb-v28/aon_timer-sim-vcs/default/simv"
OUT="$ROOT/runs/stage08_wkup_failed_seed_replay_v28_verified_20261111"
test -x "$SIMV"
if [[ -e "$OUT" ]]; then
  echo "Refusing to overwrite regression results: $OUT" >&2
  exit 2
fi
mkdir -p "$OUT"
export dv_root="$SRC/hw/dv" SIMULATOR=vcs WAVES=none GUI=0 TB_TOP=tb
for seed in 1202340700 1246806959 709099176 1015701649 1135891496; do
  run_dir="$OUT/$seed"
  mkdir -p "$run_dir/coverage"
  set +e
  (cd "$run_dir" && "$SIMV" +cdc_instrumentation_enabled=1 +UVM_NO_RELNOTES +UVM_VERBOSITY=UVM_LOW \
    -licqueue -ucli -do "$SRC/hw/dv/tools/sim.tcl" "+ntb_random_seed=$seed" -assert nopostproc \
    +UVM_TESTNAME=aon_timer_base_test +UVM_TEST_SEQ=aon_timer_stress_all_vseq \
    +en_cov=1 +test_timeout_ns=10000000000 -cm line+cond+fsm+tgl+branch+assert+group \
    -cm_dir "$run_dir/coverage/default.vdb" -cm_log /dev/null \
    -cm_name "aon_timer_stress_all.$seed") > "$run_dir/run.log" 2>&1
  status=$?
  set -e
  "$ROOT/.venv/bin/python" "$WORK/tools/verify_stage08_uvm_replay.py" \
    --log "$run_dir/run.log" --return-code "$status" --seed "$seed" --output "$run_dir/verification.json"
done
echo STAGE08_V28_REGRESSION_PASS
