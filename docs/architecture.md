# Fang architecture

Fang is a single-process orchestrator around an AST mutator and a pool of isolated test
runners. There are no runtime dependencies outside the Python standard library.

## Data flow

```text
CLI
 │  parse flags, load .fang.json, pick scope
 ▼
engine.analyze
 │
 ├─ discovery.iter_python_files ──► candidate files (tests excluded by default)
 ├─ diffmap.changed_lines ────────► added line numbers per file (diff mode)
 │
 ├─ for each file:
 │    source.read_source           decode + build byte-offset index
 │    mutators.generate_mutants    one AST visitor, compile-checked splices
 │
 ├─ sample (deterministic, seeded)
 ├─ baseline suite (green required)
 ├─ cache lookup (mutant + source + tests + config)
 ├─ ProcessPoolExecutor
 │    worker: copy project once → mutate one file → run → restore
 │
 └─ score + Wilson interval
      │
      ├─ term.render_report       ANSI terminal
      ├─ report_html.render_html  self-contained HTML
      ├─ report_html.render_badge SVG
      ├─ report_html.render_markdown PR comment
      └─ RunReport.to_dict        JSON / MCP
```

## Modules

| Module | Responsibility | Not responsible for |
| --- | --- | --- |
| `source.py` | Decoding, byte-offset-aware spans, splicing | Finding mutations |
| `mutators.py` | AST visitors, operator maps, compile validation, hints | Running tests |
| `diffmap.py` | `git diff -U0`, hunks, untracked files, path prefixes | Deciding what to mutate |
| `discovery.py` | Walking Python files, pruning, test-runner detection | Executing commands |
| `runner.py` | Popen, timeout tree-kill, test-name parsing, test counting | Choosing tests |
| `engine.py` | Scope, baseline, sampling, cache, workers, scoring | Formatting output |
| `scoring.py` | Mutation score, Wilson interval, grades | Reporting |
| `term.py` | Terminal rendering, ANSI/Unicode capability detection | Analysis |
| `report_html.py` | HTML, SVG badge, PR markdown | Analysis |
| `mcp.py` | JSON-RPC framing, tool schemas, tool dispatch | Analysis |
| `cli.py` | Commands, config merging, gates, artifacts | Analysis |

## Scope resolution

Three modes, in priority order:

1. `--lines N-M`: every candidate file, only AST nodes whose span intersects the range.
2. `--diff REF` (or `--staged`): only files in the diff, only added lines.
3. `--all` / default: every candidate file.

`fang run` without an explicit mode uses `HEAD` when the work tree has Python changes and
falls back to all files when it is clean. A non-git directory always uses all files.

Candidate files are `.py` files under `paths`, excluding common dependency/build
directories, test files (unless `mutate_tests`), files over `max_file_size`, and the
`exclude` globs.

## Mutation generation

`mutators._MutationFactory` is an `ast.NodeVisitor` with a context stack. It skips:

- module/class/function docstrings;
- decorators, argument defaults, annotations, and class bases;
- imports;
- `if __name__ == "__main__"` and `if TYPE_CHECKING` blocks;
- dunder assignments such as `__all__`;
- `return` inside `__init__`;
- calls named in `skip_calls` (default: `print`).

Every candidate is applied as a **text splice** at the original byte offsets. The result
is compiled before it is accepted, so an invalid mutation never reaches a test process.
Mutants carry absolute character offsets into the file plus the full mutated line for
display.

The operator set is deliberately small: comparison, boolean, arithmetic, constant,
return, conditional, statement removal. Each has a hint template that turns a survivor
into an actionable test idea.

## Execution and isolation

1. Run the baseline suite once in the **real project**. Refuse to continue if it is red
   or collects zero tests.
2. Compute a per-mutant timeout: `max(5s, min(120s, baseline * 5 + 2s))`, or `--timeout`.
3. Resolve cache hits before scheduling anything.
4. For each miss, create a task `(path, start, end, replacement)`.
5. With `--jobs > 1`, each process gets its own `tempfile.mkdtemp` copy of the project
   (`.git`, `.fang`, virtualenvs, caches, and build output are excluded). The worker
   reads the pristine file, splices the mutation, runs the configured test command with
   `cwd=workspace`, and restores the file in a `finally` block. It verifies the restore
   before returning.
6. A workspace is marked with a `.fang-workspace` file. `_execute` refuses to touch an
   absolute path, a path outside the workspace, or a directory without the marker. This
   prevents the class of bug where an absolute mutant path escapes isolation and mutates
   the developer's real source tree.
7. Statuses: `killed`, `survived`, `timeout`, `error` (mutant-induced crash), and
   `worker_error` (infrastructure). `worker_error` is excluded from the score and never
   cached.

With `--jobs 1` the same copy-and-restore path is used; there is no in-place mode.

## Cache

`.fang/cache.json` (versioned) maps a key to `{status, duration, killer, output}`.

Key inputs:

- mutant ID (path, span, original, replacement, operator);
- SHA-256 of the source file;
- fingerprint of the test suite: every test file, the test command, the Python version,
  Fang's version, and the enabled operators;
- config files (`pyproject.toml`, `pytest.ini`, `tox.ini`, `setup.cfg`, `.fang.json`).

Editing tests invalidates everything, which is intentional: a new test may kill a mutant
that previously survived. Only `killed`, `survived`, and `timeout` are cached.

## Sampling and statistics

`--sample N` sorts mutants by `sha1(seed + mutant_id)` and takes the first N. The result
is deterministic for a given seed and set of mutants, so repeated CI runs compare like
with like.

The displayed score is `100 * detected / evaluated`. When sampled, the report shows a
95% Wilson score interval. Wilson is used instead of the normal approximation because it
behaves sensibly at 0% and 100% and with small samples.

## Reporting

- **Terminal**: score, counts, baseline, average mutant time, survivor diffs, per-file
  bars, top killing tests, notes, verdict.
- **HTML**: one self-contained file. No external fonts, scripts, images, or CDNs. Filters
  and search are progressive enhancement; the cards are present in the markup.
- **Markdown**: a compact PR comment with a `<details>` list of survivors.
- **Badge**: a standalone SVG with the score and a grade colour.
- **JSON/MCP**: the full `RunReport` structure, including every mutant and its verdict.

## MCP

The server is a newline-delimited JSON-RPC 2.0 loop over stdio. It also accepts
`Content-Length` framing for clients that use it. `initialize` negotiates a protocol
version from `{2024-11-05, 2025-03-26, 2025-06-18}`, `tools/list` returns four schemas,
and `tools/call` dispatches to the same `engine.analyze` used by the CLI. Errors are
returned as tool results with `isError: true`, so the server stays alive.

Tool calls force small samples and at most four workers to keep an agent loop responsive.
The cache is shared with the CLI.

## Failure modes

| Failure | Behaviour |
| --- | --- |
| Suite is red | `AnalysisError`, exit 2, tail of the suite output |
| Zero tests collected | `AnalysisError`, exit 2 |
| Unknown git revision | `DiffError`, exit 2 |
| No mutants in scope | Report with `score: null`, exit 0 |
| Worker process dies | Remaining mutants retried sequentially, note in the report |
| Restore fails | `worker_error` for that mutant; not cached |
| Test command hangs | Per-mutant timeout, counted as detected, reported separately |
| Ctrl-C | Interrupt, exit 130; workers are terminated by the pool |

## Security

Fang executes the project's test command, exactly as CI would. Do not point it at
untrusted source. The MCP server exposes a test-running tool; run it in the same trust
boundary as your shell.
