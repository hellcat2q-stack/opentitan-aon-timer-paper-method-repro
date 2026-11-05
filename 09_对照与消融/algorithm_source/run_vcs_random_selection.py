#!/usr/bin/env python3
"""Run the paper's RandomSelection baseline against the verified VCS simv.

The paper defines this baseline as random selection from the available test
sequence pool.  The paper does not publish that pool for AON Timer, so this
runner uses the four sequences frozen by Stage 04/06, uniformly with
replacement.  It deliberately does not import or invoke the UCB scheduler,
target steering, Bayesian training, or a replay backend.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import random
import time
import re
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

import numpy as np
import pandas as pd


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, value) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def canonicalize_urg_bins(converter, bins, canonical_keys):
    """Map URG compressed automatic-bin rows to Stage 06 stable ordinals."""
    value_range = re.compile(r"^values:\s*\{\s*\[\s*(\d+)\s*:\s*(\d+)\s*\]\s*}$", re.I)
    grouped = {}
    for key, count in bins.items():
        grouped.setdefault(converter.report_prefix(key), []).append((key, count))
    if set(grouped) != set(canonical_keys):
        raise ValueError("report prefix set differs from canonical report")
    result = {}
    for prefix, canonical in canonical_keys.items():
        canonical_parts = [key.split("||") for key in canonical]
        canonical_ranges = [value_range.fullmatch(parts[3]) for parts in canonical_parts]
        ordinals = [int(parts[4]) for parts in canonical_parts]
        entry_parts = [key.split("||") for key, _ in grouped[prefix]]
        entry_ranges = [value_range.fullmatch(parts[3]) for parts in entry_parts]
        uniform = (len(canonical) > 1 and all(canonical_ranges)
                   and len({match.groups() for match in canonical_ranges}) == 1
                   and set(ordinals) == set(range(len(canonical))) and all(entry_ranges))
        if uniform:
            low, high = map(int, canonical_ranges[0].groups())
            span = high - low + 1
            if span <= 0 or span % len(canonical):
                raise ValueError(f"non-uniform frozen auto-bin range for {prefix}")
            width = span // len(canonical)
            by_ordinal = {ordinal: key for ordinal, key in zip(ordinals, canonical)}
            mapped, row_groups = {}, {}
            for key, count in grouped[prefix]:
                parts = key.split("||")
                match = value_range.fullmatch(parts[3])
                if not match:
                    raise ValueError(f"URG auto-bin row lacks a numeric range for {prefix}: {key}")
                row_low, row_high = map(int, match.groups())
                offset = int(parts[4])
                if row_low < low or row_high > high or (row_low - low) % width:
                    raise ValueError(f"URG auto-bin range is misaligned for {prefix}: {key}")
                ordinal = (row_low - low) // width + offset
                if not 0 <= ordinal < len(canonical) or ordinal in mapped:
                    raise ValueError(f"duplicate or out-of-range URG auto-bin ordinal for {prefix}: {key}")
                mapped[ordinal] = count
                row_groups.setdefault((row_low, row_high), []).append(offset)
            for (row_low, row_high), offsets in row_groups.items():
                offsets.sort()
                if offsets != list(range(len(offsets))) or row_high - row_low + 1 != len(offsets) * width:
                    raise ValueError(f"URG compressed auto-bin cardinality mismatch for {prefix}")
            if len(mapped) != len(canonical):
                raise ValueError(f"URG auto-bin count mismatch for {prefix}")
            for ordinal, count in mapped.items():
                result[by_ordinal[ordinal]] = count
        else:
            for canonical_key, (_, count) in zip(canonical, grouped[prefix]):
                result[canonical_key] = count
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("conversion-source", "corpus-source", "initial-csv", "mapping", "simv", "dv-root", "result-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--submissions", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--urg", default="urg")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    if args.submissions <= 0 or args.submissions % args.batch_size or args.workers <= 0:
        parser.error("submissions must be positive and divisible by batch-size; workers must be positive")
    args.result_dir = args.result_dir.resolve()
    if args.result_dir.exists():
        parser.error("result-dir must not exist; existing runs are never overwritten")
    if not args.simv.is_file() or not (args.dv_root / "tools" / "sim.tcl").is_file():
        parser.error("verified simv or DV Tcl missing")

    converter = load_module(args.conversion_source, "random_conversion")
    corpus = load_module(args.corpus_source, "random_corpus")
    initial = pd.read_csv(args.initial_csv)
    with args.mapping.open(encoding="utf-8", newline="") as handle:
        pairs = list(csv.DictReader(handle))
    bin_names = sorted(row["feature_name"] for row in pairs)
    mapping = {row["feature_name"]: int(row["cluster_id"]) for row in pairs}
    if len(pairs) != 4507 or len(mapping) != 4507 or len(initial) != 39:
        raise ValueError("frozen 39-run / 4507-bin inputs required")
    if set(initial.columns[initial.columns.get_loc("report_id") + 1:]) != set(mapping):
        raise ValueError("CSV/mapping bin universe differs")
    first_report = args.initial_csv.parent / "reports" / "original_g0"
    if not first_report.exists():
        raise ValueError("initial-csv must be the Stage 06 file with reports/original_g0")
    canonical = {}
    for key in converter.parse_report(first_report):
        canonical.setdefault(converter.report_prefix(key), []).append(key)
    if {key for values in canonical.values() for key in values} != set(mapping):
        raise ValueError("Stage 06 original report keys differ from mapping")
    sequences = list(dict.fromkeys(initial.sequence.tolist()))
    if len(sequences) != 4:
        raise ValueError(f"expected four frozen sequences, got {sequences!r}")
    source_matrix = initial[bin_names].to_numpy(dtype=np.int64)
    initial_union = int(np.count_nonzero(source_matrix.sum(axis=0)))

    seed_rng = random.Random(args.seed)
    seed_list = [seed_rng.randint(1, 2**31 - 1) for _ in range(args.submissions)]
    select_rng = random.Random(args.seed)
    selected_sequences = [select_rng.choice(sequences) for _ in range(args.submissions)]
    args.result_dir.mkdir(parents=True)
    config = {
        "method": "RandomSelection",
        "sequence_pool": sequences,
        "sampling": "uniform with replacement",
        "selection_seed": args.seed,
        "seed_list": seed_list,
        "selected_sequences": selected_sequences,
    }
    dump(args.result_dir / "policy_config.json", config)
    adapted = initial[["sequence", "runtime_cpu_seconds", *bin_names]].rename(
        columns={"sequence": "run", "runtime_cpu_seconds": "runtime"})
    adapted.to_csv(args.result_dir / "author_initial.csv", index=False)
    protocol = {
        "schema": "aon-timer-random-selection-v1",
        "method": "RandomSelection",
        "budget": args.submissions,
        "logical_batch_size": args.batch_size,
        "logical_batches": args.submissions // args.batch_size,
        "workers": args.workers,
        "seed": args.seed,
        "seed_origin": "local preregistration; author seed not disclosed",
        "seeds": seed_list,
        "selection_seed": args.seed,
        "sequence_pool": sequences,
        "sampling_rule": "uniform sequence choice with replacement; independent selection RNG reset from seed",
        "paper_parameter_gap": "The paper does not publish the complete AON Timer sequence pool; this is the frozen local four-sequence pool.",
        "initial_csv_sha256": sha(args.initial_csv),
        "mapping_sha256": sha(args.mapping),
        "adapter_sha256": sha(Path(__file__)),
        "conversion_source_sha256": sha(args.conversion_source),
        "corpus_source_sha256": sha(args.corpus_source),
        "simv_sha256": sha(args.simv),
        "initial_runs": 39,
        "bin_count": 4507,
        "initial_union": initial_union,
        "initial_coverage_included": True,
        "reward": "new bins beyond accumulated initial union",
        "runtime": "simulator CPU seconds; failed attempts included",
        "walltime": "from first submission through last coverage feedback",
        "failure_rule": "count every attempt; failures produce no coverage reward; no retry",
        "host_timeout_seconds": {"normal": 1200, "stress_all": 10800, "urg": 300},
        "steering": {"enabled": False},
        "compatibility_changes": ["VCS/URG worker adapter", "Stage06 canonical parser", "strict UVM checks", "raw logs retained on server", "never overwrite result directory"],
    }
    dump(args.result_dir / "protocol.json", protocol)
    policy_hash = sha(args.result_dir / "protocol.json")
    state = np.asarray(source_matrix.sum(axis=0) > 0, dtype=bool)
    events_hash = "0" * 64
    event_index = 0
    submitted = completed = failed = max_active = 0
    results = []
    first_submit = None

    def emit(event: str, **fields) -> None:
        nonlocal events_hash, event_index
        record = {"event_index": event_index, "event": event, "timestamp": time.time(),
                  "previous_hash": events_hash, "policy_hash": policy_hash, **fields}
        digest = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        record["event_hash"] = digest
        with (args.result_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
        events_hash, event_index = digest, event_index + 1

    def run_one(run_id: int):
        sequence = selected_sequences[run_id]
        test_name = sequence.removesuffix("_vseq")
        batch_dir = args.result_dir / "batches" / f"batch_{run_id // args.batch_size}"
        run_dir = batch_dir / str(run_id)
        run_dir.mkdir(parents=True)
        job = {"result_root": str(run_dir / "raw"), "test_name": test_name, "index": 0,
               "global_run_id": run_id, "seed": seed_list[run_id], "sequence": sequence,
               "simv": str(args.simv), "dv_root": str(args.dv_root),
               "timeout_seconds": 10800 if "stress_all" in sequence else 1200}
        started = time.time()
        result = {"run_id": run_id, "status": "error", "test_description": sequence,
                  "sequence": sequence, "seed": seed_list[run_id], "steering": {"status": "disabled"}}
        try:
            execution = corpus.run_one(job)
            raw_dir = run_dir / "raw" / test_name / "0"
            result.update(execution)
            ok = execution["vcs_return_code"] == 0 and execution["uvm_pass"] and execution["uvm_error"] == 0 and execution["uvm_fatal"] == 0
            if ok:
                report_dir, _, elapsed = converter.run_urg(
                    {"source_root": str(run_dir / "raw"), "relative_run_dir": f"{test_name}/0", "source": "random", "global_run_id": run_id},
                    run_dir / "reports", args.urg, 300)
                covered, expected = converter.parse_group_list_counts(report_dir)
                counts = canonicalize_urg_bins(converter, converter.parse_report(report_dir), canonical)
                if len(counts) != 4507 or expected != 4507 or sum(value > 0 for value in counts.values()) != covered:
                    raise ValueError("URG counts differ from frozen 4507-bin universe")
                if not list((raw_dir / "coverage" / "default.vdb").glob("snps/coverage/db/testdata/*/testbench.cumulative.xml")):
                    raise ValueError("cumulative XML absent")
                dump(run_dir / "coverage_counts.json", counts)
                result.update(status="success", parsed_bin_count=4507, run_covered_bins=covered, report_dir=str(report_dir), coverage_parse_seconds=elapsed)
            else:
                result["status"] = "failed"
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
        result.update(worker_start_time=started, worker_end_time=time.time(), worker_wall_seconds=time.time() - started)
        dump(run_dir / "execution.json", result)
        return run_id, result

    if args.preflight_only:
        dump(args.result_dir / "preflight.json", {"status": "pass", "initial_runs": 39, "bin_count": 4507, "initial_union": initial_union, "sequence_pool": sequences})
        print("RANDOM_SELECTION_PREFLIGHT_OK", flush=True)
        return 0

    pending = {}
    start = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        def submit(run_id: int) -> None:
            nonlocal submitted, max_active, first_submit
            if first_submit is None:
                first_submit = time.time()
            before = int(state.sum())
            emit("submit", run_id=run_id, seed=seed_list[run_id], sequence=selected_sequences[run_id], target=None,
                 steering={"status": "disabled"}, feedback_count=completed, active=len(pending) + 1,
                 accumulated_covered=before)
            future = pool.submit(run_one, run_id)
            pending[future] = (run_id, before)
            submitted += 1
            max_active = max(max_active, len(pending))

        for run_id in range(min(args.workers, args.submissions)):
            submit(run_id)
        next_id = min(args.workers, args.submissions)
        while pending:
            done, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
            for future in done:
                run_id, before = pending.pop(future)
                _, result = future.result()
                accepted = result.get("status") == "success"
                counts = json.loads((args.result_dir / "batches" / f"batch_{run_id // args.batch_size}" / str(run_id) / "coverage_counts.json").read_text()) if accepted else {}
                vector = [int(counts.get(name, 0) > 0) for name in bin_names]
                old = state.copy()
                if accepted:
                    state |= np.asarray(vector, dtype=bool)
                new_bins = int(state.sum() - old.sum())
                result.update(feedback_order=completed + 1, new_bins=new_bins, target_category_gain=0,
                              weighted_info_gain=float(new_bins), accumulated_covered=int(state.sum()),
                              coverage_percent=float(state.sum() / 4507 * 100), scheduler_runtime=time.time() - start)
                results.append(result)
                completed += 1
                failed += int(not accepted)
                run_root = args.result_dir / "batches" / f"batch_{run_id // args.batch_size}" / str(run_id)
                with (args.result_dir / "vectors.csv").open("a", newline="", encoding="utf-8") as handle:
                    writer = csv.writer(handle)
                    if completed == 1:
                        writer.writerow(["run_id", "accepted", *bin_names])
                    writer.writerow([run_id, accepted, *vector])
                emit("feedback", run_id=run_id, accepted=accepted, active=len(pending), feedback_count=completed,
                     new_bins=new_bins, target_gain=0, steering_status="disabled", steering_bin=None,
                     steering_bin_hit=None, opportunity_gain=float(new_bins), accumulated_covered=int(state.sum()),
                     simulator_cpu_seconds=result.get("simulator_cpu_seconds"), vector_sha256=hashlib.sha256(bytes(vector)).hexdigest())
                dump(args.result_dir / "progress.json", {"submitted": submitted, "completed": completed, "failed": failed,
                     "coverage_bins": int(state.sum()), "denominator": 4507, "event_head": events_hash})
                print(f"RANDOM_PROGRESS {completed}/{args.submissions} failed={failed} covered={int(state.sum())}/4507", flush=True)
                if next_id < args.submissions:
                    submit(next_id)
                    next_id += 1

    # Keep completion/feedback order.  The independent audit checks that the
    # vectors and result rows share this order; run_id remains the stable key.
    emit("finished", submitted=submitted, completed=completed, failed=failed)
    cpu = sum(float(row.get("simulator_cpu_seconds") or 0) for row in results)
    summary = {"schema": "aon-timer-random-selection-summary-v1", "method": "RandomSelection", "status": "completed",
               "submitted": submitted, "completed": completed, "failed": failed, "retried": 0, "accepted": completed - failed,
               "max_active_workers": max_active, "bin_count": 4507, "initial_union_bins": initial_union,
               "final_covered_bins": int(state.sum()), "final_coverage_percent": float(state.sum() / 4507 * 100),
               "new_bins_beyond_initial": int(state.sum()) - initial_union, "accumulated_simulator_cpu_seconds_all_attempts": cpu,
               "accepted_simulator_cpu_seconds": sum(float(row.get("simulator_cpu_seconds") or 0) for row in results if row.get("status") == "success"),
               "wall_seconds": time.time() - (first_submit or start), "sequence_usage": {sequence: selected_sequences.count(sequence) for sequence in sequences},
               "steering_enabled": False, "policy_sha256": policy_hash, "event_chain_head": events_hash}
    dump(args.result_dir / "run_results.json", results)
    dump(args.result_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if completed == args.submissions else 1


if __name__ == "__main__":
    raise SystemExit(main())
