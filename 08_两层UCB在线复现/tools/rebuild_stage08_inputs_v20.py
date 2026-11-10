#!/usr/bin/env python3
"""Rebuild the 39-run initial matrix from VCS cumulative XML bin identities."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path

from stage08_stable_coverage_v20 import StableCoverageSchema


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--converter", type=Path, required=True)
    parser.add_argument("--original-root", type=Path, required=True)
    parser.add_argument("--original-manifest", type=Path, required=True)
    parser.add_argument("--replay-root", type=Path, required=True)
    parser.add_argument("--replay-manifest", type=Path, required=True)
    parser.add_argument("--old-csv", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)

    converter = load_module(args.converter, "stage06_converter_v20")
    original, original_excluded = converter.accepted_runs(
        converter.json_load(args.original_manifest), args.original_root, "original"
    )
    replay, replay_excluded = converter.accepted_runs(
        converter.json_load(args.replay_manifest), args.replay_root, "timeout_fix_replay"
    )
    runs = sorted(original + replay, key=lambda r: (0 if r["source"] == "original" else 1,
                                                    r["global_run_id"]))
    if len(original) != 35 or len(original_excluded) != 5 or len(replay) != 4 or len(replay_excluded) != 1:
        raise ValueError("expected the frozen 35 original + 4 replay accepted-run corpus")

    old_rows = list(csv.DictReader(args.old_csv.open(encoding="utf-8", newline="")))
    old_by_id = {row["report_id"]: row for row in old_rows}
    if len(old_by_id) != 39:
        raise ValueError("expected 39 rows in original Stage06 input")
    old_columns = list(old_rows[0])
    if "report_id" not in old_columns:
        raise ValueError("original Stage06 CSV is missing report_id")
    metadata_columns = old_columns[: old_columns.index("report_id") + 1]
    reports_root = args.old_csv.parent / "reports"
    canonical_report = reports_root / "original_g0"
    schema = StableCoverageSchema(converter, canonical_report)
    output_rows = []
    summaries = []

    for index, run in enumerate(runs, 1):
        report_id = f"{run['source']}_g{run['global_run_id']}"
        report_dir = reports_root / report_id
        source_root = Path(run["source_root"])
        vdb = source_root / run["relative_run_dir"] / "coverage/default.vdb"
        counts = schema.parse(report_dir, vdb)
        if schema.expected_bin_names is None:
            schema.bind_bin_names(counts)
        old = old_by_id[report_id]
        row = {key: old[key] for key in metadata_columns}
        row["covered_bins"] = sum(value > 0 for value in counts.values())
        row.update(counts)
        output_rows.append(row)
        summaries.append({
            "report_id": report_id,
            "cumulative_xml_sha256": sha(next(vdb.glob("snps/coverage/db/testdata/*/testbench.cumulative.xml"))),
            "covered_bins": row["covered_bins"],
            "urg_detailed_covered": converter.parse_group_list_counts(report_dir)[0],
        })
        print(f"[{index}/{len(runs)}] parsed {report_id}: {row['covered_bins']} covered bins", flush=True)

    metadata = metadata_columns
    bin_names = sorted(schema.expected_bin_names)
    csv_path = args.output_dir / "coverage_bin_by_run.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=metadata + bin_names)
        writer.writeheader()
        writer.writerows(output_rows)

    manifest = {
        "schema": "aon-timer-stage08-stable-xml-input-v1",
        "source_csv_sha256": sha(args.old_csv),
        "converter_sha256": sha(args.converter),
        "canonical_report": "Stage06 original_g0 prefix cardinalities; row order is not used for bin identities",
        "canonical_report_groups_sha256": sha(canonical_report / "groups.txt"),
        "initial_runs": len(output_rows),
        "bin_count": len(bin_names),
        "prefix_count": len(schema.expected_map),
        "initial_union_bins": len({key for key in bin_names if any(int(row[key]) > 0 for row in output_rows)}),
        "identity_source": "VCS testbench.cumulative.xml coverpoint/bin indices and crosspoint member tuples; URG HTML contributes only numeric auto-bin fallback counts and independent covered totals",
        "runs": summaries,
    }
    manifest["csv_sha256"] = sha(csv_path)
    (args.output_dir / "input_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: manifest[key] for key in
                      ("initial_runs", "bin_count", "prefix_count", "initial_union_bins", "csv_sha256")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
