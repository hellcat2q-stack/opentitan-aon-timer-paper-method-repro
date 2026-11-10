#!/usr/bin/env bash
set -euo pipefail

ROOT=$(realpath "${1:?usage: build_stage08_wkup_poll_v24.sh REPO_ROOT}")
SCRIPT_TOOLS=${V24_INPUT_TOOLS:-"$ROOT/08_两层UCB在线复现/tools"}
V22_ROOT="$ROOT/scratch/stage08_v22_20261110"
V24_ROOT="$ROOT/scratch/stage08_v24_wkup_poll_20261111"
SRC_ROOT="$V24_ROOT/source/opentitan"
BUILD_SCRATCH="$V24_ROOT/build_scratch"
LOG="$V24_ROOT/build.log"

if [[ -e "$V24_ROOT" ]]; then
  echo "Refusing to reuse an existing v24 workspace: $V24_ROOT" >&2
  exit 2
fi
mkdir -p "$V24_ROOT/source" "$V24_ROOT/tools"
cp -a "$V22_ROOT/source/opentitan" "$SRC_ROOT"
cp -a "$V22_ROOT/tools/." "$V24_ROOT/tools/"
if [[ ! -f "$SCRIPT_TOOLS/aon_timer_wkup_bounded_poll_v24.patch" ]]; then
  echo "Missing v24 scoreboard patch" >&2
  exit 2
fi
cp "$SCRIPT_TOOLS/aon_timer_wkup_bounded_poll_v24.patch" "$V24_ROOT/tools/"

SCOREBOARD="$SRC_ROOT/hw/ip/aon_timer/dv/env/aon_timer_scoreboard.sv"
grep -q 'csr_rd(.ptr(ral.wkup_count_hi), .value(rtl_count\[63:32\])' "$SCOREBOARD"
patch --dry-run --forward --batch -p1 -d "$SRC_ROOT" \
  -i "$V24_ROOT/tools/aon_timer_wkup_bounded_poll_v24.patch" > "$LOG" 2>&1
patch --forward --batch -p1 -d "$SRC_ROOT" \
  -i "$V24_ROOT/tools/aon_timer_wkup_bounded_poll_v24.patch" >> "$LOG" 2>&1
grep -q 'pin_wait_cycles < 50' "$SCOREBOARD"

sha256sum "$V24_ROOT/tools/aon_timer_wkup_bounded_poll_v24.patch" \
  "$V24_ROOT/tools/aon_timer_coverage_steering_v22.py" \
  "$V24_ROOT/tools/run_vcs_ucb_paper_ucb_v22.py" \
  "$SRC_ROOT/hw/ip/aon_timer/dv/env/aon_timer_scoreboard.sv" \
  > "$V24_ROOT/source_sha256.txt"

export PATH="$ROOT/runtime/stage03_compat/bin:$ROOT/../opentitan_aon_timer_vcs_repro/.venv/bin:$ROOT/.venv/bin:$PATH"
export PYTHONPATH="$ROOT/runtime/stage03_compat/py:$ROOT/runtime/stage03_compat/src/fusesoc-ot-0.5.dev0:$ROOT/runtime/stage03_compat/src/edalize-0.4.0"
dvsim "$SRC_ROOT/hw/ip/aon_timer/dv/aon_timer_sim_cfg.hjson" \
  --proj-root "$SRC_ROOT" \
  --scratch-root "$BUILD_SCRATCH" \
  --branch stage08-ucb-v24 --local --max-parallel 1 \
  --build-only --build-timeout-mins 30 --fixed-seed 42 -i aon_timer_smoke \
  >> "$LOG" 2>&1

SIMV="$BUILD_SCRATCH/stage08-ucb-v24/aon_timer-sim-vcs/default/simv"
if [[ ! -x "$SIMV" ]]; then
  echo "DVSIM completed without the expected VCS executable: $SIMV" >&2
  exit 3
fi
sha256sum "$SIMV" >> "$V24_ROOT/source_sha256.txt"
echo "STAGE08_V24_BUILD_PASS"
