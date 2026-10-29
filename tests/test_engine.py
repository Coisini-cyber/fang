import hashlib
import os
import shutil
import tempfile
import unittest

from fang.config import Config
from fang.engine import AnalysisError, RunOptions, analyze
from tests.helpers import calc_project, init_repo, make_project, unittest_command, write


def digest(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


class EngineTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="fang-engine-")
        calc_project(self.root)
        self.config = Config(
            root=self.root,
            paths=["."],
            tests=["tests"],
            test_command=unittest_command(),
            jobs=1,
            cache=False,
            sample=None,
            min_score=None,
        )

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_weak_suite_has_survivors(self):
        report = analyze(self.config)
        self.assertEqual(report.mode, "all")
        self.assertGreater(report.mutants_total, 5)
        self.assertGreater(report.killed, 0)
        self.assertGreater(report.survived, 0)
        self.assertGreater(report.score, 0)
        self.assertLess(report.score, 100)
        self.assertEqual(report.tests_collected, 1)

    def test_source_is_untouched(self):
        source = os.path.join(self.root, "calc.py")
        tests = os.path.join(self.root, "tests", "test_calc.py")
        before = (digest(source), digest(tests))
        analyze(self.config)
        after = (digest(source), digest(tests))
        self.assertEqual(before, after)

    def test_cache_hits_on_second_run(self):
        self.config.cache = True
        first = analyze(self.config)
        second = analyze(self.config)
        self.assertEqual(second.cache_hits, second.mutants_considered)
        self.assertEqual(first.score, second.score)

    def test_strong_suite_scores_higher(self):
        strong_root = tempfile.mkdtemp(prefix="fang-strong-")
        try:
            calc_project(strong_root, strong=True)
            strong_config = Config(
                root=strong_root,
                paths=["."],
                tests=["tests"],
                test_command=unittest_command(),
                jobs=1,
                cache=False,
            )
            weak = analyze(self.config)
            strong = analyze(strong_config)
            self.assertGreater(strong.score, weak.score)
            self.assertGreaterEqual(strong.score, 90)
        finally:
            shutil.rmtree(strong_root, ignore_errors=True)

    def test_sampling_is_deterministic(self):
        self.config.sample = 2
        first = analyze(self.config)
        second = analyze(self.config)
        self.assertTrue(first.sampled)
        self.assertEqual(first.mutants_considered, 2)
        self.assertIsNotNone(first.score_ci)
        self.assertEqual(
            [result.mutant.id for result in first.results],
            [result.mutant.id for result in second.results],
        )

    def test_red_baseline_is_an_error(self):
        write(
            os.path.join(self.root, "tests", "test_calc.py"),
            "import unittest\n\nclass T(unittest.TestCase):\n    def test_bad(self):\n        self.assertEqual(1, 2)\n",
        )
        with self.assertRaises(AnalysisError) as caught:
            analyze(self.config)
        self.assertIn("baseline", str(caught.exception).lower())

    def test_no_tests_is_an_error(self):
        os.unlink(os.path.join(self.root, "tests", "test_calc.py"))
        with self.assertRaises(AnalysisError):
            analyze(self.config)

    def test_line_range(self):
        report = analyze(self.config, RunOptions(lines=(1, 3)))
        self.assertEqual(report.mode, "lines")
        self.assertTrue(report.results)
        for result in report.results:
            self.assertLessEqual(result.mutant.line, 3)

    def test_diff_mode_only_mutates_changed_lines(self):
        init_repo(self.root)
        path = os.path.join(self.root, "calc.py")
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write("\n\ndef mul(a, b):\n    return a * b\n")
        report = analyze(self.config, RunOptions(diff="HEAD"))
        self.assertEqual(report.mode, "diff")
        self.assertEqual(report.diff_base, "HEAD")
        self.assertTrue(report.results)
        for result in report.results:
            self.assertGreaterEqual(result.mutant.line, 12)

    def test_clean_diff_is_empty(self):
        init_repo(self.root)
        report = analyze(self.config, RunOptions(diff="HEAD"))
        self.assertEqual(report.mutants_total, 0)
        self.assertIsNone(report.score)
        self.assertTrue(report.notes)

    def test_notes_include_sampling(self):
        self.config.sample = 1
        report = analyze(self.config)
        self.assertTrue(any("sampled" in note for note in report.notes))


if __name__ == "__main__":
    unittest.main()
