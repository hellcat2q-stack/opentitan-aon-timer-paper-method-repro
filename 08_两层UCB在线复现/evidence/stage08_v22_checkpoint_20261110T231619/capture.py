#!/usr/bin/env python3
"""Capture one consistent event prefix per run; leave simulations untouched."""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_run(root):
    if not root.exists():
        return {"status": "not_started"}
    protocol_bytes = (root / "protocol.json").read_bytes()
    protocol = json.loads(protocol_bytes)
    policy_hash = sha(protocol_bytes)
    # A single read prevents counters and sequence usage from different moments.
    data = (root / "events.jsonl").read_bytes()
    data = data[:data.rfind(b"\n") + 1]
    previous, submits, feedback = "0" * 64, {}, {}
    covered, active = protocol["initial_union"], 0
    for index, line in enumerate(data.splitlines()):
        event = json.loads(line)
        event_hash = event.pop("event_hash")
        assert event["event_index"] == index and event["previous_hash"] == previous
        assert event["policy_hash"] == policy_hash
        assert sha(json.dumps(event, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()) == event_hash
        previous = event_hash
        run_id = event.get("run_id")
        if event["event"] == "submit":
            assert run_id == len(submits) and event["seed"] == protocol["seeds"][run_id]
            submits[run_id] = event
            active += 1
        elif event["event"] == "feedback":
            assert run_id in submits and run_id not in feedback
            feedback[run_id] = event
            active -= 1
            covered = event["accumulated_covered"]
        assert 0 <= active <= protocol["workers"]
    summary = root / "summary.json"
    return {
        "status": json.loads(summary.read_bytes())["status"] if summary.exists() else "running",
        "budget": protocol["budget"], "submitted": len(submits), "completed": len(feedback),
        "failed": sum(not event["accepted"] for event in feedback.values()), "active": active,
        "initial_coverage_bins": protocol["initial_union"], "coverage_bins": covered,
        "denominator": protocol["bin_count"], "coverage_percent": 100 * covered / protocol["bin_count"],
        "selected_sequences": dict(Counter(event["sequence"] for event in submits.values())),
        "target_statuses": dict(Counter(event.get("steering", {}).get("status") for event in submits.values())),
        "target_hits": sum(bool(event.get("steering_bin_hit")) for event in feedback.values()),
        "event_head": previous, "event_prefix_sha256": sha(data), "protocol_sha256": policy_hash,
        "event_prefix_chain_verified": True,
        "final_audit_available": (root / "audit.json").is_file(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    now = datetime.now().astimezone()
    work = args.root / "scratch/stage08_v22_inputs_20261110"
    pid = int((work / "pair.pid").read_text().strip())
    proc = Path(f"/proc/{pid}/cmdline")
    snapshot = {
        "observed_at_server": now.isoformat(timespec="seconds"),
        "source": "One read of each run's complete event prefix; hash chain checked, not a final coverage/physical-identity audit",
        "capture_source_sha256": sha(Path(__file__).read_bytes()),
        "controller_pid": pid,
        "controller_alive": proc.exists() and b"complete_stage08_ucb_pair_v22.sh" in proc.read_bytes(),
        "runs": {label: read_run(args.root / "runs" / name) for label, name in (
            ("v22_full", "stage08_vcs_ucb_full1000_20261110_v22"),
            ("v20_control", "stage08_vcs_paper_ucb_full1000_20261110_v20"),
        )},
        "raw_logs_exported": False,
    }
    output = args.root / "evidence" / now.strftime("stage08_v22_checkpoint_%Y%m%dT%H%M%S")
    output.mkdir(exist_ok=False)
    (output / "checkpoint.json").write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    shutil.copyfile(__file__, output / "capture.py")
    (output / "sha256.txt").write_text("".join(
        f"{sha(path.read_bytes())}  {path.name}\n" for path in sorted(output.iterdir())
    ), encoding="utf-8")
    print(json.dumps({"evidence_directory": output.name, **snapshot}), flush=True)


if __name__ == "__main__":
    main()
