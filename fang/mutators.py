from __future__ import annotations

import ast
import re
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .models import Mutant
from .source import SourceFile
from .util import sha1_short, truncate

OPERATOR_LABELS: Dict[str, str] = {
    "comparison": "comparison",
    "boolean": "boolean logic",
    "arithmetic": "arithmetic",
    "constant": "constant",
    "return": "return value",
    "conditional": "condition",
    "statement": "statement removal",
}

DEFAULT_OPERATORS: Tuple[str, ...] = tuple(OPERATOR_LABELS)

_COMPARE_SYMBOL: Dict[type, str] = {
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
    ast.Is: "is",
    ast.IsNot: "is not",
    ast.In: "in",
    ast.NotIn: "not in",
}

_COMPARE_REPLACEMENT: Dict[str, str] = {
    "==": "!=",
    "!=": "==",
    "<": "<=",
    "<=": "<",
    ">": ">=",
    ">=": ">",
    "is": "is not",
    "is not": "is",
    "in": "not in",
    "not in": "in",
}

_BINOP_REPLACEMENT: Dict[type, Tuple[str, str]] = {
    ast.Add: ("+", "-"),
    ast.Sub: ("-", "+"),
    ast.Mult: ("*", "/"),
    ast.Div: ("/", "*"),
    ast.FloorDiv: ("//", "/"),
}

_AUG_REPLACEMENT: Dict[type, Tuple[str, str]] = {
    ast.Add: ("+=", "-="),
    ast.Sub: ("-=", "+="),
    ast.Mult: ("*=", "/="),
    ast.Div: ("/=", "*="),
    ast.FloorDiv: ("//=", "/="),
}

_COMPARE_PATTERN = re.compile(
    r"\bnot\s+in\b|\bis\s+not\b|==|!=|<=|>=|<|>|\bin\b|\bis\b"
)
_BOOL_PATTERN = re.compile(r"\band\b|\bor\b")

_OPERATOR_HINTS: Dict[str, str] = {
    "comparison": "Add a test at the boundary where this comparison flips.",
    "boolean": "Cover a case where only one operand is true.",
    "arithmetic": "Assert the exact numeric result, not just its type.",
    "constant": "Assert against a different value so this constant is observable.",
    "return": "Assert the return value; calling the function is not enough.",
    "conditional": "Test the branch this condition guards, not only the happy path.",
    "statement": "Assert the side effect of this call (state, output, or log).",
}


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


class _MutationFactory(ast.NodeVisitor):
    def __init__(
        self,
        sf: SourceFile,
        only_lines: Optional[Set[int]] = None,
        operators: Optional[Sequence[str]] = None,
        skip_calls: Iterable[str] = (),
    ) -> None:
        self.sf = sf
        self.only_lines = only_lines
        self.operators = set(operators or DEFAULT_OPERATORS)
        self.skip_calls = {name.lower() for name in skip_calls}
        self.context: List[str] = []
        self.docstrings: Set[int] = set()
        self.mutants: List[Mutant] = []
        self._seen: Set[Tuple[int, int, str]] = set()

    # -- plumbing ---------------------------------------------------------

    def _collect_docstrings(self, tree: ast.AST) -> None:
        holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        for node in ast.walk(tree):
            if isinstance(node, holders) and node.body:
                first = node.body[0]
                if (
                    isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)
                ):
                    self.docstrings.add(id(first.value))

    def _context_name(self) -> str:
        return ".".join(self.context)

    def _in_scope(self, start: int, end: int) -> bool:
        if self.only_lines is None:
            return True
        first, _ = self.sf.position(start)
        last, _ = self.sf.position(end)
        return any(line in self.only_lines for line in range(first, last + 1))

    def _add(
        self,
        operator: str,
        start: int,
        end: int,
        replacement: str,
        scope_node: ast.AST,
        description: str,
        hint: Optional[str] = None,
    ) -> bool:
        if operator not in self.operators:
            return False
        if start >= end:
            return False
        original = self.sf.text[start:end]
        if original == replacement:
            return False
        if not self._in_scope(start, end):
            return False
        key = (start, end, replacement)
        if key in self._seen:
            return False

        candidate = self.sf.text[:start] + replacement + self.sf.text[end:]
        try:
            compile(candidate, self.sf.path, "exec", dont_inherit=True)
        except (SyntaxError, ValueError, TypeError):
            return False

        self._seen.add(key)
        scope_start, scope_end = self.sf.span(scope_node)
        expression_before = self.sf.text[scope_start:scope_end]
        expression_after = (
            self.sf.text[scope_start:start] + replacement + self.sf.text[end:scope_end]
        )
        line, col = self.sf.position(start)
        end_line, end_col = self.sf.position(end)
        source_line = self.sf.line_text(line)
        if line == end_line:
            mutated_line = (
                source_line[: col - 1]
                + replacement
                + source_line[col - 1 + (end - start) :]
            )
        else:
            mutated_line = None

        mutant_id = sha1_short(
            "%s\0%d\0%d\0%s\0%s\0%s"
            % (self.sf.path, start, end, original, replacement, operator)
        )
        self.mutants.append(
            Mutant(
                id=mutant_id,
                path=self.sf.path,
                start=start,
                end=end,
                line=line,
                col=col,
                end_line=end_line,
                end_col=end_col,
                operator=operator,
                context=self._context_name(),
                original=original,
                replacement=replacement,
                expression_before=expression_before,
                expression_after=expression_after,
                source_line=source_line,
                mutated_line=mutated_line,
                description=description,
                hint=hint or _OPERATOR_HINTS.get(operator, ""),
            )
        )
        return True

    def _token_between(
        self, left: ast.AST, right: ast.AST, pattern: re.Pattern
    ) -> Optional[Tuple[int, int, str]]:
        start = self.sf.span(left)[1]
        end = self.sf.span(right)[0]
        gap = self.sf.text[start:end]
        match = pattern.search(gap)
        if not match:
            return None
        token = re.sub(r"\s+", " ", match.group(0))
        return start + match.start(), start + match.end(), token

    def _find_text_between(
        self, left: ast.AST, right: ast.AST, needle: str
    ) -> Optional[Tuple[int, int, str]]:
        start = self.sf.span(left)[1]
        end = self.sf.span(right)[0]
        gap = self.sf.text[start:end]
        index = gap.find(needle)
        if index < 0:
            return None
        return start + index, start + index + len(needle), needle

    # -- structural skips -------------------------------------------------

    def visit_Module(self, node: ast.Module) -> None:
        self._collect_docstrings(node)
        for statement in node.body:
            self.visit(statement)

    def _visit_function(self, node) -> None:
        self.context.append(node.name)
        for statement in node.body:
            self.visit(statement)
        self.context.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.context.append(node.name)
        for statement in node.body:
            self.visit(statement)
        self.context.pop()

    def visit_Import(self, node: ast.Import) -> None:
        return

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        return

    def visit_Global(self, node: ast.Global) -> None:
        return

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        return

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.startswith("__") and target.id.endswith("__"):
                return
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name) and node.target.id.startswith("__") and node.target.id.endswith("__"):
            return
        if node.value is not None:
            self.visit(node.value)

    @staticmethod
    def _is_main_guard(test: ast.AST) -> bool:
        if not isinstance(test, ast.Compare):
            return False
        if not (isinstance(test.left, ast.Name) and test.left.id == "__name__"):
            return False
        for op, comparator in zip(test.ops, test.comparators):
            if isinstance(op, ast.Eq) and isinstance(comparator, ast.Constant) and comparator.value == "__main__":
                return True
        return False

    @staticmethod
    def _is_type_checking(test: ast.AST) -> bool:
        return isinstance(test, ast.Name) and test.id == "TYPE_CHECKING"

    def visit_If(self, node: ast.If) -> None:
        if self._is_main_guard(node.test) or self._is_type_checking(node.test):
            return
        self._consider_condition(node.test)
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self._consider_condition(node.test)
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self._consider_condition(node.test)
        self.generic_visit(node)

    # -- operator generators ---------------------------------------------

    def _consider_condition(self, test: ast.AST) -> None:
        if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
            return
        start, end = self.sf.span(test)
        source = self.sf.text[start:end]
        self._add(
            "conditional",
            start,
            end,
            "not (%s)" % source,
            test,
            "negate condition `%s`" % truncate(source, 64),
        )

    def visit_Compare(self, node: ast.Compare) -> None:
        if "comparison" in self.operators:
            operands = [node.left] + list(node.comparators)
            for index, op in enumerate(node.ops):
                symbol = _COMPARE_SYMBOL.get(type(op))
                if symbol is None:
                    continue
                found = self._token_between(operands[index], operands[index + 1], _COMPARE_PATTERN)
                if not found:
                    continue
                start, end, token = found
                if token != symbol:
                    continue
                replacement = _COMPARE_REPLACEMENT.get(token)
                if replacement is None:
                    continue
                self._add(
                    "comparison",
                    start,
                    end,
                    replacement,
                    node,
                    "`%s` -> `%s` in `%s`"
                    % (token, replacement, truncate(self.sf.segment(node), 64)),
                )
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        if "boolean" in self.operators:
            token = "and" if isinstance(node.op, ast.And) else "or"
            replacement = "or" if token == "and" else "and"
            for index in range(len(node.values) - 1):
                found = self._token_between(node.values[index], node.values[index + 1], _BOOL_PATTERN)
                if not found:
                    continue
                start, end, actual = found
                if actual != token:
                    continue
                self._add(
                    "boolean",
                    start,
                    end,
                    replacement,
                    node,
                    "`%s` -> `%s` in `%s`"
                    % (token, replacement, truncate(self.sf.segment(node), 64)),
                )
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        pair = _BINOP_REPLACEMENT.get(type(node.op))
        if pair and "arithmetic" in self.operators:
            found = self._find_text_between(node.left, node.right, pair[0])
            if found:
                start, end, token = found
                self._add(
                    "arithmetic",
                    start,
                    end,
                    pair[1],
                    node,
                    "`%s` -> `%s` in `%s`"
                    % (token, pair[1], truncate(self.sf.segment(node), 64)),
                )
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        pair = _AUG_REPLACEMENT.get(type(node.op))
        if pair and "arithmetic" in self.operators:
            found = self._find_text_between(node.target, node.value, pair[0])
            if found:
                start, end, token = found
                self._add(
                    "arithmetic",
                    start,
                    end,
                    pair[1],
                    node,
                    "`%s` -> `%s`" % (token, pair[1]),
                )
        self.generic_visit(node)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> None:
        if isinstance(node.op, ast.USub) and "arithmetic" in self.operators:
            operand = self.sf.segment(node.operand)
            start, end = self.sf.span(node)
            self._add(
                "arithmetic",
                start,
                end,
                operand,
                node,
                "remove negation: `%s` -> `%s`" % (truncate(self.sf.segment(node), 48), truncate(operand, 48)),
            )
        elif isinstance(node.op, ast.Not) and "boolean" in self.operators:
            operand = self.sf.segment(node.operand)
            start, end = self.sf.span(node)
            self._add(
                "boolean",
                start,
                end,
                operand,
                node,
                "remove `not`: `%s`" % truncate(operand, 64),
            )
        self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> None:
        if "return" not in self.operators or node.value is None:
            return
        if isinstance(node.value, ast.Constant) and node.value.value is None:
            return
        if self.context and self.context[-1] == "__init__":
            return
        start, end = self.sf.span(node)
        source = truncate(self.sf.text[start:end], 64)
        self._add(
            "return",
            start,
            end,
            "return None",
            node,
            "`%s` -> `return None`" % source,
        )
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if "constant" not in self.operators or id(node) in self.docstrings:
            return
        value = node.value
        if value is None or value is Ellipsis:
            return
        if isinstance(value, bool):
            replacement = "False" if value else "True"
            description = "`%s` -> `%s`" % (value, replacement)
        elif isinstance(value, int):
            new_value = 1 if value == 0 else (0 if value == 1 else value + 1)
            replacement = repr(new_value)
            description = "`%s` -> `%s`" % (value, replacement)
        elif isinstance(value, float):
            new_value = 1.0 if value == 0.0 else value + 1.0
            replacement = repr(new_value)
            description = "`%s` -> `%s`" % (value, replacement)
        elif isinstance(value, str):
            replacement = '""' if value else '"fang"'
            description = "string %s -> %s" % (_short_repr(value), replacement)
        elif isinstance(value, bytes):
            replacement = 'b""' if value else 'b"fang"'
            description = "bytes %s -> %s" % (_short_repr(value), replacement)
        else:
            return
        start, end = self.sf.span(node)
        self._add("constant", start, end, replacement, node, description)

    def visit_Expr(self, node: ast.Expr) -> None:
        if (
            "statement" in self.operators
            and isinstance(node.value, ast.Call)
            and id(node.value) not in self.docstrings
        ):
            name = _call_name(node.value)
            if name.lower() not in self.skip_calls:
                start, end = self.sf.span(node)
                source = truncate(self.sf.text[start:end], 64)
                self._add(
                    "statement",
                    start,
                    end,
                    "pass",
                    node,
                    "remove `%s`" % source,
                )
        self.generic_visit(node)


def _short_repr(value) -> str:
    text = repr(value)
    if len(text) > 32:
        return text[:29] + "..."
    return text


def generate_mutants(
    sf: SourceFile,
    only_lines: Optional[Set[int]] = None,
    operators: Optional[Sequence[str]] = None,
    skip_calls: Iterable[str] = (),
) -> List[Mutant]:
    """Return deterministic, compile-checked mutants for one source file."""
    tree = ast.parse(sf.text, filename=sf.path)
    factory = _MutationFactory(sf, only_lines=only_lines, operators=operators, skip_calls=skip_calls)
    factory.visit(tree)
    factory.mutants.sort(key=lambda mutant: (mutant.line, mutant.col, mutant.operator, mutant.replacement))
    return factory.mutants
