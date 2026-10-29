import ast
import unittest

from fang.source import SourceFile, read_source, splice


class TestSourceFile(unittest.TestCase):
    def test_unicode_offsets_round_trip(self):
        text = 'x = 1\ncaf\u00e9 = "\u00e9\u00e9\u00e9"\ny = caf\u00e9 + 2\n'
        source = SourceFile("unicode.py", text)
        tree = ast.parse(text)
        node = tree.body[2].value
        start, end = source.span(node)
        self.assertEqual(source.text[start:end], "caf\u00e9 + 2")
        self.assertEqual(source.position(start), (3, 5))
        self.assertEqual(source.position(end), (3, 13))

    def test_multiline_node(self):
        text = "value = (\n    1 +\n    2\n)\n"
        source = SourceFile("multi.py", text)
        node = ast.parse(text).body[0].value
        start, end = source.span(node)
        # Parentheses are not part of the AST node; the BinOp spans the operands.
        self.assertEqual(source.text[start:end], "1 +\n    2")

    def test_splice(self):
        self.assertEqual(splice("abcdef", 2, 4, "XY"), "abXYef")

    def test_crlf(self):
        text = "a = 1\r\nb = a + 1\r\n"
        source = SourceFile("crlf.py", text)
        node = ast.parse(text).body[1].value
        start, end = source.span(node)
        self.assertEqual(source.text[start:end], "a + 1")
        self.assertEqual(source.position(start), (2, 5))

    def test_read_source(self):
        import os
        import tempfile

        handle, path = tempfile.mkstemp(suffix=".py")
        os.close(handle)
        try:
            with open(path, "w", encoding="utf-8", newline="") as stream:
                stream.write("x = 1\n")
            source = read_source(path)
            self.assertEqual(source.text, "x = 1\n")
            self.assertEqual(source.line_text(1), "x = 1")
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
