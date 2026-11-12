#!/usr/bin/env python3
"""Read-only independent review of completed Stage09 V30 exports and raw runs.

Never resumes simulations or changes Stage09 artifacts. Missing methods yield a
partial report; a complete verdict requires all six methods and raw-file checks.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import random
import re
from zoneinfo import ZoneInfo


METHODS = ("Full", "NoIncrementalRefill", "NoRuntimePenalty", "RandomSelection",
           "SequenceUCBOnly", "ClusterUCBOnly")
FILES = ("protocol.json", "summary.json", "audit.json", "raw_uvm_audit.json",
         "union_audit.json", "input_comparison.json", "events.jsonl",
         "vectors.csv", "run_results.json", "coverage_curve.csv")
COMMON = ("initial_csv_sha256", "mapping_sha256", "simv_sha256", "author_source_sha256",
          "baseline_source_sha256", "conversion_source_sha256", "corpus_source_sha256",
          "canonical_report_sha256", "bin_count", "cluster_count", "initial_runs",
          "initial_union", "sequence_pool", "seeds", "workers", "logical_batch_size",
          "seed", "budget", "host_timeout_seconds", "failure_rule", "bin_identity")


class VerificationError(ValueError):
    pass


def require(condition, label):
    if not condition:
        raise VerificationError(label)


def read(path):
    def invalid(value):
        raise VerificationError("nonfinite JSON constant: " + value)
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=invalid)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def equal_number(left, right, label, tolerance=1e-6):
    require(isinstance(left, (int, float)) and isinstance(right, (int, float))
            and math.isfinite(left) and math.isfinite(right)
            and math.isclose(left, right, rel_tol=1e-10, abs_tol=tolerance), label)


def rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def verify_manifest(folder):
    seen = set()
    for line in (folder / "sha256.txt").read_text(encoding="utf-8").splitlines():
        expected, name = line.split(None, 1)
        require(Path(name).name == name and name not in seen, "unsafe/duplicate manifest entry")
        require(sha(folder / name) == expected, "export hash: " + name)
        seen.add(name)
    require(set(FILES) <= seen, "manifest lacks required evidence")
    return len(seen)


def frozen_inputs(initial, mapping):
    data = rows(initial)
    require(len(data) == 39, "initial corpus cardinality")
    with initial.open(encoding="utf-8", newline="") as stream:
        header = next(csv.reader(stream))
    names = sorted(header[header.index("report_id") + 1:])
    mapped = rows(mapping)
    categories = {r["feature_name"]: "category_" + r["cluster_id"] for r in mapped}
    require(len(names) == len(set(names)) == len(mapped) == len(categories) == 4507,
            "bin denominator or duplicates")
    require(set(names) == set(categories), "initial/mapping bin identity")
    require(len(set(categories.values())) == 751, "cluster cardinality")
    union = [False] * len(names)
    for row in data:
        require(row["uvm_pass"] == "True" and row["vcs_return_code"] == "0"
                and row["urg_return_code"] == "0", "initial run acceptance")
        values = [int(row[name]) for name in names]
        require(all(x >= 0 for x in values), "negative initial coverage")
        union = [old or value > 0 for old, value in zip(union, values)]
    require(sum(union) == 508, "initial coverage union")
    return {"names": names, "union": union, "categories": categories,
            "initial_sha256": sha(initial), "mapping_sha256": sha(mapping)}


def verify_events(folder, protocol, policy_hash):
    submits, feedback, active, maximum, refills = {}, [], 0, 0, 0
    previous, last_kind, last_time, finished = "0" * 64, None, -math.inf, None
    schedule = random.Random(protocol["seed"])
    random_arms = [schedule.choice(protocol["sequence_pool"]) for _ in protocol["seeds"]]
    for index, line in enumerate((folder / "events.jsonl").read_text(encoding="utf-8").splitlines()):
        event = json.loads(line)
        digest = event.pop("event_hash")
        require(event["event_index"] == index and event["previous_hash"] == previous
                and event["policy_hash"] == policy_hash, "event chain linkage")
        require(hashlib.sha256(json.dumps(event, sort_keys=True, separators=(",", ":"),
                                         allow_nan=False).encode()).hexdigest() == digest, "event hash")
        require(math.isfinite(event["timestamp"]) and event["timestamp"] >= last_time,
                "event timestamp order")
        require(finished is None, "events after finished")
        kind = event["event"]
        if kind == "submit":
            i = event["run_id"]
            require(i == len(submits) and i < protocol["budget"], "submit id/budget")
            require(event["seed"] == protocol["seeds"][i]
                    and event["feedback_count"] == len(feedback), "submission seed/feedback")
            require(event["sequence"] in protocol["sequence_pool"]
                    and event["steering"]["status"] == "disabled", "sequence/steering")
            if protocol["refill_mode"] == "batch_barrier":
                require(len(feedback) == i // protocol["logical_batch_size"] * protocol["logical_batch_size"],
                        "batch barrier violated")
            elif i >= protocol["workers"]:
                require(last_kind == "feedback", "continuous refill without feedback")
                refills += 1
            method = protocol["method"]
            if method in ("RandomSelection", "SequenceUCBOnly"):
                require(event["target"] is None, "cluster-free method has target")
            if method == "RandomSelection":
                require(event["sequence"] == random_arms[i]
                        == protocol["random_sequence_schedule"][i], "random arm schedule")
            if method == "SequenceUCBOnly":
                decision = event["ablation_decision"]
                require(decision["rule"] == "global_sequence_ucb"
                        and event["sequence"] == max(decision["scores"], key=decision["scores"].get),
                        "sequence-only decision")
            if method == "ClusterUCBOnly":
                decision = event["ablation_decision"]
                require(decision["rule"] == "uniform_target_relevant_sequence"
                        and event["sequence"] in decision["candidates"], "cluster-only decision")
            active += 1
            maximum = max(maximum, active)
            require(active <= protocol["workers"] and event["active"] == active, "submit concurrency")
            submits[i] = event
        elif kind == "feedback":
            i = event["run_id"]
            require(i in submits and all(e["run_id"] != i for e in feedback), "feedback id")
            active -= 1
            require(active >= 0 and event["active"] == active
                    and event["feedback_count"] == len(feedback) + 1, "feedback concurrency/order")
            feedback.append(event)
        elif kind == "finished":
            require(active == 0 and event["submitted"] == len(submits)
                    and event["completed"] == len(feedback) == protocol["budget"], "finished counts")
            finished = event
        else:
            raise VerificationError("unknown event kind")
        previous, last_kind, last_time = digest, kind, event["timestamp"]
    require(finished is not None and len(submits) == len(feedback) == protocol["budget"], "missing finished/budget")
    return submits, feedback, finished, previous, maximum, refills


def verify_raw(run, result, vector, names, raw_case, protocol):
    i = result["run_id"]
    folder = run / "batches" / ("batch_" + str(i // protocol["logical_batch_size"])) / str(i)
    execution = read(folder / "execution.json")
    for key in ("seed", "vcs_return_code", "uvm_error", "uvm_fatal", "uvm_pass"):
        require(execution.get(key) == result.get(key), "raw execution: " + key)
    equal_number(execution["simulator_cpu_seconds"], result["simulator_cpu_seconds"], "raw CPU")
    raw = (folder / "raw" / result["test_name"] / "0/run.log").read_bytes()
    require(hashlib.sha256(raw).hexdigest() == raw_case["log_sha256"], "raw log hash")
    text = raw.decode(errors="replace")
    cpu = re.findall(r"CPU Time:\s*([\d.]+)\s+seconds", text)
    require(bool(cpu), "raw log CPU missing")
    equal_number(float(cpu[-1]), result["simulator_cpu_seconds"], "raw log CPU measurement", 0.001)
    if result["status"] == "success":
        require(result["vcs_return_code"] == 0 and "--- UVM Report Summary ---" in text
                and re.search(r"^TEST PASSED CHECKS\s*$", text, re.M), "raw UVM completion")
        for severity in ("UVM_ERROR", "UVM_FATAL"):
            counts = re.findall(r"^\s*" + severity + r"\s*:\s*(\d+)\s*$", text, re.M)
            require(bool(counts) and int(counts[-1]) == 0, "raw UVM severity")
        require(not re.search(r"^\s*(?:(?:UVM_ERROR|UVM_FATAL)\s+@|ERROR:)", text, re.M), "raw error report")
        times = re.findall(r"^\s*Time:\s*(\d+)\s+ps\s*$", text, re.M)
        require(bool(times) and int(times[-1]) > 0
                and int(times[-1]) == raw_case["simulation_time_ps"], "raw simulation time")
        counts = read(folder / "coverage_counts.json")
        require(set(counts) == set(names)
                and [int(counts[name] > 0) for name in names] == vector, "raw coverage/vector")


def verify_run(folder, method, inputs, prereg, raw_runs=None):
    manifest_count = verify_manifest(folder)
    protocol, summary = read(folder / "protocol.json"), read(folder / "summary.json")
    require(protocol["method"] == summary["method"] == method, "method identity")
    expected = {"budget": prereg["budget_per_method"], "workers": prereg["workers_per_method"],
                "logical_batch_size": 10, "seed": prereg["seed"], "initial_runs": 39,
                "bin_count": 4507, "cluster_count": 751, "initial_union": 508}
    require(all(protocol.get(k) == v for k, v in expected.items()), "preregistered controls")
    require(protocol["initial_csv_sha256"] == inputs["initial_sha256"]
            and protocol["mapping_sha256"] == inputs["mapping_sha256"], "frozen input hashes")
    require(protocol["steering"]["enabled"] is False and summary["steering_enabled"] is False,
            "uniform steering control")
    require(protocol["refill_mode"] == ("batch_barrier" if method == "NoIncrementalRefill" else "continuous"),
            "refill mode")
    rng = random.Random(prereg["seed"])
    require(protocol["seeds"] == [rng.randint(1, 2**31 - 1) for _ in range(expected["budget"])], "seed list")
    require(summary["status"] == "completed" and summary["retried"] == 0
            and summary["submitted"] == summary["completed"] == expected["budget"], "completed budget")
    policy_hash = sha(folder / "protocol.json")
    audit, raw_audit, union_audit, input_audit = [read(folder / n) for n in FILES[2:6]]
    require(all(a["status"] == "pass" for a in (audit, raw_audit, union_audit, input_audit)), "Stage09 audit gate")
    require(all(input_audit["matching_fields"].values()), "Stage09 shared inputs")
    require(summary["policy_sha256"] == audit["protocol_sha256"] == union_audit["protocol_sha256"] == policy_hash
            and union_audit["summary_sha256"] == sha(folder / "summary.json"), "audit binding")
    submits, feedback, finished, head, maximum, refills = verify_events(folder, protocol, policy_hash)
    require(head == summary["event_chain_head"] == audit["event_chain_head"], "final event hash")
    require(maximum == summary["max_active_workers"] == audit["max_active_workers"]
            and refills == audit["refills_after_feedback"], "concurrency audit comparison")
    require(summary["initial_union_bins"] == 508 and summary["bin_count"] == 4507, "summary denominator/initial")
    names, union = inputs["names"], list(inputs["union"])
    raw_cases = {x["run_id"]: x for x in raw_audit["cases"]}
    require(len(raw_cases) == raw_audit["checked_runs"] == expected["budget"], "raw audit cardinality")
    results, curve = read(folder / "run_results.json"), rows(folder / "coverage_curve.csv")
    require(len(results) == len(curve) == expected["budget"], "result/curve cardinality")
    cpu, failures, gains, usage, milestones = 0.0, 0, [], Counter(), {}
    start = submits[0]["timestamp"]
    with (folder / "vectors.csv").open(encoding="utf-8", newline="") as stream:
        vectors = csv.reader(stream)
        require(next(vectors) == ["run_id", "accepted", *names], "vector bin identities")
        for order, (result, event, point) in enumerate(zip(results, feedback, curve), 1):
            row = next(vectors, None)
            require(row is not None and len(row) == len(names) + 2, "vector cardinality")
            i, accepted = result["run_id"], result["status"] == "success"
            require(row[0] == str(i) and row[1] == str(accepted) and event["run_id"] == i
                    and result["feedback_order"] == order and event["accepted"] is accepted, "feedback/vector order")
            vector = [int(x) for x in row[2:]]
            require(all(x in (0, 1) for x in vector), "nonbinary vector")
            require(hashlib.sha256(bytes(vector)).hexdigest() == event["vector_sha256"], "vector hash")
            submit, raw_case = submits[i], raw_cases[i]
            require(result["seed"] == submit["seed"] and result["sequence"] == result["test_description"]
                    == submit["sequence"] and result["target"] == submit["target"], "result/submit identity")
            equal_number(result["worker_wall_seconds"], result["worker_end_time"] - result["worker_start_time"], "worker wall", 0.01)
            require(result["worker_start_time"] >= submit["timestamp"]
                    and result["worker_end_time"] <= event["timestamp"], "worker timestamps")
            require(raw_case["accepted"] is accepted, "raw acceptance")
            if accepted:
                require(raw_case["status"] == "pass" and raw_case["simulation_time_ps"] > 0
                        and result["uvm_pass"] and result["uvm_error"] == result["uvm_fatal"] == 0
                        and result["vcs_return_code"] == result["urg_return_code"] == 0
                        and result["parsed_bin_count"] == len(names) and result["run_covered_bins"] == sum(vector),
                        "accepted run evidence")
            else:
                require(not any(vector), "failed run rewarded")
                failures += 1
            if raw_runs is not None:
                verify_raw(raw_runs / folder.name, result, vector, names, raw_case, protocol)
            added = [k for k, (old, hit) in enumerate(zip(union, vector)) if not old and hit]
            target_gain = sum(inputs["categories"][names[k]] == submit["target"] for k in added) if submit["target"] else 0
            require(result["new_bins"] == event["new_bins"] == len(added)
                    and result["target_category_gain"] == event["target_gain"] == target_gain, "new-bin/target reward")
            for k in added:
                union[k] = True
            covered = sum(union)
            require(covered == result["accumulated_covered"] == event["accumulated_covered"], "coverage accumulation")
            equal_number(result["coverage_percent"], covered / len(names) * 100, "coverage percent")
            runtime = result["simulator_cpu_seconds"]
            require(math.isfinite(runtime) and runtime >= 0, "CPU measurement")
            equal_number(runtime, event["simulator_cpu_seconds"], "CPU event")
            cpu += runtime
            require(int(point["feedback_order"]) == order and int(point["run_id"]) == i
                    and point["accepted"] == str(accepted) and int(point["covered_bins"]) == covered
                    and int(point["new_bins"]) == len(added), "curve identity/coverage")
            equal_number(float(point["coverage_percent"]), covered / len(names) * 100, "curve percent")
            equal_number(float(point["accumulated_simulator_cpu_seconds"]), cpu, "curve CPU")
            equal_number(float(point["wall_seconds"]), event["timestamp"] - start, "curve wall")
            usage[result["sequence"]] += 1
            gains.append(len(added))
            if order in (30, 100, 200, 500, 750, 900, 1000):
                milestones[str(order)] = covered
        require(next(vectors, None) is None, "extra vector rows")
    require(failures == summary["failed"] == audit["failed"] == finished["failed"]
            and summary["accepted"] == len(results) - failures, "failure accounting")
    require(sum(union) == summary["final_covered_bins"] == audit["final_covered_bins"]
            and summary["new_bins_beyond_initial"] == sum(gains) == sum(union) - 508, "final union")
    require(dict(usage) == summary["sequence_usage"], "sequence usage")
    equal_number(cpu, summary["accumulated_simulator_cpu_seconds_all_attempts"], "summary CPU")
    equal_number(summary["final_coverage_percent"], sum(union) / len(names) * 100, "summary percent")
    reporting_tail = summary["wall_seconds"] - (feedback[-1]["timestamp"] - start)
    require(summary["wall_seconds"] >= finished["timestamp"] - start
            and summary["wall_seconds"] - (finished["timestamp"] - start) < 5, "summary wall")
    require(union_audit["denominator"] == union_audit["merged_xml_bin_count"] == len(names)
            and union_audit["urg_merged_covered_bins"] == union_audit["python_union_bins"]
            == union_audit["merged_xml_covered_bins"] == sum(union)
            and union_audit["urg_test_count"] == 39 + len(results) - failures
            and union_audit["merged_xml_bin_identities_match_vector_union"]
            and union_audit["all_bin_definitions_match"]
            and not union_audit["missing_from_vector_union"] and not union_audit["extra_in_vector_union"], "independent URG comparison")
    return {"method": method, "status": "pass", "completed": len(results), "failed": failures,
            "covered_bins": sum(union), "denominator": len(names), "coverage_percent": sum(union) / len(names) * 100,
            "new_bins": sum(gains), "last_100_new_bins": sum(gains[-100:]),
            "simulator_cpu_seconds": cpu, "wall_seconds": summary["wall_seconds"],
            "last_feedback_wall_seconds": feedback[-1]["timestamp"] - start,
            "reporting_tail_seconds": reporting_tail, "milestones": milestones, "sequence_usage": dict(usage),
            "raw_files_rechecked": raw_runs is not None, "manifest_files_verified": manifest_count,
            "export_manifest_sha256": sha(folder / "sha256.txt"), "protocol_sha256": policy_hash,
            "summary_sha256": sha(folder / "summary.json"),
            "shared_controls": {key: protocol[key] for key in COMMON}}


def generate(evidence, inputs, prereg_path, reference_path, output, raw_runs=None):
    require(not output.exists(), "output already exists; preserve earlier review")
    prereg = read(prereg_path)
    require(tuple(prereg["methods"]) == METHODS and prereg["budget_per_method"] == 1000
            and prereg["workers_per_method"] == 10 and prereg["seed"] == 42
            and prereg["steering_for_all_methods"] is False and prereg["retry"] is False,
            "preregistration identity")
    reference = {r["method"]: r for r in rows(reference_path)}
    require(set(reference) == set(METHODS), "paper reference methods")
    reviewed, missing = [], []
    for method in METHODS:
        folder = evidence / ("stage09_v30_" + method + "_full1000_20261111")
        if not folder.exists():
            missing.append(method)
            continue
        reviewed.append(verify_run(folder, method, inputs, prereg, raw_runs))
    signatures = [json.dumps(row["shared_controls"], sort_keys=True) for row in reviewed]
    require(len(set(signatures)) <= 1, "methods use different shared inputs/protocols")
    for row in reviewed:
        row.pop("shared_controls")
    complete = not missing and all(r["raw_files_rechecked"] for r in reviewed)
    report = {"schema": "stage10-v30-independent-review-v1", "status": "pass" if complete else "partial",
              "complete": complete, "observed_at_china": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
              "scope": "Independent event/vector/reward/CPU/wall recalculation; raw log and coverage-count reread when supplied. URG database merge result is cross-checked from the Stage09 audit, not rerun here.",
              "reviewed_methods": reviewed, "missing_methods": missing,
              "raw_recheck_required_for_final": True, "same_controls_among_available_methods": True,
              "initial_csv_sha256": inputs["initial_sha256"], "mapping_sha256": inputs["mapping_sha256"],
              "preregistration_sha256": sha(prereg_path), "paper_reference_sha256": sha(reference_path),
              "verifier_sha256": sha(Path(__file__)),
              "limitations": ["Single local seed; paper denominator, sequence pool, seed and timing semantics remain unaligned.",
                              "Coverage differences from paper are descriptive; no algorithmic advantage or speedup claim.",
                              "The scoreboard uses a bounded interrupt-arrival window, not a complete cycle-accurate golden model.",
                              "Raw files and URG databases remain on server. Export hashes alone are not an independent physical bin oracle."]}
    output.mkdir(parents=True)
    (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    by_method = {r["method"]: r for r in reviewed}
    comparison = []
    for method in METHODS:
        local, paper = by_method.get(method), reference[method]
        comparison.append({"method": method, "local_status": "verified" if local else "pending",
                           "local_coverage_percent": local["coverage_percent"] if local else "",
                           "paper_reference_percent": paper["paper_coverage_percent"],
                           "descriptive_difference_pp": local["coverage_percent"] - float(paper["paper_coverage_percent"]) if local else "",
                           "local_simulator_cpu_seconds": local["simulator_cpu_seconds"] if local else "",
                           "paper_runtime_seconds_unaligned": paper["paper_accumulated_runtime_seconds"],
                           "local_wall_seconds": local["wall_seconds"] if local else "",
                           "paper_wall_seconds_unaligned": paper["paper_walltime_seconds"],
                           "last_100_new_bins": local["last_100_new_bins"] if local else ""})
    with (output / "comparison.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(comparison[0]))
        writer.writeheader()
        writer.writerows(comparison)
    table = "| 方法 | 正式运行复核 | 本地覆盖 | 论文参考 | 最后 100 次新增 bin |\n| --- | --- | ---: | ---: | ---: |\n"
    for row in comparison:
        local = by_method.get(row["method"])
        coverage = f"{local['covered_bins']}/4507（{local['coverage_percent']:.4f}%）" if local else "待完成"
        table += f"| {row['method']} | {'通过' if local else '等待'} | {coverage} | {row['paper_reference_percent']}% | {local['last_100_new_bins'] if local else ''} |\n"
    title = "第十步最终复核" if complete else "第十步准备：部分复核，尚未完成"
    (output / "README.md").write_text(
        f"# {title}\n\n观测时间：{report['observed_at_china']}。已复核 {len(reviewed)}/6 种方法。"
        "只有六种方法均完成、共享协议一致、原始文件重新读取及全部审计通过，才标记第十步完成。\n\n" + table +
        "\n上表论文数字为公开参考；分母、pool、seed 和 runtime 定义未完全对齐，差值不能作为算法优势或加速比。"
        "缺少的方法保留为空，不用第八步定向 V30 或旧解析器结果填补。\n\n"
        "独立重算冻结初始并集、事件链、seed、覆盖向量、新增奖励、目标 cluster 收益、逐次 CPU 与 wall 曲线、失败预算和末段增益。"
        "服务器模式还重新读取每个原始 UVM 日志、execution 和 coverage counts；URG 合并结果核对已有独立审计，本脚本不再次启动 URG。"
        "原始数据库和完整日志仍只保留服务器。\n\n"
        "wall_seconds 使用原始摘要从首项提交至收尾报告的实测值；verification.json 另列最后一次覆盖反馈时间及报告尾部开销。"
        "共享服务器负载和反馈顺序影响 walltime。完整结论需等待剩余方法。\n", encoding="utf-8")
    (output / "sha256.txt").write_text("".join(f"{sha(p)}  {p.name}\n" for p in sorted(output.iterdir()) if p.is_file()), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("evidence-root", "initial-csv", "mapping", "preregistration", "paper-reference", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--raw-runs-root", type=Path)
    parser.add_argument("--allow-incomplete", action="store_true", help="Allow a visibly partial preparation report; never promotes it to complete")
    args = parser.parse_args()
    try:
        inputs = frozen_inputs(args.initial_csv, args.mapping)
        report = generate(args.evidence_root, inputs, args.preregistration, args.paper_reference,
                          args.output, args.raw_runs_root)
    except (VerificationError, KeyError, OSError, ValueError, StopIteration) as exc:
        print(json.dumps({"status": "fail", "error": type(exc).__name__,
                          "detail": str(exc) if isinstance(exc, VerificationError) else "malformed or missing evidence"}))
        return 1
    print(json.dumps({"status": report["status"], "complete": report["complete"],
                      "reviewed_methods": [r["method"] for r in report["reviewed_methods"]],
                      "missing_methods": report["missing_methods"]}))
    return 0 if report["complete"] or args.allow_incomplete else 2


if __name__ == "__main__":
    raise SystemExit(main())
