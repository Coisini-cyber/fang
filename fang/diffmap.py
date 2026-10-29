from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set

from .discovery import to_posix

HUNK = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class DiffError(Exception):
    pass


@dataclass
class DiffInfo:
    base: str
    head: Optional[str]
    files: Dict[str, Set[int]] = field(default_factory=dict)
    deleted: List[str] = field(default_factory=list)
    untracked: List[str] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0

    @property
    def changed_files(self) -> int:
        return len(self.files)

    @property
    def changed_lines(self) -> int:
        return sum(len(lines) for lines in self.files.values())


def _git(root: str, arguments: Sequence[str]) -> str:
    command = ["git", "-C", root, "-c", "core.quotepath=false"] + list(arguments)
    try:
        process = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except OSError as error:
        raise DiffError("git is not available: %s" % error)
    except subprocess.TimeoutExpired:
        raise DiffError("git command timed out")
    if process.returncode != 0:
        message = (process.stderr or process.stdout or "").strip()
        raise DiffError(message or "git command failed: %s" % " ".join(command))
    return process.stdout


def git_toplevel(root: str) -> Optional[str]:
    try:
        return _git(root, ["rev-parse", "--show-toplevel"]).strip() or None
    except DiffError:
        return None


def git_head(root: str) -> Optional[str]:
    try:
        return _git(root, ["rev-parse", "--short", "HEAD"]).strip() or None
    except DiffError:
        return None


def _unquote(path: str) -> str:
    path = path.strip()
    if len(path) >= 2 and path[0] == '"' and path[-1] == '"':
        inner = path[1:-1]
        return inner.replace('\\"', '"').replace("\\\\", "\\")
    return path


def _strip_prefix(path: str, prefix: str) -> str:
    path = to_posix(path)
    if prefix and path.startswith(prefix):
        return path[len(prefix) :]
    return path


def parse_unified_diff(text: str, prefix: str = "") -> DiffInfo:
    info = DiffInfo(base="", head=None)
    old_path: Optional[str] = None
    current: Optional[str] = None
    new_line: Optional[int] = None

    for line in text.splitlines():
        if line.startswith("--- "):
            raw = _unquote(line[4:])
            if raw == "/dev/null":
                old_path = None
            else:
                if raw.startswith("a/"):
                    raw = raw[2:]
                old_path = _strip_prefix(raw, prefix)
            new_line = None
            continue
        if line.startswith("+++ "):
            raw = _unquote(line[4:])
            if raw == "/dev/null":
                if old_path:
                    info.deleted.append(old_path)
                current = None
            else:
                if raw.startswith("b/"):
                    raw = raw[2:]
                current = _strip_prefix(raw, prefix)
                info.files.setdefault(current, set())
            new_line = None
            continue
        match = HUNK.match(line)
        if match:
            if current:
                new_line = int(match.group(2))
            continue
        if current is None or new_line is None:
            continue
        if line.startswith("+"):
            info.files[current].add(new_line)
            info.additions += 1
            new_line += 1
        elif line.startswith("-"):
            info.deletions += 1
        elif line.startswith(" "):
            new_line += 1
    return info


def _path_in_scope(relative: str, paths: Optional[Sequence[str]]) -> bool:
    if not paths:
        return True
    for entry in paths:
        candidate = to_posix(entry).rstrip("/")
        if candidate.startswith("./"):
            candidate = candidate[2:]
        if candidate in ("", "."):
            return True
        if relative == candidate or relative.startswith(candidate + "/"):
            return True
    return False


def _count_lines(path: str) -> int:
    try:
        with open(path, "r", encoding="utf-8", errors="replace", newline="") as handle:
            return max(1, len(handle.read().splitlines()))
    except OSError:
        return 1


def changed_lines(
    root: str,
    base: str = "HEAD",
    staged: bool = False,
    paths: Optional[Sequence[str]] = None,
) -> DiffInfo:
    """Return added line numbers per changed Python file, relative to root."""
    if git_toplevel(root) is None:
        raise DiffError("%s is not inside a git work tree" % root)

    try:
        _git(root, ["rev-parse", "--verify", "%s^{commit}" % base])
    except DiffError:
        raise DiffError("unknown git revision: %s" % base)

    prefix = _git(root, ["rev-parse", "--show-prefix"]).strip()
    arguments = ["diff", "-U0", "--no-color", "--no-ext-diff", "--no-renames"]
    if staged:
        arguments.append("--cached")
    arguments.append(base)
    arguments.append("--")
    arguments.extend(paths or ["."])
    diff_text = _git(root, arguments)

    info = parse_unified_diff(diff_text, prefix=prefix)
    info.base = base
    info.head = git_head(root)

    if not staged:
        try:
            untracked_text = _git(root, ["ls-files", "--others", "--exclude-standard", "--", "."])
        except DiffError:
            untracked_text = ""
        for line in untracked_text.splitlines():
            relative = to_posix(line.strip())
            if not relative.endswith(".py") or not _path_in_scope(relative, paths):
                continue
            info.untracked.append(relative)
            info.files.setdefault(
                relative, set(range(1, _count_lines(os.path.join(root, relative)) + 1))
            )

    info.files = {path: lines for path, lines in info.files.items() if path.endswith(".py")}
    return info
