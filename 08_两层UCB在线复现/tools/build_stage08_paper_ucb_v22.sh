#!/usr/bin/env bash
set -euo pipefail

ROOT=$(realpath "${1:?usage: build_stage08_paper_ucb_v22.sh REPO_ROOT}")
SCRIPT_TOOLS=${V22_INPUT_TOOLS:-"$ROOT/08_两层UCB在线复现/tools"}
V20_ROOT="$ROOT/scratch/stage08_v20_20261110"
V22_ROOT="$ROOT/scratch/stage08_v22_20261110"
SRC_ROOT="$V22_ROOT/source/opentitan"
BUILD_SCRATCH="$V22_ROOT/build_scratch"
LOG="$V22_ROOT/build.log"

if [[ -e "$V22_ROOT" ]]; then
  echo "Refusing to reuse an existing v22 retry workspace: $V22_ROOT" >&2
  exit 2
fi
mkdir -p "$V22_ROOT/source" "$V22_ROOT/tools"
cp -a "$V20_ROOT/source/opentitan" "$SRC_ROOT"
for file in \
  aon_timer_directed_coverage.patch \
  aon_timer_scoreboard_wkup_hi_fix.patch \
  aon_timer_jump_counter_fix.patch \
  aon_timer_base_safe_steering.patch \
  aon_timer_coverage_steering.py \
  aon_timer_coverage_steering_v20.py \
  stage08_stable_coverage_v20.py \
  run_stage06_conversion_stable.py; do
  cp "$V20_ROOT/tools/$file" "$V22_ROOT/tools/"
done
for file in \
  aon_timer_parameter_range_v22.patch \
  aon_timer_coverage_steering_v22.py \
  run_vcs_ucb_paper_ucb_v22.py; do
  if [[ ! -f "$SCRIPT_TOOLS/$file" ]]; then
    echo "Missing v22 experiment input: $SCRIPT_TOOLS/$file" >&2
    exit 2
  fi
  cp "$SCRIPT_TOOLS/$file" "$V22_ROOT/tools/"
done

BASE_SEQ="$SRC_ROOT/hw/ip/aon_timer/dv/env/seq_lib/aon_timer_base_vseq.sv"
SCOREBOARD="$SRC_ROOT/hw/ip/aon_timer/dv/env/aon_timer_scoreboard.sv"
PATCH="$V22_ROOT/tools/aon_timer_parameter_range_v22.patch"
for required in \
  "$V22_ROOT/tools/aon_timer_directed_coverage.patch" \
  "$V22_ROOT/tools/aon_timer_jump_counter_fix.patch" \
  "$V22_ROOT/tools/aon_timer_base_safe_steering.patch" \
  "$V22_ROOT/tools/aon_timer_coverage_steering.py" \
  "$V22_ROOT/tools/stage08_stable_coverage_v20.py" \
  "$V22_ROOT/tools/run_stage06_conversion_stable.py"; do
  if [[ ! -f "$required" ]]; then
    echo "Missing inherited v20 build/runtime dependency: $required" >&2
    exit 2
  fi
done
if ! grep -q 'if (steer_field == 0)' "$BASE_SEQ"; then
  echo "Expected safe non-target threshold domain in copied v20 source" >&2
  exit 4
fi
grep -q 'csr_rd(.ptr(ral.wkup_count_hi), .value(rtl_count\[63:32\])' "$SCOREBOARD"
patch --dry-run --forward --batch -p1 -d "$SRC_ROOT" -i "$PATCH" > "$LOG" 2>&1
patch --forward --batch -p1 -d "$SRC_ROOT" -i "$PATCH" >> "$LOG" 2>&1
grep -q 'if (steer_field == 0 && !full_threshold_domain)' "$BASE_SEQ"
grep -q 'full_threshold_domain = (get_type_name() == "aon_timer_jump_vseq")' "$BASE_SEQ"
grep -q 'if (wdog_bark_thold == 0) wdog_count == 0' "$BASE_SEQ"
sha256sum "$PATCH" "$V22_ROOT/tools/aon_timer_coverage_steering_v22.py" \
  "$V22_ROOT/tools/run_vcs_ucb_paper_ucb_v22.py" "$BASE_SEQ" "$SCOREBOARD" \
  "$SRC_ROOT/hw/ip/aon_timer/dv/env/seq_lib/aon_timer_jump_vseq.sv" \
  > "$V22_ROOT/source_sha256.txt"

export PATH="$ROOT/runtime/stage03_compat/bin:$ROOT/../opentitan_aon_timer_vcs_repro/.venv/bin:$ROOT/.venv/bin:$PATH"
export PYTHONPATH="$ROOT/runtime/stage03_compat/py:$ROOT/runtime/stage03_compat/src/fusesoc-ot-0.5.dev0:$ROOT/runtime/stage03_compat/src/edalize-0.4.0"
dvsim "$SRC_ROOT/hw/ip/aon_timer/dv/aon_timer_sim_cfg.hjson" \
  --proj-root "$SRC_ROOT" \
  --scratch-root "$BUILD_SCRATCH" \
  --branch stage08-ucb-v22 --local --max-parallel 1 \
  --build-only --build-timeout-mins 30 --fixed-seed 42 -i aon_timer_smoke \
  >> "$LOG" 2>&1

SIMV="$BUILD_SCRATCH/stage08-ucb-v22/aon_timer-sim-vcs/default/simv"
if [[ ! -x "$SIMV" ]]; then
  echo "DVSIM completed without the expected VCS executable: $SIMV" >&2
  exit 3
fi
sha256sum "$SIMV" >> "$V22_ROOT/source_sha256.txt"
echo "STAGE08_V22_BUILD_PASS"
