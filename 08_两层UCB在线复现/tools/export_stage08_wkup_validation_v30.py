#!/usr/bin/env python3
"""Export compact verified regressions and diagnostic history; raw logs stay on server."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    work = root / "scratch/stage08_v30_wkup_phase_bound_20261111"
    sys.path.insert(0, str(work / "tools"))
    from verify_stage08_uvm_replay import inspect_log
    replay = root / "runs/stage08_wkup_failed_seed_replay_v30_verified_20261111"
    cases = []
    for seed in (1135891496, 1202340700, 1246806959, 709099176, 1015701649):
        result = read(replay / str(seed) / "verification.json")
        log = replay / str(seed) / "run.log"
        actual = inspect_log(log.read_text(errors="replace"), result["return_code"])
        assert actual["status"] == result["status"] == "pass", result
        assert sha(log) == result["log_sha256"]
        cases.append(result)
    negative_dir = root / "runs/stage08_v30_stuck_low_check_20261111"
    negative = read(negative_dir / "negative_check.json")
    assert negative["status"] == "pass" and negative["strict_wkup_assertion_fired"]
    assert sha(negative_dir / "run.log") == negative["log_sha256"]
    frozen = {}
    for line in (work / "source_sha256.txt").read_text().splitlines():
        expected, name = line.split(None, 1)
        path = Path(name.strip())
        assert sha(path) == expected
        assert path.name not in frozen
        frozen[path.name] = expected
    invalid = []
    for version, directory in (
        ("v23", "stage08_v22_failed_seed_replay_v23_20261111"),
        ("v24", "stage08_wkup_failed_seed_replay_v24_20261111"),
    ):
        for log in sorted((root / "runs" / directory).glob("*/run.log")):
            result = inspect_log(log.read_text(errors="replace"), 0)
            assert result["status"] == "fail" and result["simulation_time_ps"] == 0
            invalid.append({"version": version, "seed": int(log.parent.name), **result,
                            "classification": "invalid_zero_time_replay", "log_sha256": sha(log)})
    assert len(invalid) == 9
    partial = {}
    for version in ("v23", "v24"):
        run = root / "runs" / f"stage08_vcs_ucb_full1000_20261111_{version}"
        partial[version] = {"classification": "aborted_partial_not_full",
                            "last_progress": read(run / "progress.json")}
    observations = []
    for directory, seed, marker in (
        ("stage08_wkup_diagnostic_v26_20261111", 1135891496, "WKUP_DIAG"),
        ("stage08_wkup_diagnostic_v26_seed2_20261111", 1202340700, "WKUP_DIAG"),
        ("stage08_wkup_phase_diagnostic_v29_20261111", 709099176, "WKUP_PHASE_DIAG"),
    ):
        log = root / "runs" / directory / str(seed) / "run.log"
        snapshots = []
        for line in log.read_text(errors="replace").splitlines():
            if marker not in line:
                continue
            fields = dict(re.findall(r"\b(tick|num|model_count|thold|prescale|prescaler|actual_count|actual_phase|phase|enable|exp|pin|aon)=([^ ]+)", line))
            for name, width in (("actual_count", 16), ("actual_phase", 3), ("enable", 1)):
                if name in fields:
                    fields[name] = "0x" + fields[name].removeprefix("0x")[-width:]
            timestamp = re.search(r"@\s*(\d+)\s+ps", line)
            snapshots.append({"time_ps": int(timestamp.group(1)), **fields})
        assert snapshots
        observations.append({"seed": seed, "snapshots": snapshots,
                             "diagnostic_only": True, "log_sha256": sha(log)})
    output = root / "evidence/stage08_v30_validation_20261111"
    output.mkdir(exist_ok=False)
    files = {
        "regression_audit.json": {"status": "pass", "cases": cases, "raw_logs_exported": False},
        "negative_check.json": negative,
        "diagnostic_history.json": {"invalid_earlier_replays": invalid, "partial_full_runs": partial,
                                    "observations": observations, "raw_logs_exported": False},
        "v22_preservation_audit.json": read(work / "v22_preservation_audit.json"),
    }
    for name, data in files.items():
        (output / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    (output / "source_sha256.txt").write_text("".join(
        f"{value}  {name}\n" for name, value in sorted(frozen.items())), encoding="utf-8")
    (output / "sha256.txt").write_text("".join(
        f"{sha(path)}  {path.name}\n" for path in sorted(output.iterdir())), encoding="utf-8")
    print(json.dumps({"status": "pass", "output": output.name, "regressions_passed": len(cases),
                      "invalid_old_replays": len(invalid), "raw_logs_exported": False}), flush=True)


if __name__ == "__main__":
    main()
