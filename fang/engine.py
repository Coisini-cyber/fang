from __future__ import annotations

import atexit
import hashlib
import os
import shutil
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

from . import __version__
from .cache import Cache
from .config import Config
from .diffmap import DiffError, changed_lines, git_head
from .discovery import (
    CONFIG_FILES,
    PRUNE_DIRS,
    detect_test_command,
    iter_python_files,
    iter_test_files,
)
from .models import Mutant, MutantResult, RunReport
from .mutators import generate_mutants
from .runner import Command, count_tests, has_no_tests, parse_killer, run_command
from .scoring import mutation_score, score_interval
from .source import read_source
from .util import sha1_short, sha256_bytes, utc_now

ProgressCallback = Callable[[int, int, Dict[str, int]], None]

_WORKSPACE: Dict[str, str] = {}


class AnalysisError(Exception):
    def __init__(self, message: str, output: str = "") -> None:
        super().__init__(message)
        self.output = output


@dataclass
class RunOptions:
    diff: Optional[str] = None
    staged: bool = False
    analyze_all: bool = False
    lines: Optional[Tuple[int, int]] = None


def _ignore_workspace(_directory: str, names: Sequence[str]) -> Set[str]:
    ignored = set()
    for name in names:
        if name in PRUNE_DIRS or name in (".git", ".fang"):
            ignored.add(name)
        elif name.endswith(".pyc") or name.endswith(".pyo"):
            ignored.add(name)
    return ignored


def _make_workspace(root: str) -> str:
    workspace = tempfile.mkdtemp(prefix="fang-ws-")
    try:
        shutil.copytree(
            root,
            workspace,
            dirs_exist_ok=True,
            ignore=_ignore_workspace,
            symlinks=False,
        )
    except Exception:
        shutil.rmtree(workspace, ignore_errors=True)
        raise
    with open(os.path.join(workspace, ".fang-workspace"), "w", encoding="utf-8") as marker:
        marker.write("fang isolated workspace\n")
    return workspace


def _init_worker(root: str) -> None:
    _WORKSPACE["path"] = _make_workspace(root)
    atexit.register(shutil.rmtree, _WORKSPACE["path"], True)


def _execute(
    workspace: str,
    relative_path: str,
    start: int,
    end: int,
    replacement: str,
    argv: Sequence[str],
    shell: bool,
    timeout: float,
) -> Tuple[str, float, Optional[str], str]:
    marker = os.path.join(workspace, ".fang-workspace")
    if not os.path.isfile(marker):
        return (
            "worker_error",
            0.0,
            None,
            "refusing to mutate %s: not a Fang workspace" % workspace,
        )
    if os.path.isabs(relative_path):
        return (
            "worker_error",
            0.0,
            None,
            "refusing to mutate an absolute path: %s" % relative_path,
        )
    target = os.path.abspath(os.path.join(workspace, relative_path))
    try:
        if os.path.commonpath([workspace, target]) != os.path.abspath(workspace):
            return (
                "worker_error",
                0.0,
                None,
                "refusing to mutate a path outside the workspace: %s" % relative_path,
            )
    except ValueError:
        return ("worker_error", 0.0, None, "invalid workspace path")
    encoding = "utf-8"
    try:
        with open(target, "r", encoding=encoding, newline="") as handle:
            original = handle.read()
    except UnicodeDecodeError:
        encoding = "latin-1"
        with open(target, "r", encoding=encoding, newline="") as handle:
            original = handle.read()
    except OSError as error:
        return ("error", 0.0, None, "could not read %s: %s" % (relative_path, error))

    mutated = original[:start] + replacement + original[end:]
    if mutated == original:
        return ("worker_error", 0.0, None, "mutation did not change the source")
    result = None
    restored = True
    try:
        with open(target, "w", encoding=encoding, newline="") as handle:
            handle.write(mutated)
        result = run_command(Command(argv=list(argv), shell=shell), workspace, timeout=timeout)
    finally:
        try:
            with open(target, "w", encoding=encoding, newline="") as handle:
                handle.write(original)
            with open(target, "r", encoding=encoding, newline="") as handle:
                restored = handle.read() == original
        except OSError:
            restored = False
    if not restored:
        return (
            "worker_error",
            result.duration if result else 0.0,
            None,
            "workspace file could not be restored after the mutant run",
        )
    if result is None:
        return ("worker_error", 0.0, None, "the test command produced no result")

    if result.timed_out:
        return ("timeout", result.duration, None, result.output[-4000:])
    if result.rc == 0:
        return ("survived", result.duration, None, "")
    killer = parse_killer(result.output)
    if killer is None and any(
        marker in result.output
        for marker in ("SyntaxError", "IndentationError", "ImportError", "ModuleNotFoundError")
    ):
        return ("error", result.duration, None, result.output[-4000:])
    return ("killed", result.duration, killer, result.output[-4000:])


def _worker_task(payload) -> Tuple[str, float, Optional[str], str]:
    workspace = _WORKSPACE["path"]
    relative_path, start, end, replacement, argv, shell, timeout = payload
    return _execute(workspace, relative_path, start, end, replacement, argv, shell, timeout)


def _test_fingerprint(root: str, command: Command, operators: Sequence[str]) -> str:
    digest = hashlib.sha256()
    digest.update(__version__.encode("utf-8"))
    digest.update(sys.version.encode("utf-8"))
    digest.update(command.display().encode("utf-8"))
    digest.update(",".join(operators).encode("utf-8"))
    for relative in iter_test_files(root):
        path = os.path.join(root, relative)
        digest.update(relative.encode("utf-8"))
        try:
            if os.path.getsize(path) <= 2 * 1024 * 1024:
                with open(path, "rb") as handle:
                    digest.update(handle.read())
        except OSError:
            continue
    for name in CONFIG_FILES:
        path = os.path.join(root, name)
        if not os.path.exists(path):
            continue
        digest.update(name.encode("utf-8"))
        try:
            with open(path, "rb") as handle:
                digest.update(handle.read())
        except OSError:
            continue
    return digest.hexdigest()


def _cache_key(mutant: Mutant, file_hash: str, test_fingerprint: str) -> str:
    return sha1_short(
        "%s\0%s\0%s" % (mutant.id, file_hash, test_fingerprint), length=40
    )


def _resolve_jobs(requested: int, count: int) -> int:
    if count <= 1:
        return 1
    if requested > 0:
        return min(requested, count)
    return max(1, min(4, count, os.cpu_count() or 1))


def _sample(mutants: List[Mutant], sample: Optional[int], seed: int) -> Tuple[List[Mutant], bool]:
    if sample is None or sample <= 0 or sample >= len(mutants):
        return mutants, False
    ranked = sorted(
        mutants,
        key=lambda mutant: hashlib.sha1(
            ("%d:%s" % (seed, mutant.id)).encode("utf-8")
        ).hexdigest(),
    )
    chosen = ranked[:sample]
    chosen.sort(key=lambda mutant: (mutant.path, mutant.line, mutant.col, mutant.operator))
    return chosen, True


def _empty_report(
    root: str,
    mode: str,
    diff_base: Optional[str],
    started_at: str,
    duration: float,
    files_scanned: int,
    mutants_total: int,
    notes: List[str],
    command: Command,
    python_version: str,
) -> RunReport:
    return RunReport(
        version=__version__,
        root=root,
        mode=mode,
        diff_base=diff_base,
        started_at=started_at,
        duration=duration,
        baseline_duration=0.0,
        test_label=command.label,
        test_command=command.display(),
        files_scanned=files_scanned,
        mutants_total=mutants_total,
        mutants_considered=0,
        sampled=False,
        sample_size=None,
        results=[],
        score=None,
        score_ci=None,
        python_version=python_version,
        git_head=git_head(root),
        cache_hits=0,
        notes=notes,
    )


def analyze(
    config: Config,
    options: Optional[RunOptions] = None,
    progress: Optional[ProgressCallback] = None,
) -> RunReport:
    options = options or RunOptions()
    root = os.path.abspath(config.root)
    if not os.path.isdir(root):
        raise AnalysisError("project path does not exist: %s" % root)

    started_at = utc_now()
    clock = time.monotonic()
    python_version = "%d.%d.%d" % sys.version_info[:3]
    notes: List[str] = []
    command = detect_test_command(root, tests=config.tests, explicit=config.test_command)[0]

    mode = "all"
    diff_base: Optional[str] = None
    line_filter: Optional[Set[int]] = None
    diff_info = None

    if options.lines:
        mode = "lines"
        line_filter = set(range(options.lines[0], options.lines[1] + 1))
    elif options.diff:
        mode = "diff"
        diff_base = options.diff
        diff_paths = [path for path in config.paths if not os.path.isabs(path)] or ["."]
        try:
            diff_info = changed_lines(
                root, options.diff, staged=options.staged, paths=diff_paths
            )
        except DiffError as error:
            raise AnalysisError(str(error))
        if not diff_info.files:
            notes.append(
                "no changed Python files against %s; nothing to mutate" % options.diff
            )
            return _empty_report(
                root,
                mode,
                diff_base,
                started_at,
                time.monotonic() - clock,
                0,
                0,
                notes,
                command,
                python_version,
            )

    scan = iter_python_files(
        root,
        config.paths,
        excludes=config.exclude,
        mutate_tests=config.mutate_tests,
        max_file_size=config.max_file_size,
    )
    files = list(scan.files)
    if scan.skipped_large:
        notes.append(
            "%d file(s) skipped because they exceed %d bytes"
            % (scan.skipped_large, config.max_file_size)
        )
    if scan.skipped_excluded:
        notes.append("%d file(s) skipped by exclude patterns" % scan.skipped_excluded)

    if diff_info is not None:
        files = [path for path in files if path in diff_info.files]

    mutants: List[Mutant] = []
    file_hashes: Dict[str, str] = {}
    for relative in files:
        full_path = os.path.join(root, relative)
        try:
            source = read_source(full_path)
        except OSError as error:
            notes.append("could not read %s: %s" % (relative, error))
            continue
        # Mutants must carry project-relative paths: workers join them onto an
        # isolated workspace, and an absolute path would escape the workspace.
        source.path = relative
        if line_filter is not None:
            only_lines: Optional[Set[int]] = line_filter
        elif diff_info is not None:
            only_lines = diff_info.files.get(relative, set())
        else:
            only_lines = None
        try:
            generated = generate_mutants(
                source,
                only_lines=only_lines,
                operators=config.operators,
                skip_calls=config.skip_calls,
            )
        except SyntaxError as error:
            notes.append("skipped %s (syntax error on line %s)" % (relative, error.lineno))
            continue
        file_hashes[relative] = sha256_bytes(source.text.encode("utf-8"))
        mutants.extend(generated)

    mutants.sort(key=lambda mutant: (mutant.path, mutant.line, mutant.col, mutant.operator))
    mutants_total = len(mutants)
    if not mutants:
        notes.append("no mutable constructs found in scope")
        return _empty_report(
            root,
            mode,
            diff_base,
            started_at,
            time.monotonic() - clock,
            len(files),
            mutants_total,
            notes,
            command,
            python_version,
        )

    considered, sampled = _sample(mutants, config.sample, config.seed)
    if sampled:
        notes.append(
            "sampled %d of %d mutants (seed %d); score is an estimate"
            % (len(considered), mutants_total, config.seed)
        )

    baseline_timeout = config.baseline_timeout if config.baseline_timeout else 600.0
    baseline = run_command(command, root, timeout=baseline_timeout)
    if baseline.timed_out:
        raise AnalysisError(
            "baseline test run exceeded %ss; raise baseline_timeout in .fang.json"
            % int(baseline_timeout),
            output=baseline.output,
        )
    if baseline.rc != 0:
        raise AnalysisError(
            "baseline test run is red; Fang needs a green suite to distinguish a"
            " surviving mutant from a pre-existing failure",
            output=baseline.output,
        )
    tests_collected = count_tests(baseline.output)
    if has_no_tests(baseline.output) or tests_collected == 0:
        raise AnalysisError(
            "the test command ran but collected no tests (%s)" % command.display(),
            output=baseline.output,
        )
    if tests_collected is None:
        notes.append("could not determine the number of collected tests")

    if config.timeout is not None:
        mutant_timeout = float(config.timeout)
    else:
        mutant_timeout = max(5.0, min(120.0, baseline.duration * 5.0 + 2.0))
    if baseline.duration > 60:
        notes.append(
            "baseline suite takes %ss; consider --sample or a faster test command"
            % round(baseline.duration, 1)
        )

    test_fp = _test_fingerprint(root, command, config.operators)
    cache = Cache(os.path.join(root, ".fang", "cache.json"), enabled=config.cache)

    results: List[Optional[MutantResult]] = [None] * len(considered)
    pending: List[int] = []
    cache_hits = 0
    counts = {"killed": 0, "survived": 0, "timeout": 0, "error": 0}
    done = 0

    def record(
        index: int,
        status: str,
        duration: float,
        killer: Optional[str],
        output: str,
        cached: bool = False,
    ) -> None:
        nonlocal done
        result = MutantResult(
            mutant=considered[index],
            status=status,
            duration=duration,
            killer=killer,
            output=output,
            cached=cached,
        )
        results[index] = result
        counts[status] = counts.get(status, 0) + 1
        done += 1
        if progress:
            progress(done, len(considered), dict(counts))

    for index, mutant in enumerate(considered):
        key = _cache_key(mutant, file_hashes.get(mutant.path, ""), test_fp)
        entry = cache.get(key)
        if entry:
            record(
                index,
                str(entry.get("status", "error")),
                float(entry.get("duration", 0.0)),
                entry.get("killer"),
                str(entry.get("output", "")),
                cached=True,
            )
            cache_hits += 1
        else:
            pending.append(index)

    jobs = _resolve_jobs(config.jobs, len(pending)) if pending else 1
    try:
        if pending and jobs > 1:
            payloads = {
                index: (
                    considered[index].path,
                    considered[index].start,
                    considered[index].end,
                    considered[index].replacement,
                    list(command.argv),
                    command.shell,
                    mutant_timeout,
                )
                for index in pending
            }
            broken = False
            pool = ProcessPoolExecutor(
                max_workers=jobs, initializer=_init_worker, initargs=(root,)
            )
            try:
                futures = {
                    pool.submit(_worker_task, payloads[index]): index for index in pending
                }
                for future in as_completed(futures):
                    index = futures[future]
                    try:
                        status, duration, killer, output = future.result()
                    except Exception as error:
                        status, duration, killer, output = (
                            "worker_error",
                            0.0,
                            None,
                            "worker failed: %s" % error,
                        )
                    record(index, status, duration, killer, output)
                    mutant = considered[index]
                    key = _cache_key(
                        mutant, file_hashes.get(mutant.path, ""), test_fp
                    )
                    cache.put(key, status, duration, killer, output)
            except BrokenProcessPool:
                broken = True
                notes.append(
                    "a worker process died; remaining mutants were retried sequentially"
                )
            except Exception as error:
                broken = True
                notes.append(
                    "parallel execution failed (%s); remaining mutants were retried sequentially"
                    % error
                )
            finally:
                try:
                    pool.shutdown(wait=True, cancel_futures=True)
                except Exception:
                    pass
            if broken:
                pending = [index for index, result in enumerate(results) if result is None]
                jobs = 1

        if jobs == 1 and pending:
            try:
                workspace = _make_workspace(root)
            except Exception as error:
                raise AnalysisError("could not create an isolated workspace: %s" % error)
            try:
                for index in pending:
                    if results[index] is not None:
                        continue
                    mutant = considered[index]
                    status, duration, killer, output = _execute(
                        workspace,
                        mutant.path,
                        mutant.start,
                        mutant.end,
                        mutant.replacement,
                        list(command.argv),
                        command.shell,
                        mutant_timeout,
                    )
                    record(index, status, duration, killer, output)
                    key = _cache_key(
                        mutant, file_hashes.get(mutant.path, ""), test_fp
                    )
                    cache.put(key, status, duration, killer, output)
            finally:
                shutil.rmtree(workspace, ignore_errors=True)
    finally:
        cache.save()

    final_results = [result for result in results if result is not None]
    worker_errors = sum(1 for result in final_results if result.status == "worker_error")
    if worker_errors:
        notes.append(
            "%d mutant(s) could not be evaluated because a worker failed; rerun with --jobs 1"
            % worker_errors
        )
    scoreable = [result for result in final_results if result.status != "worker_error"]
    detected = sum(
        1
        for result in scoreable
        if result.status in ("killed", "timeout", "error")
    )
    total = len(scoreable)
    score = mutation_score(detected, total)
    interval = score_interval(detected, total) if (sampled and total) else None

    return RunReport(
        version=__version__,
        root=root,
        mode=mode,
        diff_base=diff_base,
        started_at=started_at,
        duration=time.monotonic() - clock,
        baseline_duration=baseline.duration,
        test_label=command.label,
        test_command=command.display(),
        files_scanned=len(files),
        mutants_total=mutants_total,
        mutants_considered=len(considered),
        sampled=sampled,
        sample_size=len(considered) if sampled else None,
        results=final_results,
        score=score,
        score_ci=interval,
        python_version=python_version,
        git_head=git_head(root),
        cache_hits=cache_hits,
        notes=notes,
        tests_collected=tests_collected,
        timeout=mutant_timeout,
    )
