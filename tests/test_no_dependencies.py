import ast
import os
import unittest

STDLIB = {
    "__future__",
    "argparse",
    "ast",
    "atexit",
    "bisect",
    "collections",
    "concurrent",
    "ctypes",
    "dataclasses",
    "datetime",
    "fnmatch",
    "hashlib",
    "html",
    "importlib",
    "io",
    "json",
    "math",
    "os",
    "posixpath",
    "re",
    "shlex",
    "shutil",
    "signal",
    "subprocess",
    "sys",
    "tempfile",
    "textwrap",
    "time",
    "typing",
    "webbrowser",
}


class ZeroDependencyTest(unittest.TestCase):
    def test_only_stdlib_imports(self):
        package = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fang")
        violations = []
        for name in sorted(os.listdir(package)):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(package, name), encoding="utf-8") as handle:
                tree = ast.parse(handle.read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        root = alias.name.split(".")[0]
                        if root not in STDLIB:
                            violations.append((name, alias.name))
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        continue
                    root = (node.module or "").split(".")[0]
                    if root and root not in STDLIB:
                        violations.append((name, node.module))
        self.assertEqual(violations, [], "fang must not import third-party packages")


if __name__ == "__main__":
    unittest.main()
