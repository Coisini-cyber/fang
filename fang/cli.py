from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import webbrowser
from typing import List, Optional, Tuple

from . import __version__
from .config import Config, ConfigError, load_config, template_config
from .diffmap import DiffError, changed_lines, git_head, git_toplevel
from .discovery import describe_project, detect_test_command
from .engine import AnalysisError, RunOptions, analyze
from .mutators import OPERATOR_LABELS
from .report_html import render_badge, render_html, render_markdown
from .term import Term, render_report
from .util import atomic_write, pct

EPILOG = """examples:
  fang run                          # mutate uncommitted changes (or all files if clean)
  fang run --all                    # mutate the whole project
  fang run --diff main --sample 80  # PR gate: 80 sampled mutants, 95% CI
  fang run --lines 40-70 --verbose  # mutate one region
  fang run --min-score 80 --report docs/fang.html
  fang mcp                          # expose Fang to a coding agent over stdio

Fang mutates only the Python lines in scope. It needs a green test suite.
"""


def _split(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_lines(value: str) -> Tuple[int, int]:
    match = re.match(r"^(\d+)(?:\s*-\s*(\d+))?$", value.strip())
    if not match:
        raise argparse.ArgumentTypeError("expected N or N-M, for example 40-70")
    start = int(match.group(1))
    end = int(match.group(2) or start)
    if start < 1 or end < start:
        raise argparse.ArgumentTypeError("line ranges must be positive and ordered")
    return start, end


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fang",
        description="Diff-scoped mutation testing that runs in CI time.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version="fang " + __version__)
    subparsers = parser.add_subparsers(dest="command")

    run = subparsers.add_parser("run", help="mutate a diff, lines, or a project")
    run.add_argument("path", nargs="?", default=".", help="project root (default: .)")
    run.add_argument("--config", help="path to a .fang.json file")
    run.add_argument("--diff", metavar="REF", help="mutate added lines versus a git revision")
    run.add_argument("--staged", action="store_true", help="mutate staged changes versus HEAD")
    run.add_argument("--all", action="store_true", help="mutate every Python file in scope")
    run.add_argument("--lines", type=_parse_lines, metavar="N-M", help="mutate a line range")
    run.add_argument("--paths", help="comma-separated source paths, relative to the project")
    run.add_argument("--tests", action="append", help="test path(s), relative to the project")
    run.add_argument("--test-command", help="custom shell command used to run the suite")
    run.add_argument("--operators", help="comma-separated mutation operators")
    run.add_argument("--sample", type=int, help="evaluate a deterministic sample of N mutants")
    run.add_argument("--seed", type=int, help="sampling seed (default: 0)")
    run.add_argument("--jobs", type=int, help="parallel workers (default: auto, max 4)")
    run.add_argument("--timeout", type=float, help="per-mutant timeout in seconds")
    run.add_argument("--baseline-timeout", type=float, help="baseline suite timeout in seconds")
    run.add_argument("--min-score", type=float, help="exit 1 if the mutation score is below this")
    run.add_argument("--exclude", action="append", help="extra exclude glob (repeatable)")
    run.add_argument("--mutate-tests", action="store_true", help="also mutate test files")
    run.add_argument("--report", help="HTML report path (default: .fang/report.html)")
    run.add_argument("--no-report", action="store_true", help="do not write an HTML report")
    run.add_argument("--badge", help="write an SVG score badge to this path")
    run.add_argument("--markdown", help="write a PR-comment style markdown summary")
    run.add_argument("--json", action="store_true", help="print the full report as JSON")
    run.add_argument("--json-out", help="write the full report as JSON to this path")
    run.add_argument("--no-cache", action="store_true", help="do not read or write the result cache")
    run.add_argument("--clear-cache", action="store_true", help="delete the result cache first")
    run.add_argument("--no-color", action="store_true", help="disable ANSI colour")
    run.add_argument("--ascii", action="store_true", help="use ASCII-only output")
    run.add_argument("--verbose", action="store_true", help="list every surviving mutant")
    run.add_argument("--quiet", action="store_true", help="suppress the terminal report")
    run.add_argument("--open", action="store_true", help="open the HTML report when finished")
    run.add_argument("--limit", type=int, default=12, help="survivors shown in the terminal")

    init = subparsers.add_parser("init", help="write a starter .fang.json")
    init.add_argument("path", nargs="?", default=".", help="project root (default: .)")
    init.add_argument("--force", action="store_true", help="overwrite an existing config")

    doctor = subparsers.add_parser("doctor", help="check the environment and test discovery")
    doctor.add_argument("path", nargs="?", default=".", help="project root (default: .)")

    report = subparsers.add_parser("report", help="open the latest HTML report")
    report.add_argument("path", nargs="?", default=".", help="project root (default: .)")
    report.add_argument("--no-open", action="store_true", help="print the path without opening it")

    mcp = subparsers.add_parser("mcp", help="run the MCP stdio server")
    mcp.add_argument("path", nargs="?", default=".", help="project root (default: .)")

    subparsers.add_parser("version", help="print the version")
    return parser


def _apply_args(config: Config, args: argparse.Namespace) -> None:
    if args.paths:
        config.paths = _split(args.paths)
    if args.tests:
        tests: List[str] = []
        for entry in args.tests:
            tests.extend(_split(entry))
        config.tests = tests
    if args.test_command:
        config.test_command = args.test_command
    if args.operators:
        operators = _split(args.operators)
        unknown = sorted(set(operators) - set(OPERATOR_LABELS))
        if unknown:
            raise ConfigError(
                "unknown operator(s): %s (choose from %s)"
                % (", ".join(unknown), ", ".join(sorted(OPERATOR_LABELS)))
            )
        config.operators = operators
    if args.sample is not None:
        config.sample = args.sample if args.sample > 0 else None
    if args.seed is not None:
        config.seed = args.seed
    if args.jobs is not None:
        config.jobs = max(0, args.jobs)
    if args.timeout is not None:
        config.timeout = args.timeout
    if args.baseline_timeout is not None:
        config.baseline_timeout = args.baseline_timeout
    if args.min_score is not None:
        if not 0 <= args.min_score <= 100:
            raise ConfigError("--min-score must be between 0 and 100")
        config.min_score = args.min_score
    if args.exclude:
        config.exclude = list(dict.fromkeys(list(config.exclude) + list(args.exclude)))
    if args.mutate_tests:
        config.mutate_tests = True
    if args.no_cache:
        config.cache = False
    if args.report:
        config.report_path = args.report
    if args.badge:
        config.badge_path = args.badge
    if args.markdown:
        config.markdown_path = args.markdown
    if args.json_out:
        config.json_path = args.json_out
    config.verbose = args.verbose


def _decide_mode(args: argparse.Namespace, root: str) -> RunOptions:
    if args.lines:
        return RunOptions(lines=args.lines)
    if args.diff:
        return RunOptions(diff=args.diff, staged=args.staged)
    if args.staged:
        return RunOptions(diff="HEAD", staged=True)
    if args.all:
        return RunOptions(analyze_all=True)
    if git_toplevel(root):
        try:
            info = changed_lines(root, "HEAD")
        except DiffError:
            info = None
        if info is not None and info.files:
            return RunOptions(diff="HEAD")
    return RunOptions(analyze_all=True)


def _artifact_path(path: str) -> str:
    return path if os.path.isabs(path) else os.path.abspath(path)


def _make_progress(term: Term, enabled: bool, quiet: bool):
    if not enabled or quiet:
        return None
    state = {"last": 0.0}

    def callback(done: int, total: int, counts: dict) -> None:
        now = time.monotonic()
        if done < total and now - state["last"] < 0.08:
            return
        state["last"] = now
        parts = ["%d/%d" % (done, total)]
        for key in ("killed", "survived", "timeout", "error"):
            if counts.get(key):
                parts.append("%d %s" % (counts[key], key))
        line = "  mutating " + term.dot.join(parts)
        sys.stderr.write("\r" + line[: term.width - 1] + ("" if not term.color else "\033[K"))
        if done >= total:
            sys.stderr.write("\n")
        sys.stderr.flush()

    return callback


def _print_footer(term: Term, report, artifacts: List[Tuple[str, str]]) -> None:
    if artifacts:
        print()
        for label, path in artifacts:
            print("  " + term.dim("%-8s" % label) + path)
    if report and report.score is not None and report.sampled:
        print(
            "  "
            + term.dim("%-8s" % "ci")
            + "95%% interval %s - %s (sampled)"
            % (pct(report.score_ci[0]), pct(report.score_ci[1]))
        )
    print()


def _run(args: argparse.Namespace) -> int:
    root = os.path.abspath(args.path)
    term = Term(color=not args.no_color, ascii_only=args.ascii)
    try:
        config = load_config(root, args.config)
        _apply_args(config, args)
    except ConfigError as error:
        print("fang: %s" % error, file=sys.stderr)
        return 2

    if args.clear_cache:
        cache_path = os.path.join(root, ".fang", "cache.json")
        try:
            os.unlink(cache_path)
        except OSError:
            pass

    options = _decide_mode(args, root)
    auto_diff = options.diff == "HEAD" and not (args.diff or args.staged)
    if auto_diff and not args.quiet and not args.json:
        print(
            "fang: mutating uncommitted changes vs HEAD (use --all for the whole project)",
            file=sys.stderr,
        )
    elif options.analyze_all and not args.quiet and not args.json:
        print("fang: mutating the whole project (use --diff REF to narrow it)", file=sys.stderr)

    progress = _make_progress(term, sys.stderr.isatty(), args.quiet or args.json)
    started = time.monotonic()
    try:
        report = analyze(config, options, progress=progress)
    except AnalysisError as error:
        print("fang: %s" % error, file=sys.stderr)
        if error.output:
            print(error.output[-5000:], file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("fang: interrupted", file=sys.stderr)
        return 130

    artifacts: List[Tuple[str, str]] = []
    report_path: Optional[str] = None
    if not args.no_report and config.report_path:
        report_path = _artifact_path(config.report_path)
        atomic_write(report_path, render_html(report))
        artifacts.append(("report", report_path))
    if config.badge_path:
        badge_path = _artifact_path(config.badge_path)
        atomic_write(badge_path, render_badge(report))
        artifacts.append(("badge", badge_path))
    if config.markdown_path:
        markdown_path = _artifact_path(config.markdown_path)
        atomic_write(markdown_path, render_markdown(report))
        artifacts.append(("comment", markdown_path))
    if config.json_path:
        json_path = _artifact_path(config.json_path)
        atomic_write(json_path, json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        artifacts.append(("json", json_path))

    gate_failed = (
        config.min_score is not None
        and report.score is not None
        and report.score < config.min_score
    )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    elif not args.quiet:
        print(render_report(report, term=term, verbose=args.verbose, limit=args.limit), end="")
        if config.min_score is not None and report.score is not None:
            status = term.red("FAIL") if gate_failed else term.green("PASS")
            print(
                "  %s %s  %.1f%% vs minimum %.1f%%"
                % (term.dim("%-8s" % "gate"), status, report.score, config.min_score)
            )
        if report.score is None:
            print("  " + term.dim("nothing to score; the gate was not applied"))
        _print_footer(term, report, artifacts)

    if args.open and report_path:
        webbrowser.open("file://" + os.path.abspath(report_path))

    return 1 if gate_failed else 0


def _init(args: argparse.Namespace) -> int:
    root = os.path.abspath(args.path)
    if not os.path.isdir(root):
        print("fang: no such directory: %s" % root, file=sys.stderr)
        return 2
    path = os.path.join(root, ".fang.json")
    if os.path.exists(path) and not args.force:
        print("fang: %s already exists (use --force to overwrite)" % path, file=sys.stderr)
        return 2
    atomic_write(path, json.dumps(template_config(), indent=2) + "\n")
    command, _ = detect_test_command(root)
    print("wrote %s" % path)
    print("detected test command: %s" % command.display())
    print("")
    print("next:")
    print("  fang run %s --all" % ("" if root == os.getcwd() else args.path))
    print("  fang run %s --diff HEAD --min-score 70" % ("" if root == os.getcwd() else args.path))
    return 0


def _doctor(args: argparse.Namespace) -> int:
    root = os.path.abspath(args.path)
    term = Term()
    print("")
    print(term.bold("  FANG doctor"))
    print("  " + term.rule())
    print("  python      %s" % sys.version.split()[0])
    print("  executable  %s" % sys.executable)
    print("  fang        %s" % __version__)
    print("  project     %s" % root)
    print("  git         %s" % (git_head(root) or "not a git work tree"))
    try:
        config = load_config(root)
        print("  config      %s" % (config.config_file if os.path.exists(config.config_file) else "none (.fang.json not found)"))
        command, label = detect_test_command(root, config.tests, config.test_command)
        print("  runner      %s" % label)
        print("  command     %s" % command.display())
        info = describe_project(root)
        print("  sources     %d Python files" % info["python_files"])
        print("  tests       %d test files" % info["test_files"])
        print("  pytest      %s" % ("available" if info["pytest_available"] else "not installed"))
        print("  operators   %s" % ", ".join(config.operators))
        print("  paths       %s" % ", ".join(config.paths))
    except ConfigError as error:
        print("  config      INVALID: %s" % error)
        return 2
    print("")
    return 0


def _report(args: argparse.Namespace) -> int:
    root = os.path.abspath(args.path)
    try:
        config = load_config(root)
    except ConfigError as error:
        print("fang: %s" % error, file=sys.stderr)
        return 2
    path = _artifact_path(config.report_path)
    if not os.path.exists(path):
        print("fang: no report at %s (run `fang run` first)" % path, file=sys.stderr)
        return 2
    print(path)
    if not args.no_open:
        webbrowser.open("file://" + os.path.abspath(path))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    if args.command == "run":
        return _run(args)
    if args.command == "init":
        return _init(args)
    if args.command == "doctor":
        return _doctor(args)
    if args.command == "report":
        return _report(args)
    if args.command == "version":
        print("fang %s" % __version__)
        return 0
    if args.command == "mcp":
        from .mcp import serve

        return serve(args.path)
    parser.print_help()
    return 2
