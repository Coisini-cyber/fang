import unittest

from fang.scoring import grade, mutation_score, score_interval, wilson_interval


class TestScoring(unittest.TestCase):
    def test_mutation_score(self):
        self.assertEqual(mutation_score(0, 0), None)
        self.assertEqual(mutation_score(3, 4), 75.0)

    def test_wilson_contains_estimate(self):
        low, high = wilson_interval(8, 10)
        self.assertLess(low, 0.8)
        self.assertGreater(high, 0.8)
        self.assertGreaterEqual(low, 0.0)
        self.assertLessEqual(high, 1.0)

    def test_wilson_edges(self):
        self.assertEqual(wilson_interval(0, 0), (0.0, 0.0))
        low, high = wilson_interval(0, 10)
        self.assertEqual(low, 0.0)
        self.assertGreater(high, 0.0)
        low, high = wilson_interval(10, 10)
        self.assertLess(low, 1.0)
        self.assertEqual(high, 1.0)

    def test_score_interval(self):
        self.assertEqual(score_interval(0, 0), None)
        low, high = score_interval(5, 10)
        self.assertTrue(0 <= low <= 50 <= high <= 100)

    def test_grades(self):
        self.assertEqual(grade(None), "n/a")
        self.assertEqual(grade(95), "A+")
        self.assertEqual(grade(85), "A")
        self.assertEqual(grade(75), "B")
        self.assertEqual(grade(65), "C")
        self.assertEqual(grade(55), "D")
        self.assertEqual(grade(10), "F")


if __name__ == "__main__":
    unittest.main()
