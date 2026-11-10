#!/usr/bin/env bash
set -euo pipefail
ROOT=$(realpath "${1:?usage: build_stage08_wkup_phase_bound_v30.sh REPO_ROOT}")
INPUT="$ROOT/08_两层UCB在线复现/tools"
WORK="$ROOT/scratch/stage08_v30_wkup_phase_bound_20261111"
SRC="$WORK/source/opentitan"
if [[ -e "$WORK" ]]; then
  echo "Refusing to overwrite v30 workspace: $WORK" >&2
  exit 2
fi
mkdir -p "$WORK/source" "$WORK/tools"
cp -a "$ROOT/scratch/stage08_v22_20261110/source/opentitan" "$SRC"
cp -a "$ROOT/scratch/stage08_v22_20261110/tools/." "$WORK/tools/"
cp "$INPUT/verify_stage08_uvm_replay.py" "$WORK/tools/"
for PATCH in aon_timer_reset_thread_scope_v25.patch aon_timer_wkup_aon_window_v27.patch aon_timer_wkup_cdc_fence_v28.patch aon_timer_wkup_prescaler_bound_v30.patch; do
  cp "$INPUT/$PATCH" "$WORK/tools/"
  patch --dry-run --forward --batch -p1 -d "$SRC" -i "$WORK/tools/$PATCH" >> "$WORK/build.log" 2>&1
  patch --forward --batch -p1 -d "$SRC" -i "$WORK/tools/$PATCH" >> "$WORK/build.log" 2>&1
done
grep -Fq 'logic [11:0] prescale_count_d, prescale_count_q;' "$SRC/hw/ip/aon_timer/rtl/aon_timer_core.sv"
export PATH="$ROOT/runtime/stage03_compat/bin:$ROOT/../opentitan_aon_timer_vcs_repro/.venv/bin:$ROOT/.venv/bin:$PATH"
export PYTHONPATH="$ROOT/runtime/stage03_compat/py:$ROOT/runtime/stage03_compat/src/fusesoc-ot-0.5.dev0:$ROOT/runtime/stage03_compat/src/edalize-0.4.0"
dvsim "$SRC/hw/ip/aon_timer/dv/aon_timer_sim_cfg.hjson" --proj-root "$SRC" \
  --scratch-root "$WORK/build_scratch" --branch stage08-ucb-v30 --local --max-parallel 1 \
  --build-only --build-timeout-mins 30 --fixed-seed 42 -i aon_timer_smoke >> "$WORK/build.log" 2>&1
SIMV="$WORK/build_scratch/stage08-ucb-v30/aon_timer-sim-vcs/default/simv"
test -x "$SIMV"
sha256sum "$WORK/tools/aon_timer_reset_thread_scope_v25.patch" "$WORK/tools/aon_timer_wkup_aon_window_v27.patch" "$WORK/tools/aon_timer_wkup_cdc_fence_v28.patch" "$WORK/tools/aon_timer_wkup_prescaler_bound_v30.patch" \
  "$WORK/tools/aon_timer_coverage_steering_v22.py" "$WORK/tools/run_vcs_ucb_paper_ucb_v22.py" \
  "$SRC/hw/ip/aon_timer/dv/env/aon_timer_scoreboard.sv" "$SRC/hw/ip/aon_timer/dv/env/seq_lib/aon_timer_base_vseq.sv" "$SRC/hw/ip/aon_timer/dv/env/seq_lib/aon_timer_jump_vseq.sv" "$SIMV" > "$WORK/source_sha256.txt"
echo STAGE08_V30_BUILD_PASS
