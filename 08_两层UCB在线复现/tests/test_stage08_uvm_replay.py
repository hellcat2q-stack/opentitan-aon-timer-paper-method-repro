import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
from verify_stage08_uvm_replay import inspect_log


PASS_LOG = """--- UVM Report Summary ---
UVM_ERROR : 0
UVM_FATAL : 0
TEST PASSED CHECKS
Time: 259085308063 ps
"""


class ReplayLogTests(unittest.TestCase):
    def test_completed_uvm_test(self):
        self.assertEqual(inspect_log(PASS_LOG, 0)["status"], "pass")

    def test_zero_time_successful_process_is_not_a_pass(self):
        log = "ERROR: Script run without dv_root environment variable.\nTime: 0 ps\n"
        result = inspect_log(log, 0)
        self.assertEqual(result["status"], "fail")
        self.assertIn("missing_test_pass_marker", result["errors"])
        self.assertIn("missing_or_zero_simulation_time", result["errors"])

    def test_missing_summary_is_not_a_pass(self):
        self.assertEqual(inspect_log("TEST PASSED CHECKS\nTime: 10 ps\n", 0)["status"], "fail")

    def test_reported_errors_fail_even_if_counts_claim_zero(self):
        self.assertEqual(inspect_log("UVM_ERROR @ 12 ps: assertion\n" + PASS_LOG, 0)["status"], "fail")

    def test_nonzero_count_or_exit_fails(self):
        self.assertEqual(inspect_log(PASS_LOG.replace("UVM_FATAL : 0", "UVM_FATAL : 1"), 0)["status"], "fail")
        self.assertEqual(inspect_log(PASS_LOG, 1)["status"], "fail")


if __name__ == "__main__":
    unittest.main()
