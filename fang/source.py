from __future__ import annotations

import bisect
from typing import List, Tuple


class SourceError(Exception):
    pass


class SourceFile:
    """A decoded source file with fast, byte-offset-aware position mapping.

    CPython reports ``col_offset`` and ``end_col_offset`` as UTF-8 byte offsets.
    Splicing by character offsets therefore corrupts files containing non-ASCII
    text, so every conversion goes through this class.
    """

    def __init__(self, path: str, text: str) -> None:
        self.path = path
        self.text = text
        self.lines = text.splitlines(keepends=True)
        if not self.lines:
            self.lines = [""]
        self._starts: List[int] = []
        position = 0
        for line in self.lines:
            self._starts.append(position)
            position += len(line)

    def index(self, lineno: int, byte_col: int) -> int:
        if lineno < 1 or lineno > len(self.lines):
            raise SourceError("line %d is outside %s" % (lineno, self.path))
        line = self.lines[lineno - 1]
        raw = line.encode("utf-8")
        prefix = raw[:byte_col]
        try:
            decoded = prefix.decode("utf-8")
        except UnicodeDecodeError:
            decoded = prefix.decode("utf-8", "ignore")
        return self._starts[lineno - 1] + len(decoded)

    def span(self, node) -> Tuple[int, int]:
        return (
            self.index(node.lineno, node.col_offset),
            self.index(node.end_lineno, node.end_col_offset),
        )

    def segment(self, node) -> str:
        start, end = self.span(node)
        return self.text[start:end]

    def position(self, index: int) -> Tuple[int, int]:
        """Return (line, column), both 1-based, for an absolute character index."""
        index = max(0, min(index, len(self.text)))
        row = bisect.bisect_right(self._starts, index) - 1
        return row + 1, index - self._starts[row] + 1

    def line_text(self, lineno: int) -> str:
        if lineno < 1 or lineno > len(self.lines):
            return ""
        return self.lines[lineno - 1].rstrip("\r\n")

    def line_count(self) -> int:
        return len(self.lines)


def read_source(path: str) -> SourceFile:
    try:
        with open(path, "r", encoding="utf-8", newline="") as handle:
            text = handle.read()
    except UnicodeDecodeError:
        with open(path, "r", encoding="latin-1", newline="") as handle:
            text = handle.read()
    return SourceFile(path, text)


def splice(text: str, start: int, end: int, replacement: str) -> str:
    return text[:start] + replacement + text[end:]
