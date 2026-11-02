#!/usr/bin/env python3
"""Build deterministic AON Timer cluster and information-score artifacts.

The input is the frozen Stage 06 bin-by-run CSV.  The source clusterers are
loaded from this stage's algorithm_source directory, while metadata columns
are explicitly excluded from the feature universe.  All outputs are small,
sanitized, and suitable for the Stage 08 category-mapping input.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
import platform
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd


VARIANTS = (
    "dbscan_clustering",
    "dbscan_clustering_new",
    "dbscan_clustering_new2",
    "dbscan_clustering_new3",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_clusterer(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.GenericHierarchicalClusterer


def stable_cluster_id(name: str, ordinal: int) -> int:
    """Use a compact deterministic ID; never depend on Python's hash()."""
    return ordinal


def cluster_stats(clusters: dict[str, list[str]]) -> dict:
    sizes = [len(items) for items in clusters.values()]
    return {
        "cluster_count": len(sizes),
        "item_count": int(sum(sizes)),
        "min_size": int(min(sizes)) if sizes else 0,
        "max_size": int(max(sizes)) if sizes else 0,
        "mean_size": float(np.mean(sizes)) if sizes else 0.0,
        "median_size": float(np.median(sizes)) if sizes else 0.0,
        "singleton_count": int(sum(size == 1 for size in sizes)),
        "clusters_over_max_cluster_size": int(sum(size > 256 for size in sizes)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-cluster-size", type=int, default=256)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    # The source files use hash() for feature buckets.  Require a fixed hash
    # seed so a rerun on the same host produces the same chosen mapping.
    hash_seed = os.environ.get("PYTHONHASHSEED", "")
    if hash_seed != str(args.seed):
        raise SystemExit(
            f"PYTHONHASHSEED must be {args.seed}; got {hash_seed!r}. "
            "Set it before invoking this program."
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(args.input)
    if "report_id" not in df.columns:
        raise ValueError("frozen CSV lacks report_id metadata column")
    report_index = int(df.columns.get_loc("report_id"))
    bin_columns = list(df.columns[report_index + 1 :])
    metadata_columns = list(df.columns[: report_index + 1])
    if len(bin_columns) != 4507:
        raise ValueError(f"expected 4507 coverage bins, got {len(bin_columns)}")
    matrix = df[bin_columns].fillna(0).to_numpy(dtype=float)
    binary = (matrix > 0).astype(np.int8)
    frequencies = binary.mean(axis=0)
    self_information = -np.log(np.clip(frequencies, 1e-10, 1.0))
    entropy_frequency = np.clip(frequencies, 1e-12, 1.0 - 1e-12)
    bernoulli_entropy = -(
        entropy_frequency * np.log(entropy_frequency)
        + (1.0 - entropy_frequency) * np.log(1.0 - entropy_frequency)
    )
    covered_runs = binary.sum(axis=0)
    initial_hit_count = matrix.sum(axis=0)

    # Keep the semantic partition visible and independently checkable.  The
    # frozen Stage 06 key format is
    # component::covergroup||variable_or_cross||coverpoint||bin_name||index.
    component_counts = Counter()
    covergroup_counts = Counter()
    structure_counts = Counter()
    coverpoint_counts = Counter()
    token_counts = Counter()
    for item in bin_columns:
        namespace, separator, remainder = item.partition("::")
        if separator:
            component_counts[namespace] += 1
            covergroup, inner_separator, inner = remainder.partition("||")
            if inner_separator:
                covergroup_counts[covergroup] += 1
                fields = item.split("||")
                if len(fields) >= 2:
                    structure_counts[fields[1]] += 1
                if len(fields) >= 3:
                    coverpoint_counts[fields[2]] += 1
        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", item):
            token_counts[token] += 1
    partition_summary = {
        "schema": "aon-timer-stage07-partition-v1",
        "key_format": "component::covergroup||variable_or_cross||coverpoint||bin_name||index",
        "bin_count": len(bin_columns),
        "unique_component_count": len(component_counts),
        "unique_covergroup_count": len(covergroup_counts),
        "unique_structure_count": len(structure_counts),
        "unique_coverpoint_count": len(coverpoint_counts),
        "top_components": component_counts.most_common(20),
        "top_covergroups": covergroup_counts.most_common(20),
        "structure_counts": dict(sorted(structure_counts.items())),
        "top_coverpoints": coverpoint_counts.most_common(30),
        "top_semantic_tokens": token_counts.most_common(50),
    }

    source_hashes = {}
    variant_results = {}
    for variant in VARIANTS:
        source = args.source_dir / f"{variant}.py"
        source_hashes[variant] = sha256(source)
        clusterer_class = load_clusterer(source)
        clusterer = clusterer_class(max_cluster_size=args.max_cluster_size)
        clusters = clusterer.hierarchical_split(bin_columns)
        # Keep source iteration order for traceability, but assign IDs from a
        # lexical order so the public mapping is stable across runs.
        ordered_names = sorted(clusters)
        mapping = {
            item: stable_cluster_id(name, ordinal)
            for ordinal, name in enumerate(ordered_names)
            for item in clusters[name]
        }
        if len(mapping) != len(bin_columns) or len(set(mapping)) != len(bin_columns):
            raise ValueError(f"{variant}: cluster mapping is incomplete or duplicated")
        variant_results[variant] = {
            "source": str(source.name),
            "source_sha256": source_hashes[variant],
            "cluster_names": ordered_names,
            "clusters": clusters,
            "mapping": mapping,
            "stats": cluster_stats(clusters),
        }

    # Select the variant by a declared, data-independent rule: no missing
    # bins, then fewest clusters over the configured size, then fewest
    # singletons, then lexical variant name.  This keeps selection auditable.
    ranked = sorted(
        VARIANTS,
        key=lambda name: (
            variant_results[name]["stats"]["clusters_over_max_cluster_size"],
            variant_results[name]["stats"]["singleton_count"],
            variant_results[name]["stats"]["cluster_count"],
            name,
        ),
    )
    selected = ranked[0]
    selected_result = variant_results[selected]
    selected_mapping = selected_result["mapping"]
    selected_clusters = selected_result["clusters"]

    # Cluster-level initial states and static information weights.
    cluster_rows = []
    raw_cluster_scores = {}
    for name in sorted(selected_clusters):
        cluster_id = selected_mapping[selected_clusters[name][0]]
        indices = [bin_columns.index(item) for item in selected_clusters[name]]
        raw_score = float(np.mean(self_information[indices])) if indices else 0.0
        raw_cluster_scores[cluster_id] = raw_score
        covered_bin_count = int(np.count_nonzero(covered_runs[indices] > 0))
        residual_raw = float(-np.log((covered_bin_count + 1.0) / (len(indices) + 1.0))) if indices else 0.0
        cluster_patterns = {tuple(row[indices].tolist()) for row in binary}
        structure_counter = Counter()
        for item in selected_clusters[name]:
            fields = item.split("||")
            structure_counter[fields[1] if len(fields) > 1 else "unknown"] += 1
        cluster_rows.append(
            {
                "cluster_id": cluster_id,
                "cluster_name": name,
                "bin_count": len(indices),
                "covered_bins": covered_bin_count,
                "total_hit_count": int(np.sum(initial_hit_count[indices])),
                "coverage_ratio": float(np.mean(binary[:, indices])) if indices else 0.0,
                "mean_self_information": raw_score,
                "self_information_sum": float(np.sum(self_information[indices])),
                "mean_bernoulli_entropy": float(np.mean(bernoulli_entropy[indices])) if indices else 0.0,
                "diversity_unique_patterns": len(cluster_patterns),
                "diversity_ratio": float(len(cluster_patterns) / len(df)) if len(df) else 0.0,
                "structure_variable_bins": int(structure_counter.get("variable", 0)),
                "structure_cross_bins": int(structure_counter.get("cross", 0)),
                "residual_prior_raw": residual_raw,
            }
        )
    positive = [score for score in raw_cluster_scores.values() if score > 0]
    mean_score = float(np.mean(positive)) if positive else 1.0
    positive_residual = [row["residual_prior_raw"] for row in cluster_rows if row["residual_prior_raw"] > 0]
    mean_residual = float(np.mean(positive_residual)) if positive_residual else 1.0
    for row in cluster_rows:
        row["static_information_weight"] = float(
            np.clip(raw_cluster_scores[row["cluster_id"]] / mean_score, 0.25, 4.0)
        )
        row["dynamic_residual_prior_initial"] = float(
            np.clip(row["residual_prior_raw"] / mean_residual, 0.25, 4.0)
        ) if row["residual_prior_raw"] > 0 else 1.0
        row["combined_initial_prior"] = float(
            np.clip(row["static_information_weight"] * row["dynamic_residual_prior_initial"], 0.25, 4.0)
        )

    bin_rows = []
    for index, item in enumerate(bin_columns):
        bin_rows.append(
            {
                "bin_name": item,
                "cluster_id": selected_mapping[item],
                "frequency": float(frequencies[index]),
                "covered_runs": int(covered_runs[index]),
                "initial_hit_count": int(initial_hit_count[index]),
                "self_information": float(self_information[index]),
            }
        )

    # CSVs consumed by Stage 08 and useful for independent inspection.
    mapping_path = args.output_dir / "bin_to_cluster.csv"
    with mapping_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["feature_name", "cluster_id"])
        for item in bin_columns:
            writer.writerow([item, selected_mapping[item]])
    with (args.output_dir / "cluster_initial_states.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(cluster_rows[0]))
        writer.writeheader()
        writer.writerows(cluster_rows)
    with (args.output_dir / "bin_information_scores.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(bin_rows[0]))
        writer.writeheader()
        writer.writerows(bin_rows)

    # JSON cluster representation retains the exact source names and members.
    public_clusters = {
        str(selected_mapping[members[0]]): {
            "source_cluster_name": name,
            "bins": members,
        }
        for name, members in sorted(selected_clusters.items())
    }
    (args.output_dir / "clusters.json").write_text(
        json.dumps(public_clusters, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output_dir / "variant_summary.json").write_text(
        json.dumps(
            {
                "schema": "aon-timer-stage07-variant-summary-v1",
                "input_sha256": sha256(args.input),
                "bin_count": len(bin_columns),
                "run_count": len(df),
                "max_cluster_size": args.max_cluster_size,
                "pythonhashseed": args.seed,
                "variants": {
                    name: {
                        "source": result["source"],
                        "source_sha256": result["source_sha256"],
                        "stats": result["stats"],
                    }
                    for name, result in variant_results.items()
                },
                "selection_rule": "min clusters_over_max_cluster_size, then min singleton_count, then min cluster_count, then lexical variant name",
                "selected_variant": selected,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (args.output_dir / "parameters.json").write_text(
        json.dumps(
            {
                "schema": "aon-timer-stage07-parameters-v1",
                "input": args.input.name,
                "input_sha256": sha256(args.input),
                "metadata_columns": metadata_columns,
                "coverage_bin_count": len(bin_columns),
                "accepted_run_count": len(df),
                "cluster_algorithm": selected,
                "cluster_source_sha256": source_hashes[selected],
                "max_cluster_size": args.max_cluster_size,
                "dbscan_min_samples": 2,
                "hierarchical_eps_schedule": "source-defined",
                "pythonhashseed": args.seed,
                "static_weight": "mean bin self-information / mean positive cluster score, clipped to [0.25, 4.0]",
                "entropy": "mean Bernoulli entropy per cluster across the 39 accepted run vectors",
                "diversity": "number of unique binary coverage patterns per cluster, with ratio over 39 runs",
                "dynamic_residual_prior": "-log((covered_bins+1)/(bin_count+1)), normalized over positive clusters and clipped to [0.25,4.0]",
                "self_information": "-log(covered_run_frequency), frequency over 39 accepted Stage 06 runs",
                "binary_coverage": "hit count > 0",
                "partitioning": "component, covergroup, variable_or_cross, coverpoint and semantic-token counters are recorded in partition_summary.json",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (args.output_dir / "cluster_initial_states.json").write_text(
        json.dumps(cluster_rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output_dir / "partition_summary.json").write_text(
        json.dumps(partition_summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    assigned = Counter(selected_mapping.values())
    validation = {
        "schema": "aon-timer-stage07-validation-v1",
        "input_sha256": sha256(args.input),
        "run_count": len(df),
        "metadata_column_count": len(metadata_columns),
        "bin_count": len(bin_columns),
        "mapped_bin_count": len(selected_mapping),
        "unique_cluster_id_count": len(assigned),
        "assignment_complete": len(selected_mapping) == len(bin_columns),
        "assignment_unique": len(selected_mapping) == len(set(selected_mapping)),
        "matrix_shape": [int(binary.shape[0]), int(binary.shape[1])],
        "finite_score_count": int(np.isfinite(self_information).sum()),
        "all_scores_finite": bool(np.isfinite(self_information).all()),
        "initial_union_covered_bins": int(np.count_nonzero(binary.sum(axis=0) > 0)),
        "initial_union_coverage_ratio": float(np.mean(binary.sum(axis=0) > 0)),
        "selected_variant": selected,
        "selected_stats": selected_result["stats"],
        "source_files": source_hashes,
        "host": platform.node(),
        "python": sys.version.split()[0],
    }
    (args.output_dir / "validation.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(json.dumps({"selected_variant": selected, "validation": validation}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
