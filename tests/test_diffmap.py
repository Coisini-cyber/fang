import os
import shutil
import tempfile
import unittest

from fang.diffmap import DiffError, changed_lines, git_head, parse_unified_diff
from tests.helpers import git, init_repo, make_project, write


class TestParseUnifiedDiff(unittest.TestCase):
    def test_only_added_lines_count(self):
        text = (
            "diff --git a/pkg/mod.py b/pkg/mod.py\n"
            "--- a/pkg/mod.py\n"
            "+++ b/pkg/mod.py\n"
            "@@ -1,3 +1,5 @@\n"
            " one\n"
            "+two\n"
            "+three\n"
            " four\n"
            " five\n"
        )
        info = parse_unified_diff(text)
        self.assertEqual(info.files, {"pkg/mod.py": {2, 3}})
        self.assertEqual(info.additions, 2)
        self.assertEqual(info.deletions, 0)

    def test_prefix(self):
        text = (
            "--- a/sub/mod.py\n"
            "+++ b/sub/mod.py\n"
            "@@ -0,0 +1 @@\n"
            "+x = 1\n"
        )
        info = parse_unified_diff(text, prefix="sub/")
        self.assertEqual(info.files, {"mod.py": {1}})

    def test_replacement(self):
        text = (
            "--- a/a.py\n"
            "+++ b/a.py\n"
            "@@ -2 +2 @@\n"
            "-old = 1\n"
            "+new = 2\n"
        )
        info = parse_unified_diff(text)
        self.assertEqual(info.files, {"a.py": {2}})
        self.assertEqual(info.deletions, 1)
        self.assertEqual(info.additions, 1)

    def test_deleted_file(self):
        text = "--- a/gone.py\n+++ /dev/null\n@@ -1,2 +0,0 @@\n-a = 1\n-b = 2\n"
        info = parse_unified_diff(text)
        self.assertEqual(info.deleted, ["gone.py"])
        self.assertEqual(info.files, {})

    def test_new_file(self):
        text = "--- /dev/null\n+++ b/new.py\n@@ -0,0 +1,2 @@\n+a = 1\n+b = 2\n"
        info = parse_unified_diff(text)
        self.assertEqual(info.files, {"new.py": {1, 2}})


class TestGitIntegration(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="fang-diff-")
        make_project(
            self.root,
            {
                "pkg/__init__.py": "",
                "pkg/mod.py": "def add(a, b):\n    return a + b\n",
                "README.md": "hello\n",
            },
        )
        init_repo(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_working_tree_change(self):
        path = os.path.join(self.root, "pkg", "mod.py")
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write("\n\ndef sub(a, b):\n    return a - b\n")
        info = changed_lines(self.root, "HEAD")
        self.assertIn("pkg/mod.py", info.files)
        self.assertEqual(info.files["pkg/mod.py"], {3, 4, 5, 6})
        self.assertEqual(info.head, git_head(self.root))

    def test_untracked_is_included_but_not_staged(self):
        write(
            os.path.join(self.root, "pkg", "new.py"),
            "def mul(a, b):\n    return a * b\n",
        )
        info = changed_lines(self.root, "HEAD")
        self.assertEqual(info.files.get("pkg/new.py"), {1, 2})
        staged = changed_lines(self.root, "HEAD", staged=True)
        self.assertNotIn("pkg/new.py", staged.files)

    def test_staged_change(self):
        path = os.path.join(self.root, "pkg", "mod.py")
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write("\nX = 1\n")
        git(self.root, "add", "pkg/mod.py")
        info = changed_lines(self.root, "HEAD", staged=True)
        self.assertIn(4, info.files["pkg/mod.py"])

    def test_subdirectory_root(self):
        sub = os.path.join(self.root, "pkg")
        path = os.path.join(sub, "mod.py")
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write("\nY = 2\n")
        info = changed_lines(sub, "HEAD")
        self.assertEqual(info.files, {"mod.py": {3, 4}})

    def test_subdirectory_untracked(self):
        sub = os.path.join(self.root, "pkg")
        write(os.path.join(sub, "fresh.py"), "def mul(a, b):\n    return a * b\n")
        info = changed_lines(sub, "HEAD")
        self.assertEqual(info.files.get("fresh.py"), {1, 2})

    def test_unknown_revision(self):
        with self.assertRaises(DiffError):
            changed_lines(self.root, "does-not-exist")

    def test_not_a_repo(self):
        outside = tempfile.mkdtemp(prefix="fang-norepo-")
        try:
            with self.assertRaises(DiffError):
                changed_lines(outside, "HEAD")
        finally:
            shutil.rmtree(outside, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
