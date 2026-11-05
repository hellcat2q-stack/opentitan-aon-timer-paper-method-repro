#!/usr/bin/env python3
"""VCS/URG adapter for an isolated global-gain continuous-refill policy.

Policy methods (cluster/sequence UCB, MI, residual prior, repetition handling,
information triggers and refill loop) are inherited from the hashed source.
All raw artifacts stay below a new server result directory. No replay backend.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import random
import signal
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
from aon_timer_coverage_steering import (
    confirmed_in_log,
    plusargs as steering_plusargs,
    select_target,
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("author-source", "conversion-source", "corpus-source", "initial-csv", "mapping", "simv", "dv-root", "result-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--baseline-source", type=Path)
    parser.add_argument("--submissions", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--urg", default="urg")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--steering", action="store_true",
                        help="steer an uncovered, mappable bin in the selected cluster")
    parser.add_argument("--sv-source", type=Path, action="append", default=[])
    parser.add_argument("--sv-patch", type=Path)
    args = parser.parse_args()
    if args.submissions <= 0 or args.submissions % args.batch_size or args.workers <= 0:
        parser.error("positive submissions must be divisible by batch-size; workers must be positive")
    args.result_dir = args.result_dir.resolve()
    if args.result_dir.exists():
        parser.error("result-dir must not exist; never overwrite an earlier run")
    if not args.simv.is_file() or not (args.dv_root / "tools/sim.tcl").is_file():
        parser.error("verified simv or DV Tcl missing")
    if args.steering and (len(args.sv_source) != 3 or args.sv_patch is None):
        parser.error("steering requires base, prescaler and jump SV paths plus --sv-patch")
    author = load_module(args.author_source, "author_ucb")
    converter = load_module(args.conversion_source, "conversion")
    corpus = load_module(args.corpus_source, "corpus")
    initial = pd.read_csv(args.initial_csv)
    with args.mapping.open(encoding="utf-8", newline="") as f:
        pairs = list(csv.DictReader(f))
    bin_names = sorted(row["feature_name"] for row in pairs)
    mapping = {row["feature_name"]: int(row["cluster_id"]) for row in pairs}
    if len(pairs) != 4507 or len(mapping) != 4507 or len(initial) != 39:
        raise ValueError("frozen 39-run / 4507-bin inputs required")
    if set(initial.columns[initial.columns.get_loc("report_id") + 1:]) != set(mapping):
        raise ValueError("CSV/mapping bin universe differs")
    source_matrix = initial[bin_names].to_numpy(dtype=np.int64)
    canonical = {}
    # Stage 06 froze each prefix's *insertion* order; CSV columns are sorted.
    # Restore insertion order using its first source report, never sorted CSV.
    first_report = args.initial_csv.parent / "reports/original_g0"
    if not first_report.exists():
        raise ValueError("initial-csv must be the server Stage 06 file with reports/original_g0")
    for key in converter.parse_report(first_report):
        canonical.setdefault(converter.report_prefix(key), []).append(key)
    if {key for keys in canonical.values() for key in keys} != set(mapping):
        raise ValueError("Stage 06 original report keys differ from mapping")
    sequences = list(dict.fromkeys(initial.sequence.tolist()))
    if len(sequences) != 4:
        raise ValueError("expected four frozen sequences")
    config = {
        "test_name": "aon_timer_vcs_full",
        "test_sequences": [{"name": seq, "seq": seq} for seq in sequences],
        "test_variants": [], "base_run_cmd": [], "verisim_config": {},
    }
    args.result_dir.mkdir(parents=True)
    dump(args.result_dir / "policy_config.json", config)
    adapted = initial[["sequence", "runtime_cpu_seconds", *bin_names]].rename(columns={"sequence": "run", "runtime_cpu_seconds": "runtime"})
    adapted.to_csv(args.result_dir / "author_initial.csv", index=False)
    rng = random.Random(args.seed)
    seed_list = [rng.randint(1, 2**31 - 1) for _ in range(args.submissions)]
    policy_manifest = {
        "schema": "aon-timer-stage08-policy-v1", "method": "Full",
        "budget": args.submissions, "logical_batch_size": args.batch_size,
        "logical_batches": args.submissions // args.batch_size, "workers": args.workers,
        "seed": args.seed, "seed_origin": "local preregistration; author seed not disclosed",
        "seeds": seed_list, "initial_csv_sha256": sha(args.initial_csv),
        "mapping_sha256": sha(args.mapping), "author_source_sha256": sha(args.author_source),
        "baseline_source_sha256": sha(args.baseline_source) if args.baseline_source else None,
        "adapter_sha256": sha(__file__), "conversion_source_sha256": sha(args.conversion_source),
        "corpus_source_sha256": sha(args.corpus_source), "simv_sha256": sha(args.simv),
        "initial_runs": 39, "bin_count": 4507, "cluster_count": len(set(mapping.values())),
        "initial_union": int(np.count_nonzero(source_matrix.sum(axis=0))),
        "initial_coverage_included": True, "reward": "global coverage reports successful-run union deltas; sequence UCB uses 80% mean global newly-covered bins and 20% mean target-cluster newly-covered bins from successful online runs",
        "runtime": "simulator CPU seconds; failed attempts included in audit total",
        "walltime": "from first submission through last coverage feedback",
        "failure_rule": "count every attempt; UVM/VCS/URG/parse failures produce no coverage reward; no retry",
        "stress_timeout_ns": 10000000000, "host_timeout_seconds": {"normal": 1200, "stress_all": 10800, "urg": 300},
        "policy": "author-derived cluster/sequence UCB, MI, dynamic residual, runtime penalty, repeat-eligible ranking and continuous refill loop with global-new-bin sequence reward",
        "steering": {
            "enabled": args.steering,
            "source_sha256": sha(Path(__file__).with_name("aon_timer_coverage_steering.py")) if args.steering else None,
            "sv_source_sha256": [sha(path) for path in args.sv_source] if args.steering else [],
            "sv_patch_sha256": sha(args.sv_patch) if args.sv_patch else None,
            "jump_counter_fix_patch_sha256": sha(Path(__file__).with_name("aon_timer_jump_counter_fix.patch")) if args.steering else None,
            "base_safe_steering_patch_sha256": sha(Path(__file__).with_name("aon_timer_base_safe_steering.patch")) if args.steering else None,
            "mapping": "uncovered AON Timer variable bins to constrained sequence fields; unsupported/cross bins are skipped",
            "target_hit": "per-run URG coverage count for the exact selected feature label",
        },
        "compatibility_changes": ["CSV sequence/runtime field names", "VCS/URG worker and strict UVM checks", "Stage06 canonical parser", "preserve raw logs and reject existing output", "cache fixed category indices", "append hash-chained events and audit"],
        "algorithm_changes": ["allow consecutive and concurrent selection of the current top-ranked sequence", "inner sequence UCB reward is 80% global new-bin gain and 20% target-cluster new-bin gain; initial vectors remain candidate priors only", "sequence exploration counts use successful online observations across targets", "cluster and sequence UCB observation counts advance only after successful, parsed coverage feedback; every attempt still counts toward the budget"],
    }
    dump(args.result_dir / "protocol.json", policy_manifest)

    class Analyzer(author.HTMLCoverageAnalyzer):
        def __init__(self, config_file, mapping_file):
            super().__init__(config_file, mapping_file)
            self.names = super().get_all_bin_names_ordered()
            self.indices = {
                cat: np.array([i for i, name in enumerate(self.names) if f"category_{self.category_mapping[name]}" == cat], dtype=int)
                for cat in self.category_order
            }

        def extract_category_vector(self, vector, name):
            return np.asarray(vector)[self.indices.get(name, np.array([], dtype=int))]

        def process_single_test_data(self, dashboard_path):
            run_dir = Path(dashboard_path).parents[2]
            counts = json.loads((run_dir / "coverage_counts.json").read_text())
            counts["runtime"] = json.loads((run_dir / "execution.json").read_text())["simulator_cpu_seconds"]
            return counts

    author.HTMLCoverageAnalyzer = Analyzer

    class Runner(author.GenericAdaptiveRunner):
        def __init__(self):
            self.events_hash = "0" * 64
            self.event_index = 0
            self.submitted = self.completed = self.failed = self.active = self.max_active = 0
            self.results = []
            self.steering_enabled = args.steering
            self.steering_rng = random.Random(args.seed ^ 0xA0171E)
            self.steering_reserved = set()
            self.steering_covered = {
                name for index, name in enumerate(bin_names)
                if source_matrix[:, index].any()
            }
            self.steering_counts = Counter()
            self.first_submit_time = None
            self.policy_hash = sha(args.result_dir / "protocol.json")
            super().__init__(str(args.result_dir / "policy_config.json"), args.batch_size,
                             args.submissions // args.batch_size, str(args.result_dir / "author_initial.csv"),
                             str(args.result_dir), str(args.mapping), args.seed, False, args.workers, 0.3)
            assert sum(len(v) for v in self.historical_data.values()) == 39
            assert self.get_current_coverage_stats()[1:3] == (policy_manifest["initial_union"], 4507)

        def setup_result_directory(self):
            for name in ("batches", "logs"):
                (self.result_dir / name).mkdir(exist_ok=True)
            self.flush_runtime_logs()

        def cleanup_large_run_logs(self, run_dir):
            pass  # Raw logs are required evidence; source deletes them.

        def get_category_bin_names(self, name):
            return [self.coverage_analyzer.names[i] for i in self.coverage_analyzer.indices.get(name, [])]

        def emit(self, event, **fields):
            record = {"event_index": self.event_index, "event": event, "timestamp": time.time(),
                      "previous_hash": self.events_hash, "policy_hash": self.policy_hash, **fields}
            digest = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
            record["event_hash"] = digest
            with (self.result_dir / "events.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
            self.events_hash = digest
            self.event_index += 1

        def submit_next_test(self, executor, run_id, test_config, test_identifier, target_category, seed):
            assert seed == seed_list[run_id]
            target_bins = target_category.get("bin_names", []) if target_category else []
            if self.steering_enabled:
                steering = select_target(target_bins, self.steering_covered,
                                         self.steering_reserved, test_identifier,
                                         self.steering_rng)
            else:
                steering = {"status": "disabled"}
            if steering.get("status") == "targeted":
                self.steering_reserved.add(steering["target_bin"])
            self.steering_counts[steering["status"]] += 1
            test_config = dict(test_config)
            test_config["_steering"] = steering
            if self.first_submit_time is None:
                self.first_submit_time = time.time()
            self.submitted += 1
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.emit("submit", run_id=run_id, seed=seed, sequence=test_identifier,
                      target=target_category["name"] if target_category else None,
                      steering=steering,
                      feedback_count=self.completed, active=self.active,
                      accumulated_covered=self.get_current_coverage_stats()[1])
            future, context = super().submit_next_test(
                executor, run_id, test_config, test_identifier, target_category, seed)
            context["steering"] = steering
            return future, context

        def run_single_test(self, run_id, test_config, seed, batch_dir, target_category=None):
            run_dir = batch_dir / str(run_id)
            run_dir.mkdir(exist_ok=False)
            steering = test_config.get("_steering", {"status": "disabled"})
            directed_plusargs = steering_plusargs(steering)
            job = {
                "result_root": str(run_dir / "raw"), "test_name": test_config["seq"].removesuffix("_vseq"),
                "index": 0, "global_run_id": run_id, "seed": seed, "sequence": test_config["seq"],
                "simv": str(args.simv), "dv_root": str(args.dv_root),
                "timeout_seconds": 10800 if "stress_all" in test_config["seq"] else 1200,
                "extra_plusargs": directed_plusargs,
            }
            started = time.time()
            result = {"run_id": run_id, "status": "error", "test_description": test_config["seq"],
                      "steering": steering, "steering_plusargs": directed_plusargs}
            try:
                execution = corpus.run_one(job)
                raw_dir = run_dir / "raw" / job["test_name"] / "0"
                result.update(execution)
                if steering.get("status") == "targeted":
                    log_path = raw_dir / "run.log"
                    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
                    result["steering_applied"] = confirmed_in_log(steering, log_text)
                # Simulator exit zero alone is insufficient for UVM success.
                ok = execution["vcs_return_code"] == 0 and execution["uvm_pass"] and execution["uvm_error"] == 0 and execution["uvm_fatal"] == 0
                if ok:
                    report_dir, command, elapsed = converter.run_urg(
                        {"source_root": str(run_dir / "raw"), "relative_run_dir": str(raw_dir.relative_to(run_dir / "raw")), "source": "online", "global_run_id": run_id},
                        run_dir / "reports", args.urg, 300)
                    covered, expected = converter.parse_group_list_counts(report_dir)
                    counts = converter.canonicalize_report_bins(converter.parse_report(report_dir), canonical)
                    if len(counts) != 4507 or expected != 4507 or sum(v > 0 for v in counts.values()) != covered:
                        raise ValueError("URG counts differ from frozen 4507-bin universe or detailed totals")
                    if not list((raw_dir / "coverage/default.vdb").glob("snps/coverage/db/testdata/*/testbench.cumulative.xml")):
                        raise ValueError("cumulative XML absent")
                    dump(run_dir / "coverage_counts.json", counts)
                    result.update(status="success", parsed_bin_count=4507, run_covered_bins=covered,
                                  report_dir=str(report_dir), coverage_parse_seconds=elapsed)
                else:
                    result["status"] = "failed"
            except Exception as exc:
                result["error"] = f"{type(exc).__name__}: {exc}"
            result.update(worker_start_time=started, worker_end_time=time.time(), worker_wall_seconds=time.time() - started)
            dump(run_dir / "execution.json", result)
            return result

        def generate_html_report_for_run(self, run_dir):
            result = json.loads((Path(run_dir) / "execution.json").read_text())
            return Path(result["report_dir"]) / "dashboard.html" if result["status"] == "success" else None

        def process_completed_run(self, result, context):
            try:
                info = super().process_completed_run(result, context)
            except Exception as exc:
                info = {"new_bins": 0, "target_category_gain": 0, "weighted_info_gain": 0.0,
                        "new_bin_names": [], "runtime": 0.0, "processed": False}
                result["policy_processing_error"] = f"{type(exc).__name__}: {exc}"
            self.completed += 1
            self.active -= 1
            accepted = result.get("status") == "success" and info["processed"]
            if not accepted and result.get("status") == "success":
                result["status"] = "failed"
                result["failure_stage"] = "coverage_feedback"
            self.failed += int(not accepted)
            steering = context.get("steering", {"status": "disabled"})
            target_bin_hit = None
            if steering.get("status") == "targeted":
                self.steering_reserved.discard(steering["target_bin"])
                self.steering_counts["applied_confirmed"] += int(result.get("steering_applied", False))
                if accepted:
                    run_counts = json.loads((context["run_dir"] / "coverage_counts.json").read_text())
                    self.steering_covered.update(name for name, count in run_counts.items() if count > 0)
                    target_bin_hit = int(run_counts.get(steering["target_bin"], 0)) > 0
                    self.steering_counts["target_bin_hits"] += int(target_bin_hit)
                steering = {**steering, "target_bin_hit": target_bin_hit}
            result["steering"] = steering
            before_new = context["before_covered"]
            total_coverage, covered, total, _ = self.get_current_coverage_stats()
            safe_result = {k: v for k, v in result.items() if k != "report_dir"}
            safe_result.update(feedback_order=self.completed, target=context["target_category"]["name"] if context["target_category"] else None,
                               new_bins=info["new_bins"], target_category_gain=info["target_category_gain"],
                               weighted_info_gain=info["weighted_info_gain"], accumulated_covered=covered,
                               coverage_percent=total_coverage, scheduler_runtime=self.runtime)
            self.results.append(safe_result)
            vector = [int(x) for x in self.coverage_analyzer.create_full_coverage_vector(
                json.loads((context["run_dir"] / "coverage_counts.json").read_text()) if accepted else {})]
            with (self.result_dir / "vectors.csv").open("a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if self.completed == 1:
                    writer.writerow(["run_id", "accepted", *bin_names])
                writer.writerow([context["run_id"], accepted, *vector])
            self.emit("feedback", run_id=context["run_id"], accepted=accepted, active=self.active,
                      feedback_count=self.completed, new_bins=info["new_bins"], target_gain=info["target_category_gain"],
                      steering_status=steering.get("status"), steering_bin=steering.get("target_bin"),
                      steering_bin_hit=steering.get("target_bin_hit"),
                      opportunity_gain=info["weighted_info_gain"], accumulated_covered=covered,
                      simulator_cpu_seconds=result.get("simulator_cpu_seconds"),
                      vector_sha256=hashlib.sha256(bytes(vector)).hexdigest())
            dump(self.result_dir / "progress.json", {"submitted": self.submitted, "completed": self.completed, "failed": self.failed,
                "active": self.active, "coverage_bins": covered, "denominator": total, "event_head": self.events_hash})
            print(f"STAGE08_PROGRESS {self.completed}/{args.submissions} failed={self.failed} covered={covered}/{total}", flush=True)
            return info

        def generate_final_report(self):
            cpu = sum(float(row.get("simulator_cpu_seconds") or 0) for row in self.results)
            self.emit("finished", submitted=self.submitted, completed=self.completed, failed=self.failed)
            summary = {
                "schema": "aon-timer-stage08-summary-v1", "method": "Full",
                "status": "completed" if self.completed == args.submissions else "incomplete",
                "submitted": self.submitted, "completed": self.completed, "failed": self.failed, "retried": 0,
                "accepted": self.completed - self.failed, "max_active_workers": self.max_active,
                "bin_count": 4507, "initial_union_bins": policy_manifest["initial_union"],
                "final_covered_bins": self.get_current_coverage_stats()[1],
                "final_coverage_percent": self.get_current_coverage_stats()[0],
                "new_bins_beyond_initial": self.get_current_coverage_stats()[1] - policy_manifest["initial_union"],
                "accumulated_simulator_cpu_seconds_all_attempts": cpu,
                "accepted_simulator_cpu_seconds": self.runtime,
                "wall_seconds": time.time() - self.first_submit_time,
                "sequence_usage": dict(Counter(row["test_description"] for row in self.results)),
                "steering_enabled": self.steering_enabled,
                "steering_counts": dict(self.steering_counts),
                "policy_sha256": self.policy_hash, "event_chain_head": self.events_hash,
            }
            dump(self.result_dir / "run_results.json", self.results)
            dump(self.result_dir / "summary.json", summary)
            print(json.dumps(summary), flush=True)

    runner = Runner()
    if args.preflight_only:
        dump(args.result_dir / "preflight.json", {"status": "pass", "initial_vectors": 39, "bin_count": 4507,
            "covered_bins": runner.get_current_coverage_stats()[1], "sequence_history_counts": {k: len(v) for k, v in runner.historical_data.items()}})
        print("STAGE08_PREFLIGHT_OK")
        return 0
    runner.run_all_batches()
    return 0 if runner.completed == args.submissions else 1


if __name__ == "__main__":
    raise SystemExit(main())
