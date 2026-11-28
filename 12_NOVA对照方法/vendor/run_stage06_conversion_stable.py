#!/usr/bin/env python3
"""Generate VCS/URG bin-by-run coverage data for the accepted Stage 05 runs.

The original Stage 05 runner kept only text URG reports.  This tool regenerates
reports from the server-side VDBs with ``-format both`` and
``-group show_bin_values``, then parses the actual URG HTML into a deterministic
wide CSV.  UVM-failed runs are excluded from the canonical input but remain in
the source manifests and exclusion record.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    from bs4 import BeautifulSoup
except ImportError as exc:  # pragma: no cover - exercised on the server
    raise SystemExit("beautifulsoup4 is required in the project venv") from exc


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def json_load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def numeric(value: str) -> int:
    m = re.search(r"-?\d+", value.replace(",", ""))
    return int(m.group(0)) if m else 0


def expanded_bin_names(display_name: str, number: int) -> list[str]:
    """Expand URG's compressed automatic-bin rows to stable ordinal names."""
    number = max(1, number)
    auto = re.search(r"auto\[(\d+)", display_name, re.IGNORECASE)
    if auto:
        start = int(auto.group(1))
        return [f"auto[{start + offset}]" for offset in range(number)]
    if number == 1:
        return [display_name]
    return [f"{display_name}#{offset}" for offset in range(number)]


def report_group_name(soup: BeautifulSoup) -> str:
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    marker = "Group ::"
    if marker not in title:
        raise ValueError(f"cannot find group name in title {title!r}")
    return title.split(marker, 1)[1].strip()


def section_tables(span: Any) -> list[tuple[str, Any]]:
    """Return bin tables belonging to one Summary for Variable/Cross section."""
    tables: list[tuple[str, Any]] = []
    section = ""
    bin_sections = {"Bins", "Covered bins", "Uncovered bins", "Element holes"}
    for node in span.next_elements:
        if getattr(node, "name", None) == "span" and "repname" in (node.get("class") or []):
            text = node.get_text(" ", strip=True)
            if text.startswith("Summary for Variable ") or text.startswith("Summary for Cross "):
                break
            section = text
        if getattr(node, "name", None) == "table":
            if section in bin_sections:
                tables.append((section, node))
    return tables


def parse_group_page(path: Path) -> dict[str, int]:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    group = report_group_name(soup)
    result: dict[str, int] = {}
    for span in soup.find_all("span", class_="repname"):
        heading = span.get_text(" ", strip=True)
        if heading.startswith("Summary for Variable "):
            kind = "variable"
            item = heading[len("Summary for Variable ") :].strip()
        elif heading.startswith("Summary for Cross "):
            kind = "cross"
            item = heading[len("Summary for Cross ") :].strip()
        else:
            continue
        for section, table in section_tables(span):
            rows = table.find_all("tr")
            if not rows:
                continue
            headers = [cell.get_text(" ", strip=True).upper() for cell in rows[0].find_all(["th", "td"])]
            if kind == "variable":
                if len(headers) < 2 or headers[0] != "NAME" or headers[1] != "COUNT":
                    continue
                count_index = 1
                number_index = headers.index("NUMBER") if "NUMBER" in headers else None
                name_indices = [0]
            else:
                if "COUNT" not in headers:
                    continue
                count_index = headers.index("COUNT")
                number_index = headers.index("NUMBER") if "NUMBER" in headers else None
                name_indices = list(range(count_index))
            for row in rows[1:]:
                cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
                if len(cells) <= count_index or not any(cells[i] for i in name_indices):
                    continue
                if number_index is not None and len(cells) > number_index:
                    number = numeric(cells[number_index])
                else:
                    bin_match = re.search(r"\((\d+)\s+bins?\)", " ".join(cells), re.IGNORECASE)
                    number = int(bin_match.group(1)) if bin_match else 1
                count = numeric(cells[count_index])
                if count < 0:
                    count = 0
                display = "X".join(cells[i] for i in name_indices)
                names = expanded_bin_names(display, number) if kind == "variable" else (
                    [display] if number == 1 else [f"{display}#{offset}" for offset in range(number)]
                )
                automatic = kind == "variable" and re.search(r"auto\[\s*[0-9a-fA-F]+", display)
                if automatic:
                    identities = [f"name:{bin_name}" for bin_name in names]
                elif kind == "variable" and "SUBSUMED VALUES" in headers:
                    values = cells[headers.index("SUBSUMED VALUES")] if len(cells) > headers.index("SUBSUMED VALUES") else "--"
                    identity = f"values:{values}" if values not in {"", "--"} else f"name:{display}"
                    identities = [identity] * len(names)
                else:
                    identities = [f"name:{display}"] * len(names)
                for offset, (bin_name, identity) in enumerate(zip(names, identities)):
                    stable_offset = 0 if automatic else offset
                    key = f"{group}||{kind}||{item}||{identity}||{stable_offset}"
                    # URG normally lists covered automatic bins individually;
                    # if a covered aggregate is emitted, retain its count on
                    # the first ordinal and keep the remaining bins explicit.
                    assigned = count if offset == 0 else 0
                    result[key] = result.get(key, 0) + assigned
    if not result:
        raise ValueError(f"no bin rows parsed from {path}")
    return result


def parse_auto_variable_counts(
    report_dir: Path,
    expected_map: dict[tuple[str, str, str], int],
    xml_path: Path,
) -> dict[tuple[str, str], list[int]]:
    """Recover hit counts for numeric auto bins that VCS XML omits.

    URG prints large auto bins as covered single rows and compressed uncovered
    ranges. Sorting those range rows by their first value and expanding the
    reported NUMBER gives the stable ascending bin ordinal.
    """
    import gzip
    import xml.etree.ElementTree as ET

    root = ET.fromstring(gzip.open(xml_path, "rb").read())
    needed: set[tuple[str, str]] = set()
    for source in root.findall(".//cg_src"):
        source_cp_names = {cp.get("id", ""): cp.get("exprname", "") for cp in source.findall("cp")}
        for cg in source.findall("cg_covdef"):
            group = cg.get("name", "")
            matching_groups = {key[0] for key in expected_map if key[0] == group or key[0].endswith("::" + group)}
            canonical_group = sorted(matching_groups, key=len, reverse=True)[0] if matching_groups else group
            for cp in cg.findall("cp"):
                if cp.get("type") != "auto_c" or cp.findall("bn"):
                    continue
                cp_name = source_cp_names.get(cp.get("id", ""), cp.get("id", ""))
                values = [int(x) for data in cp.findall("data") for x in data.get("vals", "").split()]
                if not values:
                    needed.add((canonical_group, cp_name))
    result: dict[tuple[str, str], list[int]] = {}
    auto_value = re.compile(r"auto\[\s*([0-9a-fA-F]+)(?:\s*:\s*([0-9a-fA-F]+))?\s*\]")

    def as_auto_value(value: str) -> int:
        base = 16 if re.search(r"[a-fA-F]", value) or len(value) >= 16 else 10
        return int(value, base)

    for page in sorted(report_dir.glob("grp*.html"), key=lambda p: int(re.search(r"grp(\d+)", p.name).group(1))):
        soup = BeautifulSoup(page.read_text(encoding="utf-8", errors="replace"), "html.parser")
        group = report_group_name(soup)
        page_segments: dict[tuple[str, str], list[tuple[int, int, int]]] = {}
        seen_tables: set[tuple[str, str, str]] = set()
        for span in soup.find_all("span", class_="repname"):
            heading = span.get_text(" ", strip=True)
            marker = "Summary for Variable "
            if not heading.startswith(marker):
                continue
            item = heading[len(marker) :].strip()
            if (group, item) not in needed:
                continue
            for section, table in section_tables(span):
                if section not in {"Bins", "Covered bins", "Uncovered bins"}:
                    continue
                table_signature = (heading, section, str(table))
                if table_signature in seen_tables:
                    continue
                seen_tables.add(table_signature)
                rows = table.find_all("tr")
                if not rows:
                    continue
                headers = [cell.get_text(" ", strip=True).upper() for cell in rows[0].find_all(["th", "td"])]
                if "NAME" not in headers or "COUNT" not in headers:
                    continue
                name_index = headers.index("NAME")
                count_index = headers.index("COUNT")
                number_index = headers.index("NUMBER") if "NUMBER" in headers else None
                for row in rows[1:]:
                    cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
                    if len(cells) <= max(name_index, count_index):
                        continue
                    display = cells[name_index]
                    match = auto_value.search(display)
                    if not match:
                        continue
                    low = as_auto_value(match.group(1))
                    if number_index is not None and len(cells) > number_index:
                        number = numeric(cells[number_index])
                    else:
                        number_match = re.search(r"\((\d+)\s+bins?\)", " ".join(cells), re.IGNORECASE)
                        number = int(number_match.group(1)) if number_match else 1
                    count = numeric(cells[count_index])
                    if number <= 0:
                        continue
                    page_segments.setdefault((group, item), []).append((low, number, count))

        for (page_group, item), entries in page_segments.items():
            expected = expected_map.get((page_group, "variable", item))
            if expected is None:
                raise ValueError(f"auto-bin report item missing from expected map: {(page_group, item)}")
            entries.sort(key=lambda entry: entry[0])
            if sum(number for _, number, _ in entries) != expected:
                raise ValueError(
                    f"auto-bin row expansion does not match report denominator for {(page_group, item)}: "
                    f"{sum(number for _, number, _ in entries)} != {expected}"
                )
            counts: list[int] = []
            for _, number, count in entries:
                if count and number > 1:
                    raise ValueError(f"URG compressed a covered multi-bin row for {(page_group, item)}")
                counts.append(count)
                counts.extend([0] * (number - 1))
            aggregate = result.setdefault((page_group, item), [0] * expected)
            for index, count in enumerate(counts):
                aggregate[index] += count
    return result


def parse_cumulative_xml(
    path: Path,
    expected_map: dict[tuple[str, str, str], int],
    auto_variable_counts: dict[tuple[str, str], list[int]],
) -> dict[str, int]:
    """Parse stable bin definitions and hit counts from VCS cumulative XML.

    URG compresses large automatic bins differently for each run. The VCS
    cumulative database retains the stable covergroup/cp/bin definition and
    count, so it is the canonical source for feature columns.
    """
    import gzip
    import xml.etree.ElementTree as ET

    root = ET.fromstring(gzip.open(path, "rb").read())
    result: dict[str, int] = {}
    for source in root.findall(".//cg_src"):
      source_name = source.get("name", "")
      source_cp_names = {cp.get("id", ""): cp.get("exprname", "") for cp in source.findall("cp")}
      source_cc_names = {cc.get("id", ""): cc.get("name", "") for cc in source.findall("cc")}
      for cg in source.findall("cg_covdef"):
        group = cg.get("name", "")
        matching_groups = {key[0] for key in expected_map if key[0] == group or key[0].endswith("::" + group)}
        canonical_group = sorted(matching_groups, key=len, reverse=True)[0] if matching_groups else group
        cp_by_id: dict[str, tuple[str, list[tuple[str, int]]]] = {}
        for cp in cg.findall("cp"):
            cp_id = cp.get("id", "")
            cp_name = source_cp_names.get(cp_id, cp_id)
            indexed_bins: list[tuple[int, str, int]] = []
            for bn in cp.findall("bn"):
                if bn.get("excl") == "1" or bn.get("unreachable") == "1":
                    continue
                indexed_bins.append((int(bn.get("id", "0")), bn.get("name", ""), int(bn.get("data", "0"))))
            indexed_bins.sort(key=lambda entry: entry[0])
            bins: list[tuple[str, int]] = [(name, count) for _, name, count in indexed_bins]
            expected = expected_map.get((canonical_group, "variable", cp_name), len(bins))
            if cp.get("type") == "auto_c":
                data_counts: dict[int, int] = {}
                for data in cp.findall("data"):
                    vals = [int(x) for x in data.get("vals", "").split()]
                    indices = [int(x) for x in data.get("index", "").split()]
                    for index_value, count_value in zip(indices, vals):
                        data_counts[index_value] = count_value
                if bins:
                    # Enumerated automatic bins are emitted as named <bn>s;
                    # their data attributes are the per-bin hit counts.
                    pass
                elif data_counts:
                    bins = [(f"auto[{i}]", data_counts.get(i, 0)) for i in range(expected)]
                else:
                    counts = auto_variable_counts.get((canonical_group, cp_name))
                    if counts is None or len(counts) != expected:
                        raise ValueError(f"missing URG auto-bin counts for {(canonical_group, cp_name)}")
                    bins = [(f"auto[{i}]", counts[i]) for i in range(expected)]
            while len(bins) < expected:
                bins.append((f"auto[{len(bins)}]", 0))
            cp_by_id[cp_id] = (cp_name, bins)
            for bin_name, count in bins:
                key = f"{canonical_group}||variable||{cp_name}||name:{bin_name}||0"
                result[key] = count
        for cc in cg.findall("cc"):
            refs = (cc.find("crosspoints").get("covdefrefs", "").split() if cc.find("crosspoints") is not None else [])
            if not refs:
                continue
            hit_data: dict[tuple[int, ...], int] = {}
            def walk(node: Any, prefix: tuple[int, ...] = ()) -> None:
                tag = getattr(node, "tag", "")
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
                if tag == "cn_t_s_d":
                    hit_data[prefix + (int(node.get("val", "0")),)] = int(node.get("data", "0"))
                    return
                if tag == "cn_t_m_d":
                    vals = tuple(int(x) for x in node.get("val", "").split())
                    data = tuple(int(x) for x in node.get("data", "").split())
                    for i, value in enumerate(vals):
                        hit_data[prefix + (value,)] = data[i] if i < len(data) else 0
                    return
                for child in list(node):
                    if child.tag in {"cn_nt_s", "cn_nt_r", "cn_t_s_d", "cn_t_m_d"}:
                        walk(child, prefix)
            covered = cc.find("covered_auto_crosses")
            if covered is not None:
                for child in list(covered):
                    walk(child)
            cc_name = cc.get("name") or source_cc_names.get(cc.get("id", ""), f"cross_{cc.get('id', '')}")
            if not cc_name:
                cc_name = "cross"
            expected = expected_map.get((canonical_group, "cross", cc_name), 0)
            import itertools
            combinations = list(itertools.product(*(range(len(cp_by_id.get(ref, (ref, []))[1])) for ref in refs)))
            if expected:
                combinations = combinations[:expected] + [tuple()] * max(0, expected - len(combinations))
            for ordinal, combination in enumerate(combinations):
                labels: list[str] = []
                for ref, index in zip(refs, combination):
                    bins = cp_by_id.get(ref, (ref, []))[1]
                    labels.append(bins[index][0] if 0 <= index < len(bins) else f"index[{index}]")
                count = hit_data.get(tuple(combination), 0)
                key = f"{canonical_group}||cross||{cc_name}||name:{'X'.join(labels) or f'index[{ordinal}]'}||0"
                result[key] = count
    if not result:
        raise ValueError(f"no coverage bins parsed from cumulative XML {path}")
    return result


def expected_map_from_report(report_dir: Path) -> dict[tuple[str, str, str], int]:
    keys_by_prefix: dict[tuple[str, str, str], set[str]] = {}
    for page in sorted(report_dir.glob("grp*.html"), key=lambda p: int(re.search(r"grp(\d+)", p.name).group(1))):
        for key in parse_group_page(page):
            parts = key.split("||")
            if len(parts) != 5:
                continue
            group, kind, item, _, ordinal = parts
            if ordinal.isdigit():
                prefix = (group, kind, item)
                keys_by_prefix.setdefault(prefix, set()).add(key)
    return {prefix: len(keys) for prefix, keys in keys_by_prefix.items()}


def parse_report(report_dir: Path) -> dict[str, int]:
    pages = sorted(report_dir.glob("grp*.html"), key=lambda p: int(re.search(r"grp(\d+)", p.name).group(1)))
    if not pages:
        raise ValueError(f"no grp*.html pages in {report_dir}")
    bins: dict[str, int] = {}
    for page in pages:
        for key, count in parse_group_page(page).items():
            bins[key] = bins.get(key, 0) + count
    return bins


def report_prefix(key: str) -> tuple[str, str, str]:
    """Return the covergroup/kind/item prefix for one parsed URG bin."""
    parts = key.split("||")
    if len(parts) != 5 or not parts[4].isdigit():
        raise ValueError(f"invalid parsed report key: {key!r}")
    return parts[0], parts[1], parts[2]


def canonicalize_report_bins(
    bins: dict[str, int], canonical_keys: dict[tuple[str, str, str], list[str]]
) -> dict[str, int]:
    """Map one URG report onto the first report's stable row ordering.

    A single URG prefix can contain an aggregate automatic-bin row alongside
    individual covered rows. Their display labels vary, but the row ordering
    and cardinality are stable across the reports generated from this VDB
    family.
    """
    result: dict[str, int] = {}
    grouped: dict[tuple[str, str, str], list[tuple[str, int]]] = {}
    for key, count in bins.items():
        grouped.setdefault(report_prefix(key), []).append((key, count))
    if set(grouped) != set(canonical_keys):
        raise ValueError("report prefix set differs from canonical report")
    for prefix, canonical in canonical_keys.items():
        entries = grouped[prefix]
        if len(entries) != len(canonical):
            raise ValueError(f"report bin count differs for prefix {prefix}: {len(entries)} != {len(canonical)}")
        for canonical_key, (_, count) in zip(canonical, entries):
            result[canonical_key] = count
    return result


def parse_group_list_counts(report_dir: Path) -> tuple[int, int]:
    """Read covered/expected totals by summing the detailed groups.txt rows."""
    lines = (report_dir / "groups.txt").read_text(encoding="utf-8", errors="replace").splitlines()
    marker = next((i for i, line in enumerate(lines) if line.startswith("Total groups in report:")), None)
    if marker is None:
        raise ValueError(f"groups.txt is missing its report group count: {report_dir}")
    header = next((i for i in range(marker + 1, len(lines)) if "INSTANCES WEIGHT GOAL" in lines[i] and line_starts_covered(lines[i])), None)
    if header is None:
        raise ValueError(f"groups.txt is missing its detailed group table: {report_dir}")
    covered = expected = rows = 0
    for line in lines[header + 1 :]:
        match = re.match(r"^\s*(\d+)\s+(\d+)\s+(?:[0-9.]+|--)\s+", line)
        if match:
            covered += int(match.group(1))
            expected += int(match.group(2))
            rows += 1
    if rows == 0:
        raise ValueError(f"groups.txt has no detailed group rows: {report_dir}")
    return covered, expected


def line_starts_covered(line: str) -> bool:
    return line.lstrip().startswith("COVERED")


def parse_dashboard_totals(report_dir: Path) -> tuple[int, int]:
    text = (report_dir / "dashboard.txt").read_text(encoding="utf-8", errors="replace")
    match = re.search(
        r"Total Groups Coverage Summary\s+COVERED EXPECTED SCORE\s+COVERED EXPECTED INST SCORE WEIGHT\s+(\d+)\s+(\d+)",
        text,
        re.DOTALL,
    )
    if not match:
        raise ValueError(f"cannot parse dashboard group totals in {report_dir}")
    return int(match.group(1)), int(match.group(2))


def accepted_runs(manifest: dict[str, Any], root: Path, source: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for run in manifest.get("runs", []):
        ok = bool(run.get("uvm_pass")) and run.get("vcs_return_code") == 0 and run.get("urg_return_code") == 0
        item = dict(run)
        item.update({"source": source, "source_root": str(root)})
        if ok:
            accepted.append(item)
        else:
            excluded.append(item)
    return accepted, excluded


def run_urg(run: dict[str, Any], output_root: Path, urg: str, timeout: int) -> tuple[Path, list[str], float]:
    source_root = Path(run["source_root"])
    vdb = source_root / run["relative_run_dir"] / "coverage" / "default.vdb"
    if not vdb.exists():
        raise FileNotFoundError(vdb)
    report_dir = output_root / f"{run['source']}_g{run['global_run_id']}"
    report_dir.mkdir(parents=True, exist_ok=True)
    command = [
        urg, "-lca", "-full64", "+urg+lic+wait", "-metric", "group", "-show", "tests",
        "-group", "ratio", "-group", "lrm_bin_name", "-group", "instcov_for_score",
        "-group", "maxmissing", "100000", "-group", "show_bin_values", "-dir", str(vdb),
        "-format", "both", "-report", str(report_dir),
    ]
    log = report_dir / "urg.log"
    started = time.monotonic()
    with log.open("w", encoding="utf-8") as handle:
        proc = subprocess.run(command, stdout=handle, stderr=subprocess.STDOUT, check=False, timeout=timeout)
    elapsed = round(time.monotonic() - started, 3)
    (report_dir / "urg_rc").write_text(f"{proc.returncode}\n", encoding="utf-8")
    (report_dir / "urg_command.txt").write_text(" ".join(command) + "\n", encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"URG failed rc={proc.returncode} for {run['source']} global_run_id={run['global_run_id']}")
    return report_dir, command, elapsed


def sanitized_command(command: list[str], report_id: str) -> list[str]:
    result = list(command)
    for flag, replacement in (("-dir", f"<VDB:{report_id}>"), ("-report", f"<REPORT:{report_id}>")):
        if flag in result:
            index = result.index(flag)
            if index + 1 < len(result):
                result[index + 1] = replacement
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original-root", type=Path, required=True)
    parser.add_argument("--original-manifest", type=Path, required=True)
    parser.add_argument("--replay-root", type=Path, required=True)
    parser.add_argument("--replay-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--urg", default="urg")
    parser.add_argument("--urg-timeout-seconds", type=int, default=1800)
    args = parser.parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error("output-dir must be new or empty; existing results are never overwritten")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_root = args.output_dir / "reports"
    report_root.mkdir(exist_ok=True)

    original, original_excluded = accepted_runs(json_load(args.original_manifest), args.original_root, "original")
    replay, replay_excluded = accepted_runs(json_load(args.replay_manifest), args.replay_root, "timeout_fix_replay")
    runs = sorted(original + replay, key=lambda r: (0 if r["source"] == "original" else 1, r["global_run_id"]))
    if len(original) != 35 or len(original_excluded) != 5:
        raise SystemExit(f"original manifest must contain 35 PASS and 5 excluded runs; got {len(original)} and {len(original_excluded)}")
    if not replay:
        raise SystemExit("timeout-fix replay manifest contains no passing runs")
    if len(runs) != len(original) + len(replay):
        raise SystemExit("accepted run count mismatch")
    if len(replay) + len(replay_excluded) != 5:
        raise SystemExit(f"unexpected exclusion counts: original={len(original_excluded)} replay={len(replay_excluded)}")

    records: list[dict[str, Any]] = []
    all_bins: dict[str, None] = {}
    report_counts: dict[str, int] = {}
    detailed_group_totals: dict[str, dict[str, int]] = {}
    commands: list[dict[str, Any]] = []
    canonical_keys: dict[tuple[str, str, str], list[str]] | None = None
    for index, run in enumerate(runs, 1):
        print(f"[{index}/{len(runs)}] URG {run['source']} global={run['global_run_id']}", flush=True)
        report_dir, command, elapsed = run_urg(run, report_root, args.urg, args.urg_timeout_seconds)
        group_covered, group_expected = parse_group_list_counts(report_dir)
        dashboard_covered, dashboard_expected = parse_dashboard_totals(report_dir)
        report_bins = parse_report(report_dir)
        if group_expected != len(report_bins):
            raise ValueError("URG detailed bin parse did not match groups.txt for this report")
        if canonical_keys is None:
            canonical_keys = {}
            for key in report_bins:
                canonical_keys.setdefault(report_prefix(key), []).append(key)
        bins = canonicalize_report_bins(report_bins, canonical_keys)
        source_root = Path(run["source_root"])
        vdb = source_root / run["relative_run_dir"] / "coverage" / "default.vdb"
        xmls = sorted(vdb.glob("snps/coverage/db/testdata/*/testbench.cumulative.xml"))
        if not xmls:
            raise FileNotFoundError(f"no cumulative XML in {vdb}")
        for key in bins:
            all_bins[key] = None
        report_id = f"{run['source']}_g{run['global_run_id']}"
        report_counts[report_id] = len(bins)
        detailed_group_totals[report_id] = {
            "groups_txt_covered": group_covered,
            "groups_txt_expected": group_expected,
            "dashboard_covered": dashboard_covered,
            "dashboard_expected": dashboard_expected,
        }
        row = dict(run)
        row.update({"report_id": report_id, "report_relative_dir": str(report_dir.relative_to(args.output_dir)).replace("\\", "/"), "urg_generation_seconds": elapsed, "bins": bins})
        records.append(row)
        commands.append({"report_id": report_id, "command": sanitized_command(command, report_id), "return_code": 0, "elapsed_seconds": elapsed})

    bin_keys = sorted(all_bins)
    if set(report_counts.values()) != {len(bin_keys)}:
        raise SystemExit(f"per-run URG bin manifests differ: {sorted(set(report_counts.values()))}")
    if len(bin_keys) != 4507:
        raise SystemExit(f"canonical cumulative XML bin manifest expected 4507 bins, got {len(bin_keys)}")
    if len({v["dashboard_expected"] for v in detailed_group_totals.values()}) != 1:
        raise SystemExit("dashboard expected denominator varies between reports")
    rows: list[dict[str, Any]] = []
    for run in records:
        row = {
            "run_id": f"{run['source']}_g{run['global_run_id']}",
            "source": run["source"],
            "global_run_id": run["global_run_id"],
            "test_name": run["test_name"],
            "sequence": run["sequence"],
            "sequence_run_index": run["sequence_run_index"],
            "seed": run["seed"],
            "runtime_cpu_seconds": run.get("simulator_cpu_seconds"),
            "wall_seconds": run.get("wall_seconds"),
            "uvm_pass": run.get("uvm_pass"),
            "vcs_return_code": run.get("vcs_return_code"),
            "urg_return_code": run.get("urg_return_code"),
            "covered_bins": sum(count > 0 for count in run["bins"].values()),
            "report_id": run["report_id"],
        }
        row.update({key: run["bins"].get(key, 0) for key in bin_keys})
        rows.append(row)
    rows.sort(key=lambda row: row["run_id"])
    csv_path = args.output_dir / "coverage_bin_by_run.csv"
    fieldnames = list(rows[0].keys())
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    bin_manifest = {
        "schema": "aon-timer-stage06-bin-manifest-v1",
        "status": "completed",
        "input_rule": "include UVM_PASS with VCS and original URG return code 0; exclude all original UVM failures; include their timeout-fix replay only as separately identified runs",
        "accepted_run_count": len(rows),
        "accepted_original_count": len(original),
        "accepted_replay_count": len(replay),
        "excluded_original_runs": [{k: v for k, v in item.items() if k not in {"source_root"}} for item in original_excluded],
        "excluded_replay_runs": [{k: v for k, v in item.items() if k != "source_root"} for item in replay_excluded],
        "bin_key_format": "group::variable_or_cross::item::bin_name",
        "bin_count": len(bin_keys),
        "bin_count_source": "ordered variable/cross rows from URG grp*.html; stable column labels are frozen from the first report and every generated groups.txt detailed row total is verified",
        "dashboard_expected_groups": next(iter(detailed_group_totals.values()))["dashboard_expected"],
        "dashboard_vs_detailed_bin_count_difference": next(iter(detailed_group_totals.values()))["dashboard_expected"] - len(bin_keys),
        "dashboard_covered_groups_min": min(v["dashboard_covered"] for v in detailed_group_totals.values()),
        "dashboard_covered_groups_max": max(v["dashboard_covered"] for v in detailed_group_totals.values()),
        "detailed_groups_txt_covered_min": min(v["groups_txt_covered"] for v in detailed_group_totals.values()),
        "detailed_groups_txt_covered_max": max(v["groups_txt_covered"] for v in detailed_group_totals.values()),
        "dashboard_detailed_bin_discrepancy": "Dashboard score denominator and covered total are retained separately; they do not equal the sum of detailed bin tables. The canonical feature matrix uses individually parsed coverpoint/cross bins.",
        "per_report_urg_totals": detailed_group_totals,
        "report_bin_counts": report_counts,
        "report_bin_count_min": min(report_counts.values()),
        "report_bin_count_max": max(report_counts.values()),
        "coverage_count_semantics": "integer COUNT parsed from URG covered/uncovered tables; each report row is mapped to the corresponding frozen prefix/order position and missing bins are zero-filled",
        "runtime_semantics": "simulator_cpu_seconds copied from Stage 05 result.json; wall_seconds retained separately",
        "csv": "coverage_bin_by_run.csv",
        "csv_sha256": sha256(csv_path),
        "commands": "urg_commands.json (server-specific paths redacted)",
        "source_manifests": [args.original_manifest.name, args.replay_manifest.name],
    }
    (args.output_dir / "bin_manifest.json").write_text(json.dumps(bin_manifest, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "urg_commands.json").write_text(json.dumps(commands, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "conversion_sha256.txt").write_text(
        "coverage_bin_by_run.csv  " + sha256(csv_path) + "\n" +
        "bin_manifest.json  " + sha256(args.output_dir / "bin_manifest.json") + "\n" +
        "urg_commands.json  " + sha256(args.output_dir / "urg_commands.json") + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"accepted_runs": len(rows), "bin_count": len(bin_keys), "csv_sha256": sha256(csv_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
