import ast
import unittest

from fang.mutators import (
    DEFAULT_OPERATORS,
    OPERATOR_LABELS,
    _short_repr,
    generate_mutants,
)
from fang.source import SourceFile

SOURCE = '''"""A module docstring with 100 and < inside."""

LIMIT = 100


def discount(total, tier="gold"):
    """Docstring with 42."""
    if total < LIMIT and tier != "basic":
        return total * 0.1
    print("side effect")
    return 0


class Cart:
    def __init__(self):
        self.items = []
        return self

    def total(self):
        return sum(self.items) + 1


def contains(items, needle):
    return needle in items


if __name__ == "__main__":
    print(discount(50))
'''


class TestMutators(unittest.TestCase):
    def setUp(self):
        self.source = SourceFile("sample.py", SOURCE)
        self.mutants = generate_mutants(self.source)

    def test_all_mutants_compile(self):
        self.assertGreater(len(self.mutants), 10)
        for mutant in self.mutants:
            candidate = (
                self.source.text[: mutant.start]
                + mutant.replacement
                + self.source.text[mutant.end :]
            )
            ast.parse(candidate)
            self.assertNotEqual(candidate, self.source.text)

    def test_deterministic(self):
        again = generate_mutants(SourceFile("sample.py", SOURCE))
        self.assertEqual([m.id for m in self.mutants], [m.id for m in again])
        self.assertEqual(
            [(m.start, m.end, m.replacement) for m in self.mutants],
            [(m.start, m.end, m.replacement) for m in again],
        )

    def test_operators_present(self):
        operators = {mutant.operator for mutant in self.mutants}
        self.assertEqual(operators, set(DEFAULT_OPERATORS))

    def test_skips_docstrings_main_guard_and_imports(self):
        for mutant in self.mutants:
            self.assertNotIn("module docstring", mutant.source_line)
            self.assertNotIn("Docstring", mutant.source_line)
            self.assertNotIn("__main__", mutant.source_line)
            self.assertNotIn("discount(50)", mutant.source_line)

    def test_init_return_is_not_mutated(self):
        for mutant in self.mutants:
            self.assertFalse(mutant.context.endswith("__init__") and mutant.operator == "return")

    def test_only_lines_filters(self):
        filtered = generate_mutants(self.source, only_lines={8})
        self.assertTrue(filtered)
        for mutant in filtered:
            self.assertEqual(mutant.line, 8)

    def test_skip_calls(self):
        with_print = generate_mutants(SourceFile("sample.py", SOURCE), skip_calls=[])
        without_print = generate_mutants(
            SourceFile("sample.py", SOURCE), skip_calls=["print"]
        )
        self.assertTrue(
            any(m.operator == "statement" and "side effect" in m.source_line for m in with_print)
        )
        self.assertFalse(
            any(m.operator == "statement" and "side effect" in m.source_line for m in without_print)
        )

    def test_comparison_replacement(self):
        comparisons = [m for m in self.mutants if m.operator == "comparison"]
        pairs = {(m.original, m.replacement) for m in comparisons}
        self.assertIn(("<", "<="), pairs)
        self.assertIn(("!=", "=="), pairs)
        self.assertIn(("in", "not in"), pairs)

    def test_mutated_line(self):
        comparison = next(m for m in self.mutants if m.operator == "comparison" and m.line == 8)
        self.assertIsNotNone(comparison.mutated_line)
        self.assertIn("<=", comparison.mutated_line)

    def test_unicode_offsets(self):
        text = 'caf\u00e9 = 1\nif caf\u00e9 < 2:\n    result = caf\u00e9 + 1\n'
        source = SourceFile("unicode.py", text)
        mutants = generate_mutants(source)
        self.assertTrue(mutants)
        for mutant in mutants:
            candidate = (
                text[: mutant.start] + mutant.replacement + text[mutant.end :]
            )
            ast.parse(candidate)

    def test_multiline_expression(self):
        text = "def f(a, b):\n    return (\n        a + b\n    )\n"
        source = SourceFile("multi.py", text)
        mutants = generate_mutants(source)
        arithmetic = [m for m in mutants if m.operator == "arithmetic"]
        self.assertTrue(arithmetic)
        for mutant in arithmetic:
            candidate = text[: mutant.start] + mutant.replacement + text[mutant.end :]
            ast.parse(candidate)

    def test_no_mutants_for_pass(self):
        source = SourceFile("empty.py", "def f():\n    pass\n")
        self.assertEqual(generate_mutants(source), [])

    def test_every_comparison_operator(self):
        text = (
            "def f(a, b):\n"
            "    return [a == b, a != b, a < b, a <= b, a > b, a >= b,\n"
            "            a is b, a is not b, a in b, a not in b]\n"
        )
        mutants = generate_mutants(SourceFile("compare.py", text))
        pairs = {(m.original, m.replacement) for m in mutants if m.operator == "comparison"}
        expected = {
            ("==", "!="),
            ("!=", "=="),
            ("<", "<="),
            ("<=", "<"),
            (">", ">="),
            (">=", ">"),
            ("is", "is not"),
            ("is not", "is"),
            ("in", "not in"),
            ("not in", "in"),
        }
        self.assertEqual(pairs, expected)

    def test_every_arithmetic_operator(self):
        text = (
            "def f(a, b):\n"
            "    a += b\n"
            "    a -= b\n"
            "    a *= b\n"
            "    a /= b\n"
            "    a //= b\n"
            "    return a + b - a * b / a // b\n"
        )
        mutants = generate_mutants(SourceFile("arith.py", text))
        pairs = {(m.original, m.replacement) for m in mutants if m.operator == "arithmetic"}
        expected = {
            ("+=", "-="),
            ("-=", "+="),
            ("*=", "/="),
            ("/=", "*="),
            ("//=", "/="),
            ("+", "-"),
            ("-", "+"),
            ("*", "/"),
            ("/", "*"),
            ("//", "/"),
        }
        self.assertEqual(pairs, expected)

    def test_boolean_operators(self):
        text = "def f(a, b):\n    if a and b or not a:\n        return True\n"
        mutants = generate_mutants(SourceFile("bool.py", text))
        pairs = {(m.original, m.replacement) for m in mutants if m.operator == "boolean"}
        self.assertIn(("and", "or"), pairs)
        self.assertIn(("or", "and"), pairs)
        self.assertIn(("not a", "a"), pairs)

    def test_conditional_is_skipped_for_not(self):
        text = "def f(a):\n    if not a:\n        return 1\n    return 0\n"
        mutants = generate_mutants(SourceFile("not.py", text))
        self.assertFalse(any(m.operator == "conditional" for m in mutants))

    def test_context_is_dotted(self):
        text = (
            "class Outer:\n"
            "    def inner(self):\n"
            "        return 1\n"
        )
        mutants = generate_mutants(SourceFile("ctx.py", text))
        self.assertTrue(mutants)
        self.assertTrue(all(m.context == "Outer.inner" for m in mutants))

    def test_descriptions_and_hints_are_present(self):
        for mutant in self.mutants:
            self.assertTrue(mutant.description)
            self.assertTrue(mutant.hint)
            self.assertIn(mutant.operator, OPERATOR_LABELS)

    def test_statement_removal_of_method_call(self):
        text = "def f(logger):\n    logger.info('x')\n    return 1\n"
        mutants = generate_mutants(SourceFile("call.py", text), skip_calls=[])
        statements = [m for m in mutants if m.operator == "statement"]
        self.assertEqual(len(statements), 1)
        self.assertIn("logger.info", statements[0].source_line)

    def test_empty_string_and_bytes_constants(self):
        text = "x = \"\"\ny = b\"\"\nz = 0.0\n"
        mutants = generate_mutants(SourceFile("const.py", text))
        pairs = {(m.original, m.replacement) for m in mutants if m.operator == "constant"}
        self.assertIn(('""', '"fang"'), pairs)
        self.assertIn(('b""', 'b"fang"'), pairs)
        self.assertIn(("0.0", "1.0"), pairs)

    def test_none_constant_is_skipped(self):
        source = SourceFile("none.py", "x = None\n")
        self.assertEqual(generate_mutants(source), [])

    def test_short_repr(self):
        self.assertEqual(_short_repr("abc"), "'abc'")
        self.assertLessEqual(len(_short_repr("x" * 100)), 32)
        self.assertTrue(_short_repr("x" * 100).endswith("..."))

    def test_multiline_statement_removal(self):
        text = (
            "def f(logger):\n"
            "    logger.info(\n"
            "        'a long message',\n"
            "    )\n"
            "    return 1\n"
        )
        mutants = generate_mutants(SourceFile("multi_call.py", text), skip_calls=[])
        statements = [m for m in mutants if m.operator == "statement"]
        self.assertEqual(len(statements), 1)
        candidate = text[: statements[0].start] + "pass" + text[statements[0].end :]
        ast.parse(candidate)


if __name__ == "__main__":
    unittest.main()
