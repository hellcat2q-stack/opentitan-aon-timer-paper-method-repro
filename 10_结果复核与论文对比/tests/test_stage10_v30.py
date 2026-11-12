"""Adversarial checks using the actual accepted Full export as the fixture."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
from verify_stage10_v30 import VerificationError, frozen_inputs, generate, read, verify_run


class ReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        repo = Path(__file__).parents[2]
        stage10 = Path(__file__).parents[1]
        cls.evidence = Path(os.environ.get("AON_STAGE10_TEST_EVIDENCE", str(repo / "09_对照与消融/evidence")))
        cls.initial = Path(os.environ.get("AON_STAGE10_TEST_INITIAL", str(stage10 / "inputs/v30_20261112/coverage_bin_by_run.csv")))
        cls.mapping = Path(os.environ.get("AON_STAGE10_TEST_MAPPING", str(stage10 / "inputs/v30_20261112/bin_to_cluster.csv")))
        cls.prereg_path = Path(os.environ.get("AON_STAGE10_TEST_PREREG", str(repo / "09_对照与消融/preregistration_v30_20261111.json")))
        cls.paper = Path(os.environ.get("AON_STAGE10_TEST_PAPER", str(repo / "01_论文协议与来源/reference_results.csv")))
        cls.inputs = frozen_inputs(cls.initial, cls.mapping)
        cls.prereg = read(cls.prereg_path)
        cls.fixture = cls.evidence / "stage09_v30_Full_full1000_20261111"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / self.fixture.name

    def copy(self):
        shutil.copytree(self.fixture, self.folder)

    def rehash(self):
        (self.folder / "sha256.txt").write_text("".join(
            f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n"
            for p in sorted(self.folder.iterdir()) if p.name != "sha256.txt"), encoding="utf-8")

    def change_json(self, name, change, rehash=True):
        path = self.folder / name
        value = read(path)
        change(value)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        if rehash:
            self.rehash()

    def verify(self):
        return verify_run(self.folder, "Full", self.inputs, self.prereg)

    def test_actual_full_recalculates_coverage_cpu_and_late_gain(self):
        result = verify_run(self.fixture, "Full", self.inputs, self.prereg)
        self.assertEqual((result["completed"], result["failed"], result["covered_bins"]), (1000, 0, 4125))
        self.assertEqual(result["last_100_new_bins"], 56)
        self.assertAlmostEqual(result["simulator_cpu_seconds"], 175218.55)
        self.assertFalse(result["raw_files_rechecked"])

    def test_modified_export_fails_before_trusting_summary(self):
        self.copy()
        self.change_json("summary.json", lambda j: j.update(failed=1), rehash=False)
        with self.assertRaisesRegex(VerificationError, "export hash"):
            self.verify()

    def test_rehashed_wrong_new_bin_reward_is_rejected(self):
        self.copy()
        self.change_json("run_results.json", lambda j: j[0].update(new_bins=j[0]["new_bins"] + 1))
        with self.assertRaisesRegex(VerificationError, "reward"):
            self.verify()

    def test_rehashed_wrong_cpu_is_rejected(self):
        self.copy()
        self.change_json("run_results.json", lambda j: j[0].update(simulator_cpu_seconds=j[0]["simulator_cpu_seconds"] + 1))
        with self.assertRaisesRegex(VerificationError, "CPU event"):
            self.verify()

    def test_rehashed_wrong_vector_is_rejected(self):
        self.copy()
        path = self.folder / "vectors.csv"
        lines = path.read_text(encoding="utf-8").splitlines()
        cells = lines[1].split(",")
        cells[2] = "1" if cells[2] == "0" else "0"
        lines[1] = ",".join(cells)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.rehash()
        with self.assertRaisesRegex(VerificationError, "vector hash"):
            self.verify()

    def test_rehashed_wrong_urg_union_is_rejected(self):
        self.copy()
        self.change_json("union_audit.json", lambda j: j.update(urg_merged_covered_bins=4126))
        with self.assertRaisesRegex(VerificationError, "URG comparison"):
            self.verify()

    def test_rehashed_changed_worker_protocol_is_rejected(self):
        self.copy()
        self.change_json("protocol.json", lambda j: j.update(workers=20))
        with self.assertRaisesRegex(VerificationError, "preregistered controls"):
            self.verify()

    def test_missing_five_methods_stays_partial(self):
        self.copy()
        result = generate(Path(self.temp.name), self.inputs, self.prereg_path, self.paper,
                          Path(self.temp.name) / "review")
        self.assertEqual(result["status"], "partial")
        self.assertFalse(result["complete"])
        self.assertEqual(len(result["missing_methods"]), 5)
        self.assertFalse(result["reviewed_methods"][0]["raw_files_rechecked"])


if __name__ == "__main__":
    unittest.main()
