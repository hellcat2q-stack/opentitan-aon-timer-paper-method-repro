"""Execute real V30 smoke/full ablations with bounded concurrency and audits."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from stage09_policy import METHODS
from export_stage09_v30 import export_run, manifest, plot

WORK_NAME = "stage09_v30_ablation_20261111"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def verify_manifest(path):
    for line in path.read_text().splitlines():
        expected, filename = line.split(None, 1)
        if sha(Path(filename.strip())) != expected:
            raise RuntimeError(f"Frozen input/source changed: {Path(filename).name}")


def paths(root):
    v30 = root / "scratch/stage08_v30_wkup_phase_bound_20261111"
    v19 = root / "scratch/stage08_vcs_paper_ucb_20261109_v19"
    v20 = root / "scratch/stage08_v20_20261110"
    return {
        "simv": v30 / "build_scratch/stage08-ucb-v30/aon_timer-sim-vcs/default/simv",
        "dv-root": v30 / "source/opentitan/hw/dv",
        "initial-csv": root / "runs/stage08_inputs_xml_20261110_v20_retry1/coverage_bin_by_run.csv",
        "mapping": root / "runs/stage07_recluster_xml_20261110_v20/bin_to_cluster.csv",
        "canonical-report": root / "runs/stage06_conversion_20261101T_v10/reports/original_g0",
        "author-source": v19 / "source/generic_adaptive_runner_ucb_continuous_refill_paper_ucb_v17.py",
        "baseline-source": v19 / "source/generic_adaptive_runner_ucb_continuous_refill_norepeat_poolmi.py",
        "conversion-source": v20 / "tools/run_stage06_conversion_stable.py",
        "corpus-source": v19 / "source/run_aon_timer_initial_corpus.py",
    }


def prepare(root, work):
    source_tools = Path(__file__).resolve().parent
    v30 = root / "scratch/stage08_v30_wkup_phase_bound_20261111"
    verify_manifest(v30 / "source_sha256.txt")
    final = read(v30 / "finalization_status.json")
    assert final["status"] == "pass" and final["completed"] == 1000 and final["failed"] == 0
    work.mkdir(exist_ok=False)
    shutil.copytree(v30 / "tools", work / "tools")
    for path in source_tools.glob("*.py"):
        shutil.copyfile(path, work / "tools" / path.name)
    tests = source_tools.parent / "tests"
    if tests.exists():
        shutil.copytree(tests, work / "tests", ignore=shutil.ignore_patterns("__pycache__"))
    # Freeze the complete executable Python/patch dependency set and inputs.
    frozen = [p for p in (work / "tools").iterdir() if p.is_file() and p.suffix in (".py", ".patch")]
    frozen += [p for p in paths(root).values() if p.is_file()]
    frozen += [root / "scratch/stage08_v22_inputs_20261110/audit_stage08_urg_union_v22.py"]
    (work / "frozen_sha256.txt").write_text("".join(f"{sha(p)}  {p}\n" for p in sorted(set(frozen))))
    write(work / "preregistration.json", {
        "schema": "stage09-v30-preregistration-v1", "methods": list(METHODS),
        "budget_per_method": 1000, "smoke_budget_per_method": 30, "workers_per_method": 10,
        "global_method_concurrency": 1, "seed": 42, "initial_runs": 39, "initial_bins": 508,
        "bin_count": 4507, "steering_for_all_methods": False, "retry": False,
        "created_at_server": datetime.now().astimezone().isoformat(timespec="seconds"),
        "reference_full": "stage08_vcs_ucb_full1000_20261111_v30",
        "reference_scope": "Steered V30 reference only; not the uniform no-steering matrix Full",
        "frozen_dependency_manifest_sha256": sha(work / "frozen_sha256.txt"),
    })
    print("STAGE09_PREPARED", work.name, flush=True)


def verify_run(root, work, run):
    protocol, summary = read(run / "protocol.json"), read(run / "summary.json")
    assert summary["status"] == "completed"
    assert summary["submitted"] == summary["completed"] == protocol["budget"]
    assert summary["retried"] == 0
    baseline = read(root / "runs/stage08_vcs_ucb_full1000_20261111_v30/protocol.json")
    keys = ("initial_csv_sha256", "mapping_sha256", "author_source_sha256", "baseline_source_sha256",
            "conversion_source_sha256", "corpus_source_sha256", "simv_sha256", "canonical_report_sha256",
            "workers", "logical_batch_size", "initial_runs", "bin_count", "cluster_count", "initial_union")
    matching = {key: protocol[key] == baseline[key] for key in keys}
    matching["seeds"] = protocol["seeds"] == baseline["seeds"][:protocol["budget"]]
    assert all(matching.values()), matching
    assert protocol["steering"]["enabled"] is False
    write(run / "input_comparison.json", {"status": "pass", "matching_fields": matching,
          "scope": "Same V30 build and all frozen inputs; method policy/adapter and uniformly disabled steering intentionally differ"})
    subprocess.run([str(root / ".venv/bin/python"), str(work / "tools/audit_stage09_v30.py"),
                    "--run-dir", str(run), "--initial-csv", str(paths(root)["initial-csv"]),
                    "--mapping", str(paths(root)["mapping"])], check=True)
    sys.path.insert(0, str(work / "tools"))
    from verify_stage08_uvm_replay import inspect_log
    cases = []
    for result in read(run / "run_results.json"):
        i = result["run_id"]
        log = run / "batches" / f"batch_{i // 10}" / str(i) / "raw" / result["test_name"] / "0/run.log"
        raw = log.read_bytes()
        checked = inspect_log(raw.decode(errors="replace"), result["vcs_return_code"])
        if result["status"] == "success":
            assert checked["status"] == "pass", (i, checked)
        cases.append({"run_id": i, "accepted": result["status"] == "success", **checked,
                      "log_sha256": hashlib.sha256(raw).hexdigest()})
    write(run / "raw_uvm_audit.json", {"status": "pass", "checked_runs": len(cases), "cases": cases,
          "all_accepted_runs_have_real_test_pass_and_nonzero_simulation_time": True, "raw_logs_exported": False})
    union = root / "runs" / (run.name + "_urg_union")
    if not (union / "union_audit.json").exists():
        if union.exists():
            raise RuntimeError("Incomplete previous URG merge; inspect before manual resume")
        subprocess.run([str(root / ".venv/bin/python"),
                        str(root / "scratch/stage08_v22_inputs_20261110/audit_stage08_urg_union_v22.py"),
                        "--root", str(root), "--run-dir", str(run), "--output-dir", str(union)], check=True)
    assert read(union / "union_audit.json")["status"] == "pass"
    shutil.copyfile(union / "union_audit.json", run / "union_audit.json")
    if protocol["budget"] == 30:
        assert summary["failed"] == 0, summary


def compare(root, work):
    output = root / "evidence/stage09_v30_matrix_20261111"
    output.mkdir(exist_ok=False)
    records, series = [], []
    for method in METHODS:
        run = root / "runs" / f"stage09_v30_{method}_full1000_20261111"
        summary = read(run / "summary.json")
        assert read(run / "audit.json")["status"] == read(run / "union_audit.json")["status"] == "pass"
        records.append(summary)
        series.append((method, run / "coverage_curve.csv"))
    write(output / "comparison.json", {"status": "pass", "scope": "Six methods under uniform V30 no-steering protocol",
          "preregistration_sha256": sha(work / "preregistration.json"), "methods": records,
          "v30_steered_full_reference": read(root / "runs/stage08_vcs_ucb_full1000_20261111_v30/summary.json")})
    plot(series, output / "comparison.png")
    table = "| 方法 | 覆盖 bins/4507 | 覆盖率 | 失败 | CPU 秒 | Wall 秒 |\n| --- | ---: | ---: | ---: | ---: | ---: |\n"
    for s in records:
        table += (f"| {s['method']} | {s['final_covered_bins']} | {s['final_coverage_percent']:.4f}% | {s['failed']} | "
                  f"{s['accumulated_simulator_cpu_seconds_all_attempts']:.2f} | {s['wall_seconds']:.2f} |\n")
    (output / "README.md").write_text(
        "# 第九步统一环境对照与消融：最终结果\n\n六种方法均完成 1000 次，"
        "全部通过事件/向量/奖励、原始 UVM 日志与独立 URG 合并审计。\n\n" + table +
        "\n统一初始 39 条语料、508/4507、V30 build、seed 42、10 workers、1000 次预算，全部关闭 steering。"
        "逐方法的 30 次 smoke 为独立门禁，不拼入正式预算。\n\n"
        "本表为单 seed 本地作者衍生实现；论文隐藏回归池、seed 和覆盖分母尚未完全对齐，不能声称逐数复现论文。"
        "原 V30 4127/4507 为开启额外 steering 的单独参考；旧随机基线使用旧解析器，也不作为本表对照。"
        "共享服务器负载会影响 CPU 与 walltime，单轮耗时差不能作为统计显著性结论。\n", encoding="utf-8")
    shutil.copyfile(work / "preregistration.json", output / "preregistration.json")
    (output / "source_sha256.txt").write_text("".join(
        f"{sha(p)}  {p.name}\n" for p in sorted((work / "tools").iterdir()) if p.is_file() and p.name.startswith(("run_stage09", "stage09", "audit_stage09", "export_stage09"))))
    manifest(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    work = root / "scratch" / WORK_NAME
    if args.prepare:
        prepare(root, work)
        return
    import fcntl
    lock = (work / "workflow.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state = {"status": "running", "phase": "preflight", "completed": []}
    status_path = work / "workflow_status.json"

    def status(**fields):
        state.update(fields)
        state["observed_at_server"] = datetime.now().astimezone().isoformat(timespec="seconds")
        write(status_path, state)
        print(json.dumps(state), flush=True)

    try:
        verify_manifest(work / "frozen_sha256.txt")
        subprocess.run([str(root / ".venv/bin/python"), str(work / "tests/test_stage09_policy.py"), "-v"], check=True)
        env = os.environ.copy()
        env.update(PYTHONHASHSEED="0", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
        for method in METHODS:
            for phase, budget in (("smoke30", 30), ("full1000", 1000)):
                name = f"stage09_v30_{method}_{phase}_20261111"
                run = root / "runs" / name
                export = root / "evidence" / name
                status(method=method, phase=phase, run_name=name)
                if export.exists():
                    assert args.resume, "Use --resume only after inspecting prior results"
                    verify_run(root, work, run)
                    state["completed"].append(name)
                    continue
                if run.exists():
                    assert args.resume and (run / "summary.json").exists(), "Existing/incomplete run requires manual inspection"
                else:
                    cmd = [str(root / ".venv/bin/python"), "-u", str(work / "tools/run_stage09_v30.py"),
                           "--method", method, "--result-dir", str(run), "--submissions", str(budget),
                           "--workers", "10", "--batch-size", "10", "--seed", "42"]
                    for key, value in paths(root).items():
                        cmd += ["--" + key, str(value)]
                    with (work / (name + ".log")).open("w") as log:
                        subprocess.run(cmd, cwd=root, env=env, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=subprocess.STDOUT, check=True)
                status(phase=phase + "_audit")
                verify_manifest(work / "frozen_sha256.txt")
                verify_run(root, work, run)
                export_run(run, export)
                state["completed"].append(name)
                status()
        status(phase="comparison")
        compare(root, work)
        status(status="pass", phase="complete")
    except Exception as exc:
        status(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    main()
