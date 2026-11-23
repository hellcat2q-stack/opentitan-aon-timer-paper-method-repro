"""Verify catalog, executed test, feedback and final policy state by test ID."""
from collections import Counter, defaultdict
import csv
import json
import math
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify_identity(root, initial_csv):
    protocol = read(root / "protocol.json")
    ids = protocol["sequence_pool"]
    catalog = {entry["id"]: entry for entry in protocol["test_catalog_entries"]}
    assert not catalog or set(catalog) == set(ids)
    submits = {event["run_id"]: event for event in (
        json.loads(line) for line in (root / "events.jsonl").read_text().splitlines()
    ) if event["event"] == "submit"}
    counts, gains, runtimes, vectors = Counter(), defaultdict(list), defaultdict(list), Counter()
    with Path(initial_csv).open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            vectors[row["sequence"].strip()] += 1
            runtimes[row["sequence"].strip()].append(float(row["runtime_cpu_seconds"]))
    results = read(root / "run_results.json")
    for result in results:
        arm = result["test_id"]
        assert arm in ids and submits[result["run_id"]]["sequence"] == arm
        run = root / "batches" / f"batch_{result['run_id'] // protocol['logical_batch_size']}" / str(result["run_id"])
        execution = read(run / "execution.json")
        assert execution["test_id"] == arm == result["test_description"]
        if catalog:
            entry = catalog[arm]
            assert execution["sequence"] == entry["sequence"] == result["sequence"]
            assert execution["official_test"] == entry["official_test"] == result["official_test"]
            assert execution["test_run_options"] == entry["run_options"] == result["test_run_options"]
            command = (run / "raw" / result["test_name"] / "0/command.txt").read_text()
            assert "+UVM_TEST_SEQ=" + entry["sequence"] in command
            assert all(option in command for option in entry["run_options"])
        if result["status"] == "success":
            counts[arm] += 1
            gains[arm].append(result["new_bins"])
            runtimes[arm].append(result["simulator_cpu_seconds"])
            vectors[arm] += int(result["run_covered_bins"] > 0)
    state = read(root / "policy_arm_state.json")
    for key in ("successful_run_counts", "gain_history", "runtime_history", "historical_vector_counts"):
        assert set(state[key]) == set(ids)
    for arm in ids:
        assert state["successful_run_counts"][arm] == counts[arm]
        assert state["gain_history"][arm] == gains[arm]
        actual = state["runtime_history"][arm]
        assert len(actual) == len(runtimes[arm])
        assert all(math.isclose(a, b, abs_tol=1e-6) for a, b in zip(actual, runtimes[arm]))
        assert state["historical_vector_counts"][arm] == vectors[arm]
    audit = {"status": "pass", "checked_runs": len(results), "test_pool_size": len(ids),
             "all_submissions_match_executed_test_id": True,
             "all_official_sequence_and_options_match_catalog": bool(catalog),
             "all_policy_counts_gains_runtimes_and_history_match_test_id": True,
             "successful_run_counts": {arm: counts[arm] for arm in ids}}
    (root / "arm_identity_audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    return audit
