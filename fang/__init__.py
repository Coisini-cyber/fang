"""Fang — mutation testing that bites.

Fang mutates only the Python lines touched by a diff, runs the test suite with
early exit, and reports which behavioural changes your tests failed to notice.
It has no runtime dependencies outside the Python standard library.
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
