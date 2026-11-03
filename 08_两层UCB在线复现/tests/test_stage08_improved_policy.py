import importlib.util
import os
import sys
import unittest
from collections import defaultdict
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SOURCE = Path(os.environ.get("STAGE08_IMPROVED_SOURCE", str(
    REPO / "08_两层UCB在线复现" / "algorithm_source" /
    "generic_adaptive_runner_ucb_continuous_refill_norepeat_poolmi_improved.py"
)))
SPEC = importlib.util.spec_from_file_location("stage08_improved_policy", SOURCE)
POLICY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = POLICY
SPEC.loader.exec_module(POLICY)


EXPORT_PATH = Path(os.environ.get(
    "STAGE08_IMPROVED_EXPORT",
    str(SOURCE.parents[1] / "tools" / "export_stage08_improved.py"),
))
EXPORT_SPEC = importlib.util.spec_from_file_location("stage08_improved_export", EXPORT_PATH)
EXPORT = importlib.util.module_from_spec(EXPORT_SPEC)
sys.modules[EXPORT_SPEC.name] = EXPORT
EXPORT_SPEC.loader.exec_module(EXPORT)


class ImprovedPolicyTests(unittest.TestCase):
    def make_runner(self):
        runner = object.__new__(POLICY.GenericAdaptiveRunner)
        runner.sequence_gain_history = defaultdict(list)
        runner.sequence_run_count = defaultdict(int)
        runner.category_gain_history = defaultdict(list)
        runner.sequence_category_gain_history = defaultdict(lambda: defaultdict(list))
        runner.sequence_category_run_count = defaultdict(lambda: defaultdict(int))
        runner.category_successful_run_count = defaultdict(int)
        return runner

    def test_repetition_is_eligible(self):
        runner = self.make_runner()
        self.assertFalse(runner.is_sequence_repetition_blocked("aon_timer_jump_vseq"))
        self.assertFalse(runner.should_refresh_sequence_for_repetition("aon_timer_jump_vseq"))

    def test_reward_uses_online_target_cluster_gains(self):
        runner = self.make_runner()
        runner.sequence_category_gain_history["jump"]["category_7"] = [2, 0, 4]
        self.assertEqual(runner.compute_category_gain("jump", "category_7"), 2.0)
        self.assertEqual(runner.compute_category_gain("jump", "category_8"), 0.0)

    def test_failed_or_unparsed_run_does_not_update_ucb(self):
        runner = self.make_runner()
        context = {"test_identifier": "jump", "target_category": {"name": "category_7"}}
        info = {"new_bins": 3, "target_category_gain": 2, "processed": True}
        self.assertFalse(runner.record_successful_ucb_feedback({"status": "failed"}, context, info))
        self.assertFalse(runner.record_successful_ucb_feedback({"status": "success"}, context, dict(info, processed=False)))
        self.assertEqual(dict(runner.sequence_run_count), {})
        self.assertEqual(dict(runner.category_successful_run_count), {})
        self.assertEqual(list(runner.sequence_gain_history["jump"]), [])

    def test_export_omits_paths_and_raw_error_text(self):
        sanitized = EXPORT.sanitize_run_results([{
            "run_id": 3,
            "status": "failed",
            "sequence": "aon_timer_stress_all_vseq",
            "relative_run_dir": "private/run/3",
            "report_dir": "/server/private/report",
            "error": "tool failed at /server/private/path",
        }])[0]
        self.assertEqual(sanitized["run_id"], 3)
        self.assertNotIn("relative_run_dir", sanitized)
        self.assertNotIn("report_dir", sanitized)
        self.assertNotIn("error", sanitized)
    def test_reselect_after_single_zero_gain_completion(self):
        runner = self.make_runner()
        runner.batch_size = 10
        self.assertTrue(runner.should_trigger_reselection({
            "pending_target_category_gain": 0,
            "pending_weighted_info_gain": 0.0,
            "pending_completed_tests": 1,
        }))
    def test_successful_zero_gain_is_a_valid_observation(self):
        runner = self.make_runner()
        context = {"test_identifier": "jump", "target_category": {"name": "category_7"}}
        self.assertTrue(runner.record_successful_ucb_feedback(
            {"status": "success"}, context,
            {"new_bins": 0, "target_category_gain": 0, "processed": True},
        ))
        self.assertEqual(runner.sequence_run_count["jump"], 1)
        self.assertEqual(runner.sequence_category_run_count["jump"]["category_7"], 1)
        self.assertEqual(runner.category_successful_run_count["category_7"], 1)
        self.assertEqual(runner.compute_category_gain("jump", "category_7"), 0.0)


if __name__ == "__main__":
    unittest.main()