"""Keep the authorized eight-test repair queued without restarting six-test jobs."""
from datetime import datetime
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repair-root", type=Path, required=True)
    parser.add_argument("--priority-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.repair_root.resolve()
    priority = args.priority_root / "scratch/stage09_17test_all_20261124/workflow_status.json"
    control = root / "scratch/stage09_8test_only_continuation_20261124"
    control.mkdir(exist_ok=False)
    def status(**fields):
        fields["observed_at_server"] = datetime.now().astimezone().isoformat()
        temporary = control / "workflow_status.tmp"
        temporary.write_text(json.dumps(fields, indent=2) + "\n")
        temporary.replace(control / "workflow_status.json")
        print(json.dumps(fields), flush=True)
    status(status="queued", method="NoRuntimePenalty", pool=8,
           waiting_for="17-test workflow to finish or stop at a failed gate", six_test_jobs_cancelled=True)
    while True:
        if priority.exists():
            state = json.loads(priority.read_text())
            if state["status"] in ("pass", "failed"):
                break
        time.sleep(30)
    work = root / "scratch/stage09_8test_idfix_20261123"
    sys.path.insert(0, str(work / "tools"))
    import run_stage09_identity_repair_v30 as repair
    from export_stage09_v30 import export_run
    repair.configure(8)
    import fcntl
    lock = (root / "scratch/stage09_identity_repair_20261123/workflow.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    env = os.environ.copy()
    env.update(PYTHONHASHSEED="0", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
               STAGE09_REPO_ROOT=str(root), STAGE09_AUTHOR_SOURCE=str(repair.matrix.paths(root)["author-source"]))
    try:
        for phase, budget in (("smoke30", 30), ("full1000", 1000)):
            name = f"stage09_8test_idfix_NoRuntimePenalty_{phase}_20261123"
            run, exported = root / "runs" / name, root / "evidence" / name
            assert not run.exists() and not exported.exists(), "Inspect existing outputs; never overwrite"
            repair.matrix.verify_manifest(work / "frozen_sha256.txt")
            status(status="running", pool=8, method="NoRuntimePenalty", phase=phase, run_name=name)
            with (control / (name + ".log")).open("w") as log:
                subprocess.run(repair.command(root, work, 8, "NoRuntimePenalty", run, budget),
                               cwd=root, env=env, stdin=subprocess.DEVNULL,
                               stdout=log, stderr=subprocess.STDOUT, check=True)
            status(status="running", pool=8, method="NoRuntimePenalty", phase=phase + "_audit", run_name=name)
            repair.matrix.verify_manifest(work / "frozen_sha256.txt")
            repair.matrix.verify_run(root, work, run)
            assert repair.matrix.read(run / "arm_identity_audit.json")["status"] == "pass"
            export_run(run, exported)
        repair.comparison(root, 8)
        status(status="pass", phase="complete", pool=8, six_test_jobs_cancelled=True)
    except Exception as exc:
        status(status="failed", error=f"{type(exc).__name__}: {exc}", pool=8)
        raise


if __name__ == "__main__":
    main()
