import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

TOOLS = Path(__file__).parents[1] / "tools"
ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(TOOLS))
from test_catalog import entries_by_id, load_catalog, selected_ids
import run_stage09_matrix_v30 as matrix
from run_stage09_6test_matrix_v30 import configure


class SixTestPoolTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog(ROOT / "configs/aon_timer_6test_catalog.json")
        self.parent = load_catalog(ROOT / "configs/aon_timer_8test_catalog.json")

    def test_subset_retains_all_core_tests_and_unchanged_options(self):
        parent = entries_by_id(self.parent)
        self.assertEqual(selected_ids(self.catalog), selected_ids(self.parent)[:6])
        for item in self.catalog["tests"]:
            self.assertEqual(item, parent[item["id"]])
        self.assertEqual(self.catalog["source_revision"], self.parent["source_revision"])

    def test_selected_and_excluded_partition_official_inventory(self):
        inventory = json.loads((ROOT / "04_测试配置与执行入口/evidence/stage04_sequence_inventory.json").read_text(encoding="utf-8"))
        selected = {item["official_test"] for item in self.catalog["tests"]}
        excluded = set(self.catalog["excluded_by_design"])
        self.assertEqual(len(selected), 6)
        self.assertFalse(selected & excluded)
        self.assertEqual(selected | excluded, set(inventory["dvsim_tests"]))

    def test_rejects_undeclared_or_mismatched_pool_sizes(self):
        for count in (None, 8, 5):
            data = copy.deepcopy(self.catalog)
            if count is None:
                data.pop("selected_test_count")
            else:
                data["selected_test_count"] = count
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "catalog.json"
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_catalog(path)

    def test_launcher_keeps_six_and_eight_outputs_separate(self):
        keys = ("WORK_NAME", "RUN_PREFIX", "RUN_DATE", "SELECTED_TEST_COUNT", "CATALOG_PATH", "POOL_LABEL")
        original = {key: getattr(matrix, key) for key in keys}
        try:
            self.assertEqual(matrix.SELECTED_TEST_COUNT, 8)
            configure()
            self.assertEqual(matrix.SELECTED_TEST_COUNT, 6)
            self.assertEqual(matrix.WORK_NAME, "stage09_6test_ablation_20261123")
            self.assertEqual(matrix.RUN_PREFIX, "stage09_6test")
            self.assertEqual(matrix.RUN_DATE, "20261123")
            self.assertEqual(matrix.paths(ROOT)["catalog"], ROOT / "configs/aon_timer_6test_catalog.json")
        finally:
            for key, value in original.items():
                setattr(matrix, key, value)


if __name__ == "__main__":
    unittest.main()
