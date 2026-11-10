"""Read one run's bin counts from stable VCS cumulative XML identities."""
from __future__ import annotations

from collections import Counter
import gzip
import itertools
from pathlib import Path
import xml.etree.ElementTree as ET


def _expand_cross_pattern(node, prefix=()):
    """Expand a VCS cross pattern tree into exact coverpoint-index tuples."""
    tag = node.tag
    if tag == "cn_nt_s":
        prefix = prefix + (int(node.get("val", "0")),)
    elif tag == "cn_nt_r":
        low, high = int(node.get("low", "0")), int(node.get("high", "0"))
        return {
            item
            for value in range(low, high + 1)
            for child in list(node)
            for item in _expand_cross_pattern(child, prefix + (value,))
        }
    elif tag in {"cn_t_s", "cn_t_s_d"}:
        return {prefix + (int(node.get("val", "0")),)}
    elif tag == "cn_t_r":
        low, high = int(node.get("low", "0")), int(node.get("high", "0"))
        return {prefix + (value,) for value in range(low, high + 1)}
    elif tag == "cn_t_m_d":
        return {prefix + (int(value),) for value in node.get("val", "").split()}
    return {
        item
        for child in list(node)
        for item in _expand_cross_pattern(child, prefix)
    }


def _cross_counts_from_xml(converter, xml_path: Path, expected_map):
    root = ET.fromstring(gzip.open(xml_path, "rb").read())
    result = {}
    for source in root.findall(".//cg_src"):
        source_cp_names = {cp.get("id", ""): cp.get("exprname", "") for cp in source.findall("cp")}
        source_cc_names = {cc.get("id", ""): cc.get("name", "") for cc in source.findall("cc")}
        for cg in source.findall("cg_covdef"):
            group = cg.get("name", "")
            matching_groups = {
                key[0] for key in expected_map
                if key[0] == group or key[0].endswith("::" + group)
            }
            canonical_group = sorted(matching_groups, key=len, reverse=True)[0] if matching_groups else group
            cp_by_id = {}
            for cp in cg.findall("cp"):
                cp_id = cp.get("id", "")
                cp_name = source_cp_names.get(cp_id, cp_id)
                bins = [
                    (int(bn.get("id", "0")), bn.get("name", ""))
                    for bn in cp.findall("bn")
                    if bn.get("excl") != "1" and bn.get("unreachable") != "1"
                ]
                bins.sort(key=lambda item: item[0])
                labels = [name for _, name in bins]
                expected = expected_map.get((canonical_group, "variable", cp_name), len(labels))
                if cp.get("type") == "auto_c" and not labels:
                    data_indices = {
                        int(index)
                        for data in cp.findall("data")
                        for index in data.get("index", "").split()
                    }
                    labels = [f"auto[{index}]" for index in range(expected)]
                    if data_indices and max(data_indices) >= expected:
                        raise ValueError(f"auto-bin index exceeds schema for {(canonical_group, cp_name)}")
                while len(labels) < expected:
                    labels.append(f"auto[{len(labels)}]")
                cp_by_id[cp_id] = labels

            for cc in cg.findall("cc"):
                crosspoints = cc.find("crosspoints")
                refs = crosspoints.get("covdefrefs", "").split() if crosspoints is not None else []
                if not refs:
                    continue
                cc_name = cc.get("name") or source_cc_names.get(cc.get("id", ""), f"cross_{cc.get('id', '')}")
                expected_total = expected_map.get((canonical_group, "cross", cc_name), 0)
                if not expected_total:
                    continue
                sizes = [len(cp_by_id.get(ref, [])) for ref in refs]
                if not all(sizes):
                    raise ValueError(f"cross references an unknown coverpoint in {(canonical_group, cc_name)}")

                excluded = set()
                named_bins = []
                named = cc.find("named_cross_bins")
                if named is not None:
                    for entry in named.findall("n_cn"):
                        pattern = set().union(*(
                            _expand_cross_pattern(child) for child in list(entry)
                        )) if list(entry) else set()
                        excluded.update(pattern)
                        if entry.get("illegal") != "1" and entry.get("ignore") != "1":
                            named_bins.append((entry.get("name", ""), int(entry.get("data", "0"))))
                excluded_node = cc.find("excluded_crosses")
                if excluded_node is not None:
                    for child in list(excluded_node):
                        excluded.update(_expand_cross_pattern(child))

                auto_expected = expected_total - len(named_bins)
                auto_combinations = []
                if auto_expected < 0:
                    raise ValueError(f"named cross bins exceed schema for {(canonical_group, cc_name)}")
                if auto_expected:
                    for combo in itertools.product(*(range(size) for size in sizes)):
                        if combo in excluded:
                            continue
                        auto_combinations.append(combo)
                        if len(auto_combinations) == auto_expected:
                            break
                if len(auto_combinations) != auto_expected:
                    raise ValueError(
                        f"cross schema has too few legal tuples for {(canonical_group, cc_name)}: "
                        f"{len(auto_combinations)} != {auto_expected}"
                    )

                hit_data = {}

                def walk(node, prefix=()):
                    tag = node.tag
                    if tag == "cn_nt_s":
                        prefix = prefix + (int(node.get("val", "0")),)
                    elif tag == "cn_nt_r":
                        low, high = int(node.get("low", "0")), int(node.get("high", "0"))
                        for value in range(low, high + 1):
                            for child in list(node):
                                walk(child, prefix + (value,))
                        return
                    elif tag == "cn_t_r":
                        return
                    elif tag == "cn_t_s_d":
                        hit_data[prefix + (int(node.get("val", "0")),)] = int(node.get("data", "0"))
                        return
                    elif tag == "cn_t_m_d":
                        values = [int(value) for value in node.get("val", "").split()]
                        counts = [int(value) for value in node.get("data", "").split()]
                        for index, value in enumerate(values):
                            hit_data[prefix + (value,)] = counts[index] if index < len(counts) else 0
                        return
                    for child in list(node):
                        if child.tag in {"cn_nt_s", "cn_nt_r", "cn_t_s_d", "cn_t_m_d"}:
                            walk(child, prefix)

                covered = cc.find("covered_auto_crosses")
                if covered is not None:
                    for child in list(covered):
                        walk(child)

                for name, count in named_bins:
                    result[f"{canonical_group}||cross||{cc_name}||name:{name}||0"] = count
                for ordinal, combo in enumerate(auto_combinations):
                    labels = [cp_by_id[ref][index] for ref, index in zip(refs, combo)]
                    count = hit_data.get(tuple(combo), 0)
                    key = f"{canonical_group}||cross||{cc_name}||name:{'X'.join(labels)}||0"
                    result[key] = count
    return result


class StableCoverageSchema:
    def __init__(self, converter, canonical_report: Path, expected_bin_names=None):
        self.converter = converter
        self.canonical_report = Path(canonical_report)
        self.expected_map = converter.expected_map_from_report(self.canonical_report)
        self.expected_count = sum(self.expected_map.values())
        if not self.expected_map or self.expected_count <= 0:
            raise ValueError("canonical report has no detailed bin schema")
        self.expected_bin_names = set(expected_bin_names) if expected_bin_names is not None else None

    def parse(self, report_dir: Path, vdb: Path) -> dict[str, int]:
        xml_paths = sorted(Path(vdb).glob("snps/coverage/db/testdata/*/testbench.cumulative.xml"))
        if len(xml_paths) != 1:
            raise ValueError(f"expected one cumulative XML in {vdb}, found {len(xml_paths)}")
        xml_path = xml_paths[0]
        auto_counts = self.converter.parse_auto_variable_counts(
            Path(report_dir), self.expected_map, xml_path
        )
        counts = self.converter.parse_cumulative_xml(
            xml_path, self.expected_map, auto_counts
        )
        counts = {key: value for key, value in counts.items() if key.split("||")[1] != "cross"}
        counts.update(_cross_counts_from_xml(self.converter, xml_path, self.expected_map))
        if len(counts) != self.expected_count:
            raise ValueError(
                f"cumulative XML produced {len(counts)} bins, expected {self.expected_count}"
            )
        actual_prefix_counts = {}
        for key in counts:
            parts = key.split("||")
            if len(parts) != 5:
                raise ValueError(f"invalid stable bin identity: {key!r}")
            prefix = tuple(parts[:3])
            actual_prefix_counts[prefix] = actual_prefix_counts.get(prefix, 0) + 1
        if actual_prefix_counts != self.expected_map:
            missing = set(self.expected_map.items()) - set(actual_prefix_counts.items())
            extra = set(actual_prefix_counts.items()) - set(self.expected_map.items())
            raise ValueError(
                f"cumulative XML prefix schema differs: missing={list(missing)[:3]} "
                f"extra={list(extra)[:3]}"
            )
        if self.expected_bin_names is not None and set(counts) != self.expected_bin_names:
            missing = self.expected_bin_names - set(counts)
            extra = set(counts) - self.expected_bin_names
            raise ValueError(
                f"cumulative XML bin identities differ: missing={sorted(missing)[:3]} "
                f"extra={sorted(extra)[:3]}"
            )
        covered, expected = self.converter.parse_group_list_counts(Path(report_dir))
        xml_covered = sum(value > 0 for value in counts.values())
        if expected != self.expected_count or xml_covered != covered:
            xml_by_prefix = Counter()
            for key, value in counts.items():
                if value > 0:
                    xml_by_prefix[tuple(key.split("||")[:3])] += 1
            urg_by_prefix = Counter()
            try:
                for key, value in self.converter.parse_report(Path(report_dir)).items():
                    if value > 0:
                        urg_by_prefix[self.converter.report_prefix(key)] += 1
            except Exception:
                pass
            deltas = {
                "xml_only": [(prefix, xml_by_prefix[prefix], urg_by_prefix[prefix])
                             for prefix in sorted(xml_by_prefix.keys() | urg_by_prefix.keys())
                             if xml_by_prefix[prefix] != urg_by_prefix[prefix]][:8]
            }
            raise ValueError(
                "cumulative XML covered-bin total differs from URG detailed groups.txt: "
                f"xml={xml_covered}, urg={covered}, expected={expected}; "
                f"prefix_deltas={deltas['xml_only']}"
            )
        return counts

    def bind_bin_names(self, counts: dict[str, int]) -> None:
        names = set(counts)
        if len(names) != self.expected_count:
            raise ValueError("cannot bind an incomplete or duplicate bin schema")
        if self.expected_bin_names is not None and names != self.expected_bin_names:
            raise ValueError("attempt to replace an already-bound bin schema")
        self.expected_bin_names = names
