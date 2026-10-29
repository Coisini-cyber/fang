from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

STATUSES = ("killed", "survived", "timeout", "error", "worker_error")


@dataclass(frozen=True)
class Mutant:
    """One concrete, syntactically valid single-edit mutation."""

    id: str
    path: str
    start: int
    end: int
    line: int
    col: int
    end_line: int
    end_col: int
    operator: str
    context: str
    original: str
    replacement: str
    expression_before: str
    expression_after: str
    source_line: str
    mutated_line: Optional[str]
    description: str
    hint: str

    @property
    def location(self) -> str:
        return "%s:%d" % (self.path, self.line)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "path": self.path,
            "line": self.line,
            "col": self.col,
            "end_line": self.end_line,
            "end_col": self.end_col,
            "operator": self.operator,
            "context": self.context,
            "original": self.original,
            "replacement": self.replacement,
            "expression_before": self.expression_before,
            "expression_after": self.expression_after,
            "source_line": self.source_line,
            "mutated_line": self.mutated_line,
            "description": self.description,
            "hint": self.hint,
        }


@dataclass
class MutantResult:
    mutant: Mutant
    status: str
    duration: float = 0.0
    killer: Optional[str] = None
    output: str = ""
    cached: bool = False

    def to_dict(self) -> Dict[str, Any]:
        data = self.mutant.to_dict()
        data.update(
            {
                "status": self.status,
                "duration": round(self.duration, 4),
                "killer": self.killer,
                "cached": self.cached,
                "output": self.output,
            }
        )
        return data


@dataclass
class RunReport:
    version: str
    root: str
    mode: str
    diff_base: Optional[str]
    started_at: str
    duration: float
    baseline_duration: float
    test_label: str
    test_command: str
    files_scanned: int
    mutants_total: int
    mutants_considered: int
    sampled: bool
    sample_size: Optional[int]
    results: List[MutantResult]
    score: Optional[float]
    score_ci: Optional[Tuple[float, float]]
    python_version: str
    git_head: Optional[str]
    cache_hits: int
    notes: List[str] = field(default_factory=list)
    tests_collected: Optional[int] = None
    timeout: float = 0.0

    @property
    def killed(self) -> int:
        return sum(1 for result in self.results if result.status == "killed")

    @property
    def survived(self) -> int:
        return sum(1 for result in self.results if result.status == "survived")

    @property
    def timeouts(self) -> int:
        return sum(1 for result in self.results if result.status == "timeout")

    @property
    def errors(self) -> int:
        return sum(1 for result in self.results if result.status == "error")

    @property
    def worker_errors(self) -> int:
        return sum(1 for result in self.results if result.status == "worker_error")

    def survivors(self) -> List[MutantResult]:
        return [result for result in self.results if result.status == "survived"]

    def operator_counts(self) -> Dict[str, Dict[str, int]]:
        counts: Dict[str, Dict[str, int]] = {}
        for result in self.results:
            if result.status == "worker_error":
                continue
            bucket = counts.setdefault(result.mutant.operator, {"killed": 0, "survived": 0})
            if result.status == "survived":
                bucket["survived"] += 1
            else:
                bucket["killed"] += 1
        return counts

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool": "fang",
            "version": self.version,
            "root": self.root,
            "mode": self.mode,
            "diff_base": self.diff_base,
            "started_at": self.started_at,
            "duration": round(self.duration, 3),
            "baseline_duration": round(self.baseline_duration, 3),
            "test_label": self.test_label,
            "test_command": self.test_command,
            "files_scanned": self.files_scanned,
            "mutants_total": self.mutants_total,
            "mutants_considered": self.mutants_considered,
            "sampled": self.sampled,
            "sample_size": self.sample_size,
            "python_version": self.python_version,
            "git_head": self.git_head,
            "cache_hits": self.cache_hits,
            "tests_collected": self.tests_collected,
            "timeout": round(self.timeout, 2),
            "score": None if self.score is None else round(self.score, 2),
            "score_ci": None
            if self.score_ci is None
            else [round(self.score_ci[0], 2), round(self.score_ci[1], 2)],
            "killed": self.killed,
            "survived": self.survived,
            "timeout_count": self.timeouts,
            "error_count": self.errors,
            "worker_error_count": self.worker_errors,
            "notes": list(self.notes),
            "operators": self.operator_counts(),
            "results": [result.to_dict() for result in self.results],
        }
