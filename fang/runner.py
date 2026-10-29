from __future__ import annotations

import os
import re
import shlex
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from .util import clip_output


@dataclass(frozen=True)
class Command:
    argv: List[str]
    shell: bool = False
    label: str = ""
    display_text: str = ""

    def display(self) -> str:
        if self.display_text:
            return self.display_text
        if self.shell:
            return self.argv[0]
        try:
            return shlex.join(self.argv)
        except AttributeError:  # pragma: no cover - Python < 3.8
            return " ".join(self.argv)


@dataclass
class RunResult:
    rc: int
    output: str
    duration: float
    timed_out: bool = False

    @property
    def passed(self) -> bool:
        return self.rc == 0 and not self.timed_out


def _kill_tree(process: subprocess.Popen) -> None:
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return
        except Exception:
            pass
    else:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            return
        except Exception:
            pass
    try:
        process.kill()
    except Exception:
        pass


def run_command(
    command: Command,
    cwd: str,
    timeout: Optional[float] = None,
    extra_env: Optional[Dict[str, str]] = None,
) -> RunResult:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
            "FANG": "1",
        }
    )
    if extra_env:
        env.update(extra_env)

    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    else:
        kwargs["start_new_session"] = True

    args = command.argv[0] if command.shell else list(command.argv)
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            args,
            cwd=cwd,
            shell=command.shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            **kwargs
        )
    except OSError as error:
        return RunResult(rc=127, output="failed to start command: %s" % error, duration=0.0)

    timed_out = False
    try:
        output, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_tree(process)
        try:
            output, _ = process.communicate(timeout=15)
        except Exception:
            output = ""
    duration = time.monotonic() - started
    return RunResult(
        rc=-9 if timed_out else int(process.returncode or 0),
        output=clip_output(output or ""),
        duration=duration,
        timed_out=timed_out,
    )


_FAILED_PYTEST = re.compile(r"^FAILED\s+(\S+::\S+)", re.MULTILINE)
_UNITTEST_FAIL = re.compile(r"^(?:FAIL|ERROR):\s+(\w+)\s+\(([^)]+)\)", re.MULTILINE)


def parse_killer(output: str) -> Optional[str]:
    match = _FAILED_PYTEST.search(output)
    if match:
        return match.group(1)
    match = _UNITTEST_FAIL.search(output)
    if match:
        name, location = match.group(1), match.group(2)
        return "%s.%s" % (location, name)
    return None


_RAN = re.compile(r"^Ran\s+(\d+)\s+tests?\b", re.MULTILINE)
_COLLECTED = re.compile(r"collected\s+(\d+)\s+items?", re.IGNORECASE)
_PASSED = re.compile(r"(\d+)\s+passed", re.IGNORECASE)


def count_tests(output: str) -> Optional[int]:
    match = _RAN.search(output)
    if match:
        return int(match.group(1))
    match = _COLLECTED.search(output)
    if match:
        return int(match.group(1))
    match = _PASSED.search(output)
    if match:
        return int(match.group(1))
    if "no tests ran" in output.lower():
        return 0
    return None


def has_no_tests(output: str) -> bool:
    lowered = output.lower()
    return "no tests ran" in lowered or "ran 0 tests" in lowered


def command_from_string(text: str, label: Optional[str] = None) -> Command:
    return Command(argv=[text], shell=True, label=label or text)


def command_from_argv(
    argv: List[str], label: Optional[str] = None, display_text: str = ""
) -> Command:
    return Command(
        argv=list(argv),
        shell=False,
        label=label or " ".join(argv),
        display_text=display_text,
    )
