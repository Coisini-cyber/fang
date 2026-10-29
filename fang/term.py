from __future__ import annotations

import os
import shutil
import sys
import textwrap
from collections import Counter
from typing import Dict, List, Optional, Tuple

from .models import MutantResult, RunReport
from .scoring import grade, grade_word
from .util import human_duration, human_int, pct, truncate

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
GRAY = "\033[90m"


def _enable_windows_vt() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


def color_supported(stream=None) -> bool:
    stream = stream or sys.stdout
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    if not getattr(stream, "isatty", lambda: False)():
        return False
    if os.environ.get("TERM", "") == "dumb":
        return False
    _enable_windows_vt()
    return True


def unicode_supported(stream=None) -> bool:
    stream = stream or sys.stdout
    encoding = getattr(stream, "encoding", None) or "utf-8"
    try:
        "\u2588\u2591\u2500\u2192\u00b7".encode(encoding)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


class Term:
    def __init__(self, color: bool = True, ascii_only: bool = False) -> None:
        self.color = bool(color) and color_supported()
        self.ascii = bool(ascii_only) or not unicode_supported()
        self.block = "#" if self.ascii else "\u2588"
        self.shade = "." if self.ascii else "\u2591"
        self.rule_char = "-" if self.ascii else "\u2500"
        self.dot = "." if self.ascii else "\u00b7"
        self.arrow = "->" if self.ascii else "\u2192"
        self.bullet = "*" if self.ascii else "\u21b3"
        try:
            self.width = max(72, min(110, shutil.get_terminal_size((100, 24)).columns))
        except OSError:
            self.width = 100

    def paint(self, text: str, *codes: str) -> str:
        if not self.color or not codes:
            return text
        return "".join(codes) + text + RESET

    def bold(self, text: str) -> str:
        return self.paint(text, BOLD)

    def dim(self, text: str) -> str:
        return self.paint(text, DIM)

    def red(self, text: str) -> str:
        return self.paint(text, RED)

    def green(self, text: str) -> str:
        return self.paint(text, GREEN)

    def yellow(self, text: str) -> str:
        return self.paint(text, YELLOW)

    def cyan(self, text: str) -> str:
        return self.paint(text, CYAN)

    def magenta(self, text: str) -> str:
        return self.paint(text, MAGENTA)

    def gray(self, text: str) -> str:
        return self.paint(text, GRAY)

    def rule(self, char: Optional[str] = None, width: Optional[int] = None) -> str:
        return (char or self.rule_char) * (width or self.width)

    def bar(self, fraction: float, width: int = 22, color: Optional[str] = None) -> str:
        fraction = max(0.0, min(1.0, fraction))
        filled = int(round(fraction * width))
        body = self.block * filled + self.shade * (width - filled)
        if color:
            return self.paint(body, color)
        return body


def _score_color(score: Optional[float]) -> Optional[str]:
    if score is None:
        return None
    if score >= 80:
        return GREEN
    if score >= 60:
        return YELLOW
    return RED


def _file_stats(report: RunReport) -> Dict[str, Tuple[int, int]]:
    stats: Dict[str, Tuple[int, int]] = {}
    for result in report.results:
        if result.status == "worker_error":
            continue
        killed, survived = stats.get(result.mutant.path, (0, 0))
        if result.status == "survived":
            survived += 1
        else:
            killed += 1
        stats[result.mutant.path] = (killed, survived)
    return stats


def _wrap(text: str, width: int) -> List[str]:
    return textwrap.wrap(text, width=max(20, width), break_long_words=False, break_on_hyphens=False)


def render_report(
    report: RunReport,
    term: Optional[Term] = None,
    verbose: bool = False,
    limit: int = 12,
) -> str:
    term = term or Term()
    lines: List[str] = []
    width = term.width
    score_color = _score_color(report.score)
    total = report.mutants_considered
    detected = report.killed + report.timeouts + report.errors
    fraction = (detected / total) if total else 0.0

    lines.append("")
    lines.append(
        term.bold(term.cyan("  FANG")) + term.dim("  %s mutation report" % term.dot)
    )
    location = report.root
    if len(location) > width - 10:
        location = "..." + location[-(width - 13) :]
    mode = report.mode
    if report.mode == "diff" and report.diff_base:
        mode = "diff vs %s" % report.diff_base
    lines.append(term.dim("  %s %s %s" % (location, term.dot, mode)))
    lines.append("  " + term.rule(width=width - 4))

    score_text = pct(report.score)
    if report.score is not None:
        colored_score = term.paint(score_text, BOLD, score_color or "")
    else:
        colored_score = term.dim(score_text)
    bar = term.bar(fraction, color=score_color)
    grade_text = grade(report.score)
    if report.score is not None:
        grade_text = "%s %s %s" % (grade_text, term.dot, grade_word(report.score))
    lines.append(
        "  %s  %s   %s  %s"
        % (
            term.gray("SCORE  "),
            colored_score.ljust(18),
            bar,
            term.paint(grade_text, BOLD, score_color or ""),
        )
    )
    counts = "%d killed %s %d survived" % (
        report.killed,
        term.dot,
        report.survived,
    )
    if report.timeouts:
        counts += " %s %d timeout" % (term.dot, report.timeouts)
    if report.errors:
        counts += " %s %d crash" % (term.dot, report.errors)
    if report.worker_errors:
        counts += " %s %d worker error" % (term.dot, report.worker_errors)
    lines.append("  %s  %s" % (" " * 7, term.dim(counts)))

    if report.sampled and report.score_ci:
        sample_line = "sampled %d of %d %s 95%% CI %s" % (
            total,
            report.mutants_total,
            term.dot,
            "%s-%s" % (pct(report.score_ci[0]), pct(report.score_ci[1])),
        )
    else:
        sample_line = "%d mutants in scope" % report.mutants_total
    measured = [result.duration for result in report.results if result.status != "worker_error"]
    average = (sum(measured) / len(measured)) if measured else 0.0
    tests = (
        "%s tests %s %s baseline %s %s/mutant"
        % (
            human_int(report.tests_collected) if report.tests_collected is not None else "?",
            term.dot,
            human_duration(report.baseline_duration),
            term.dot,
            human_duration(average),
        )
    )
    if report.cache_hits:
        sample_line += " %s %d cached" % (term.dot, report.cache_hits)
    lines.append("  %s  %s %s %s" % (" " * 7, tests, term.dot, term.dim(sample_line)))

    lines.append("  " + term.rule(width=width - 4))
    lines.append("")

    survivors = [result for result in report.results if result.status == "survived"]
    if survivors:
        header = "  %s %s %s" % (
            term.bold(term.red("SURVIVORS")),
            term.dim("(%d)" % len(survivors)),
            term.dim("mutations your tests did not notice"),
        )
        lines.append(header)
        lines.append("")
        shown = survivors if verbose else survivors[:limit]
        for result in shown:
            lines.extend(_render_mutant(result, term, width))
        if len(survivors) > len(shown):
            lines.append(
                term.dim(
                    "  ... and %d more surviving mutant(s); rerun with --verbose to list all"
                    % (len(survivors) - len(shown))
                )
            )
        lines.append("")
    else:
        lines.append(
            "  %s %s"
            % (
                term.green(term.bold("NO SURVIVORS")),
                term.dim("%s every generated mutant was detected" % term.dot),
            )
        )
        lines.append("")

    stats = _file_stats(report)
    if len(stats) > 1:
        lines.append("  %s" % term.bold("FILES"))
        for path in sorted(stats):
            killed, survived = stats[path]
            file_total = killed + survived
            file_score = 100.0 * killed / file_total if file_total else 0.0
            file_bar = term.bar(file_score / 100.0, width=16, color=_score_color(file_score))
            lines.append(
                "  %-38s %s %6s  %d/%d"
                % (truncate(path, 38), file_bar, pct(file_score, 0), killed, file_total)
            )
        lines.append("")

    killers = Counter(
        result.killer for result in report.results if result.killer and result.status == "killed"
    )
    if killers:
        lines.append("  %s" % term.bold("TESTS DOING THE WORK"))
        for name, count in killers.most_common(5):
            lines.append("  %s %s %s" % (term.green(str(count).rjust(3)), term.dot, truncate(name, width - 12)))
        lines.append("")

    if report.notes:
        for note in report.notes:
            for chunk in _wrap(note, width - 8):
                lines.append("  " + term.dim("! " + chunk))
        lines.append("")

    lines.append("  " + term.rule(width=width - 4))
    lines.append(
        "  %s %s %s"
        % (
            term.dim("verdict"),
            term.paint(grade_word(report.score), BOLD, score_color or ""),
            term.dim(
                "%s %s %s %s tests"
                % (
                    term.dot,
                    report.test_label,
                    term.dot,
                    human_int(report.tests_collected)
                    if report.tests_collected is not None
                    else "?",
                )
            ),
        )
    )
    lines.append("")
    return "\n".join(lines)


def _render_mutant(result: MutantResult, term: Term, width: int) -> List[str]:
    mutant = result.mutant
    lines = []
    context = " %s %s" % (term.dot, mutant.context) if mutant.context else ""
    lines.append(
        "  %s%s  %s"
        % (
            term.cyan(term.bold("%s:%d" % (mutant.path, mutant.line))),
            term.dim(context),
            term.dim("[%s]" % mutant.operator),
        )
    )
    source = mutant.source_line.strip()
    if mutant.mutated_line is not None:
        mutated = mutant.mutated_line.strip()
        lines.append("    " + term.red("- " + truncate(source, width - 8)))
        lines.append("    " + term.green("+ " + truncate(mutated, width - 8)))
    else:
        lines.append("    " + term.red("- " + truncate(mutant.expression_before, width - 8)))
        lines.append("    " + term.green("+ " + truncate(mutant.expression_after, width - 8)))
    detail = "%s %s %s" % (mutant.description, term.dot, mutant.hint)
    for chunk in _wrap(detail, width - 8)[:3]:
        lines.append("    " + term.dim(chunk))
    lines.append("")
    return lines
