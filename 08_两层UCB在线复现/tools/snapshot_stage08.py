#!/usr/bin/env python3
"""Write a sanitized live checkpoint without declaring an unfinished run complete."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--server-root", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    args = p.parse_args()
    root, out = args.server_root, args.output_dir
    out.mkdir(exist_ok=False, parents=True)
    work = root / "scratch/stage08_v1_20261102"
    checkpoint = {"schema": "aon-timer-stage08-live-checkpoint-v1",
        "captured_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "status": "in_progress", "full_plan": {"submissions": 1000, "workers": 10, "logical_batch": 10, "seed": 42},
        "full_launch_gate": "smoke has 10 audited completions; UVM failures count without rewards, infrastructure errors block full",
        "phases": {}}
    for phase in ("preflight", "smoke", "full"):
        run = root / f"runs/stage08_{phase}_20261102_v1"
        phase_data = {"created": run.exists()}
        for name in ("preflight.json", "progress.json", "summary.json", "audit.json"):
            if (run / name).is_file():
                phase_data[name.removesuffix(".json")] = json.loads((run / name).read_text())
        checkpoint["phases"][phase] = phase_data
        if (run / "protocol.json").is_file():
            (out / f"{phase}_protocol.json").write_bytes((run / "protocol.json").read_bytes())
    failures = []
    for file in (root / "runs/stage08_smoke_20261102_v1/batches").glob("batch_*/*/execution.json"):
        result = json.loads(file.read_text())
        if result["status"] != "success":
            fields = ("run_id", "seed", "sequence", "status", "vcs_return_code", "urg_return_code", "uvm_error", "uvm_fatal", "uvm_pass", "wall_seconds", "simulator_cpu_seconds", "error")
            entry = {k: result[k] for k in fields if k in result}
            signatures = []
            for log in file.parent.glob("raw/*/0/run.log"):
                signatures.extend(line for line in log.read_text(errors="replace").splitlines() if line.startswith("UVM_ERROR @") or line.startswith("UVM_FATAL @"))
            entry["signatures"] = signatures
            entry["accepted_for_coverage"] = False
            failures.append(entry)
    checkpoint["smoke_failure_evidence"] = failures
    for name in ("source_sha256.txt", "pipeline.rc"):
        if (work / name).is_file():
            (out / name).write_bytes((work / name).read_bytes())
    (out / "checkpoint.json").write_text(json.dumps(checkpoint, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with (out / "sha256.txt").open("w", encoding="utf-8") as f:
        for file in sorted(out.iterdir()):
            if file.name != "sha256.txt":
                f.write(hashlib.sha256(file.read_bytes()).hexdigest() + "  " + file.name + "\n")
    print(json.dumps(checkpoint, ensure_ascii=False))


if __name__ == "__main__":
    main()
