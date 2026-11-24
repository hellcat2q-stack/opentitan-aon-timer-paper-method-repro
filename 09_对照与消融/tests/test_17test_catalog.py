"""Protect the complete official pool and its distinct shared-class test IDs."""
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(os.environ.get("STAGE09_REPO_ROOT", Path(__file__).parents[2]))
sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
from test_catalog import entries_by_id, load_catalog, selected_ids


class CompleteCatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog(ROOT / "configs/aon_timer_17test_catalog.json")
        self.entries = entries_by_id(self.catalog)

    def test_complete_official_inventory_without_exclusions(self):
        path = next(ROOT.glob("04_*/evidence/stage04_sequence_inventory.json"))
        inventory = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(selected_ids(self.catalog)), 17)
        self.assertEqual(len(set(selected_ids(self.catalog))), 17)
        self.assertEqual({e["official_test"] for e in self.catalog["tests"]}, set(inventory["dvsim_tests"]))
        self.assertEqual(self.catalog["source_revision"], inventory["source_revision"])
        self.assertEqual(self.catalog["excluded_by_design"], [])

    def test_existing_eight_test_definitions_are_preserved(self):
        old = load_catalog(ROOT / "configs/aon_timer_8test_catalog.json")
        self.assertEqual(self.catalog["tests"][:8], old["tests"])

    def test_new_shared_class_tests_keep_official_dispatch_options(self):
        for entry in self.catalog["tests"][4:]:
            self.assertEqual(entry["sequence"], "aon_timer_common_vseq")
            self.assertNotEqual(entry["id"], entry["sequence"])
        self.assertEqual(self.entries["aon_timer_sec_cm"]["run_options"], ["+run_sec_cm_fi", "+en_scb=0"])
        self.assertEqual(self.entries["aon_timer_tl_intg_err"]["run_options"], ["+run_tl_intg_err", "+en_scb=0"])
        reset = self.entries["aon_timer_stress_all_with_rand_reset"]
        self.assertIn("+stress_seq=aon_timer_stress_all_vseq", reset["run_options"])
        self.assertIn("+test_timeout_ns=10000000000", reset["run_options"])
        self.assertEqual(reset["timeout_seconds"], 10800)


if __name__ == "__main__":
    unittest.main()
