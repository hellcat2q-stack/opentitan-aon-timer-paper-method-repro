"""Explicit ablations of the frozen V30 author-derived policy; no simulator code."""
from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor, as_completed
import math
import random


METHODS = ("Full", "NoIncrementalRefill", "NoRuntimePenalty", "RandomSelection",
           "SequenceUCBOnly", "ClusterUCBOnly")


def no_runtime_selection(source, namespace, filename):
    """Remove both adaptive weight endpoints without changing measured runtimes."""
    tree = ast.parse(source, filename=filename)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GenericAdaptiveRunner")
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "select_next_sequence")
    expected = {"min_weight": 0.1, "max_weight": 0.5}
    changed = set()
    for node in ast.walk(method):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in expected:
                if not isinstance(node.value, ast.Constant) or node.value.value != expected[name]:
                    raise ValueError(f"Frozen adaptive runtime endpoint changed: {name}")
                node.value = ast.copy_location(ast.Constant(0.0), node.value)
                changed.add(name)
    if changed != set(expected):
        raise ValueError("Both adaptive runtime endpoints must be removed")
    module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    local = {}
    exec(compile(module, filename, "exec"), namespace, local)
    return local[method.name]


def relevant_sequences(runner, category):
    all_ids = runner.test_config.get_all_test_identifiers()
    relevant = [name for name in all_ids if any(
        any(runner.coverage_analyzer.extract_category_vector(vector, category) > 0)
        for vector in runner.historical_data.get(name, []))]
    return relevant or list(all_ids)


def configure_policy(author, method, source_path):
    if method not in METHODS:
        raise ValueError(method)
    base = author.GenericAdaptiveRunner
    runtime_free = (no_runtime_selection(source_path.read_text(encoding="utf-8"),
                                        vars(author), str(source_path))
                    if method == "NoRuntimePenalty" else None)

    class Policy(base):
        def __init__(self, *args, **kwargs):
            self.ablation_method = method
            self.last_ablation_decision = None
            self._cluster_random_stage = False
            super().__init__(*args, **kwargs)
            self.ablation_rng = random.Random(self.seed)
            if method == "NoRuntimePenalty":
                self.runtime_penalty_weight = 0.0

        def select_next_sequence(self, batch_num):
            if method == "RandomSelection":
                # The schedule is addressed by run_id in the adapter. Selection
                # calls, including the final unused reselection, consume no RNG.
                arm = self.test_config.get_all_test_identifiers()[0]
                return self.test_config.parse_test_identifier(arm), arm, None
            if method == "SequenceUCBOnly":
                ids = self.test_config.get_all_test_identifiers()
                total = sum(self.sequence_run_count.values())
                progress = self.get_current_coverage_stats()[0] / 100
                coefficient = 3.0 if progress < 0.3 else 2.0 if progress < 0.7 else 1.0
                runtimes = self.get_average_runtimes()
                maximum = max(runtimes.values(), default=1.0)
                scores = {}
                for arm in ids:
                    gains = self.sequence_gain_history.get(arm, [])
                    observations = self.sequence_run_count[arm]
                    mean = sum(gains) / len(gains) if gains else 0.0
                    bonus = coefficient * math.sqrt(math.log(total + (1 if observations else 2)) /
                                                   (observations + 1e-8 if observations else 1))
                    factor = 1 - (0.1 + 0.4 * progress) * runtimes.get(arm, 0) / maximum if maximum else 1.0
                    scores[arm] = (mean + bonus) * max(0.0, factor)
                arm = max(scores, key=scores.get)
                self.last_ablation_decision = {"rule": "global_sequence_ucb", "scores": scores,
                                               "selected": arm, "successful_online_runs": total}
                return self.test_config.parse_test_identifier(arm), arm, None
            if runtime_free is not None:
                return runtime_free(self, batch_num)
            if method == "ClusterUCBOnly":
                # Keep exactly Full's cluster decision, including its phase and
                # MI rules. Its sequence ranking uses equal scores and has no
                # learning or RNG side effects; then sample the same domain.
                self._cluster_random_stage = True
                try:
                    _, _, target = super().select_next_sequence(batch_num)
                finally:
                    self._cluster_random_stage = False
                if target is None:
                    candidates = list(self.test_config.get_all_test_identifiers())
                else:
                    candidates = relevant_sequences(self, target["name"])
                    if self.is_category_stalled(target["name"]):
                        _, _, _, stats = self.get_current_coverage_stats()
                        backup, _ = self.get_pool_backup_sequences(target["name"], stats,
                            self.test_config.get_all_test_identifiers())
                        candidates += [arm for arm in backup if arm not in candidates]
                arm = self.ablation_rng.choice(candidates)
                self.last_ablation_decision = {"rule": "uniform_target_relevant_sequence",
                                               "candidates": candidates, "selected": arm}
                return self.test_config.parse_test_identifier(arm), arm, target
            return super().select_next_sequence(batch_num)

        def compute_sequence_ucb_score(self, *args, **kwargs):
            if method == "ClusterUCBOnly":
                return 1.0
            return super().compute_sequence_ucb_score(*args, **kwargs)

        def build_candidate_pool_for_category(self, category_name, all_test_ids=None,
                                              top_k=None, log_event="pool_build"):
            if method == "ClusterUCBOnly":
                pool = {arm: 1.0 for arm in relevant_sequences(self, category_name)}
                self.record_cluster_candidate_pool(category_name, pool, event=log_event)
                return pool
            return super().build_candidate_pool_for_category(category_name, all_test_ids, top_k, log_event)

        def run_all_batches(self):
            if method != "NoIncrementalRefill":
                return super().run_all_batches()
            # Freeze every batch's selection before any of its feedback is
            # processed. Completed jobs update the same reward machinery, but
            # no worker is replenished until this entire batch has drained.
            self.setup_result_directory()
            rng = random.Random(self.seed)
            total = self.total_batches * self.batch_size
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                for start in range(0, total, self.batch_size):
                    futures = {}
                    selected, arm, target = self.select_next_sequence(start // self.batch_size)
                    for run_id in range(start, min(start + self.batch_size, total)):
                        seed = rng.randint(1, 2**31 - 1)
                        future, context = self.submit_next_test(executor, run_id, selected, arm, target, seed)
                        futures[future] = context
                        self.active_sequence_count[arm] += 1
                        self.recent_sequence_history.append(arm)
                    for future in as_completed(futures):
                        context = futures[future]
                        self.active_sequence_count[context["test_identifier"]] -= 1
                        result = future.result()
                        info = self.process_completed_run(result, context)
                        self.record_successful_ucb_feedback(result, context, info)
                        self.completed_run_history.append({"test_identifier": context["test_identifier"], "result": result})
                    self.flush_runtime_logs()
            self.generate_final_report()

    author.GenericAdaptiveRunner = Policy
    return author
