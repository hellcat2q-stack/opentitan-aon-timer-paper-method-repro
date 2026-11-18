import json
from pathlib import Path
import sys
import unittest


TOOLS = Path(__file__).parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from test_catalog import entries_by_id, load_catalog, selected_ids


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog_path = Path(__file__).parents[2] / "configs" / "aon_timer_8test_catalog.json"
        self.catalog = load_catalog(self.catalog_path)

    def test_exactly_eight_unique_entries(self):
        ids = selected_ids(self.catalog)
        self.assertEqual(len(ids), 8)
        self.assertEqual(len(set(ids)), 8)
        self.assertEqual(len(entries_by_id(self.catalog)), 8)

    def test_common_sequence_options_are_preserved(self):
        entries = entries_by_id(self.catalog)
        self.assertEqual(entries["aon_timer_intr_test"]["sequence"], "aon_timer_common_vseq")
        self.assertEqual(entries["aon_timer_intr_test"]["run_options"], ["+run_intr_test"])
        self.assertEqual(entries["aon_timer_csr_rw"]["run_options"], ["+en_scb=0", "+csr_rw"])
        self.assertEqual(entries["aon_timer_mem_walk"]["run_options"], ["+en_scb=0", "+csr_mem_walk"])
        self.assertEqual(entries["aon_timer_tl_errors"]["run_options"], ["+run_tl_errors"])

    def test_catalog_is_independent_of_the_official_inventory(self):
        inventory = json.loads((Path(__file__).parents[2] /
                                "04_测试配置与执行入口" / "evidence" /
                                "stage04_sequence_inventory.json").read_text(encoding="utf-8"))
        official = set(inventory["dvsim_tests"])
        selected = {item["official_test"] for item in self.catalog["tests"]}
        self.assertTrue(selected <= official)
        self.assertEqual(len(official), 17)


if __name__ == "__main__":
    unittest.main()
