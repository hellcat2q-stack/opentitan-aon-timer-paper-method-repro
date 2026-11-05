import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from aon_timer_coverage_steering import (
    confirmed_in_log,
    map_feature,
    plusargs,
    select_target,
)


class SteeringMappingTest(unittest.TestCase):
    def test_named_wakeup_bin_maps_to_full_width_threshold(self):
        feature = (
            "aon_timer_env_pkg::aon_timer_env_cov::timer_cfg_cg||variable||"
            "wkup_thold_cp||name:wkup[63]||0"
        )
        target = map_feature(feature)
        self.assertEqual(target["field"], "wkup_thold")
        self.assertGreater(target["value"], (1 << 63))

    def test_auto_count_bin_steers_its_threshold(self):
        feature = (
            "aon_timer_env_pkg::aon_timer_env_cov::wake_up_timer_thold_hit_cg||variable||"
            "wkup_count_cp||values:{ [ 64'h0000000000000000 : "
            "64'h007fffffffffffff ] }||0"
        )
        target = map_feature(feature)
        self.assertEqual(target["field"], "wkup_thold")
        self.assertGreater(target["value"], 0)
        self.assertEqual(plusargs({**target, "status": "targeted"})[0], "+aon_steer_field=1")

    def test_wakeup_compressed_ranges_use_the_stable_bin_ordinal(self):
        prefix = (
            "aon_timer_env_pkg::aon_timer_env_cov::wake_up_timer_thold_hit_cg||variable||"
            "wkup_count_cp||values:{ [ 64'h0080000000000000 : 64'hffffffffffffffff ] }||"
        )
        first = map_feature(prefix + "0")
        last = map_feature(prefix + "510")
        self.assertGreater(first["value"], 1 << 55)
        self.assertGreater(last["value"], first["value"])
        self.assertLessEqual(last["value"], (1 << 64) - 1)

    def test_watchdog_count_target_selects_bark_mode(self):
        feature = (
            "aon_timer_env_pkg::aon_timer_env_cov::watchdog_timer_bark_thold_hit_cg||variable||"
            "wdog_count_cp||values:{ [ 0 : 4294967295 ] }||0"
        )
        target = map_feature(feature)
        self.assertEqual(target["field"], "wdog_bark_thold")
        self.assertEqual(target["value"], 8388612)
        self.assertEqual(target["auxiliary"]["field"], "aim_bite")
        self.assertEqual(target["auxiliary"]["value"], 0)

    def test_decimal_watchdog_bin_range_is_mapped(self):
        feature = (
            "aon_timer_env_pkg::aon_timer_env_cov::watchdog_timer_bark_thold_hit_cg||variable||"
            "wdog_count_cp||values:{ [ 0 : 4294967295 ] }||0"
        )
        target = map_feature(feature)
        self.assertEqual(target["field"], "wdog_bark_thold")
        self.assertEqual(target["value"], 8388612)
        self.assertEqual(target["auxiliary"]["value"], 0)

    def test_watchdog_auto_bin_ordinals_select_distinct_values(self):
        prefix = (
            "aon_timer_env_pkg::aon_timer_env_cov::watchdog_timer_bite_thold_hit_cg||variable||"
            "wdog_count_cp||values:{ [ 0 : 4294967295 ] }||"
        )
        low = map_feature(prefix + "0")
        high = map_feature(prefix + "255")
        self.assertLess(low["value"], 1 << 24)
        self.assertGreater(high["value"], 0xFF000000)
        self.assertGreater(high["value"], low["value"])
        self.assertEqual(low["auxiliary"]["value"], 1)

    def test_watchdog_bite_target_selects_bite_mode(self):
        feature = (
            "aon_timer_env_pkg::aon_timer_env_cov::watchdog_timer_bite_thold_hit_cg||variable||"
            "wdog_count_cp||values:{ [ 0 : 4294967295 ] }||255"
        )
        target = map_feature(feature)
        self.assertEqual(target["field"], "wdog_bite_thold")
        self.assertGreater(target["value"], 0xFF000000)
        self.assertEqual(target["auxiliary"]["field"], "aim_bite")
        self.assertEqual(target["auxiliary"]["value"], 1)

    def test_bite_threshold_config_target_enables_bite_mode(self):
        feature = (
            "aon_timer_env_pkg::aon_timer_env_cov::timer_cfg_cg||variable||"
            "bite_thold_cp||name:bite[31]||0"
        )
        target = map_feature(feature)
        self.assertEqual(target["field"], "wdog_bite_thold")
        self.assertEqual(target["auxiliary"]["field"], "aim_bite")
        self.assertEqual(target["auxiliary"]["value"], 1)

    def test_cross_bins_are_not_guessed(self):
        feature = (
            "aon_timer_env_pkg::aon_timer_env_cov::wake_up_timer_thold_hit_cg||cross||"
            "wkup_thold_cpXwkup_int_cp||name:[auto[0:ff]]X[set]||0"
        )
        self.assertIsNone(map_feature(feature))

    def test_applied_marker_must_match_requested_and_actual_values(self):
        feature = (
            "aon_timer_env_pkg::aon_timer_env_cov::timer_cfg_cg||variable||"
            "bark_thold_cp||name:bark[0]||0"
        )
        target = {**map_feature(feature), "status": "targeted"}
        value = target["value"]
        marker = (
            "AON_TIMER_STEERING_APPLIED field=2 "
            f"requested=0x{value:x} actual=0x{value:x} "
            "aux_field=0 aux_requested=0x0 aux_actual=0x0"
        )
        self.assertTrue(confirmed_in_log(target, marker))
        self.assertFalse(confirmed_in_log(target, marker.replace("actual=", "actual=1")))

    def test_jump_counter_constraint_is_safe_at_full_width_maxima(self):
        patch = Path(__file__).resolve().parents[1] / "tools" / "aon_timer_jump_counter_fix.patch"
        text = patch.read_text()
        added = "\n".join(line[1:] for line in text.splitlines()
                           if line.startswith("+") and not line.startswith("+++"))
        self.assertIn("if (wkup_thold == 0) wkup_count == 0;", text)
        self.assertIn("wkup_count inside {[wkup_thold-wkup_count_gap:wkup_thold]};", text)
        self.assertIn("wdog_count inside {[wdog_bite_thold-wdog_count_gap:wdog_bite_thold]};", text)
        self.assertNotIn("wkup_thold+10", added)
        self.assertNotIn("wdog_bite_thold+10", added)

    def test_unsteered_sequences_keep_small_reachable_thresholds(self):
        patch = Path(__file__).resolve().parents[1] / "tools" / "aon_timer_base_safe_steering.patch"
        added = "\n".join(line[1:] for line in patch.read_text().splitlines()
                           if line.startswith("+") and not line.startswith("+++"))
        self.assertIn("if (steer_field == 0)", added)
        self.assertIn("wkup_thold inside {[1:10]};", added)
        self.assertIn("wdog_bark_thold inside {[1:10]};", added)
        self.assertIn("wdog_bite_thold inside {[1:10]};", added)

    def test_selection_uses_only_uncovered_compatible_targets(self):
        names = [
            "aon_timer_env_pkg::aon_timer_env_cov::timer_cfg_cg||variable||"
            "prescale_cp||name:prescale[0]||0",
            "aon_timer_env_pkg::aon_timer_env_cov::timer_cfg_cg||variable||"
            "bark_thold_cp||name:bark[0]||0",
        ]
        reserved = {names[0]}
        result = select_target(names, set(), reserved, "aon_timer_jump_vseq", random.Random(3))
        self.assertEqual(result["target_bin"], names[1])
        self.assertEqual(select_target(names[:1], set(), set(), "aon_timer_jump_vseq", random.Random(3))["status"],
                         "no_sequence_compatible_bin")
        self.assertEqual(select_target(names[1:], set(), set(), "aon_timer_smoke_vseq", random.Random(3))["status"],
                         "no_sequence_compatible_bin")


if __name__ == "__main__":
    unittest.main()
