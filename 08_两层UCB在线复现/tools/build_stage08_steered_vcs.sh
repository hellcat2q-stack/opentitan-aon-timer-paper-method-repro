#!/usr/bin/env bash
set -euo pipefail

ROOT=$(realpath "${1:?usage: build_stage08_steered_vcs.sh REPO_ROOT}")
SCRATCH="$ROOT/scratch/stage08_steered_build_v4_20261105"
LOG="$ROOT/scratch/stage08_steered_build_v4_20261105.log"
WORK="$ROOT/scratch/stage08_vcs_steered_20261105"
if [[ -e "$SCRATCH" ]]; then
  echo "Refusing to reuse build scratch: $SCRATCH" >&2
  exit 2
fi

export PATH="$ROOT/runtime/stage03_compat/bin:$ROOT/../opentitan_aon_timer_vcs_repro/.venv/bin:$ROOT/.venv/bin:$PATH"
export PYTHONPATH="$ROOT/runtime/stage03_compat/py:$ROOT/runtime/stage03_compat/src/fusesoc-ot-0.5.dev0:$ROOT/runtime/stage03_compat/src/edalize-0.4.0"

JUMP_PATCH="$WORK/aon_timer_jump_counter_fix.patch"
JUMP_SOURCE="$ROOT/src/opentitan/hw/ip/aon_timer/dv/env/seq_lib/aon_timer_jump_vseq.sv"
BASE_PATCH="$WORK/aon_timer_base_safe_steering.patch"
BASE_SOURCE="$ROOT/src/opentitan/hw/ip/aon_timer/dv/env/seq_lib/aon_timer_base_vseq.sv"
if grep -q 'wkup_thold dist' "$BASE_SOURCE"; then
  patch --dry-run -p1 -d "$ROOT/src/opentitan" -i "$BASE_PATCH" > "$LOG" 2>&1
  patch --forward --batch -p1 -d "$ROOT/src/opentitan" -i "$BASE_PATCH" >> "$LOG" 2>&1
elif ! grep -q 'if (steer_field == 0)' "$BASE_SOURCE"; then
  echo "Refusing to patch an unexpected base sequence source: $BASE_SOURCE" >&2
  exit 4
fi
if grep -q 'wkup_thold+10' "$JUMP_SOURCE"; then
  patch --dry-run -p1 -d "$ROOT/src/opentitan" -i "$JUMP_PATCH" >> "$LOG" 2>&1
  patch --forward --batch -p1 -d "$ROOT/src/opentitan" -i "$JUMP_PATCH" >> "$LOG" 2>&1
elif ! grep -q 'wkup_count_gap inside' "$JUMP_SOURCE"; then
  echo "Refusing to patch an unexpected jump sequence source: $JUMP_SOURCE" >&2
  exit 5
fi
grep -q 'if (steer_field == 0)' "$BASE_SOURCE"
grep -q 'wkup_count_gap inside' "$JUMP_SOURCE"

dvsim "$ROOT/src/opentitan/hw/ip/aon_timer/dv/aon_timer_sim_cfg.hjson" \
  --proj-root "$ROOT/src/opentitan" \
  --scratch-root "$SCRATCH" \
  --branch stage08-steered-build-v4 --local --max-parallel 1 \
  --build-only --build-timeout-mins 30 --fixed-seed 42 -i aon_timer_smoke \
  >> "$LOG" 2>&1

SIMV="$SCRATCH/stage08-steered-build-v4/aon_timer-sim-vcs/default/simv"
if [[ ! -x "$SIMV" ]]; then
  echo "DVSIM completed without the expected VCS executable: $SIMV" >&2
  exit 3
fi
sha256sum "$SIMV"
echo "STEERED_VCS_BUILD_PASS"
