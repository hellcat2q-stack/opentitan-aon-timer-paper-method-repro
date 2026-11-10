import gzip
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
from audit_stage08_urg_union_v22 import merged_cross_counts_urg_compat


def test_merged_named_cross_bin_exclusions_are_preserved(tmp_path):
    xml = """<root><cg_src name="intr_test_cg">
      <cp id="0" exprname="cp_a"/><cp id="1" exprname="cp_b"/>
      <cg_covdef name="intr_test_cg">
        <cp type="user" id="0"><bn id="0" name="a[0]"/><bn id="1" name="a[1]"/></cp>
        <cp type="user" id="1"><bn id="0" name="b[0]"/><bn id="1" name="b[1]"/></cp>
        <cc id="0" name="cross_ab"><crosspoints covdefrefs="0 1"/>
          <covered_auto_crosses><cn_nt_s val="1"><cn_t_s_d val="0" data="7"/></cn_nt_s></covered_auto_crosses>
          <named_cross_bins><n_cn_d name="excluded_11" data="0" illegal="1">
            <cn_nt_s val="1"><cn_t_r low="1"/></cn_nt_s>
          </n_cn_d></named_cross_bins>
        </cc>
      </cg_covdef>
    </cg_src></root>"""
    source, normalized = tmp_path / "merged.xml.gz", tmp_path / "normalized.xml.gz"
    with gzip.open(source, "wb") as handle:
        handle.write(xml.encode())
    expected = {
        ("intr_test_cg", "variable", "cp_a"): 2,
        ("intr_test_cg", "variable", "cp_b"): 2,
        ("intr_test_cg", "cross", "cross_ab"): 3,
    }
    counts, renamed, singleton_ranges = merged_cross_counts_urg_compat(None, source, expected, normalized)
    assert renamed == 1
    assert singleton_ranges == 1
    assert len(counts) == 3
    assert counts["intr_test_cg||cross||cross_ab||name:a[1]Xb[0]||0"] == 7
    assert "intr_test_cg||cross||cross_ab||name:a[1]Xb[1]||0" not in counts


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        test_merged_named_cross_bin_exclusions_are_preserved(Path(directory))
    print("URG_MERGED_CROSS_COMPAT_V22_PASS")
