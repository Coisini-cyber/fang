from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .discovery import DEFAULT_EXCLUDES
from .mutators import DEFAULT_OPERATORS, OPERATOR_LABELS


class ConfigError(Exception):
    pass


@dataclass
class Config:
    root: str = "."
    paths: List[str] = field(default_factory=lambda: ["."])
    tests: List[str] = field(default_factory=list)
    test_command: Optional[str] = None
    exclude: List[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDES))
    operators: List[str] = field(default_factory=lambda: list(DEFAULT_OPERATORS))
    jobs: int = 0
    timeout: Optional[float] = None
    baseline_timeout: Optional[float] = None
    sample: Optional[int] = None
    seed: int = 0
    min_score: Optional[float] = None
    mutate_tests: bool = False
    skip_calls: List[str] = field(default_factory=lambda: ["print"])
    cache: bool = True
    max_file_size: int = 512 * 1024
    report_path: str = ".fang/report.html"
    badge_path: Optional[str] = None
    markdown_path: Optional[str] = None
    json_path: Optional[str] = None
    color: str = "auto"
    ascii_only: bool = False
    verbose: bool = False

    @property
    def config_file(self) -> str:
        return os.path.join(self.root, ".fang.json")


_ALLOWED_KEYS = {
    "paths",
    "tests",
    "test_command",
    "exclude",
    "operators",
    "jobs",
    "timeout",
    "baseline_timeout",
    "sample",
    "seed",
    "min_score",
    "mutate_tests",
    "skip_calls",
    "cache",
    "max_file_size",
    "report",
    "badge",
}


def _expect(value: Any, types, name: str) -> None:
    if not isinstance(value, types):
        raise ConfigError("%s has the wrong type in .fang.json" % name)


def load_config(root: str, path: Optional[str] = None) -> Config:
    config = Config(root=os.path.abspath(root))
    config_path = path or config.config_file
    if not os.path.exists(config_path):
        return config
    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as error:
        raise ConfigError("could not read %s: %s" % (config_path, error))
    if not isinstance(data, dict):
        raise ConfigError("%s must contain a JSON object" % config_path)

    unknown = sorted(set(data) - _ALLOWED_KEYS)
    if unknown:
        raise ConfigError(
            "unknown key(s) in %s: %s" % (config_path, ", ".join(unknown))
        )

    if "paths" in data:
        _expect(data["paths"], (list, str), "paths")
        config.paths = [data["paths"]] if isinstance(data["paths"], str) else list(data["paths"])
    if "tests" in data:
        _expect(data["tests"], (list, str), "tests")
        config.tests = [data["tests"]] if isinstance(data["tests"], str) else list(data["tests"])
    if "test_command" in data:
        _expect(data["test_command"], (str, type(None)), "test_command")
        config.test_command = data["test_command"]
    if "exclude" in data:
        _expect(data["exclude"], list, "exclude")
        config.exclude = [str(item) for item in data["exclude"]]
    if "operators" in data:
        _expect(data["operators"], list, "operators")
        unknown_operators = sorted(set(data["operators"]) - set(OPERATOR_LABELS))
        if unknown_operators:
            raise ConfigError(
                "unknown operator(s): %s (choose from %s)"
                % (", ".join(unknown_operators), ", ".join(sorted(OPERATOR_LABELS)))
            )
        config.operators = list(data["operators"])
    if "jobs" in data:
        _expect(data["jobs"], int, "jobs")
        config.jobs = max(0, int(data["jobs"]))
    if "timeout" in data:
        _expect(data["timeout"], (int, float, type(None)), "timeout")
        config.timeout = None if data["timeout"] is None else float(data["timeout"])
    if "baseline_timeout" in data:
        _expect(data["baseline_timeout"], (int, float, type(None)), "baseline_timeout")
        config.baseline_timeout = (
            None if data["baseline_timeout"] is None else float(data["baseline_timeout"])
        )
    if "sample" in data:
        _expect(data["sample"], (int, type(None)), "sample")
        config.sample = None if data["sample"] is None else max(1, int(data["sample"]))
    if "seed" in data:
        _expect(data["seed"], int, "seed")
        config.seed = int(data["seed"])
    if "min_score" in data:
        _expect(data["min_score"], (int, float, type(None)), "min_score")
        config.min_score = None if data["min_score"] is None else float(data["min_score"])
    if "mutate_tests" in data:
        _expect(data["mutate_tests"], bool, "mutate_tests")
        config.mutate_tests = bool(data["mutate_tests"])
    if "skip_calls" in data:
        _expect(data["skip_calls"], list, "skip_calls")
        config.skip_calls = [str(item) for item in data["skip_calls"]]
    if "cache" in data:
        _expect(data["cache"], bool, "cache")
        config.cache = bool(data["cache"])
    if "max_file_size" in data:
        _expect(data["max_file_size"], int, "max_file_size")
        config.max_file_size = int(data["max_file_size"])
    if "report" in data:
        _expect(data["report"], str, "report")
        config.report_path = data["report"]
    if "badge" in data:
        _expect(data["badge"], (str, type(None)), "badge")
        config.badge_path = data["badge"]
    return config


def template_config() -> Dict[str, Any]:
    return {
        "paths": ["."],
        "tests": [],
        "test_command": None,
        "exclude": list(DEFAULT_EXCLUDES),
        "operators": list(DEFAULT_OPERATORS),
        "jobs": 0,
        "timeout": None,
        "sample": None,
        "min_score": 70,
        "mutate_tests": False,
        "skip_calls": ["print"],
        "cache": True,
        "report": ".fang/report.html",
    }
