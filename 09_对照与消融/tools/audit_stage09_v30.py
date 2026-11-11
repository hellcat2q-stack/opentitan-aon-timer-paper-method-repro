#!/usr/bin/env python3
"""Independently verify the budget, hash chain and coverage feedback of a run."""
import argparse
import csv
import hashlib
import json
import math
import random
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--initial-csv", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    args = parser.parse_args()
    root = args.run_dir
    protocol, summary = read(root / "protocol.json"), read(root / "summary.json")
    results = read(root / "run_results.json")
    n = protocol["budget"]
    policy_hash = sha(root / "protocol.json")
    assert protocol["initial_csv_sha256"] == sha(args.initial_csv)
    assert protocol["mapping_sha256"] == sha(args.mapping)
    with args.mapping.open(encoding="utf-8", newline="") as handle:
        category_by_bin = {r["feature_name"]: f"category_{r['cluster_id']}" for r in csv.DictReader(handle)}
    assert protocol["steering"]["enabled"] is False
    barrier = protocol["method"] == "NoIncrementalRefill"
    assert protocol["refill_mode"] == ("batch_barrier" if barrier else "continuous")
    rng = random.Random(protocol["seed"])
    expected_schedule = [rng.choice(protocol["sequence_pool"]) for _ in range(n)]
    assert summary["policy_sha256"] == policy_hash
    previous = "0" * 64
    submits, feedback, active, max_active, refill_count = {}, {}, 0, 0, 0
    for index, line in enumerate((root / "events.jsonl").read_text().splitlines()):
        event = json.loads(line)
        expected_hash = event.pop("event_hash")
        assert event["event_index"] == index and event["previous_hash"] == previous
        assert event["policy_hash"] == policy_hash
        actual_hash = hashlib.sha256(json.dumps(event, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        assert actual_hash == expected_hash
        previous = actual_hash
        if event["event"] == "submit":
            run_id = event["run_id"]
            assert run_id == len(submits)
            assert event["seed"] == protocol["seeds"][run_id]
            assert event["feedback_count"] == len(feedback)
            if run_id >= protocol["workers"]:
                if barrier:
                    assert event["feedback_count"] == (run_id // protocol["logical_batch_size"]) * protocol["logical_batch_size"], "batch started before previous batch drained"
                else:
                    assert last_event == "feedback", "refill must follow feedback"
                    refill_count += 1
            if protocol["method"] == "RandomSelection":
                assert event["sequence"] == expected_schedule[run_id]
                assert protocol["random_sequence_schedule"][run_id] == event["sequence"]
                assert event["target"] is None
            if protocol["method"] == "SequenceUCBOnly":
                assert event["target"] is None
                decision = event["ablation_decision"]
                assert decision["rule"] == "global_sequence_ucb"
                assert event["sequence"] == max(decision["scores"], key=decision["scores"].get)
            if protocol["method"] == "ClusterUCBOnly":
                decision = event["ablation_decision"]
                assert decision["rule"] == "uniform_target_relevant_sequence"
                assert event["sequence"] in decision["candidates"]
            active += 1
            assert active <= protocol["workers"] and event["active"] == active
            max_active = max(max_active, active)
            submits[run_id] = event
        elif event["event"] == "feedback":
            run_id = event["run_id"]
            assert run_id in submits and run_id not in feedback
            active -= 1
            assert active >= 0 and event["active"] == active
            assert event["feedback_count"] == len(feedback) + 1
            feedback[run_id] = event
        last_event = event["event"]
    assert active == 0 and len(submits) == len(feedback) == len(results) == n
    assert previous == summary["event_chain_head"]
    assert summary["submitted"] == summary["completed"] == n and summary["retried"] == 0

    with args.initial_csv.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        names = sorted(reader.fieldnames[reader.fieldnames.index("report_id") + 1:])
        union = [False] * len(names)
        for row in reader:
            union = [old or int(row[name]) > 0 for old, name in zip(union, names)]
    assert len(names) == 4507 and sum(union) == protocol["initial_union"]
    with (root / "vectors.csv").open(encoding="utf-8", newline="") as f:
        rows = csv.reader(f)
        assert next(rows) == ["run_id", "accepted", *names]
        vectors = list(rows)
    assert len(vectors) == n
    cpu, failed, missing_cpu = 0.0, 0, 0
    steering_enabled = protocol.get("steering", {}).get("enabled", False)
    steering_targets = steering_applied = steering_hits = 0
    curve = []
    for position, (row, result) in enumerate(zip(vectors, results), start=1):
        run_id, accepted = int(row[0]), row[1] == "True"
        vector = [int(x) for x in row[2:]]
        event = feedback[run_id]
        assert accepted == event["accepted"] == (result["status"] == "success")
        assert run_id == result["run_id"] and result["feedback_order"] == position
        assert result["seed"] == protocol["seeds"][run_id]
        assert hashlib.sha256(bytes(vector)).hexdigest() == event["vector_sha256"]
        run_dir = root / "batches" / f"batch_{run_id // protocol['logical_batch_size']}" / str(run_id)
        execution = read(run_dir / "execution.json")
        assert execution["worker_start_time"] >= submits[run_id]["timestamp"]
        assert execution["worker_end_time"] <= event["timestamp"]
        if accepted:
            counts = read(run_dir / "coverage_counts.json")
            assert set(counts) == set(names)
            assert vector == [int(counts[name] > 0) for name in names]
            assert result["vcs_return_code"] == result["urg_return_code"] == 0
            assert result["uvm_pass"] and result["uvm_error"] == result["uvm_fatal"] == 0
            assert sum(vector) == result["run_covered_bins"]
        else:
            assert not any(vector)
            failed += 1
        if steering_enabled:
            submitted_target = submits[run_id].get("steering", {})
            reported_target = result.get("steering", {})
            assert submitted_target.get("status") == reported_target.get("status")
            assert feedback[run_id]["steering_status"] == reported_target.get("status")
            if reported_target.get("status") == "targeted":
                steering_targets += 1
                target_bin = reported_target["target_bin"]
                assert target_bin in names
                assert feedback[run_id]["steering_bin"] == target_bin
                plusargs = result.get("steering_plusargs", [])
                command_path = (run_dir / "raw" /
                                result["test_description"].removesuffix("_vseq") /
                                "0" / "command.txt")
                command_text = command_path.read_text(encoding="utf-8")
                assert plusargs and all(arg in command_text for arg in plusargs)
                assert execution.get("steering_plusargs") == plusargs
                applied = bool(result.get("steering_applied"))
                assert execution.get("steering_applied") == applied
                steering_applied += int(applied)
                if accepted:
                    target_hit = bool(vector[names.index(target_bin)])
                    assert reported_target.get("target_bin_hit") == target_hit
                    assert feedback[run_id]["steering_bin_hit"] == target_hit
                    steering_hits += int(target_hit)
                else:
                    assert reported_target.get("target_bin_hit") is None
        else:
            assert result.get("steering", {}).get("status") == "disabled"
        before = sum(union)
        target = submits[run_id]["target"]
        target_gain = sum(not old and hit > 0 and category_by_bin[name] == target
                          for old, hit, name in zip(union, vector, names)) if target else 0
        assert event["target_gain"] == result["target_category_gain"] == target_gain
        union = [old or hit > 0 for old, hit in zip(union, vector)]
        assert event["new_bins"] == result["new_bins"] == sum(union) - before
        assert event["accumulated_covered"] == result["accumulated_covered"] == sum(union)
        runtime = result.get("simulator_cpu_seconds")
        if runtime is None:
            missing_cpu += 1
        else:
            assert math.isfinite(runtime) and runtime >= 0
            cpu += runtime
        curve.append({"feedback_order": position, "run_id": run_id, "accepted": accepted,
            "accumulated_simulator_cpu_seconds": cpu, "wall_seconds": event["timestamp"] - submits[0]["timestamp"],
            "covered_bins": sum(union), "coverage_percent": sum(union) / 4507 * 100,
            "new_bins": sum(union) - before})
    assert sum(union) == summary["final_covered_bins"] and failed == summary["failed"]
    assert math.isclose(cpu, summary["accumulated_simulator_cpu_seconds_all_attempts"], abs_tol=1e-6)
    with (root / "coverage_curve.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(curve[0]))
        writer.writeheader()
        writer.writerows(curve)
    audit = {"status": "pass", "budget": n, "completed": n, "failed": failed, "retried": 0,
        "bin_count": 4507, "initial_covered_bins": protocol["initial_union"], "final_covered_bins": sum(union),
        "hash_chain_verified": True, "all_seeds_match_preregistered_list": True,
        "all_vectors_match_run_counts": True, "all_rewards_match_union_deltas": True,
        "all_accepted_runs_have_uvm_pass": True, "max_active_workers": max_active,
        "refills_after_feedback": refill_count, "missing_cpu_time_count": missing_cpu,
        "method": protocol["method"], "refill_mode": protocol["refill_mode"],
        "batch_barriers_verified": barrier,
        "random_schedule_verified": protocol["method"] == "RandomSelection",
        "all_target_rewards_match_cluster_union_deltas": True,
        "protocol_sha256": policy_hash, "event_chain_head": previous,
        "steering_enabled": steering_enabled, "steering_targets": steering_targets,
        "steering_applied_confirmed": steering_applied, "steering_target_bin_hits": steering_hits,
        "limitation": "Uses the Stage06 frozen URG prefix/row identity convention; does not independently prove physical bin identity."}
    (root / "audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit), flush=True)


if __name__ == "__main__":
    main()
