"""Exercise the exact frozen selector/feedback methods with shared-class tests."""
import ast
from collections import defaultdict
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import random
import sys
from types import SimpleNamespace
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
from stage09_policy import METHODS, configure_policy

ROOT = Path(os.environ.get("STAGE09_REPO_ROOT", Path(__file__).parents[2]))
SOURCE = Path(os.environ.get("STAGE09_AUTHOR_SOURCE", next(ROOT.glob("08_*/algorithm_source/*paper_ucb_v17.py"))))


def exact_classes():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    keep = {"TestConfig": {"get_all_test_identifiers", "parse_test_identifier", "select_random_test"},
            "GenericAdaptiveRunner": {"select_next_sequence", "compute_sequence_ucb_score", "compute_category_gain",
                "record_successful_ucb_feedback", "submit_next_test", "process_completed_run", "get_average_runtimes",
                "is_sequence_repetition_blocked"}}
    classes = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name in keep:
            methods = [m for m in node.body if isinstance(m, ast.FunctionDef) and m.name in keep[node.name]]
            classes.append(ast.ClassDef(name=node.name, bases=[], keywords=[], body=methods, decorator_list=[]))
    namespace = {"np": np, "random": random, "Path": Path}
    exec(compile(ast.fix_missing_locations(ast.Module(body=classes, type_ignores=[])), str(SOURCE), "exec"), namespace)
    return namespace


class ArmIdentityTests(unittest.TestCase):
    def runner(self, method, catalog, selected, target_available=True):
        ns = exact_classes()
        config = ns["TestConfig"]()
        config.test_sequences = [{"name": e["id"], "seq": e["sequence"], "run_options": e["run_options"]}
                                 for e in catalog["tests"]]
        ns = configure_policy(SimpleNamespace(**ns), method, SOURCE)
        runner = object.__new__(ns.GenericAdaptiveRunner)
        runner.test_config = config
        runner.ablation_rng = random.Random(42)
        runner.last_ablation_decision = None
        runner.seed = 42
        runner.sequence_run_count = defaultdict(int)
        runner.sequence_gain_history = defaultdict(list)
        runner.sequence_runtimes = defaultdict(list)
        runner.historical_data = defaultdict(list, {selected: [np.array([1])]})
        runner.sequence_category_gain_history = defaultdict(lambda: defaultdict(list))
        runner.sequence_category_run_count = defaultdict(lambda: defaultdict(int))
        runner.category_gain_history = defaultdict(list)
        runner.category_successful_run_count = defaultdict(int)
        runner.recent_target_category_history = []
        category = {"name": "category_0", "coverage_percent": 10., "covered_bins": 1,
                    "total_bins": 10, "uncovered_bins": 9, "bin_names": ["bin"]}
        runner.get_current_coverage_stats = lambda: (10., 1, 10, {"category_0": category} if target_available else {})
        runner.select_target_category_with_ucb = lambda *a, **k: category if target_available else None
        runner.is_category_stalled = lambda *a: False
        runner.accumulated_coverage = {"bin": 1}
        runner.runtime = 0.
        runner.cleanup_large_run_logs = lambda *a: None
        runner.log_vericov_trace = lambda *a: None
        runner.generate_html_report_for_run = lambda *a: Path("unused/dashboard.html")
        runner.calculate_incremental_info = lambda *a: {"new_bins": 0, "target_category_gain": 0, "weighted_info_gain": 0.}
        runner.update_dynamic_category_entropy_importance = lambda **k: None
        runner.coverage_analyzer = SimpleNamespace(
            extract_category_vector=lambda vector, cat: vector,
            process_single_test_data=lambda path: {"bin": 1, "runtime": 2.5},
            category_mapping={"bin": "category_0"},
            create_full_coverage_vector=lambda counts: np.array([counts.get("bin", 0)]))
        return runner

    def test_affected_selectors_and_feedback_preserve_each_shared_class_arm(self):
        for count in (6, 8):
            catalog = json.loads((ROOT / f"configs/aon_timer_{count}test_catalog.json").read_text())
            for method in ("Full", "NoIncrementalRefill", "NoRuntimePenalty"):
                for entry in catalog["tests"][4:]:
                    with self.subTest(pool=count, method=method, arm=entry["id"]), redirect_stdout(io.StringIO()):
                        r = self.runner(method, catalog, entry["id"])
                        config, arm, target = r.select_next_sequence(0)
                        self.assertEqual(arm, entry["id"])
                        self.assertEqual(config["seq"], "aon_timer_common_vseq")
                        self.assertEqual(config["seq_config"]["run_options"], entry["run_options"])
                        context = {"run_id": 0, "run_dir": Path("unused"), "test_identifier": arm,
                                   "test_config": config, "target_category": target}
                        info = r.process_completed_run({"status": "success"}, context)
                        r.record_successful_ucb_feedback({"status": "success"}, context, info)
                        self.assertEqual(r.sequence_run_count[arm], 1)
                        self.assertEqual(r.sequence_gain_history[arm], [0])
                        self.assertEqual(r.sequence_runtimes[arm], [2.5])
                        self.assertEqual(len(r.historical_data[arm]), 2)
                        self.assertNotIn("aon_timer_common_vseq", r.sequence_run_count)
                        self.assertNotIn("aon_timer_common_vseq", r.historical_data)

    def test_random_fallback_keeps_official_test_identity(self):
        catalog = json.loads((ROOT / "configs/aon_timer_8test_catalog.json").read_text())
        for method in ("Full", "NoIncrementalRefill", "NoRuntimePenalty"):
            with self.subTest(method=method), redirect_stdout(io.StringIO()):
                r = self.runner(method, catalog, "aon_timer_intr_test", target_available=False)
                parsed = r.test_config.parse_test_identifier("aon_timer_intr_test")
                r.test_config.select_random_test = lambda: parsed
                self.assertEqual(r.select_next_sequence(0)[1], "aon_timer_intr_test")

    def test_all_six_methods_return_ids_in_the_catalog(self):
        for count in (6, 8):
            catalog = json.loads((ROOT / f"configs/aon_timer_{count}test_catalog.json").read_text())
            ids = {e["id"] for e in catalog["tests"]}
            for method in METHODS:
                with self.subTest(pool=count, method=method), redirect_stdout(io.StringIO()):
                    r = self.runner(method, catalog, "aon_timer_intr_test")
                    config, arm, _ = r.select_next_sequence(0)
                    self.assertIn(arm, ids)
                    self.assertEqual(arm, config["seq_config"]["name"])


if __name__ == "__main__":
    unittest.main()
