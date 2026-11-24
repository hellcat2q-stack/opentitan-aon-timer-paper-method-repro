"""Load and validate an explicit AON Timer test catalog."""
from __future__ import annotations

import json
from pathlib import Path


def load_catalog(path: str | Path) -> dict:
    catalog_path = Path(path)
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    tests = catalog.get("tests")
    expected_count = catalog.get("selected_test_count", 8)
    if expected_count not in (6, 8, 17) or not isinstance(tests, list) or len(tests) != expected_count:
        raise ValueError("the selected catalog must match its declared six, eight or seventeen tests")
    ids = [item.get("id") for item in tests]
    if any(not item for item in ids) or len(set(ids)) != len(ids):
        raise ValueError("catalog test ids must be unique and non-empty")
    for item in tests:
        for key in ("official_test", "sequence", "run_options", "timeout_seconds", "role"):
            if key not in item:
                raise ValueError(f"catalog entry {item.get('id')} lacks {key}")
        if any(not isinstance(arg, str) or not arg.startswith("+")
               for arg in item["run_options"]):
            raise ValueError(f"invalid plusarg in catalog entry {item['id']}")
        if item["timeout_seconds"] <= 0:
            raise ValueError(f"invalid timeout for catalog entry {item['id']}")
    return catalog


def entries_by_id(catalog: dict) -> dict[str, dict]:
    return {item["id"]: item for item in catalog["tests"]}


def selected_ids(catalog: dict) -> list[str]:
    return [item["id"] for item in catalog["tests"]]
