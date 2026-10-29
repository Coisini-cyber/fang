from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import __version__
from .config import ConfigError, load_config
from .diffmap import DiffError
from .discovery import describe_project, detect_test_command
from .engine import AnalysisError, RunOptions, analyze
from .models import RunReport
from .scoring import grade

PROTOCOL_VERSIONS = {"2024-11-05", "2025-03-26", "2025-06-18"}

INSTRUCTIONS = (
    "Fang measures whether a test suite would notice a behavioural change. "
    "Call fang_check_diff after editing code or tests: it mutates only the lines in "
    "the current diff and returns the surviving mutants, each with a concrete hint. "
    "Add tests for the survivors, then call it again. It needs a green suite and a "
    "fast test command. Use fang_mutation_score with all=true to audit a whole project."
)

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "fang_check_diff",
        "description": (
            "Diff-scoped mutation testing. Mutates only added Python lines versus a git "
            "revision (default HEAD), runs the test suite, and returns the mutants the "
            "tests failed to detect. Use this to verify that new tests actually bite."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "root": {"type": "string", "description": "Project root (default: server root)."},
                "diff": {"type": "string", "description": "Git revision to diff against (default: HEAD)."},
                "sample": {"type": "integer", "minimum": 1, "description": "Max mutants to evaluate (default: 40)."},
                "jobs": {"type": "integer", "minimum": 1, "description": "Parallel workers (default: 2)."},
                "timeout": {"type": "number", "description": "Per-mutant timeout in seconds."},
                "survivor_limit": {"type": "integer", "minimum": 1, "description": "Max survivors returned (default: 25)."},
            },
        },
    },
    {
        "name": "fang_mutation_score",
        "description": (
            "Return only the mutation score and counts for a diff or the whole project. "
            "Cheaper than fang_check_diff when you just need the number."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "root": {"type": "string"},
                "diff": {"type": "string", "description": "Git revision (default: HEAD)."},
                "all": {"type": "boolean", "description": "Audit the whole project instead of a diff."},
                "sample": {"type": "integer", "minimum": 1},
                "jobs": {"type": "integer", "minimum": 1},
                "timeout": {"type": "number"},
            },
        },
    },
    {
        "name": "fang_list_survivors",
        "description": (
            "Run the analysis and return surviving mutants only, with file, line, "
            "operator, before/after code, and a hint. Supports offset/limit pagination."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "root": {"type": "string"},
                "diff": {"type": "string"},
                "all": {"type": "boolean"},
                "sample": {"type": "integer", "minimum": 1, "description": "Default: 60."},
                "jobs": {"type": "integer", "minimum": 1},
                "limit": {"type": "integer", "minimum": 1, "description": "Default: 25."},
                "offset": {"type": "integer", "minimum": 0, "description": "Default: 0."},
            },
        },
    },
    {
        "name": "fang_doctor",
        "description": "Inspect the project: detected test runner, Python files, test files, and config.",
        "inputSchema": {
            "type": "object",
            "properties": {"root": {"type": "string"}},
        },
    },
]


def _resolve_root(server_root: str, value: Optional[str]) -> str:
    if not value:
        return os.path.abspath(server_root)
    if os.path.isabs(value):
        return os.path.abspath(value)
    return os.path.abspath(os.path.join(server_root, value))


def _survivor_payload(result, include_output: bool = False) -> Dict[str, Any]:
    mutant = result.mutant
    payload = {
        "id": mutant.id,
        "path": mutant.path,
        "line": mutant.line,
        "context": mutant.context or "module",
        "operator": mutant.operator,
        "before": mutant.original,
        "after": mutant.replacement,
        "expression_before": mutant.expression_before,
        "expression_after": mutant.expression_after,
        "hint": mutant.hint,
    }
    if include_output:
        payload["output"] = result.output[-800:]
    return payload


def _summary(report: RunReport) -> Dict[str, Any]:
    return {
        "score": None if report.score is None else round(report.score, 2),
        "grade": grade(report.score),
        "killed": report.killed,
        "survived": report.survived,
        "timeouts": report.timeouts,
        "errors": report.errors,
        "mutants": {
            "total": report.mutants_total,
            "considered": report.mutants_considered,
            "sampled": report.sampled,
            "ci95": None
            if report.score_ci is None
            else [round(report.score_ci[0], 2), round(report.score_ci[1], 2)],
        },
        "tests": {
            "collected": report.tests_collected,
            "baseline_seconds": round(report.baseline_duration, 3),
            "command": report.test_command,
        },
        "scope": report.mode if report.mode != "diff" else "diff vs %s" % report.diff_base,
        "duration_seconds": round(report.duration, 3),
        "notes": report.notes,
    }


def _run_tool(
    server_root: str,
    arguments: Dict[str, Any],
    force_all: bool = False,
) -> RunReport:
    root = _resolve_root(server_root, arguments.get("root"))
    config = load_config(root)
    config.jobs = max(1, min(4, int(arguments.get("jobs") or 2)))
    config.cache = True
    config.report_path = ""
    if arguments.get("timeout"):
        config.timeout = float(arguments["timeout"])
    if arguments.get("sample"):
        config.sample = int(arguments["sample"])

    analyze_all = bool(force_all or arguments.get("all"))
    if analyze_all:
        options = RunOptions(analyze_all=True)
    else:
        options = RunOptions(diff=str(arguments.get("diff") or "HEAD"))
    return analyze(config, options)


def _tool_text(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(payload, indent=2, ensure_ascii=False)}]}


def _error_text(message: str, output: str = "") -> Dict[str, Any]:
    payload: Dict[str, Any] = {"error": message}
    if output:
        payload["output"] = output[-3000:]
    return {
        "content": [{"type": "text", "text": json.dumps(payload, indent=2, ensure_ascii=False)}],
        "isError": True,
    }


def _call_tool(server_root: str, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    try:
        if name == "fang_doctor":
            root = _resolve_root(server_root, arguments.get("root"))
            info = describe_project(root)
            config = load_config(root)
            command, label = detect_test_command(root, config.tests, config.test_command)
            return _tool_text(
                {
                    "root": root,
                    "python": sys.version.split()[0],
                    "fang": __version__,
                    "runner": label,
                    "command": command.display(),
                    "config": config.config_file if os.path.exists(config.config_file) else None,
                    "python_files": info["python_files"],
                    "test_files": info["test_files"],
                    "pytest_available": info["pytest_available"],
                    "paths": config.paths,
                    "operators": config.operators,
                }
            )

        if name == "fang_mutation_score":
            report = _run_tool(server_root, arguments)
            return _tool_text(_summary(report))

        if name in ("fang_check_diff", "fang_list_survivors"):
            if name == "fang_check_diff":
                arguments = dict(arguments)
                arguments.setdefault("sample", 40)
                limit = int(arguments.pop("survivor_limit", 25))
                offset = 0
            else:
                arguments = dict(arguments)
                arguments.setdefault("sample", 60)
                limit = int(arguments.pop("limit", 25))
                offset = int(arguments.pop("offset", 0))
            report = _run_tool(server_root, arguments)
            survivors = [result for result in report.results if result.status == "survived"]
            page = survivors[offset : offset + limit]
            payload = _summary(report)
            payload["survivors"] = [_survivor_payload(result) for result in page]
            payload["pagination"] = {
                "offset": offset,
                "limit": limit,
                "returned": len(page),
                "total": len(survivors),
                "truncated": offset + len(page) < len(survivors),
            }
            return _tool_text(payload)

        return _error_text("unknown tool: %s" % name)
    except (AnalysisError, ConfigError, DiffError) as error:
        return _error_text(str(error), getattr(error, "output", ""))
    except Exception as error:  # keep the server alive
        return _error_text("fang failed: %s" % error)


def handle_message(server_root: str, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(message, dict):
        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32700, "message": "parse error"},
        }
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}

    if method == "initialize":
        requested = params.get("protocolVersion")
        version = requested if requested in PROTOCOL_VERSIONS else "2024-11-05"
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "fang", "version": __version__},
                "instructions": INSTRUCTIONS,
            },
        }
    if method in ("notifications/initialized", "notifications/cancelled"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str):
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32602, "message": "tools/call requires a name"},
            }
        if not isinstance(arguments, dict):
            arguments = {}
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": _call_tool(server_root, name, arguments),
        }
    if method == "resources/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"resources": []}}
    if method == "prompts/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"prompts": []}}

    if request_id is None:
        return None
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": "method not found: %s" % method},
    }


def _iter_messages(stream) -> Iterable[Dict[str, Any]]:
    while True:
        line = stream.readline()
        if not line:
            return
        if isinstance(line, bytes):
            try:
                line = line.decode("utf-8")
            except UnicodeDecodeError:
                continue
        if not line.strip():
            continue
        if line.lower().startswith("content-length:"):
            try:
                length = int(line.split(":", 1)[1].strip())
            except (IndexError, ValueError):
                continue
            while True:
                header = stream.readline()
                if isinstance(header, bytes):
                    header = header.decode("utf-8", "replace")
                if header in ("\r\n", "\n", ""):
                    break
            body = stream.read(length)
            if isinstance(body, bytes):
                body = body.decode("utf-8", "replace")
            try:
                yield json.loads(body)
            except ValueError:
                continue
        else:
            try:
                yield json.loads(line)
            except ValueError:
                yield {"__parse_error__": True}


def serve(root: str = ".") -> int:
    server_root = os.path.abspath(root)
    if not os.path.isdir(server_root):
        sys.stderr.write("fang mcp: no such directory: %s\n" % server_root)
        return 2

    stdin = getattr(sys.stdin, "buffer", sys.stdin)
    stdout = getattr(sys.stdout, "buffer", sys.stdout)
    for message in _iter_messages(stdin):
        if message.get("__parse_error__"):
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "parse error"},
            }
        else:
            response = handle_message(server_root, message)
        if response is None:
            continue
        raw = json.dumps(response, ensure_ascii=False)
        if hasattr(stdout, "write"):
            stdout.write(raw.encode("utf-8") + b"\n")
            stdout.flush()
    return 0
