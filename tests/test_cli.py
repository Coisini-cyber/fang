import json
import os
import shutil
import tempfile
import unittest

from tests.helpers import calc_project, git, init_repo, run_cli


class CLITest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="fang-cli-")
        calc_project(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_json_run(self):
        process = run_cli(
            ["run", self.root, "--all", "--json", "--no-report", "--jobs", "1"]
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        data = json.loads(process.stdout)
        self.assertEqual(data["tool"], "fang")
        self.assertEqual(data["mode"], "all")
        self.assertGreater(data["killed"], 0)
        self.assertGreater(data["survived"], 0)
        self.assertGreater(data["score"], 0)

    def test_parallel_run(self):
        process = run_cli(
            ["run", self.root, "--all", "--json", "--no-report", "--jobs", "2"]
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        data = json.loads(process.stdout)
        self.assertGreater(data["killed"], 0)
        self.assertEqual(data["worker_error_count"], 0)

    def test_gate_fails_below_minimum(self):
        process = run_cli(
            ["run", self.root, "--all", "--min-score", "100", "--no-report", "--jobs", "1"]
        )
        self.assertEqual(process.returncode, 1)
        self.assertIn("FAIL", process.stdout)

    def test_gate_passes_at_zero(self):
        process = run_cli(
            ["run", self.root, "--all", "--min-score", "0", "--no-report", "--jobs", "1"]
        )
        self.assertEqual(process.returncode, 0)

    def test_artifacts(self):
        report = os.path.join(self.root, "out", "report.html")
        badge = os.path.join(self.root, "out", "badge.svg")
        markdown = os.path.join(self.root, "out", "comment.md")
        payload = os.path.join(self.root, "out", "report.json")
        process = run_cli(
            [
                "run",
                self.root,
                "--all",
                "--jobs",
                "1",
                "--report",
                report,
                "--badge",
                badge,
                "--markdown",
                markdown,
                "--json-out",
                payload,
                "--quiet",
            ]
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stdout.strip(), "")
        self.assertTrue(os.path.exists(report))
        self.assertTrue(os.path.exists(badge))
        self.assertTrue(os.path.exists(markdown))
        self.assertTrue(os.path.exists(payload))
        with open(report, encoding="utf-8") as handle:
            html = handle.read()
        self.assertIn("<!doctype html>", html)
        self.assertIn("mutation score", html)
        self.assertNotIn("<script src=", html)
        self.assertNotIn("<link", html)
        with open(payload, encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertIn("results", data)

    def test_no_color_has_no_ansi(self):
        process = run_cli(
            ["run", self.root, "--all", "--no-color", "--no-report", "--jobs", "1"]
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertNotIn("\x1b[", process.stdout)

    def test_diff_mode(self):
        init_repo(self.root)
        path = os.path.join(self.root, "calc.py")
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write("\n\ndef mul(a, b):\n    return a * b\n")
        process = run_cli(
            ["run", self.root, "--diff", "HEAD", "--json", "--no-report", "--jobs", "1"]
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        data = json.loads(process.stdout)
        self.assertEqual(data["mode"], "diff")
        self.assertEqual(data["diff_base"], "HEAD")
        self.assertTrue(data["results"])
        for result in data["results"]:
            self.assertGreaterEqual(result["line"], 12)

    def test_auto_diff_mode(self):
        init_repo(self.root)
        path = os.path.join(self.root, "calc.py")
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write("\n\ndef mul(a, b):\n    return a * b\n")
        process = run_cli(
            [
                "run",
                self.root,
                "--json",
                "--no-report",
                "--jobs",
                "1",
                "--test-command",
                "python -m unittest tests.test_calc",
            ]
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        data = json.loads(process.stdout)
        self.assertEqual(data["mode"], "diff")
        self.assertEqual(data["diff_base"], "HEAD")

    def test_unknown_operator(self):
        process = run_cli(
            ["run", self.root, "--all", "--operators", "nope", "--no-report"]
        )
        self.assertEqual(process.returncode, 2)
        self.assertIn("unknown operator", process.stderr)

    def test_init_and_doctor(self):
        init = run_cli(["init", self.root])
        self.assertEqual(init.returncode, 0, init.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.root, ".fang.json")))
        again = run_cli(["init", self.root])
        self.assertEqual(again.returncode, 2)
        doctor = run_cli(["doctor", self.root])
        self.assertEqual(doctor.returncode, 0, doctor.stderr)
        self.assertIn("FANG doctor", doctor.stdout)
        self.assertIn("tests", doctor.stdout)

    def test_missing_path(self):
        process = run_cli(["run", os.path.join(self.root, "missing"), "--all"])
        self.assertEqual(process.returncode, 2)


if __name__ == "__main__":
    unittest.main()
