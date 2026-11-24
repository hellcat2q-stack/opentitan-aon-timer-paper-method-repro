"""Expose and verify the original 39 VDBs in an isolated server checkout.

Only missing directory symlinks are created. No database, result, algorithm or
protocol is modified. The initial manifest determines all expected XML hashes.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ensure_initial_vdb_links(root):
    root = Path(root).resolve()
    initial = root / "runs/stage08_inputs_xml_20261110_v20_retry1/coverage_bin_by_run.csv"
    shared_root = initial.resolve(strict=True).parents[2]
    manifest = json.loads((initial.parent / "input_manifest.json").read_text(encoding="utf-8"))
    expected = {item["report_id"]: item["cumulative_xml_sha256"] for item in manifest["runs"]}
    with initial.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 39, "Expected the frozen 39-run initial corpus"
    sources = {"original": "stage05_initial_corpus_20261101T",
               "timeout_fix_replay": "stage05_timeout_fix_20261101T"}

    def check(base, source):
        checked = []
        for row in rows:
            if row["source"] != source:
                continue
            vdb = base / row["test_name"] / row["sequence_run_index"] / "coverage/default.vdb"
            xml = list(vdb.glob("snps/coverage/db/testdata/*/testbench.cumulative.xml"))
            assert len(xml) == 1, f"Missing or ambiguous initial XML: {row['report_id']}"
            actual = sha(xml[0])
            assert actual == expected[row["report_id"]], f"Initial XML hash differs: {row['report_id']}"
            checked.append({"report_id": row["report_id"], "cumulative_xml_sha256": actual})
        return checked

    # Check the authoritative source before creating any alias.
    verified = []
    for source, name in sources.items():
        verified.extend(check(shared_root / "runs" / name, source))
    assert len(verified) == 39
    links = []
    for source, name in sources.items():
        destination = root / "runs" / name
        target = shared_root / "runs" / name
        created = False
        if not destination.exists() and not destination.is_symlink():
            destination.symlink_to(target, target_is_directory=True)
            created = True
        check(destination, source)
        links.append({"path": "runs/" + name, "created": created,
                      "source": "<INITIAL_CORPUS_ROOT>/runs/" + name})
    return {"status": "pass", "initial_vdb_count": 39, "initial_csv_sha256": sha(initial),
            "input_manifest_sha256": sha(initial.parent / "input_manifest.json"),
            "all_initial_xml_hashes_match_manifest": True, "links": links,
            "verified_initial_xml": verified,
            "changes": "Only missing directory symlinks; existing VDBs and frozen inputs unchanged"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists(), "Preserve earlier audit records"
    record = ensure_initial_vdb_links(args.root)
    record["helper_sha256"] = sha(Path(__file__))
    args.output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in record.items() if k != "verified_initial_xml"}))


if __name__ == "__main__":
    main()
