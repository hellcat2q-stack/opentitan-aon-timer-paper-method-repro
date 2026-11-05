#!/usr/bin/env python3
"""Export compact RandomSelection evidence; leave raw VCS data on the server."""
import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path

SAFE_FIELDS = frozenset({
    "run_id", "status", "test_description", "global_run_id", "test_name", "sequence",
    "test_run_options", "sequence_run_index", "seed", "vcs_return_code", "urg_return_code",
    "wall_seconds", "simulator_cpu_seconds", "uvm_pass", "uvm_error", "uvm_fatal",
    "covered_groups", "expected_groups", "group_score_percent", "parsed_bin_count",
    "run_covered_bins", "coverage_parse_seconds", "worker_start_time", "worker_end_time",
    "worker_wall_seconds", "feedback_order", "target", "new_bins", "target_category_gain",
    "weighted_info_gain", "accumulated_covered", "coverage_percent", "scheduler_runtime",
    "steering",
})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    for name in ("protocol.json", "summary.json", "audit.json", "sequence_selection_audit.json", "events.jsonl", "vectors.csv", "coverage_curve.csv"):
        shutil.copyfile(args.run_dir / name, args.output_dir / name)
    rows = json.loads((args.run_dir / "run_results.json").read_text(encoding="utf-8"))
    (args.output_dir / "run_results.json").write_text(
        json.dumps([{key: value for key, value in row.items() if key in SAFE_FIELDS} for row in rows], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    with (args.run_dir / "coverage_curve.csv").open(newline="", encoding="utf-8") as handle:
        curve = list(csv.DictReader(handle))
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, field, label in zip(axes, ["accumulated_simulator_cpu_seconds", "wall_seconds"], ["Accumulated simulator CPU time (s)", "Wall time (s)"]):
        ax.step([float(row[field]) for row in curve], [float(row["coverage_percent"]) for row in curve], where="post")
        ax.set(xlabel=label, ylabel="Coverage (%)", title="AON Timer RandomSelection (local VCS)")
        ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(args.output_dir / "coverage_curve.png", dpi=160)
    plt.close(fig)
    with (args.output_dir / "sha256.txt").open("w", encoding="utf-8") as handle:
        for path in sorted(args.output_dir.iterdir()):
            if path.name != "sha256.txt":
                handle.write(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n")


if __name__ == "__main__":
    main()
