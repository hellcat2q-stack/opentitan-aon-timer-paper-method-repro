import sys
import unittest
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import run_vcs_ucb_optimized as runner


class ConverterStub:
    @staticmethod
    def report_prefix(key):
        return tuple(key.split("||")[:3])


class UrgBinMappingTests(unittest.TestCase):
    def setUp(self):
        self.prefix = ("covergroup", "variable", "count_cp")
        self.frozen = [
            f"covergroup||variable||count_cp||values:{{ [ 0 : 4294967295 ] }}||{index}"
            for index in range(256)
        ]
        self.canonical = {self.prefix: self.frozen}

    @staticmethod
    def key(low, high, ordinal, count):
        return (
            f"covergroup||variable||count_cp||values:{{ [ {low} : {high} ] }}||{ordinal}",
            count,
        )

    def test_compressed_urg_rows_map_covered_auto_bin_by_value_range(self):
        target_ordinal = 118
        rows = [self.key(1996488704, 4294967295, index, 0) for index in range(137)]
        rows += [self.key(1979711488, 1996488703, 0, 2)]
        rows += [self.key(0, 1979711487, index, 0) for index in range(118)]

        mapped = runner.canonicalize_urg_bins(ConverterStub, dict(rows), self.canonical)

        self.assertEqual(mapped[self.frozen[target_ordinal]], 2)
        self.assertEqual(sum(value > 0 for value in mapped.values()), 1)
        self.assertEqual(sum(mapped.values()), 2)

    def test_named_rows_keep_existing_mapping_behavior(self):
        prefix = ("covergroup", "variable", "named_cp")
        canonical = {
            prefix: [
                "covergroup||variable||named_cp||name:first||0",
                "covergroup||variable||named_cp||name:second||0",
            ]
        }
        bins = {
            "covergroup||variable||named_cp||name:reported_a||0": 1,
            "covergroup||variable||named_cp||name:reported_b||0": 0,
        }

        mapped = runner.canonicalize_urg_bins(ConverterStub, bins, canonical)

        self.assertEqual(mapped, {canonical[prefix][0]: 1, canonical[prefix][1]: 0})


if __name__ == "__main__":
    unittest.main()
