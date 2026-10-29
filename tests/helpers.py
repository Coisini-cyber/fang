from __future__ import annotations

import os
import subprocess
import sys
from typing import Dict, Iterable

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def write(path: str, content: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def make_project(base: str, files: Dict[str, str]) -> str:
    os.makedirs(base, exist_ok=True)
    for relative, content in files.items():
        write(os.path.join(base, relative), content)
    return base


def unittest_command() -> str:
    return '"%s" -m unittest discover -s tests -t . -f' % sys.executable


def git(root: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    process = subprocess.run(
        ["git", "-C", root] + list(args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and process.returncode != 0:
        raise AssertionError("git %s failed: %s" % (" ".join(args), process.stderr))
    return process


def init_repo(root: str) -> str:
    git(root, "init", "-q")
    git(root, "config", "user.email", "fang@example.com")
    git(root, "config", "user.name", "Fang Tests")
    git(root, "config", "core.autocrlf", "false")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "initial")
    return root


def calc_project(base: str, strong: bool = False) -> str:
    source = '''def add(a, b):
    return a + b


def is_adult(age):
    return age >= 18


def label(age):
    if age >= 18:
        return "adult"
    return "minor"
'''
    if strong:
        tests = '''import unittest

from calc import add, is_adult, label


class TestCalc(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)

    def test_adult_boundary(self):
        self.assertTrue(is_adult(18))
        self.assertFalse(is_adult(17))

    def test_label(self):
        self.assertEqual(label(18), "adult")
        self.assertEqual(label(17), "minor")
'''
    else:
        tests = '''import unittest

from calc import add


class TestCalc(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)
'''
    return make_project(
        base,
        {
            "calc.py": source,
            "tests/__init__.py": "",
            "tests/test_calc.py": tests,
        },
    )


def run_cli(args: Iterable[str], cwd: str = REPO_ROOT, timeout: int = 180):
    return subprocess.run(
        [sys.executable, "-m", "fang"] + list(args),
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=dict(os.environ, PYTHONPATH=REPO_ROOT),
    )
