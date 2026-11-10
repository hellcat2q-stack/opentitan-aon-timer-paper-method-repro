"""The Full finalizer must survive shell-to-Python exec and detect real exits."""
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
from finalize_stage08_wkup_v30 import runner_is_active


class RunnerLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.proc = Path(self.temp.name)
        self.process = self.proc / "123"
        self.process.mkdir()
        self.run = Path("/project/runs/full")
        self.launcher = Path("/project/tools/launch.sh")

    def process_state(self, argv, state="S"):
        (self.process / "stat").write_text(f"123 (runner) {state} 1 0 0\n")
        (self.process / "cmdline").write_bytes(b"\0".join(str(a).encode() for a in argv) + b"\0")

    def active(self):
        return runner_is_active(123, self.run, self.launcher, self.proc)

    def test_launcher_exec_and_runner_exit(self):
        self.process_state(["bash", self.launcher, "/project", "full"])
        self.assertTrue(self.active())
        self.process_state(["python", "runner.py", "--result-dir", self.run], "R")
        self.assertTrue(self.active())
        self.process_state([], "Z")
        self.assertFalse(self.active())

    def test_missing_process_is_finished(self):
        self.assertFalse(self.active())

    def test_reused_pid_is_rejected(self):
        self.process_state(["unrelated-process"])
        with self.assertRaisesRegex(RuntimeError, "unexpected process"):
            self.active()

    def test_other_launch_phase_is_rejected(self):
        self.process_state(["bash", self.launcher, "/project", "smoke"])
        with self.assertRaisesRegex(RuntimeError, "unexpected process"):
            self.active()


if __name__ == "__main__":
    unittest.main()
