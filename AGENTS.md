# Working on Fang

This file is for coding agents and new contributors. Fang is pure Python 3.9+ with no
third-party runtime dependencies. Keep it that way.

## Ground rules

- **No runtime dependencies.** The test `tests/test_no_dependencies.py` parses every
  module in `fang/` and fails on a non-stdlib import. Do not add `rich`, `click`,
  `pytest`, `requests`, or an MCP SDK.
- **Never mutate the real project.** Test execution happens in a temporary copy marked
  with `.fang-workspace`. `engine._execute` must keep its absolute-path, marker, and
  common-path guards.
- **A green baseline is non-negotiable.** Do not add an "ignore baseline failures" mode;
  it makes every mutant look killed.
- **Never cache `worker_error`.** Cache poisoning once produced a fake 100% score and is
  covered by the cache rules in `engine.py`/`cache.py`.
- **Mutant paths stay project-relative.** An absolute `mutant.path` makes
  `os.path.join(workspace, path)` escape the workspace. `SourceFile.path` is set to the
  relative path in `engine.analyze` for exactly this reason.
- **The HTML report stays self-contained.** No CDN, no external font, no remote image.

## Commands

```bash
python -m compileall -q fang
python -m unittest discover -s tests -v        # under a minute, 89 tests
python -m fang doctor examples/shop
python -m fang run examples/shop --all --jobs 2
```

## Before you finish a change

1. Run the full unit suite.
2. Run the demo: `python -m fang run examples/shop --all --no-cache --jobs 2`.
   The source tree must be byte-identical afterwards (`git status`).
3. For changes to the mutation engine, run a focused self-audit:

   ```bash
   python -m fang run . --all --paths fang/mutators.py \
     --test-command "python -m unittest tests.test_mutators" \
     --sample 60 --jobs 4 --min-score 0
   ```

   Read the survivors. Add a test only when the survivor represents observable behaviour;
   document equivalent mutants instead of writing a test that asserts nothing.

## Using Fang on your own change

- Inner loop: `python -m fang run --diff HEAD --sample 40`
- Before a PR: `python -m fang run --diff origin/main --sample 120 --min-score 80`
- Focus a module: `python -m fang run . --all --paths fang/engine.py --sample 60`
- Machine output: add `--json --no-report`

If the diff has no added Python lines, Fang reports `score: null`. That is not a failure.

## MCP

`python -m fang mcp <root>` exposes `fang_check_diff`, `fang_mutation_score`,
`fang_list_survivors`, and `fang_doctor`. The server writes only JSON-RPC to stdout; every
diagnostic must go to stderr.

## Style

Match the surrounding code: `from __future__ import annotations`, small dataclasses,
explicit error messages, and no clever metaprogramming. Keep functions testable without a
network or a real user project.
