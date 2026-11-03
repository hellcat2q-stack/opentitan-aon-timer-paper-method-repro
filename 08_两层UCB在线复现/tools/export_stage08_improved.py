#!/usr/bin/env python3
"""Export only protocol, compact results, vectors and hashes; raw logs stay put."""
import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path


SAFE_RUN_RESULT_FIELDS = frozenset({
    "run_id", "status", "test_description", "global_run_id", "test_name", "sequence",
    "test_run_options", "sequence_run_index", "seed", "vcs_return_code", "urg_return_code",
    "wall_seconds", "simulator_cpu_seconds", "uvm_pass", "uvm_error", "uvm_fatal",
    "covered_groups", "expected_groups", "group_score_percent", "parsed_bin_count",
    "run_covered_bins", "coverage_parse_seconds", "worker_start_time", "worker_end_time",
    "worker_wall_seconds", "feedback_order", "target", "new_bins", "target_category_gain",
    "weighted_info_gain", "accumulated_covered", "coverage_percent", "scheduler_runtime",
})


def sanitize_run_results(rows):
    """Keep reproducibility metrics while excluding paths and raw error strings."""
    return [{key: value for key, value in row.items() if key in SAFE_RUN_RESULT_FIELDS} for row in rows]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    names = ["protocol.json", "summary.json", "audit.json", "run_results.json", "events.jsonl", "vectors.csv", "coverage_curve.csv"]
    for name in names:
        source = args.run_dir / name
        if not source.is_file():
            raise FileNotFoundError(name)
        if name == "run_results.json":
            rows = json.loads(source.read_text(encoding="utf-8"))
            (args.output_dir / name).write_text(
                json.dumps(sanitize_run_results(rows), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        else:
            shutil.copyfile(source, args.output_dir / name)
    # This plot displays measured local data; paper values are never injected.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    with (args.run_dir / "coverage_curve.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, field, label in zip(axes, ["accumulated_simulator_cpu_seconds", "wall_seconds"], ["Accumulated simulator CPU time (s)", "Wall time (s)"]):
        ax.step([float(row[field]) for row in rows], [float(row["coverage_percent"]) for row in rows], where="post")
        ax.set(xlabel=label, ylabel="Coverage (%)", title="AON Timer Full (local VCS)")
        ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(args.output_dir / "coverage_curve.png", dpi=160)
    plt.close(fig)
    with (args.output_dir / "sha256.txt").open("w", encoding="utf-8") as f:
        for path in sorted(args.output_dir.iterdir()):
            if path.name != "sha256.txt":
                f.write(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n")
    print(json.dumps({"exported": len(list(args.output_dir.iterdir())), "raw_logs_exported": False}))


if __name__ == "__main__":
    main()
