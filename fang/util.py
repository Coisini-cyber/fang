from __future__ import annotations

import hashlib
import os
import tempfile
from datetime import datetime, timezone
from typing import Optional


def sha1_short(text: str, length: int = 12) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:length]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path: str, text: str) -> None:
    """Write text to path atomically, creating parent directories."""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".fang-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def human_duration(seconds: float) -> str:
    if seconds < 0.95:
        return "%.2fs" % seconds
    if seconds < 60:
        return "%.1fs" % seconds
    minutes, rest = divmod(int(round(seconds)), 60)
    if minutes < 60:
        return "%dm %02ds" % (minutes, rest)
    hours, minutes = divmod(minutes, 60)
    return "%dh %02dm" % (hours, minutes)


def human_int(value: int) -> str:
    return "{:,}".format(value)


def human_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024.0 or unit == "GB":
            return "%.1f %s" % (size, unit)
        size /= 1024.0
    return "%.1f GB" % size


def clip_output(text: str, limit: int = 16000) -> str:
    """Keep the beginning and the end of long test output."""
    if len(text) <= limit:
        return text
    half = limit // 2
    omitted = len(text) - (half * 2)
    return text[:half] + "\n... [%s characters omitted by fang] ...\n" % human_int(omitted) + text[-half:]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def plural(count: int, singular: str, plural_form: Optional[str] = None) -> str:
    word = singular if count == 1 else (plural_form or singular + "s")
    return "%s %s" % (human_int(count), word)


def pct(value: Optional[float], digits: int = 1) -> str:
    if value is None:
        return "n/a"
    return ("%." + str(digits) + "f%%") % value


def truncate(text: str, width: int, ellipsis: str = "...") -> str:
    text = " ".join(str(text).split())
    if len(text) <= width:
        return text
    if width <= len(ellipsis):
        return text[:width]
    return text[: width - len(ellipsis)] + ellipsis


def safe_relpath(path: str, root: str) -> str:
    try:
        rel = os.path.relpath(os.path.abspath(path), os.path.abspath(root))
    except ValueError:
        return path
    return rel.replace(os.sep, "/")
