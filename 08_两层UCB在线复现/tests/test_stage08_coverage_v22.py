import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import aon_timer_coverage_steering_v22 as steering

PREFIX = "aon_timer_env_pkg::aon_timer_env_cov::"


def feature(group, cp, label):
    return f"{PREFIX}{group}||variable||{cp}||name:{label}||0"


def test_ordinal_boundaries_and_safe_sequences():
    for group, cp, count, width in (
        ("wake_up_timer_thold_hit_cg", "wkup_thold_cp", 512, 64),
        ("watchdog_timer_bark_thold_hit_cg", "wdog_thold_cp", 256, 32),
        ("watchdog_timer_bite_thold_hit_cg", "wdog_count_cp", 256, 32),
    ):
        for ordinal in (0, count // 2, count - 1):
            name = feature(group, cp, f"auto[{ordinal}]")
            target = steering.map_feature(name)
            assert target is not None
            low, high = ordinal * (1 << width) // count, (ordinal + 1) * (1 << width) // count - 1
            assert low <= target["value"] <= high
            for seq in ("aon_timer_smoke_vseq", "aon_timer_stress_all_vseq", "aon_timer_prescaler_vseq"):
                assert steering.select_target([name], set(), set(), seq, random.Random(42))["status"] == "no_sequence_compatible_bin"
            assert steering.select_target([name], set(), set(), "aon_timer_jump_vseq", random.Random(42))["target_bin"] == name
        assert steering.map_feature(feature(group, cp, f"auto[{count}]")) is None


def test_configuration_targets_and_exclusion():
    names = [feature("timer_cfg_cg", "bark_thold_cp", "bark_0"),
             feature("timer_cfg_cg", "wkup_thold_cp", "wkup[23]")]
    assert steering.map_feature(names[0])["value"] == 0
    choice = steering.select_target(names, {names[0]}, set(), "aon_timer_jump_vseq", random.Random(42))
    assert choice["target_bin"] == names[1]
    assert steering.select_target(names, {names[0]}, {names[1]}, "aon_timer_jump_vseq", random.Random(42))["status"] == "no_uncovered_mappable_bin"
    prescaler = feature("timer_cfg_cg", "prescale_cp", "prescale[7]")
    assert steering.select_target([prescaler], set(), set(), "aon_timer_prescaler_vseq", random.Random(42))["status"] == "targeted"
    assert steering.select_target([prescaler], set(), set(), "aon_timer_jump_vseq", random.Random(42))["status"] == "no_sequence_compatible_bin"
    assert steering.map_feature(names[0].replace("||0", "||1")) is None
    assert steering.map_feature("malformed") is None


def test_actual_configuration_interval_labels():
    for cp, label, low, high in (
        ("bark_thold_cp", "bark[134217728:268435454]", 134217728, 268435454),
        ("bite_thold_cp", "bite[4160749538:4294967295]", 4160749538, 4294967295),
        ("wkup_thold_cp", "wkup[0x2ffffffffffffff5:0x33fffffffffffff3]", 0x2ffffffffffffff5, 0x33fffffffffffff3),
        ("prescale_cp", "prescale[128:254]", 128, 254),
    ):
        name = feature("timer_cfg_cg", cp, label)
        target = steering.map_feature(name)
        assert target is not None and low <= target["value"] <= high
        assert target["range_low"] == low and target["range_high"] == high
    assert steering.map_feature(feature("timer_cfg_cg", "bark_thold_cp", "bark[4294967296:4294967297]")) is None
    assert steering.map_feature(feature("timer_cfg_cg", "bark_thold_cp", "bite[1:100]")) is None
    assert steering.map_feature(feature("timer_cfg_cg", "bark_thold_cp", "bark[2:1]")) is None


if __name__ == "__main__":
    test_ordinal_boundaries_and_safe_sequences()
    test_configuration_targets_and_exclusion()
    test_actual_configuration_interval_labels()
    print("V22_MAPPING_TESTS_PASS")
