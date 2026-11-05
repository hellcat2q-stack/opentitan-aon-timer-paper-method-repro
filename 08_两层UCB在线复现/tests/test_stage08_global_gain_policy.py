import importlib.util
import math
import sys
import unittest
from collections import defaultdict
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SOURCE_NAME = (
    "generic_adaptive_runner_ucb_continuous_refill_poolmi_global_gain.py"
)
SOURCE_CANDIDATES = (
    Path(__file__).resolve().parent / "source" / SOURCE_NAME,
    REPO / "08_两层UCB在线复现" / "algorithm_source" / SOURCE_NAME,
)
SOURCE = next((path for path in SOURCE_CANDIDATES if path.is_file()), SOURCE_CANDIDATES[0])
SPEC = importlib.util.spec_from_file_location("stage08_global_gain_policy", SOURCE)
POLICY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = POLICY
SPEC.loader.exec_module(POLICY)


class GlobalGainPolicyTests(unittest.TestCase):
    def make_runner(self):
        runner = object.__new__(POLICY.GenericAdaptiveRunner)
        runner.sequence_gain_history = defaultdict(list)
        runner.sequence_run_count = defaultdict(int)
        runner.category_gain_history = defaultdict(list)
        runner.sequence_category_gain_history = defaultdict(lambda: defaultdict(list))
        runner.sequence_category_run_count = defaultdict(lambda: defaultdict(int))
        runner.category_successful_run_count = defaultdict(int)
        return runner

    def test_global_gain_is_primary_and_target_gain_is_secondary(self):
        runner = self.make_runner()
        runner.sequence_gain_history["jump"] = [0, 8]
        runner.sequence_category_gain_history["jump"]["category_7"] = [0, 2]
        self.assertAlmostEqual(runner.compute_category_gain("jump", "category_7"), 3.4)

    def test_ucb_exploration_uses_global_sequence_observation_count(self):
        runner = self.make_runner()
        runner.sequence_run_count["jump"] = 2
        runner.sequence_gain_history["jump"] = [1, 3]
        runner.sequence_category_run_count["jump"]["category_7"] = 0
        score = runner.compute_sequence_ucb_score("jump", "category_7", 10, 1.0)
        self.assertAlmostEqual(score, 1.6 + (math.log(11) / 2) ** 0.5)

    def test_successful_feedback_updates_global_and_target_statistics(self):
        runner = self.make_runner()
        context = {"test_identifier": "jump", "target_category": {"name": "category_7"}}
        info = {"new_bins": 4, "target_category_gain": 2, "processed": True}
        self.assertTrue(runner.record_successful_ucb_feedback({"status": "success"}, context, info))
        self.assertEqual(runner.sequence_run_count["jump"], 1)
        self.assertEqual(runner.sequence_gain_history["jump"], [4])
        self.assertEqual(runner.sequence_category_run_count["jump"]["category_7"], 1)

    def test_failed_feedback_does_not_advance_ucb_observations(self):
        runner = self.make_runner()
        context = {"test_identifier": "jump", "target_category": {"name": "category_7"}}
        info = {"new_bins": 4, "target_category_gain": 2, "processed": True}
        self.assertFalse(runner.record_successful_ucb_feedback({"status": "failed"}, context, info))
        self.assertEqual(runner.sequence_run_count["jump"], 0)
        self.assertEqual(runner.sequence_gain_history["jump"], [])

    def test_zero_gain_completion_triggers_immediate_rescore(self):
        runner = self.make_runner()
        runner.batch_size = 10
        self.assertTrue(runner.should_trigger_reselection({
            "pending_target_category_gain": 0,
            "pending_weighted_info_gain": 0.0,
            "pending_completed_tests": 1,
        }))
        self.assertFalse(runner.is_sequence_repetition_blocked("aon_timer_jump_vseq"))


if __name__ == "__main__":
    unittest.main()
