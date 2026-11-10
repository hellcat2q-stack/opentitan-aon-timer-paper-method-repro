#!/usr/bin/env bash
set -euo pipefail

ROOT=$(realpath "${1:?usage: build_stage08_paper_ucb_v20.sh REPO_ROOT}")
V20_ROOT="$ROOT/scratch/stage08_v20_20261110"
SRC_ROOT="$V20_ROOT/source/opentitan"
BUILD_SCRATCH="$V20_ROOT/build_scratch"
LOG="$V20_ROOT/build.log"

if [[ -e "$BUILD_SCRATCH" ]]; then
  echo "Refusing to reuse an existing v20 build directory: $BUILD_SCRATCH" >&2
  exit 2
fi
if [[ ! -e "$SRC_ROOT" ]]; then
  mkdir -p "$V20_ROOT/source"
  cp -a "$ROOT/src/opentitan" "$SRC_ROOT"
fi

BASE_SEQ="$SRC_ROOT/hw/ip/aon_timer/dv/env/seq_lib/aon_timer_base_vseq.sv"
JUMP_SEQ="$SRC_ROOT/hw/ip/aon_timer/dv/env/seq_lib/aon_timer_jump_vseq.sv"
SCOREBOARD="$SRC_ROOT/hw/ip/aon_timer/dv/env/aon_timer_scoreboard.sv"
PATCH="$V20_ROOT/tools/aon_timer_scoreboard_wkup_hi_fix.patch"
grep -q 'if (steer_field == 0)' "$BASE_SEQ"
grep -q 'wkup_count_gap inside' "$JUMP_SEQ"
if grep -q 'csr_rd(.ptr(ral.wkup_count_lo), .value(rtl_count\[63:32\])' "$SCOREBOARD"; then
  patch --dry-run --forward --batch -p1 -d "$SRC_ROOT" -i "$PATCH" > "$LOG" 2>&1
  patch --forward --batch -p1 -d "$SRC_ROOT" -i "$PATCH" >> "$LOG" 2>&1
elif ! grep -q 'csr_rd(.ptr(ral.wkup_count_hi), .value(rtl_count\[63:32\])' "$SCOREBOARD"; then
  echo "Unexpected wakeup scoreboard high-word read" >&2
  exit 4
fi
grep -q 'csr_rd(.ptr(ral.wkup_count_hi), .value(rtl_count\[63:32\])' "$SCOREBOARD"
sha256sum "$SCOREBOARD" "$BASE_SEQ" "$JUMP_SEQ" > "$V20_ROOT/source_sha256.txt"

export PATH="$ROOT/runtime/stage03_compat/bin:$ROOT/../opentitan_aon_timer_vcs_repro/.venv/bin:$ROOT/.venv/bin:$PATH"
export PYTHONPATH="$ROOT/runtime/stage03_compat/py:$ROOT/runtime/stage03_compat/src/fusesoc-ot-0.5.dev0:$ROOT/runtime/stage03_compat/src/edalize-0.4.0"
dvsim "$SRC_ROOT/hw/ip/aon_timer/dv/aon_timer_sim_cfg.hjson" \
  --proj-root "$SRC_ROOT" \
  --scratch-root "$BUILD_SCRATCH" \
  --branch stage08-scoreboard-v20 --local --max-parallel 1 \
  --build-only --build-timeout-mins 30 --fixed-seed 42 -i aon_timer_smoke \
  >> "$LOG" 2>&1

SIMV="$BUILD_SCRATCH/stage08-scoreboard-v20/aon_timer-sim-vcs/default/simv"
if [[ ! -x "$SIMV" ]]; then
  echo "DVSIM completed without the expected VCS executable: $SIMV" >&2
  exit 3
fi
sha256sum "$SIMV" >> "$V20_ROOT/source_sha256.txt"
echo "STAGE08_V20_BUILD_PASS"
