"""Behavioral tests for ablations; simulations remain the acceptance evidence."""
from collections import defaultdict
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
from stage09_policy import configure_policy, no_runtime_selection, relevant_sequences


class Config:
    def get_all_test_identifiers(self):
        return ["slow", "fast"]

    def parse_test_identifier(self, arm):
        return {"seq": arm, "type": "sequence"}


class Base:
    def __init__(self):
        self.seed = 42
        self.runtime_penalty_weight = .3
        self.test_config = Config()
        self.sequence_run_count = defaultdict(int, slow=1, fast=1)
        self.sequence_gain_history = defaultdict(list, slow=[2], fast=[0])
        self.historical_data = {"slow": [np.array([1, 0])], "fast": [np.array([0, 0])]}
        self.coverage_analyzer = SimpleNamespace(extract_category_vector=lambda v, cat: v)
        self.pools = []

    def select_next_sequence(self, batch):
        self.compute_sequence_ucb_score("slow", "cat", 1, 1)
        return {"seq": "slow"}, "slow", {"name": "cat"}

    def compute_sequence_ucb_score(self, *args, **kwargs):
        raise AssertionError("Sequence UCB must not be reached by cluster-only")

    def is_category_stalled(self, target):
        return False

    def get_current_coverage_stats(self):
        return 50.0, 1, 2, {}

    def get_average_runtimes(self):
        return {"slow": 100.0, "fast": 1.0}

    def record_cluster_candidate_pool(self, name, pool, event):
        self.pools.append(pool)


class AblationTests(unittest.TestCase):
    def policy(self, method):
        author = SimpleNamespace(GenericAdaptiveRunner=Base)
        return configure_policy(author, method, Path("unused")).GenericAdaptiveRunner()

    def test_unknown_method_rejected(self):
        with self.assertRaises(ValueError):
            configure_policy(SimpleNamespace(), "typo", Path("unused"))

    def test_sequence_only_never_uses_cluster_or_base_sequence_rule(self):
        runner = self.policy("SequenceUCBOnly")
        _, arm, target = runner.select_next_sequence(0)
        self.assertIsNone(target)
        self.assertEqual(arm, max(runner.last_ablation_decision["scores"], key=runner.last_ablation_decision["scores"].get))
        self.assertEqual(runner.last_ablation_decision["successful_online_runs"], 2)

    def test_sequence_global_reward_changes_choice(self):
        runner = self.policy("SequenceUCBOnly")
        runner.sequence_gain_history["fast"] = [100]
        self.assertEqual(runner.select_next_sequence(0)[1], "fast")

    def test_cluster_only_never_calls_base_sequence_ucb(self):
        runner = self.policy("ClusterUCBOnly")
        self.assertEqual(runner.select_next_sequence(0)[1], "slow")
        self.assertEqual(runner.build_candidate_pool_for_category("cat"), {"slow": 1.0})

    def test_cluster_cold_start_uses_every_arm(self):
        runner = self.policy("ClusterUCBOnly")
        runner.historical_data = {}
        self.assertEqual(relevant_sequences(runner, "cat"), ["slow", "fast"])
        choices = [runner.select_next_sequence(0)[1] for _ in range(30)]
        self.assertEqual(set(choices), {"slow", "fast"})

    def test_random_selection_calls_do_not_consume_schedule_rng(self):
        runner = self.policy("RandomSelection")
        original = runner.ablation_rng.getstate()
        for _ in range(12):
            self.assertIsNone(runner.select_next_sequence(0)[2])
        self.assertEqual(original, runner.ablation_rng.getstate())

    def test_runtime_penalty_endpoints_are_both_disabled(self):
        source = '''class GenericAdaptiveRunner:
    def select_next_sequence(self, batch):
        min_weight = 0.1
        max_weight = 0.5
        return (min_weight + (max_weight-min_weight)*0.8, self.actual_cpu)
'''
        method = no_runtime_selection(source, {}, "fixture.py")
        runner = SimpleNamespace(actual_cpu=123.45)
        self.assertEqual(method(runner, 0), (0.0, 123.45))
        with self.assertRaises(ValueError):
            no_runtime_selection(source.replace("max_weight = 0.5", "max_weight = 0.8"), {}, "fixture.py")

    def test_no_refill_barrier_defers_second_batch_until_first_feedback(self):
        author = SimpleNamespace(GenericAdaptiveRunner=Base)
        policy = configure_policy(author, "NoIncrementalRefill", Path("unused")).GenericAdaptiveRunner

        class Runner(policy):
            def __init__(self):
                super().__init__()
                self.batch_size = self.max_workers = 2
                self.total_batches = 2
                self.active_sequence_count = defaultdict(int)
                self.recent_sequence_history = []
                self.completed_run_history = []
                self.done = []
                self.observed_at_submit = []
                self.first_batch_received = threading.Event()

            def setup_result_directory(self):
                pass

            def select_next_sequence(self, batch):
                return {}, "slow", None

            def submit_next_test(self, executor, run_id, config, arm, target, seed):
                self.observed_at_submit.append((run_id, len(self.done)))
                def task():
                    if run_id == 0:
                        self.first_batch_received.wait(5)
                    return {"run_id": run_id, "status": "success"}
                return executor.submit(task), {"test_identifier": arm, "run_id": run_id}

            def process_completed_run(self, result, context):
                self.done.append(result["run_id"])
                if result["run_id"] == 1:
                    self.first_batch_received.set()
                return {}

            def record_successful_ucb_feedback(self, *args):
                pass

            def flush_runtime_logs(self):
                pass

            def generate_final_report(self):
                pass

        runner = Runner()
        runner.run_all_batches()
        self.assertEqual(runner.observed_at_submit, [(0, 0), (1, 0), (2, 2), (3, 2)])
        self.assertEqual(sorted(runner.done), [0, 1, 2, 3])


if __name__ == "__main__":
    unittest.main()
