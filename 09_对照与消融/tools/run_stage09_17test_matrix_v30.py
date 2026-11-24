"""Run all 17 official test entries with the repaired six-method V30 protocol."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import argparse
import csv
import json
import os
from pathlib import Path
import random
import subprocess
import time

import run_stage09_matrix_v30 as matrix
from export_stage09_v30 import export_run, manifest
from stage09_policy import METHODS

DATE = "20261124"
WORK_NAME = f"stage09_17test_all_{DATE}"


def configure():
    matrix.WORK_NAME = WORK_NAME
    matrix.RUN_PREFIX = "stage09_17test"
    matrix.RUN_DATE = DATE
    matrix.SELECTED_TEST_COUNT = 17
    matrix.CATALOG_PATH = "configs/aon_timer_17test_catalog.json"
    matrix.POOL_LABEL = "十七测试池"


def verify_official_catalog(root, output):
    """Independently resolve the frozen official HJSON test/run-mode entries."""
    import hjson
    configure()
    src = matrix.paths(root)["dv-root"].parents[1]
    cfg = src / "hw/ip/aon_timer/dv/aon_timer_sim_cfg.hjson"
    seen, definitions, modes, files = set(), {}, {}, {}

    def visit(path):
        path = path.resolve()
        if path in seen:
            return
        seen.add(path)
        files[str(path.relative_to(src.resolve()))] = matrix.sha(path)
        data = hjson.loads(path.read_text())
        for imp in data.get("import_cfgs", []):
            visit(Path(imp.replace("{proj_root}", str(src))))
        for item in data.get("run_modes", []):
            modes[item["name"]] = item
        for item in data.get("tests", []):
            name = item["name"].replace("{name}", "aon_timer")
            assert name not in definitions, name
            definitions[name] = item

    visit(cfg)
    catalog = matrix.read(matrix.paths(root)["catalog"])
    assert len(definitions) == 17
    assert {e["official_test"] for e in catalog["tests"]} == set(definitions)
    records = []
    for entry in catalog["tests"]:
        official = definitions[entry["official_test"]]
        inherited = [modes[n] for n in official.get("en_run_modes", [])]
        seq = official.get("uvm_test_seq")
        options = []
        for mode in inherited:
            seq = seq or mode.get("uvm_test_seq")
            options.extend(mode.get("run_opts", []))
        options.extend(official.get("run_opts", []))
        seq = seq.replace("{name}", "aon_timer")
        options = [o.replace("{name}", "aon_timer") for o in options]
        assert entry["sequence"] == seq, entry
        assert entry["run_options"] == options, (entry, options)
        if "run_timeout_mins" in official:
            assert entry["timeout_seconds"] == official["run_timeout_mins"] * 60
        records.append({"test_id": entry["id"], "official_test": entry["official_test"],
                        "sequence": seq, "run_options": options,
                        "official_build_mode": official.get("build_mode", "default"),
                        "executed_build": "shared frozen V30 simv; same coverage denominator across all methods"})
    matrix.write(output, {"status": "pass", "official_count": 17,
                          "source_revision": catalog["source_revision"],
                          "source_files_sha256": files, "tests": records})


def command(root, work, method, run, budget):
    cmd = [str(root / ".venv/bin/python"), "-u", str(work / "tools/run_stage09_v30.py"),
           "--method", method, "--result-dir", str(run), "--submissions", str(budget),
           "--workers", "10", "--batch-size", "10", "--seed", "42"]
    for key, value in matrix.paths(root).items():
        cmd += ["--" + key, str(value)]
    return cmd


def probe_catalog(root, work, status):
    """Execute every official test once, outside the initial and formal corpus."""
    from run_stage09_v30 import load_module
    from stage08_stable_coverage_v20 import StableCoverageSchema
    from verify_stage08_uvm_replay import inspect_log
    inputs = matrix.paths(root)
    corpus = load_module(inputs["corpus-source"], "catalog_probe_corpus")
    converter = load_module(inputs["conversion-source"], "catalog_probe_converter")
    with inputs["mapping"].open(newline="") as handle:
        names = sorted(r["feature_name"] for r in csv.DictReader(handle))
    rng = random.Random(42)
    jobs = []
    probe = root / "runs" / f"stage09_17test_catalog_probe17_{DATE}"
    probe.mkdir(exist_ok=False)
    entries = matrix.read(inputs["catalog"])["tests"]
    for i, e in enumerate(entries):
        jobs.append((e, {"result_root": str(probe / "raw"), "test_name": e["official_test"],
            "index": 0, "global_run_id": i, "seed": rng.randint(1, 2**31-1),
            "sequence": e["sequence"], "simv": str(inputs["simv"]),
            "dv_root": str(inputs["dv-root"]), "timeout_seconds": e["timeout_seconds"],
            "test_run_options": e["run_options"], "extra_plusargs": []}))
    matrix.write(probe / "protocol.json", {"scope": "Independent catalog gate only; never used for policy feedback or initial/formal coverage",
        "tests": entries, "jobs": [j for e, j in jobs], "seed": 42, "workers": 10,
        "catalog_sha256": matrix.sha(inputs["catalog"]), "simv_sha256": matrix.sha(inputs["simv"])})

    def execute(entry, job):
        result = corpus.run_one(job)
        raw = probe / "raw" / job["test_name"] / "0"
        log = raw / "run.log"
        checked = inspect_log(log.read_text(errors="replace"), result["vcs_return_code"])
        record = {"test_id": entry["id"], "official_test": entry["official_test"],
                  "execution": result, "strict_uvm_check": checked,
                  "log_sha256": matrix.sha(log), "command_sha256": matrix.sha(raw / "command.txt")}
        try:
            assert checked["status"] == "pass", checked
            assert result["uvm_pass"] and result["uvm_error"] == result["uvm_fatal"] == 0
            assert result["vcs_return_code"] == result["urg_return_code"] == 0
            report, _, _ = converter.run_urg({"source_root": str(probe / "raw"),
                "relative_run_dir": str(raw.relative_to(probe / "raw")),
                "source": "catalog_probe", "global_run_id": job["global_run_id"]},
                probe / "reports" / entry["id"], "urg", 300)
            schema = StableCoverageSchema(converter, inputs["canonical-report"], names)
            counts = schema.parse(report, raw / "coverage/default.vdb")
            assert len(counts) == 4507
            record.update(status="pass", parsed_bin_count=len(counts),
                          covered_bins=sum(v > 0 for v in counts.values()))
        except Exception as exc:
            record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        matrix.write(raw / "probe_audit.json", record)
        return record

    started = time.monotonic()
    records = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(execute, *job) for job in jobs]
        for future in as_completed(futures):
            records.append(future.result())
            matrix.write(probe / "progress.json", {"completed": len(records), "total": 17,
                "failed": sum(r["status"] != "pass" for r in records), "records": records})
            status(phase="catalog_probe17", probe_completed=len(records),
                   probe_failed=sum(r["status"] != "pass" for r in records))
    audit = {"status": "pass" if all(r["status"] == "pass" for r in records) else "failed",
             "completed": len(records), "failed": sum(r["status"] != "pass" for r in records),
             "wall_seconds": time.monotonic() - started,
             "cpu_seconds": sum(r["execution"].get("simulator_cpu_seconds") or 0 for r in records),
             "records": records}
    matrix.write(probe / "audit.json", audit)
    exported = root / "evidence" / probe.name
    exported.mkdir(exist_ok=False)
    # Only protocol, hashes and result metadata leave the raw simulation tree.
    for name in ("protocol.json", "audit.json"):
        value = matrix.read(probe / name)
        serialized = json.dumps(value).replace(str(root), "<ROOT>")
        matrix.write(exported / name, json.loads(serialized))
    manifest(exported)
    assert audit["status"] == "pass", "At least one official catalog test failed; inspect raw logs before any formal run"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    configure()
    work = root / "scratch" / WORK_NAME
    if args.prepare:
        matrix.prepare(root, work)
        verify_official_catalog(root, work / "official_catalog_audit.json")
        audit = matrix.read(work / "official_catalog_audit.json")
        src = matrix.paths(root)["dv-root"].parents[1]
        provenance = [src / rel for rel in audit["source_files_sha256"]]
        provenance += list((root / "runtime17_deps").rglob("*.py"))
        with (work / "frozen_sha256.txt").open("a") as handle:
            for path in sorted(provenance):
                handle.write(f"{matrix.sha(path)}  {path}\n")
        prereg = matrix.read(work / "preregistration.json")
        prereg.update(catalog_probe_attempts=17, catalog_probe_excluded_from_formal_budget=True,
                      official_catalog_audit_sha256=matrix.sha(work / "official_catalog_audit.json"),
                      frozen_dependency_manifest_sha256=matrix.sha(work / "frozen_sha256.txt"))
        matrix.write(work / "preregistration.json", prereg)
        return
    import fcntl
    lock = (work / "workflow.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state = {"status": "running", "phase": "preflight", "completed": []}
    def status(**fields):
        state.update(fields)
        state["observed_at_server"] = datetime.now().astimezone().isoformat()
        matrix.write(work / "workflow_status.json", state)
        print(json.dumps(state), flush=True)
    env = os.environ.copy()
    env.update(PYTHONHASHSEED="0", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
               STAGE09_REPO_ROOT=str(root), STAGE09_AUTHOR_SOURCE=str(matrix.paths(root)["author-source"]))
    try:
        status()
        matrix.verify_manifest(work / "frozen_sha256.txt")
        verify_official_catalog(root, work / "official_catalog_audit.json")
        for name in ("test_stage09_policy.py", "test_stage09_arm_identity.py", "test_17test_catalog.py"):
            subprocess.run([str(root / ".venv/bin/python"), str(work / "tests" / name), "-v"], env=env, check=True)
        for method in METHODS:
            output = work / ("preflight_" + method)
            if output.exists():
                assert args.resume and matrix.read(output / "preflight.json")["status"] == "pass"
                continue
            subprocess.run(command(root, work, method, output, 30) + ["--preflight-only"],
                           env=env, cwd=root, check=True)
        probe = root / "runs" / f"stage09_17test_catalog_probe17_{DATE}"
        if probe.exists():
            assert args.resume and matrix.read(probe / "audit.json")["status"] == "pass"
        else:
            status(phase="catalog_probe17")
            probe_catalog(root, work, status)
        for method in METHODS:
            for phase, budget in (("smoke30", 30), ("full1000", 1000)):
                name = f"stage09_17test_{method}_{phase}_{DATE}"
                run, exported = root / "runs" / name, root / "evidence" / name
                status(method=method, phase=phase, run_name=name)
                matrix.verify_manifest(work / "frozen_sha256.txt")
                if exported.exists():
                    assert args.resume
                    matrix.verify_run(root, work, run)
                    assert matrix.read(run / "arm_identity_audit.json")["status"] == "pass"
                    state["completed"].append(name)
                    continue
                if run.exists():
                    assert args.resume and (run / "summary.json").exists(), "Incomplete run requires investigation; never restart silently"
                else:
                    with (work / (name + ".log")).open("w") as log:
                        subprocess.run(command(root, work, method, run, budget), env=env, cwd=root,
                                       stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, check=True)
                status(phase=phase + "_audit")
                matrix.verify_manifest(work / "frozen_sha256.txt")
                matrix.verify_run(root, work, run)
                assert matrix.read(run / "arm_identity_audit.json")["status"] == "pass"
                export_run(run, exported)
                state["completed"].append(name)
                status()
        matrix.compare(root, work)
        status(status="pass", phase="complete")
    except Exception as exc:
        status(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    main()
