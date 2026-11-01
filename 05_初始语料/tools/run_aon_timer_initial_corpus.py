#!/usr/bin/env python3
"""Run the Stage 05 AON Timer initial corpus with the verified VCS simv entry.

The runner deliberately records all raw data on the server.  It does not merge
coverage databases or perform adaptive selection; each configured sequence is
run exactly ``runs_per_sequence`` times with deterministic derived seeds.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import random
import re
import subprocess
import time
from pathlib import Path
from typing import Any

SEQUENCES = (
    ("aon_timer_smoke", "aon_timer_smoke_vseq"),
    ("aon_timer_prescaler", "aon_timer_prescaler_vseq"),
    ("aon_timer_jump", "aon_timer_jump_vseq"),
    ("aon_timer_stress_all", "aon_timer_stress_all_vseq"),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_count(text: str, label: str) -> int | None:
    match = re.search(rf"^\s*{re.escape(label)}\s*:\s*(\d+)\s*$", text, re.MULTILINE)
    return int(match.group(1)) if match else None


def parse_cpu_seconds(text: str) -> float | None:
    match = re.search(r"^CPU Time:\s*([0-9.]+)\s+seconds", text, re.MULTILINE)
    return float(match.group(1)) if match else None


def parse_urg_dashboard(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    match = re.search(
        r"Total Groups Coverage Summary\s+COVERED EXPECTED SCORE.*?\n\s*(\d+)\s+(\d+)\s+([0-9.]+)",
        text,
        re.DOTALL,
    )
    if not match:
        return {"covered_groups": None, "expected_groups": None, "group_score_percent": None}
    return {
        "covered_groups": int(match.group(1)),
        "expected_groups": int(match.group(2)),
        "group_score_percent": float(match.group(3)),
    }


def run_one(job: dict[str, Any]) -> dict[str, Any]:
    root = Path(job["result_root"])
    run_dir = root / job["test_name"] / str(job["index"])
    run_dir.mkdir(parents=True, exist_ok=True)
    coverage_dir = run_dir / "coverage" / "default.vdb"
    report_dir = run_dir / "urg_report"
    simv = job["simv"]
    dv_root = job["dv_root"]
    sim_tcl = Path(dv_root) / "tools" / "sim.tcl"
    seed = job["seed"]
    sequence = job["sequence"]
    test_name = job["test_name"]
    command = [
        simv,
        "+cdc_instrumentation_enabled=1",
        "+UVM_NO_RELNOTES",
        "+UVM_VERBOSITY=UVM_LOW",
        "-licqueue",
        "-ucli",
        "-do",
        str(sim_tcl),
        f"+ntb_random_seed={seed}",
        "-assert",
        "nopostproc",
        "+UVM_TESTNAME=aon_timer_base_test",
        f"+UVM_TEST_SEQ={sequence}",
        "+en_cov=1",
        "-cm",
        "line+cond+fsm+tgl+branch+assert",
        "-cm_dir",
        str(coverage_dir),
        "-cm_log",
        "/dev/null",
        "-cm_name",
        f"{test_name}.{seed}",
    ]
    (run_dir / "command.txt").write_text(" ".join(command) + "\n", encoding="utf-8")
    env = os.environ.copy()
    env.update({"dv_root": dv_root, "SIMULATOR": "vcs", "WAVES": "none"})
    started = time.monotonic()
    sim_rc = 125
    with (run_dir / "run.log").open("w", encoding="utf-8") as log:
        try:
            proc = subprocess.run(
                command,
                cwd=run_dir,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
                timeout=job["timeout_seconds"],
            )
            sim_rc = proc.returncode
        except subprocess.TimeoutExpired:
            sim_rc = 124
            log.write(f"\nSTAGE05_TIMEOUT seconds={job['timeout_seconds']}\n")
    elapsed = time.monotonic() - started
    (run_dir / "rc").write_text(f"{sim_rc}\n", encoding="utf-8")
    log_text = (run_dir / "run.log").read_text(encoding="utf-8", errors="replace")
    markers = "\n".join(
        line
        for line in log_text.splitlines()
        if re.search(r"UVM_ERROR :|UVM_FATAL :|TEST PASSED CHECKS|Coverage Metrics: during simulation", line)
    ) + "\n"
    (run_dir / "markers.txt").write_text(markers, encoding="utf-8")
    urg_command = [
        "urg",
        "-lca",
        "-full64",
        "+urg+lic+wait",
        "-metric",
        "group",
        "-show",
        "tests",
        "-group",
        "ratio",
        "-group",
        "lrm_bin_name",
        "-group",
        "instcov_for_score",
        "-group",
        "maxmissing",
        "100000",
        "-dir",
        str(coverage_dir),
        "-format",
        "text",
        "-report",
        str(report_dir),
    ]
    (run_dir / "urg_command.txt").write_text(" ".join(urg_command) + "\n", encoding="utf-8")
    urg_rc = 99
    if sim_rc == 0 and coverage_dir.exists():
        with (run_dir / "urg.log").open("w", encoding="utf-8") as urg_log:
            try:
                urg_proc = subprocess.run(
                    urg_command,
                    cwd=run_dir,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=urg_log,
                    stderr=subprocess.STDOUT,
                    check=False,
                    timeout=job["timeout_seconds"],
                )
                urg_rc = urg_proc.returncode
            except subprocess.TimeoutExpired:
                urg_rc = 124
                urg_log.write(f"\nSTAGE05_TIMEOUT seconds={job['timeout_seconds']}\n")
    else:
        (run_dir / "urg.log").write_text("URG skipped because simulation failed or produced no VDB.\n", encoding="utf-8")
    (run_dir / "urg_rc").write_text(f"{urg_rc}\n", encoding="utf-8")
    dashboard = parse_urg_dashboard(report_dir / "dashboard.txt")
    result = {
        "global_run_id": job["global_run_id"],
        "test_name": test_name,
        "sequence": sequence,
        "sequence_run_index": job["index"],
        "seed": seed,
        "vcs_return_code": sim_rc,
        "urg_return_code": urg_rc,
        "wall_seconds": round(elapsed, 3),
        "simulator_cpu_seconds": parse_cpu_seconds(log_text),
        "uvm_pass": "TEST PASSED CHECKS" in log_text,
        "uvm_error": parse_count(log_text, "UVM_ERROR"),
        "uvm_fatal": parse_count(log_text, "UVM_FATAL"),
        **dashboard,
        "relative_run_dir": str(run_dir.relative_to(root)).replace(os.sep, "/"),
    }
    (run_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    hash_paths = ["command.txt", "urg_command.txt", "run.log", "rc", "markers.txt", "urg.log", "urg_rc", "result.json"]
    with (run_dir / "sha256sums.txt").open("w", encoding="utf-8") as hashes:
        for name in hash_paths:
            path = run_dir / name
            hashes.write(f"{sha256(path)}  {name}\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simv", required=True)
    parser.add_argument("--dv-root", required=True)
    parser.add_argument("--result-dir", required=True)
    parser.add_argument("--runs-per-sequence", type=int, default=10)
    parser.add_argument("--base-seed", type=int, default=505)
    parser.add_argument("--parallel", type=int, default=4)
    parser.add_argument("--timeout-mins", type=int, default=20)
    args = parser.parse_args()
    if args.runs_per_sequence <= 0 or args.parallel <= 0 or args.timeout_mins <= 0:
        parser.error("runs-per-sequence, parallel, and timeout-mins must be positive")
    result_root = Path(args.result_dir).resolve()
    if result_root.exists() and any(result_root.iterdir()):
        parser.error("result-dir must be new or empty; existing results are never overwritten")
    result_root.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.base_seed)
    jobs: list[dict[str, Any]] = []
    global_run_id = 0
    for test_name, sequence in SEQUENCES:
        for index in range(args.runs_per_sequence):
            jobs.append(
                {
                    "global_run_id": global_run_id,
                    "test_name": test_name,
                    "sequence": sequence,
                    "index": index,
                    "seed": rng.randint(1, 2**31 - 1),
                    "simv": str(Path(args.simv).resolve()),
                    "dv_root": str(Path(args.dv_root).resolve()),
                    "result_root": str(result_root),
                    "timeout_seconds": args.timeout_mins * 60,
                }
            )
            global_run_id += 1
    (result_root / "protocol.json").write_text(
        json.dumps(
            {
                "stage": 5,
                "runs_per_sequence": args.runs_per_sequence,
                "sequence_count": len(SEQUENCES),
                "expected_runs": len(jobs),
                "base_seed": args.base_seed,
                "seed_rule": "random.Random(base_seed).randint(1, 2**31-1), sequence-major job order",
                "parallel_workers": args.parallel,
                "timeout_minutes_per_run": args.timeout_mins,
                "adaptive_selection": False,
                "sequences": [{"test_name": n, "sequence": s} for n, s in SEQUENCES],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallel) as pool:
        futures = [pool.submit(run_one, job) for job in jobs]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results.append(result)
            print(
                f"{result['global_run_id']:02d} {result['test_name']}[{result['sequence_run_index']}] "
                f"seed={result['seed']} vcs={result['vcs_return_code']} urg={result['urg_return_code']} "
                f"wall={result['wall_seconds']}s",
                flush=True,
            )
    results.sort(key=lambda item: item["global_run_id"])
    manifest = {
        "stage": 5,
        "protocol_file": "protocol.json",
        "runs": results,
        "counts": {
            "total": len(results),
            "vcs_pass": sum(r["vcs_return_code"] == 0 for r in results),
            "urg_pass": sum(r["urg_return_code"] == 0 for r in results),
            "uvm_pass": sum(r["uvm_pass"] for r in results),
            "timeouts": sum(r["vcs_return_code"] == 124 or r["urg_return_code"] == 124 for r in results),
        },
    }
    (result_root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest["counts"], sort_keys=True))
    passed = (
        manifest["counts"]["total"] == len(jobs)
        and manifest["counts"]["vcs_pass"] == len(jobs)
        and manifest["counts"]["urg_pass"] == len(jobs)
        and manifest["counts"]["uvm_pass"] == len(jobs)
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
