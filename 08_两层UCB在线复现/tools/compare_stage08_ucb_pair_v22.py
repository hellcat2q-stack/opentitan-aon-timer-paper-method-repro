#!/usr/bin/env python3
"""Audit shared inputs before comparing the old and expanded-domain UCB runs."""
import argparse
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--treatment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--validate-inputs-only", action="store_true")
    args = parser.parse_args()
    control, treatment = (read(root / "protocol.json") for root in (args.control, args.treatment))
    required_equal = (
        "budget", "logical_batch_size", "workers", "seed", "seeds", "initial_csv_sha256",
        "mapping_sha256", "author_source_sha256", "baseline_source_sha256",
        "conversion_source_sha256", "corpus_source_sha256", "canonical_report_sha256",
        "bin_identity", "initial_union", "bin_count", "cluster_count", "reward", "failure_rule",
    )
    for field in required_equal:
        if control[field] != treatment[field]:
            raise ValueError(f"unmatched control/treatment protocol: {field}")
    if args.validate_inputs_only:
        report = {"status": "matched_inputs_preflight", "matched_fields": list(required_equal),
                  "seed": control["seed"], "initial_union": control["initial_union"],
                  "denominator": control["bin_count"], "full_result_available": False}
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report))
        return
    rows = {}
    for label, root in (("v20_control", args.control), ("v22_treatment", args.treatment)):
        summary, audit = read(root / "summary.json"), read(root / "audit.json")
        assert audit["status"] == "pass", audit
        assert summary["completed"] == summary["submitted"] == 1000, summary
        rows[label] = {key: summary[key] for key in (
            "completed", "accepted", "failed", "final_covered_bins", "final_coverage_percent",
            "initial_union_bins", "new_bins_beyond_initial", "sequence_usage", "steering_counts",
            "wall_seconds", "accumulated_simulator_cpu_seconds_all_attempts",
        )}
    delta = rows["v22_treatment"]["final_covered_bins"] - rows["v20_control"]["final_covered_bins"]
    report = {
        "status": "completed", "comparison": "v20 vs v22, both use the same two-layer UCB policy",
        "matched_fields": list(required_equal), "seed": control["seed"], "budget_per_arm": 1000,
        "rows": rows, "treatment_minus_control_bins": delta,
        "treatment_minus_control_percentage_points": 100 * delta / control["bin_count"],
        "limits": ["One preregistered seed; this does not establish statistical significance.",
                   "Both arms use UCB: this tests parameter and target-mapping changes, not UCB versus random selection.",
                   "Continuous refill uses completion order; shared-server wall time and sequence order can vary."],
        "protocol_sha256": {label: hashlib.sha256((root / "protocol.json").read_bytes()).hexdigest()
                            for label, root in (("v20", args.control), ("v22", args.treatment))},
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "pass", "delta_bins": delta, "comparison": str(args.output)}))


if __name__ == "__main__":
    main()
