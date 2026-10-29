import os
import shutil
import sys
import tempfile
import unittest

from fang.discovery import (
    detect_test_command,
    is_test_path,
    iter_python_files,
    iter_test_files,
)
from tests.helpers import REPO_ROOT, make_project, write


class DiscoveryTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="fang-discovery-")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_is_test_path(self):
        self.assertTrue(is_test_path("tests/test_calc.py"))
        self.assertTrue(is_test_path("pkg/tests/helpers.py"))
        self.assertTrue(is_test_path("test_mod.py"))
        self.assertTrue(is_test_path("mod_test.py"))
        self.assertTrue(is_test_path("conftest.py"))
        self.assertFalse(is_test_path("pkg/mod.py"))

    def test_iter_python_files_skips_tests_and_pruned_dirs(self):
        make_project(
            self.root,
            {
                "pkg/mod.py": "x = 1\n",
                "pkg/test_mod.py": "x = 1\n",
                "tests/test_calc.py": "x = 1\n",
                ".venv/lib.py": "x = 1\n",
                "__pycache__/junk.py": "x = 1\n",
            },
        )
        scan = iter_python_files(self.root, ["."])
        self.assertEqual(scan.files, ["pkg/mod.py"])
        self.assertGreater(scan.skipped_tests, 0)

    def test_iter_test_files(self):
        make_project(
            self.root,
            {"pkg/mod.py": "x = 1\n", "tests/test_calc.py": "x = 1\n"},
        )
        self.assertEqual(iter_test_files(self.root), ["tests/test_calc.py"])

    def test_detected_command_display_is_portable(self):
        command, label = detect_test_command(REPO_ROOT)
        self.assertIn(label, ("pytest", "unittest"))
        self.assertNotIn(sys.executable, command.display())
        self.assertTrue(command.display().startswith("python -m "))

    def test_explicit_command_is_used_verbatim(self):
        command, label = detect_test_command(
            self.root, explicit="python -m unittest tests.test_calc"
        )
        self.assertEqual(label, "python -m unittest tests.test_calc")
        self.assertTrue(command.shell)
        self.assertEqual(command.display(), "python -m unittest tests.test_calc")


if __name__ == "__main__":
    unittest.main()
