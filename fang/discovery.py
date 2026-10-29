from __future__ import annotations

import fnmatch
import importlib.util
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .runner import Command, command_from_argv

PRUNE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    ".idea",
    ".vscode",
    "node_modules",
    "site-packages",
    "dist",
    "build",
    ".eggs",
    ".fang",
}

DEFAULT_EXCLUDES = (
    "tests/*",
    "*/tests/*",
    "test/*",
    "*/test/*",
    "test_*.py",
    "*_test.py",
    "conftest.py",
    "**/migrations/**",
    "**/alembic/versions/**",
)

CONFIG_FILES = (
    "pyproject.toml",
    "pytest.ini",
    "tox.ini",
    "setup.cfg",
    "setup.py",
    ".fang.json",
)


@dataclass
class ScanResult:
    files: List[str] = field(default_factory=list)
    skipped_large: int = 0
    skipped_tests: int = 0
    skipped_excluded: int = 0


def to_posix(path: str) -> str:
    return path.replace(os.sep, "/")


def is_test_path(relative_path: str) -> bool:
    path = to_posix(relative_path)
    parts = path.split("/")
    name = parts[-1]
    if name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py":
        return True
    directories = parts[:-1]
    return "tests" in directories or "test" in directories


def _matches_any(relative_path: str, patterns: Iterable[str]) -> bool:
    path = to_posix(relative_path)
    for pattern in patterns:
        if fnmatch.fnmatch(path, pattern):
            return True
        if pattern.startswith("**/") and fnmatch.fnmatch(path, pattern[3:]):
            return True
    return False


def _walk_python(root: str, start: str) -> Iterable[str]:
    start = os.path.abspath(start)
    if os.path.isfile(start):
        if start.endswith(".py"):
            yield os.path.relpath(start, root)
        return
    for current, directories, filenames in os.walk(start):
        directories[:] = [
            directory
            for directory in directories
            if directory not in PRUNE_DIRS and not directory.startswith(".")
        ]
        for filename in sorted(filenames):
            if filename.endswith(".py"):
                yield os.path.relpath(os.path.join(current, filename), root)


def iter_python_files(
    root: str,
    paths: Sequence[str],
    excludes: Sequence[str] = DEFAULT_EXCLUDES,
    mutate_tests: bool = False,
    max_file_size: int = 512 * 1024,
) -> ScanResult:
    seen = set()
    result = ScanResult()
    for entry in paths or ["."]:
        absolute = entry if os.path.isabs(entry) else os.path.join(root, entry)
        for relative in _walk_python(root, absolute):
            relative = to_posix(relative)
            if relative.startswith("../") or relative in seen:
                continue
            seen.add(relative)
            if not mutate_tests and is_test_path(relative):
                result.skipped_tests += 1
                continue
            if _matches_any(relative, excludes):
                result.skipped_excluded += 1
                continue
            full = os.path.join(root, relative)
            try:
                if os.path.getsize(full) > max_file_size:
                    result.skipped_large += 1
                    continue
            except OSError:
                continue
            result.files.append(relative)
    result.files.sort()
    return result


def iter_test_files(root: str) -> List[str]:
    files: List[str] = []
    for current, directories, filenames in os.walk(root):
        directories[:] = [
            directory
            for directory in directories
            if directory not in PRUNE_DIRS and not directory.startswith(".")
        ]
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            relative = to_posix(os.path.relpath(os.path.join(current, filename), root))
            if is_test_path(relative):
                files.append(relative)
    files.sort()
    return files


def _has_pytest_config(root: str) -> bool:
    if os.path.exists(os.path.join(root, "pytest.ini")) or os.path.exists(os.path.join(root, "conftest.py")):
        return True
    for name in ("pyproject.toml", "tox.ini", "setup.cfg"):
        path = os.path.join(root, name)
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError:
            continue
        if "[tool.pytest" in text or "[pytest]" in text or "[tool:pytest]" in text:
            return True
    return False


def pytest_available() -> bool:
    return importlib.util.find_spec("pytest") is not None


def detect_test_command(
    root: str,
    tests: Optional[Sequence[str]] = None,
    explicit: Optional[str] = None,
) -> Tuple[Command, str]:
    """Pick a reasonable test command for the project."""
    if explicit:
        return Command(argv=[explicit], shell=True, label=explicit), explicit

    candidates = [entry for entry in (tests or []) if os.path.exists(os.path.join(root, entry))]
    if not candidates:
        candidates = ["tests"] if os.path.isdir(os.path.join(root, "tests")) else ["."]

    use_pytest = pytest_available() and (
        _has_pytest_config(root) or os.path.isdir(os.path.join(root, "tests"))
    )
    if use_pytest:
        argv = [
            sys.executable,
            "-m",
            "pytest",
            "-x",
            "-q",
            "--tb=short",
            "--disable-warnings",
            "-p",
            "no:cacheprovider",
        ]
        argv.extend(candidates)
        display = (
            "python -m pytest -x -q --tb=short --disable-warnings"
            " -p no:cacheprovider " + " ".join(candidates)
        )
        return command_from_argv(argv, "pytest", display_text=display), "pytest"

    argv = [sys.executable, "-m", "unittest", "discover", "-s", candidates[0], "-t", ".", "-f"]
    display = "python -m unittest discover -s %s -t . -f" % candidates[0]
    return command_from_argv(argv, "unittest", display_text=display), "unittest"


def describe_project(root: str) -> Dict[str, object]:
    scan = iter_python_files(root, ["."])
    test_files = iter_test_files(root)
    return {
        "root": root,
        "python_files": len(scan.files),
        "test_files": len(test_files),
        "skipped_large": scan.skipped_large,
        "pytest_available": pytest_available(),
        "has_pytest_config": _has_pytest_config(root),
        "candidates": scan.files[:20],
    }
