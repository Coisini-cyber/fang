import sys
import unittest

from fang.runner import (
    Command,
    count_tests,
    has_no_tests,
    parse_killer,
    run_command,
)


class TestRunner(unittest.TestCase):
    def test_run_success(self):
        result = run_command(
            Command(argv=[sys.executable, "-c", "print('hello')"]), cwd=".", timeout=20
        )
        self.assertEqual(result.rc, 0)
        self.assertIn("hello", result.output)
        self.assertFalse(result.timed_out)
        self.assertGreaterEqual(result.duration, 0)

    def test_run_failure(self):
        result = run_command(
            Command(argv=[sys.executable, "-c", "import sys; sys.exit(3)"]),
            cwd=".",
            timeout=20,
        )
        self.assertEqual(result.rc, 3)
        self.assertFalse(result.passed)

    def test_timeout_kills_process(self):
        result = run_command(
            Command(argv=[sys.executable, "-c", "import time; time.sleep(30)"]),
            cwd=".",
            timeout=0.5,
        )
        self.assertTrue(result.timed_out)
        self.assertLess(result.duration, 10)

    def test_timeout_kills_tree(self):
        code = (
            "import subprocess, sys, time;"
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']);"
            "time.sleep(30)"
        )
        result = run_command(Command(argv=[sys.executable, "-c", code]), cwd=".", timeout=0.5)
        self.assertTrue(result.timed_out)

    def test_parse_killer_pytest(self):
        output = "FAILED tests/test_calc.py::test_add - AssertionError\n1 failed"
        self.assertEqual(parse_killer(output), "tests/test_calc.py::test_add")

    def test_parse_killer_unittest(self):
        output = "FAIL: test_add (tests.test_calc.TestCalc)\n"
        self.assertEqual(parse_killer(output), "tests.test_calc.TestCalc.test_add")

    def test_parse_killer_summary_is_not_a_test(self):
        self.assertIsNone(parse_killer("FAILED (errors=1)\n"))

    def test_count_tests(self):
        self.assertEqual(count_tests("Ran 12 tests in 0.1s"), 12)
        self.assertEqual(count_tests("collected 7 items"), 7)
        self.assertEqual(count_tests("7 passed in 0.2s"), 7)
        self.assertEqual(count_tests("no tests ran"), 0)
        self.assertIsNone(count_tests("something else"))

    def test_has_no_tests(self):
        self.assertTrue(has_no_tests("Ran 0 tests in 0.0s"))
        self.assertTrue(has_no_tests("no tests ran in 0.01s"))
        self.assertFalse(has_no_tests("Ran 1 test"))


if __name__ == "__main__":
    unittest.main()
