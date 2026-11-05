#!/usr/bin/env python3
"""Independently verify the pre-generated RandomSelection sequence schedule."""
import argparse
import hashlib
import json
import random
from collections import Counter
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads((args.run_dir / "protocol.json").read_text(encoding="utf-8"))
    summary = json.loads((args.run_dir / "summary.json").read_text(encoding="utf-8"))
    results = json.loads((args.run_dir / "run_results.json").read_text(encoding="utf-8"))
    budget = protocol["budget"]
    pool = protocol["sequence_pool"]
    assert protocol["method"] == summary["method"] == "RandomSelection"
    assert protocol["sampling_rule"].startswith("uniform sequence choice with replacement")
    assert protocol["steering"]["enabled"] is False and summary["steering_enabled"] is False
    assert protocol["workers"] == summary["max_active_workers"] == 10
    assert len(results) == summary["submitted"] == summary["completed"] == budget == 1000
    expected_rng = random.Random(protocol["selection_seed"])
    expected = [expected_rng.choice(pool) for _ in range(budget)]
    by_id = {row["run_id"]: row for row in results}
    assert set(by_id) == set(range(budget))
    for run_id, sequence in enumerate(expected):
        row = by_id[run_id]
        assert row["sequence"] == sequence, (run_id, row["sequence"], sequence)
        assert row["test_description"] == sequence
        assert row["seed"] == protocol["seeds"][run_id]
        assert row["status"] == "success"
    observed = Counter(row["sequence"] for row in results)
    assert set(observed) == set(pool)
    audit = {
        "status": "pass",
        "method": "RandomSelection",
        "budget": budget,
        "selection_seed": protocol["selection_seed"],
        "sequence_pool": pool,
        "uniform_with_replacement_schedule_matches_seed": True,
        "all_run_seeds_match_protocol": True,
        "observed_sequence_usage": dict(observed),
        "steering_disabled": True,
        "results_sha256": sha(args.run_dir / "run_results.json"),
        "protocol_sha256": sha(args.run_dir / "protocol.json"),
    }
    (args.run_dir / "sequence_selection_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False))


if __name__ == "__main__":
    main()
