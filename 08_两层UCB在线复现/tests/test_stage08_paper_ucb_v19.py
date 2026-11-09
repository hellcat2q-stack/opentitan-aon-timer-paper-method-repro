import sys
import unittest
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import run_vcs_ucb_paper_ucb_v19 as runner


class ConverterStub:
    @staticmethod
    def report_prefix(key):
        return tuple(key.split("||")[:3])


class UrgV19MappingTests(unittest.TestCase):
    def test_automatic_rows_are_matched_by_numeric_range(self):
        prefix = ("covergroup", "variable", "wkup_count_cp")
        frozen = [
            f"covergroup||variable||wkup_count_cp||values:{{ [ 0 : 255 ] }}||{index}"
            for index in range(4)
        ]
        # URG can emit the same rows in a different order after one bin turns
        # from an uncovered range into an explicit covered row.
        reported = {
            "covergroup||variable||wkup_count_cp||values:{ [ 128 : 191 ] }||0": 15,
            "covergroup||variable||wkup_count_cp||values:{ [ 0 : 63 ] }||0": 0,
            "covergroup||variable||wkup_count_cp||values:{ [ 192 : 255 ] }||0": 0,
            "covergroup||variable||wkup_count_cp||values:{ [ 64 : 127 ] }||0": 4,
        }
        mapped = runner.canonicalize_urg_bins(
            ConverterStub, reported, {prefix: frozen}
        )
        self.assertEqual(mapped[frozen[1]], 4)
        self.assertEqual(mapped[frozen[2]], 15)
        self.assertEqual(sum(value > 0 for value in mapped.values()), 2)

    def test_singleton_rows_map_to_frozen_two_value_bins(self):
        prefix = ("covergroup", "variable", "pause_in_sleep_cp")
        frozen = [
            "covergroup||variable||pause_in_sleep_cp||values:{ [ 0 : 1 ] }||0",
            "covergroup||variable||pause_in_sleep_cp||values:{ [ 0 : 1 ] }||1",
        ]
        reported = {
            "covergroup||variable||pause_in_sleep_cp||values:{ [ 1 ] }||0": 7,
            "covergroup||variable||pause_in_sleep_cp||values:{ [ 0 ] }||0": 3,
        }
        mapped = runner.canonicalize_urg_bins(
            ConverterStub, reported, {prefix: frozen}
        )
        self.assertEqual(mapped[frozen[0]], 3)
        self.assertEqual(mapped[frozen[1]], 7)

    def test_named_rows_match_by_stable_label_after_reordering(self):
        prefix = ("covergroup", "variable", "timer_cfg_cp")
        frozen = [
            "covergroup||variable||timer_cfg_cp||name:wkup[53]||0",
            "covergroup||variable||timer_cfg_cp||name:wkup[54]||0",
        ]
        reported = {
            frozen[1]: 0,
            frozen[0]: 15,
        }
        mapped = runner.canonicalize_urg_bins(
            ConverterStub, reported, {prefix: frozen}
        )
        self.assertEqual(mapped[frozen[0]], 15)
        self.assertEqual(mapped[frozen[1]], 0)


if __name__ == "__main__":
    unittest.main()
