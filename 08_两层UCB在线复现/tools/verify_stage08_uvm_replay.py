#!/usr/bin/env python3
"""Reject empty/zero-time VCS exits as well as UVM failures in seed replays."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def inspect_log(text, return_code):
    counts = {}
    for severity in ("UVM_ERROR", "UVM_FATAL"):
        matches = re.findall(rf"^\s*{severity}\s*:\s*(\d+)\s*$", text, re.MULTILINE)
        counts[severity.lower()] = int(matches[-1]) if matches else None
    times = re.findall(r"^\s*Time:\s*(\d+)\s+ps\s*$", text, re.MULTILINE)
    simulation_time = int(times[-1]) if times else None
    errors = []
    if return_code != 0:
        errors.append("nonzero_process_exit")
    if not re.search(r"^TEST PASSED CHECKS\s*$", text, re.MULTILINE):
        errors.append("missing_test_pass_marker")
    if "--- UVM Report Summary ---" not in text:
        errors.append("missing_uvm_summary")
    if any(value != 0 for value in counts.values()):
        errors.append("missing_or_nonzero_uvm_error_counts")
    if re.search(r"^\s*(?:UVM_ERROR|UVM_FATAL)\s+@", text, re.MULTILINE):
        errors.append("uvm_error_or_fatal_report")
    if re.search(r"^\s*ERROR:", text, re.MULTILINE):
        errors.append("simulator_script_error")
    if simulation_time is None or simulation_time <= 0:
        errors.append("missing_or_zero_simulation_time")
    return {"status": "fail" if errors else "pass", "return_code": return_code,
            **counts, "simulation_time_ps": simulation_time, "errors": errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--return-code", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.log.read_bytes()
    result = {"seed": args.seed, **inspect_log(raw.decode(errors="replace"), args.return_code),
              "log_sha256": hashlib.sha256(raw).hexdigest(), "raw_logs_exported": False}
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result), flush=True)
    raise SystemExit(0 if result["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
