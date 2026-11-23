"""Run only the three identity-affected methods in independent 8/6-test runs."""
from datetime import datetime
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

import run_stage09_matrix_v30 as matrix
from export_stage09_v30 import export_run, manifest, plot
from stage09_policy import METHODS

AFFECTED = ("Full", "NoIncrementalRefill", "NoRuntimePenalty")
REUSED = ("RandomSelection", "SequenceUCBOnly", "ClusterUCBOnly")
DATE = "20261123"
WORKFLOW = f"stage09_identity_repair_{DATE}"


def configure(count):
    matrix.WORK_NAME = f"stage09_{count}test_idfix_{DATE}"
    matrix.RUN_PREFIX = f"stage09_{count}test_idfix"
    matrix.RUN_DATE = DATE
    matrix.SELECTED_TEST_COUNT = count
    matrix.CATALOG_PATH = f"configs/aon_timer_{count}test_catalog.json"
    matrix.METHODS = AFFECTED


def command(root, work, count, method, output, budget):
    configure(count)
    cmd = [str(root / ".venv/bin/python"), "-u", str(work / "tools/run_stage09_v30.py"),
           "--method", method, "--result-dir", str(output), "--submissions", str(budget),
           "--workers", "10", "--batch-size", "10", "--seed", "42"]
    for key, value in matrix.paths(root).items():
        cmd += ["--" + key, str(value)]
    return cmd


def comparison(root, count):
    output = root / "evidence" / f"stage09_{count}test_idfix_matrix_{DATE}"
    output.mkdir(exist_ok=False)
    records, series = [], []
    for method in AFFECTED + (REUSED if count == 8 else ()):
        reused = method in REUSED
        name = (f"stage09_8test_{method}_full1000_20261119" if reused
                else f"stage09_{count}test_idfix_{method}_full1000_{DATE}")
        evidence = root / "evidence" / name
        assert matrix.read(evidence / "audit.json")["status"] == "pass"
        assert matrix.read(evidence / "union_audit.json")["status"] == "pass"
        for line in (evidence / "sha256.txt").read_text().splitlines():
            expected, file = line.split(None, 1)
            assert matrix.sha(evidence / file.strip()) == expected
        if not reused:
            assert matrix.read(evidence / "arm_identity_audit.json")["status"] == "pass"
        summary = matrix.read(evidence / "summary.json")
        records.append({"method": method, "reused_unaffected_result": reused,
                        "source_evidence": name, "summary": summary,
                        "source_manifest_sha256": matrix.sha(evidence / "sha256.txt")})
        series.append((method, evidence / "coverage_curve.csv"))
    matrix.write(output / "comparison.json", {"status": "pass", "test_pool_size": count,
        "scope": "Three repaired methods; unaffected eight-test results reused without rerunning. Six-test unaffected methods have no completed formal results and are outside this repair request.",
        "records": records})
    plot(series, output / "comparison.png")
    lines = [f"# {count}-test 身份修正实测结果", "", "原始受影响结果保留；修正仅统一 test ID，不修改仿真参数或 UCB 公式。", "",
             "| 方法 | 覆盖 bins/4507 | 覆盖率 | 失败 | CPU 秒 | Wall 秒 | 来源 |",
             "| --- | ---: | ---: | ---: | ---: | ---: | --- |"]
    for record in records:
        s = record["summary"]
        lines.append(f"| {s['method']} | {s['final_covered_bins']} | {s['final_coverage_percent']:.4f}% | {s['failed']} | {s['accumulated_simulator_cpu_seconds_all_attempts']:.2f} | {s['wall_seconds']:.2f} | {'原轮次复用' if record['reused_unaffected_result'] else '修正后新跑'} |")
    (output / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    control = root / "scratch" / WORKFLOW
    order = [(count, method) for method in AFFECTED for count in (8, 6)]
    if args.prepare:
        control.mkdir(exist_ok=False)
        for count in (8, 6):
            configure(count)
            matrix.prepare(root, root / "scratch" / matrix.WORK_NAME)
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        matrix.write(control / "preregistration.json", {
            "schema": "stage09-identity-repair-preregistration-v1", "source_revision": revision,
            "created_at_server": datetime.now().astimezone().isoformat(),
            "affected_methods_to_rerun": list(AFFECTED), "unaffected_methods_not_rerun": list(REUSED),
            "order": [{"pool": count, "method": method} for count, method in order],
            "smoke_per_job": 30, "formal_per_job": 1000, "seed": 42, "workers": 10,
            "global_method_concurrency": 1, "initial_runs": 39, "initial_bins": 508,
            "bin_count": 4507, "batch_size": 10, "steering": False, "retry": False,
            "change": "Use catalog test ID as scheduling and feedback arm; preserve SV class, official options and all UCB scoring formulas.",
            "old_results_policy": "Preserve all old completed and stopped runs. Never concatenate smoke or stopped feedback with new formal runs.",
            "per_pool_frozen_manifests": {str(count): matrix.sha(root / "scratch" / f"stage09_{count}test_idfix_{DATE}" / "frozen_sha256.txt") for count in (8, 6)}})
        return
    import fcntl
    lock = (control / "workflow.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state = {"status": "running", "completed": []}
    def status(**fields):
        state.update(fields)
        state["observed_at_server"] = datetime.now().astimezone().isoformat()
        matrix.write(control / "workflow_status.json", state)
        print(json.dumps(state), flush=True)
    env = os.environ.copy()
    env.update(PYTHONHASHSEED="0", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
               STAGE09_REPO_ROOT=str(root))
    try:
        # Validate both pools and all six methods before the first simulator job.
        for count in (8, 6):
            configure(count)
            work = root / "scratch" / matrix.WORK_NAME
            matrix.verify_manifest(work / "frozen_sha256.txt")
            env["STAGE09_AUTHOR_SOURCE"] = str(matrix.paths(root)["author-source"])
            for name in ("test_stage09_policy.py", "test_stage09_arm_identity.py"):
                subprocess.run([str(root / ".venv/bin/python"), str(work / "tests" / name), "-v"], env=env, check=True)
            for method in METHODS:
                output = control / f"preflight_{count}test_{method}"
                if output.exists():
                    assert args.resume and matrix.read(output / "preflight.json")["status"] == "pass"
                    continue
                with (control / f"preflight_{count}test_{method}.log").open("w") as log:
                    subprocess.run(command(root, work, count, method, output, 30) + ["--preflight-only"],
                                   env=env, cwd=root, stdout=log, stderr=subprocess.STDOUT, check=True)
        for count, method in order:
            configure(count)
            work = root / "scratch" / matrix.WORK_NAME
            for phase, budget in (("smoke30", 30), ("full1000", 1000)):
                name = f"stage09_{count}test_idfix_{method}_{phase}_{DATE}"
                run, export = root / "runs" / name, root / "evidence" / name
                status(pool=count, method=method, phase=phase, run_name=name)
                matrix.verify_manifest(work / "frozen_sha256.txt")
                if export.exists():
                    assert args.resume
                    matrix.verify_run(root, work, run)
                    state["completed"].append(name)
                    continue
                if run.exists():
                    assert args.resume and (run / "summary.json").exists(), "Incomplete run requires investigation; never silently restart"
                else:
                    with (work / (name + ".log")).open("w") as log:
                        subprocess.run(command(root, work, count, method, run, budget), cwd=root, env=env,
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, check=True)
                status(phase=phase + "_audit")
                matrix.verify_manifest(work / "frozen_sha256.txt")
                matrix.verify_run(root, work, run)
                assert matrix.read(run / "arm_identity_audit.json")["status"] == "pass"
                export_run(run, export)
                state["completed"].append(name)
                status()
        for count in (8, 6):
            comparison(root, count)
        status(status="pass", phase="complete")
    except Exception as exc:
        status(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    main()
