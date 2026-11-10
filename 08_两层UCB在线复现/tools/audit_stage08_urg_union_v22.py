#!/usr/bin/env python3
"""Cross-check a completed run against an independent, fresh URG VDB union.

Run on the school server. Raw commands, reports and merged VDB stay there;
only union_audit.json is suitable for the repository's evidence directory.
This does not change a running experiment or its frozen parser/adapter.
"""
import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def merged_report_group_name(soup):
    """URG merged pages use both 'Group :' and 'Group ::' in their titles."""
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    match = re.search(r"\bGroup\s*::?\s*(.+)$", title)
    if match is None:
        raise ValueError(f"Cannot find merged report group in title {title!r}")
    return match.group(1).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--reuse-existing-merge", action="store_true",
                        help="Read an existing identical command's merge; never rerun or overwrite it")
    args = parser.parse_args()
    root, run, output = args.root.resolve(), args.run_dir.resolve(), args.output_dir.resolve()
    protocol, summary, audit = (read(run / name) for name in
                                ("protocol.json", "summary.json", "audit.json"))
    if audit["status"] != "pass" or summary["status"] != "completed":
        raise ValueError("Require completed simulation and a passing event/vector audit")
    tools = root / "scratch/stage08_v20_20261110/tools"
    sys.path.insert(0, str(tools))
    from stage08_stable_coverage_v20 import StableCoverageSchema, _cross_counts_from_xml
    converter_path = tools / "run_stage06_conversion_stable.py"
    converter = module(converter_path, "union_converter")
    if sha(converter_path) != protocol["conversion_source_sha256"]:
        raise ValueError("Frozen converter hash differs from simulation protocol")
    # Audit-only title compatibility; the frozen worker/parser files stay unchanged.
    converter.report_group_name = merged_report_group_name
    initial = root / "runs/stage08_inputs_xml_20261110_v20_retry1/coverage_bin_by_run.csv"
    if sha(initial) != protocol["initial_csv_sha256"]:
        raise ValueError("Initial matrix hash differs from simulation protocol")
    with initial.open(encoding="utf-8", newline="") as handle:
        initial_rows = list(csv.DictReader(handle))
    conversion = root / "runs/stage06_conversion_20261101T_v10"
    initial_roots = {
        "original": root / "runs/stage05_initial_corpus_20261101T",
        "timeout_fix_replay": root / "runs/stage05_timeout_fix_20261101T",
    }
    source_manifest = read(initial.parent / "input_manifest.json")
    xml_hashes = {item["report_id"]: item["cumulative_xml_sha256"]
                  for item in source_manifest["runs"]}
    vdbs = []
    for row in initial_rows:
        vdb = (initial_roots[row["source"]] / row["test_name"] /
               row["sequence_run_index"] / "coverage/default.vdb")
        xml = list(vdb.glob("snps/coverage/db/testdata/*/testbench.cumulative.xml"))
        if len(xml) != 1 or sha(xml[0]) != xml_hashes[row["report_id"]]:
            raise ValueError(f"Initial VDB differs for {row['report_id']}: "
                             f"XML count={len(xml)}, "
                             f"actual_sha256={sha(xml[0]) if len(xml) == 1 else None}, "
                             f"expected_sha256={xml_hashes[row['report_id']]}")
        vdbs.append(vdb)
    for result in read(run / "run_results.json"):
        if result["status"] != "success":
            continue
        run_id = result["run_id"]
        vdbs.append(run / "batches" / f"batch_{run_id // protocol['logical_batch_size']}" /
                    str(run_id) / "raw" / result["test_name"] / "0/coverage/default.vdb")
    if len(vdbs) != protocol["initial_runs"] + summary["accepted"]:
        raise ValueError("Unexpected VDB count")
    if len(set(vdbs)) != len(vdbs) or not all(path.is_dir() for path in vdbs):
        raise ValueError("Missing or duplicate source VDB")
    output.mkdir(parents=True, exist_ok=args.reuse_existing_merge)
    merged, report = output / "merged.vdb", output / "report"
    command = ["urg", "-lca", "-full64", "+urg+lic+wait", "-metric", "group",
               "-show", "tests", "-group", "ratio", "-group", "lrm_bin_name",
               "-group", "instcov_for_score", "-group", "maxmissing", "100000",
               "-group", "show_bin_values", "-dir", *map(str, vdbs),
               "-dbname", str(merged), "-format", "both", "-report", str(report)]
    if args.reuse_existing_merge:
        if read(output / "command.json") != command:
            raise ValueError("Existing merge command does not match requested VDB union")
    else:
        (output / "command.json").write_text(json.dumps(command, indent=2) + "\n")
        with (output / "urg.log").open("w") as log:
            subprocess.run(command, cwd=output, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=600)
    if (output / "union_audit.json").exists():
        raise FileExistsError("Refusing to overwrite an existing union audit")
    test_count = int(re.search(r"Total tests in report:\s*(\d+)",
                              (report / "tests.txt").read_text()).group(1))
    names = set(initial_rows[0]) - set(list(initial_rows[0])[:list(initial_rows[0]).index("report_id") + 1])
    union = {name for name in names if any(int(row[name]) > 0 for row in initial_rows)}
    with (run / "vectors.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["accepted"] == "True":
                union.update(name for name in names if int(row[name]) > 0)
    # Read the same XML identities, then explicitly report every mismatch rather
    # than letting the parser's first strict exception suppress the URG evidence.
    schema = StableCoverageSchema(converter, conversion / "reports/original_g0")
    xml_paths = list(merged.glob("snps/coverage/db/testdata/*/testbench.cumulative.xml"))
    if len(xml_paths) != 1:
        raise ValueError("Expected one merged cumulative XML")
    auto_counts = converter.parse_auto_variable_counts(report, schema.expected_map, xml_paths[0])
    merged_counts = converter.parse_cumulative_xml(xml_paths[0], schema.expected_map, auto_counts)
    merged_counts = {key: value for key, value in merged_counts.items() if key.split("||")[1] != "cross"}
    merged_counts.update(_cross_counts_from_xml(converter, xml_paths[0], schema.expected_map))
    merged_union = {name for name, value in merged_counts.items() if value > 0}
    missing_definitions = names - set(merged_counts)
    extra_definitions = set(merged_counts) - names
    covered, denominator = converter.parse_group_list_counts(report)
    total_passed = (test_count == len(vdbs) and denominator == protocol["bin_count"]
                    and covered == len(union) == summary["final_covered_bins"])
    passed = (total_passed and merged_union == union and len(merged_counts) == len(names)
              and not (missing_definitions or extra_definitions))
    result = {
        "status": "pass" if passed else "partial" if total_passed else "fail", "run_name": run.name,
        "scope": "Independent detailed total plus separate merged XML identity comparison; partial is not a full identity-audit pass",
        "independent_urg_total_check": "pass" if total_passed else "fail",
        "initial_vdb_count": len(initial_rows), "accepted_online_vdb_count": summary["accepted"],
        "urg_test_count": test_count, "denominator": denominator,
        "urg_merged_covered_bins": covered, "python_union_bins": len(union),
        "merged_xml_covered_bins": len(merged_union), "merged_xml_bin_count": len(merged_counts),
        "merged_xml_bin_identities_match_vector_union": merged_union == union,
        "missing_from_vector_union": sorted(merged_union - union),
        "extra_in_vector_union": sorted(union - merged_union),
        "all_bin_definitions_match": not (missing_definitions or extra_definitions),
        "definitions_missing_from_merged_xml": sorted(missing_definitions),
        "definitions_extra_in_merged_xml": sorted(extra_definitions),
        "protocol_sha256": sha(run / "protocol.json"), "summary_sha256": sha(run / "summary.json"),
        "initial_csv_sha256": sha(initial), "urg_groups_sha256": sha(report / "groups.txt"),
        "merged_xml_sha256": sha(xml_paths[0]),
        "auditor_sha256": sha(Path(__file__)),
        "merged_report_compatibility": "Audit-only HTML group title support for both one and two colons; running experiment's converter unchanged",
        "limits": "Independent URG merge verifies the total. Exact identity comparison uses the frozen XML parser with audit-only HTML title compatibility and does not independently prove every bin's physical meaning.",
        "raw_logs_exported": False,
    }
    (output / "union_audit.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result), flush=True)
    if not passed:
        raise RuntimeError("URG union differs from the simulation evidence")


if __name__ == "__main__":
    main()
