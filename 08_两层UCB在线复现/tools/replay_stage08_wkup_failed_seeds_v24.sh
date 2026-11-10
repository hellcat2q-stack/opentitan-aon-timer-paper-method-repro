#!/usr/bin/env bash
set -euo pipefail

ROOT=$(realpath "${1:?usage: replay_stage08_wkup_failed_seeds_v24.sh REPO_ROOT}")
V24_ROOT="$ROOT/scratch/stage08_v24_wkup_poll_20261111"
SRC_ROOT="$V24_ROOT/source/opentitan"
SIMV="$V24_ROOT/build_scratch/stage08-ucb-v24/aon_timer-sim-vcs/default/simv"
OUT="$ROOT/runs/stage08_wkup_failed_seed_replay_v24_verified_20261111"
VERIFY="$(dirname "$(realpath "$0")")/verify_stage08_uvm_replay.py"
if [[ ! -x "$SIMV" ]]; then
  echo "v24 simv is missing: $SIMV" >&2
  exit 2
fi
if [[ -e "$OUT" ]]; then
  echo "Refusing to overwrite existing regression results: $OUT" >&2
  exit 2
fi
mkdir -p "$OUT"
export dv_root="$SRC_ROOT/hw/dv" SIMULATOR=vcs WAVES=none GUI=0 TB_TOP=tb

for seed in 1135891496 1202340700 1246806959 709099176 1015701649; do
  run_dir="$OUT/$seed"
  mkdir -p "$run_dir/coverage"
  log="$run_dir/run.log"
  set +e
  (cd "$run_dir" && "$SIMV" +cdc_instrumentation_enabled=1 +UVM_NO_RELNOTES +UVM_VERBOSITY=UVM_LOW \
    -licqueue -ucli -do "$SRC_ROOT/hw/dv/tools/sim.tcl" \
    "+ntb_random_seed=$seed" -assert nopostproc \
    +UVM_TESTNAME=aon_timer_base_test +UVM_TEST_SEQ=aon_timer_stress_all_vseq \
    +en_cov=1 +test_timeout_ns=10000000000 \
    -cm line+cond+fsm+tgl+branch+assert+group \
    -cm_dir "$run_dir/coverage/default.vdb" -cm_log /dev/null \
    -cm_name "aon_timer_stress_all.$seed") > "$log" 2>&1
  status=$?
  set -e
  if ! "$ROOT/.venv/bin/python" "$VERIFY" --log "$log" --return-code "$status" \
      --seed "$seed" --output "$run_dir/verification.json"; then
    echo "V24 WKUP regression failed: seed=$seed rc=$status log=$log" >&2
    exit 1
  fi
  echo "V24_WKUP_SEED_PASS seed=$seed"
done
