import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from main import format_vector

PROJECT = Path(__file__).resolve().parents[1]


class CommandLineTests(unittest.TestCase):
    def test_cli_saves_only_exercise2_results_from_another_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results"
            process = subprocess.run(
                [sys.executable, str(PROJECT / "main.py"), "--output-dir", str(output)],
                cwd=directory, capture_output=True, text=True, encoding="utf-8", check=False,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertIn("B2:", process.stdout)
            self.assertNotIn("B1:", process.stdout)
            self.assertIn("总体验证: PASS", process.stdout)
            self.assertIn("(0.325000, -0.450000, 0.315000)", process.stdout)
            result = json.loads((output / "exercise2.json").read_text(encoding="utf-8"))
            self.assertEqual(result["exercise"], "B2")
            self.assertTrue(result["validation"]["passed"])
            self.assertEqual(len(result["matrix_path"]), 6)
            self.assertEqual(len(result["quaternion_path"]), 6)
            self.assertEqual(len(result["validation"]["errors"]), 30)
            self.assertGreater(len(str(result["matrix_path"]["tcp_in_base"]["translation_m"][0])), 10)
            self.assertIn("四元数", (output / "exercise2.txt").read_text(encoding="utf-8"))
            self.assertEqual({p.name for p in output.iterdir()}, {"exercise2.txt", "exercise2.json"})

    def test_output_target_that_is_a_file_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "already-a-file"
            target.write_text("keep this file", encoding="utf-8")
            process = subprocess.run(
                [sys.executable, str(PROJECT / "main.py"), "--output-dir", str(target)],
                capture_output=True, text=True, encoding="utf-8", check=False,
            )
            self.assertNotEqual(process.returncode, 0)
            self.assertIn("运行失败", process.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), "keep this file")

    def test_display_rounding_does_not_change_input(self):
        values = (-1e-17, 0.123456789123)
        self.assertEqual(format_vector(values, 6), "(0.000000, 0.123457)")
        self.assertEqual(values[1], 0.123456789123)


if __name__ == "__main__":
    unittest.main()
