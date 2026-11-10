from __future__ import annotations

import random
import sys
import gzip
from pathlib import Path
from tempfile import TemporaryDirectory


TOOLS = Path(__file__).parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

import aon_timer_coverage_steering_v20 as steering
from stage08_stable_coverage_v20 import _cross_counts_from_xml


def test_xml_wakeup_auto_bin_uses_stable_ordinal():
    feature = (
        "aon_timer_env_pkg::aon_timer_env_cov::wake_up_timer_thold_hit_cg"
        "||variable||wkup_thold_cp||name:auto[23]||0"
    )
    mapped = steering.map_feature(feature)
    assert mapped is not None
    assert mapped["field"] == "wkup_thold"
    assert mapped["value"] == steering._uniform_unsigned_bin_value(23, 512, 64)


def test_xml_watchdog_count_bin_sets_bite_mode_and_count_margin():
    feature = (
        "aon_timer_env_pkg::aon_timer_env_cov::watchdog_timer_bite_thold_hit_cg"
        "||variable||wdog_count_cp||name:auto[17]||0"
    )
    mapped = steering.map_feature(feature)
    assert mapped is not None
    assert mapped["field"] == "wdog_bite_thold"
    assert mapped["value"] == steering._uniform_unsigned_bin_value(17, 256, 32) + 5
    assert mapped["auxiliary"]["value"] == 1


def test_ordinal_target_is_restricted_to_selected_jump_sequence():
    feature = (
        "aon_timer_env_pkg::aon_timer_env_cov::watchdog_timer_bark_thold_hit_cg"
        "||variable||wdog_thold_cp||name:auto[7]||0"
    )
    target = steering.select_target([feature], set(), set(), "aon_timer_smoke_vseq", random.Random(1))
    assert target["status"] == "no_sequence_compatible_bin"
    target = steering.select_target([feature], set(), set(), "aon_timer_jump_vseq", random.Random(1))
    assert target["status"] == "targeted"
    assert target["target_bin"] == feature


def test_cross_parser_excludes_illegal_tuples_before_applying_bin_limit(tmp_path):
    xml = '''<root><cg_src name="intr_test_cg">
      <cp id="0" exprname="cp_intr"/><cp id="1" exprname="cp_intr_test"/>
      <cp id="2" exprname="cp_intr_en"/><cp id="3" exprname="cp_intr_state"/>
      <cg_covdef name="intr_test_cg">
        <cp type="user" id="0"><bn id="0" name="all_values[0]"/><bn id="1" name="all_values[1]"/></cp>
        <cp type="auto_c" id="1"><data vals="0 0" index="0 1"/></cp>
        <cp type="auto_c" id="2"><data vals="0 0" index="0 1"/></cp>
        <cp type="auto_c" id="3"><data vals="0 0" index="0 1"/></cp>
        <cc id="0" name="intr_test_cg_cc">
          <crosspoints covdefrefs="0 1 2 3"/>
          <covered_auto_crosses><cn_nt_s val="1"><cn_nt_s val="1"><cn_nt_s val="0">
            <cn_t_s_d val="1" data="8"/>
          </cn_nt_s></cn_nt_s></cn_nt_s></covered_auto_crosses>
          <named_cross_bins><n_cn name="test_1_state_0" data="0" illegal="1">
            <cn_nt_r low="0" high="1"><cn_nt_r low="1" high="1">
              <cn_nt_r low="0" high="1"><cn_t_r low="0" high="0"/></cn_nt_r>
            </cn_nt_r></cn_nt_r>
          </n_cn></named_cross_bins>
        </cc>
      </cg_covdef>
    </cg_src></root>'''
    path = tmp_path / "testbench.cumulative.xml"
    with gzip.open(path, "wb") as handle:
        handle.write(xml.encode())
    expected = {
        ("intr_test_cg", "variable", "cp_intr"): 2,
        ("intr_test_cg", "variable", "cp_intr_test"): 2,
        ("intr_test_cg", "variable", "cp_intr_en"): 2,
        ("intr_test_cg", "variable", "cp_intr_state"): 2,
        ("intr_test_cg", "cross", "intr_test_cg_cc"): 12,
    }
    parsed = _cross_counts_from_xml(None, path, expected)
    hit = "intr_test_cg||cross||intr_test_cg_cc||name:all_values[1]Xauto[1]Xauto[0]Xauto[1]||0"
    assert len(parsed) == 12
    assert parsed[hit] == 8


if __name__ == "__main__":
    test_xml_wakeup_auto_bin_uses_stable_ordinal()
    test_xml_watchdog_count_bin_sets_bite_mode_and_count_margin()
    test_ordinal_target_is_restricted_to_selected_jump_sequence()
    with TemporaryDirectory() as temp_dir:
        test_cross_parser_excludes_illegal_tuples_before_applying_bin_limit(Path(temp_dir))
    print("V20_STEERING_TESTS_PASS")
