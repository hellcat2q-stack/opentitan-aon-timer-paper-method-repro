#!/usr/bin/env python3
"""Wait for the existing V30 Full, audit it and export sanitized evidence.

Run on the school server. Never launches simulations or changes frozen inputs.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runner_is_active(pid, run, launcher, proc_root=Path("/proc")):
    """Follow the launcher's exec into the runner; stop for exits and zombies."""
    process = proc_root / str(pid)
    try:
        # A child can remain a zombie until the workflow reaches its shell wait.
        argv = (process / "cmdline").read_bytes().split(b"\0")
        state = (process / "stat").read_text().rsplit(")", 1)[1].split()[0]
    except FileNotFoundError:
        return False
    if state == "Z":
        return False
    if str(run).encode() in argv:
        return True
    # The background shell has not necessarily exec'd Python when we first poll.
    if str(launcher).encode() in argv and b"full" in argv:
        return True
    raise RuntimeError("Runner PID refers to an unexpected process")


def main():
    import fcntl

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--runner-pid", type=int, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    work = root / "scratch/stage08_v30_wkup_phase_bound_20261111"
    run = root / "runs/stage08_vcs_ucb_full1000_20261111_v30"
    launcher = root / "08_两层UCB在线复现/tools/launch_stage08_wkup_phase_bound_v30.sh"
    replay = root / "runs/stage08_wkup_failed_seed_replay_v30_verified_20261111"
    inputs = root / "scratch/stage08_v22_inputs_20261110"
    py = root / ".venv/bin/python"
    export = root / "evidence/stage08_v30_full1000_20261111"
    lock = (work / "finalize.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    phase = "waiting_for_full"

    def status(state, **extra):
        data = {"status": state, "phase": phase,
                "observed_at_server": datetime.now().astimezone().isoformat(timespec="seconds"),
                **extra}
        tmp = work / "finalization_status.tmp"
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        tmp.replace(work / "finalization_status.json")
        print(json.dumps(data), flush=True)

    def execute(command):
        subprocess.run(list(map(str, command)), check=True, cwd=root)

    try:
        status("running", runner_pid=args.runner_pid)
        while runner_is_active(args.runner_pid, run, launcher):
            time.sleep(30)
        phase = "full_gate"
        summary = read(run / "summary.json")
        if not (summary["status"] == "completed" and
                summary["submitted"] == summary["completed"] == 1000 and
                summary["retried"] == 0):
            raise RuntimeError("Full has not finished its 1000-attempt budget")
        phase = "v22_input_comparison"
        protocol = read(run / "protocol.json")
        baseline = read(root / "runs/stage08_vcs_ucb_full1000_20261110_v22/protocol.json")
        same_fields = ("initial_csv_sha256", "mapping_sha256", "author_source_sha256",
                       "baseline_source_sha256", "adapter_sha256", "conversion_source_sha256",
                       "corpus_source_sha256", "seeds", "workers", "logical_batch_size", "budget",
                       "initial_union", "bin_count")
        fields_match = {name: protocol[name] == baseline[name] for name in same_fields}
        fields_match["steering_source_sha256"] = (protocol["steering"]["source_sha256"] ==
                                                   baseline["steering"]["source_sha256"])
        if not all(fields_match.values()):
            raise RuntimeError(f"V22 comparison inputs differ: {fields_match}")
        phase = "source_hashes"
        negative = root / "runs/stage08_v30_stuck_low_check_20261111/negative_check.json"
        if read(negative)["status"] != "pass":
            raise RuntimeError("Stuck-low fault did not trigger the strict WKUP assertion")
        source_hashes = {}
        for line in (work / "source_sha256.txt").read_text().splitlines():
            expected, name = line.split(None, 1)
            path = Path(name.strip())
            if digest(path) != expected:
                raise RuntimeError(f"Frozen source/build changed: {path.name}")
            source_hashes[path.name] = expected
        phase = "event_vector_reward_audit"
        status("running")
        execute([py, inputs / "audit_stage08.py", "--run-dir", run,
                 "--initial-csv", root / "runs/stage08_inputs_xml_20261110_v20_retry1/coverage_bin_by_run.csv"])
        phase = "raw_uvm_audit"
        status("running")
        sys.path.insert(0, str(work / "tools"))
        from verify_stage08_uvm_replay import inspect_log
        raw_cases = []
        for result in read(run / "run_results.json"):
            run_id = result["run_id"]
            log = (run / "batches" / f"batch_{run_id // 10}" / str(run_id) /
                   "raw" / result["test_name"] / "0/run.log")
            raw = log.read_bytes()
            checked = inspect_log(raw.decode(errors="replace"), result["vcs_return_code"])
            accepted = result["status"] == "success"
            if accepted and checked["status"] != "pass":
                raise RuntimeError(f"Raw UVM evidence rejected accepted run {run_id}: {checked}")
            raw_cases.append({"run_id": run_id, "accepted": accepted, **checked,
                              "log_sha256": hashlib.sha256(raw).hexdigest()})
        phase = "urg_union_audit"
        status("running")
        merge = root / "runs/stage08_v30_full1000_urg_union_20261111"
        execute([py, inputs / "audit_stage08_urg_union_v22.py",
                 "--root", root, "--run-dir", run, "--output-dir", merge])
        phase = "export_evidence"
        status("running")
        execute([py, inputs / "export_stage08_improved.py", "--run-dir", run, "--output-dir", export])
        (export / "union_audit.json").write_bytes((merge / "union_audit.json").read_bytes())
        (export / "v22_input_comparison.json").write_text(json.dumps({
            "status": "pass", "matching_fields": fields_match,
            "scope": "Same UCB adapter/policy sources and experiment inputs; testbench/build intentionally differ",
        }, indent=2) + "\n", encoding="utf-8")
        (export / "negative_check.json").write_bytes(negative.read_bytes())
        (export / "source_sha256.txt").write_text("".join(
            f"{value}  {name}\n" for name, value in sorted(source_hashes.items())), encoding="utf-8")
        (export / "raw_uvm_audit.json").write_text(json.dumps({
            "status": "pass", "checked_runs": len(raw_cases), "cases": raw_cases,
            "all_accepted_runs_have_real_test_pass_and_nonzero_simulation_time": True,
            "raw_logs_exported": False}, indent=2) + "\n", encoding="utf-8")
        # Revalidate the actual raw logs, not only previously generated booleans.
        cases = []
        for seed in (1135891496, 1202340700, 1246806959, 709099176, 1015701649):
            prior = read(replay / str(seed) / "verification.json")
            raw = (replay / str(seed) / "run.log").read_bytes()
            actual = {"seed": seed, **inspect_log(raw.decode(errors="replace"), prior["return_code"]),
                      "log_sha256": hashlib.sha256(raw).hexdigest()}
            if actual["log_sha256"] != prior["log_sha256"]:
                raise RuntimeError(f"Replay log changed for {seed}")
            cases.append(actual)
        replay_passed = all(case["status"] == "pass" for case in cases)
        (export / "regression_audit.json").write_text(json.dumps({
            "status": "pass" if replay_passed else "fail", "cases": cases,
            "invalid_earlier_replay": "Earlier directories without 'verified' exited at 0 ps; not accepted as regression evidence",
            "raw_logs_exported": False}, indent=2) + "\n", encoding="utf-8")
        (export / "v22_preservation_audit.json").write_bytes(
            (work / "v22_preservation_audit.json").read_bytes())
        baseline_summary = read(root / "runs/stage08_vcs_ucb_full1000_20261110_v22/summary.json")
        usage = "\n".join(f"| {name} | {count} |" for name, count in summary["sequence_usage"].items())
        report = (
            "# V30 Full 实测结果\n\n"
            "本文件在预算完成、事件/向量/奖励审计、原始 UVM 日志与独立 URG 合并核对后生成。\n\n"
            f"- 提交/完成：{summary['submitted']}/{summary['completed']}；接受 {summary['accepted']}；失败 {summary['failed']}；重试 {summary['retried']}。\n"
            f"- 覆盖：{summary['final_covered_bins']}/4507（{summary['final_coverage_percent']:.4f}%）；初始 508 bins；新增 {summary['new_bins_beyond_initial']} bins。\n"
            f"- wall time：{summary['wall_seconds']:.2f} 秒；累计 simulator CPU：{summary['accumulated_simulator_cpu_seconds_all_attempts']:.2f} 秒。\n"
            f"- 原 V22：{baseline_summary['final_covered_bins']}/4507，失败 {baseline_summary['failed']}；源代码/build 的原始哈希清单核对通过。\n"
            f"- 原始日志复核 {len(raw_cases)} 次；已知失败 seed 真实回归 {sum(case['status'] == 'pass' for case in cases)}/5。\n\n"
            "| 顶层序列 | 提交数 |\n| --- | ---: |\n" + usage + "\n\n"
            "保留 V22 的 UCB adapter/policy、初始向量、cluster map、seed 列表、worker 数和预算；本轮改变 testbench 的配置同步、复位进程作用域与合法分频首周期等待。"
            "这不是 UCB 对随机选择的优越性实验，也不是论文原始结果。"
            "scoreboard 的时序检查使用 12 位相位的有限上界，不声称是完整逐周期黄金模型。\n\n"
            "原始 VDB、simv、完整日志保留服务器；本目录只包含脱敏证据、哈希及实测曲线。\n"
        )
        (export / "README.md").write_text(report, encoding="utf-8")
        (export / "sha256.txt").write_text("".join(
            f"{digest(path)}  {path.name}\n" for path in sorted(export.iterdir())
            if path.name != "sha256.txt"), encoding="utf-8")
        phase = "complete"
        passed = summary["failed"] == 0 and replay_passed
        status("pass" if passed else "fail", completed=summary["completed"],
               failed=summary["failed"], coverage_bins=summary["final_covered_bins"],
               coverage_percent=summary["final_coverage_percent"],
               regression_passed=replay_passed, evidence_directory=export.name)
        if not passed:
            raise RuntimeError("Evidence exported, but zero-failure/regression gate did not pass")
    except Exception as error:
        status("failed", error=f"{type(error).__name__}: {error}")
        raise


if __name__ == "__main__":
    main()
