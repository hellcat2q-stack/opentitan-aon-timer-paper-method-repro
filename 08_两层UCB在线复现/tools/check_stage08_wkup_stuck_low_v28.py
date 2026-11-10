#!/usr/bin/env python3
"""Fault-injection check: the bounded WKUP window must still reject stuck-low pins."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from verify_stage08_uvm_replay import inspect_log


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    work = root / "scratch/stage08_v28_wkup_cdc_fence_20261111"
    out = root / "runs/stage08_v28_stuck_low_check_20261111"
    out.mkdir(exist_ok=False)
    dv_root = work / "source/opentitan/hw/dv"
    tcl = out / "force_stuck_low.tcl"
    tcl.write_text('source "$::env(dv_root)/tools/sim.tcl"\n'
                   'force tb.dut.intr_wkup_timer_expired_o 0\n'
                   'force tb.dut.wkup_req_o 0\nrun\nquit\n')
    env = os.environ.copy()
    env.update(dv_root=str(dv_root), SIMULATOR="vcs", WAVES="none", GUI="1", TB_TOP="tb")
    command = [str(work / "build_scratch/stage08-ucb-v28/aon_timer-sim-vcs/default/simv"),
               "+cdc_instrumentation_enabled=1", "+UVM_NO_RELNOTES", "+UVM_VERBOSITY=UVM_LOW",
               "-licqueue", "-ucli", "-do", str(tcl), "+ntb_random_seed=42", "-assert", "nopostproc",
               "+UVM_TESTNAME=aon_timer_base_test", "+UVM_TEST_SEQ=aon_timer_jump_vseq",
               "+aon_steer_field=1", "+aon_steer_value=7", "+en_cov=1",
               "+test_timeout_ns=10000000000", "-cm", "line+cond+fsm+tgl+branch+assert+group",
               "-cm_dir", str(out / "coverage/default.vdb"), "-cm_log", "/dev/null",
               "-cm_name", "wkup_stuck_low.42"]
    (out / "command.json").write_text(json.dumps(command, indent=2) + "\n")
    with (out / "run.log").open("w") as log:
        result = subprocess.run(command, env=env, cwd=out, stdin=subprocess.DEVNULL,
                                stdout=log, stderr=subprocess.STDOUT, timeout=1200)
    raw = (out / "run.log").read_bytes()
    text = raw.decode(errors="replace")
    checked = inspect_log(text, result.returncode)
    expected = bool(re.search(r"UVM_ERROR[^\n]*Check failed intr_status_exp\[WKUP\]", text))
    passed = (expected and checked["simulation_time_ps"] is not None and
              checked["simulation_time_ps"] > 0 and checked["uvm_error"] == 1 and
              checked["uvm_fatal"] == 0 and "TEST FAILED CHECKS" in text)
    report = {"status": "pass" if passed else "fail",
              "purpose": "Intentional pin fault must fail the existing strict WKUP assertion",
              "faulted_simulation_accepted_as_coverage": False,
              "strict_wkup_assertion_fired": expected, "observed": checked,
              "log_sha256": hashlib.sha256(raw).hexdigest(), "raw_logs_exported": False}
    (out / "negative_check.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
