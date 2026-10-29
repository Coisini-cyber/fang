from __future__ import annotations

import math
from typing import Optional, Tuple


def wilson_interval(successes: int, total: int, z: float = 1.96) -> Tuple[float, float]:
    """Wilson score interval for a binomial proportion, returned as 0..1."""
    if total <= 0:
        return (0.0, 0.0)
    p = successes / float(total)
    denominator = 1.0 + z * z / total
    centre = (p + z * z / (2.0 * total)) / denominator
    margin = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * total)) / total) / denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def mutation_score(killed: int, total: int) -> Optional[float]:
    if total <= 0:
        return None
    return 100.0 * killed / total


def score_interval(killed: int, total: int) -> Optional[Tuple[float, float]]:
    if total <= 0:
        return None
    low, high = wilson_interval(killed, total)
    return (low * 100.0, high * 100.0)


def grade(score: Optional[float]) -> str:
    if score is None:
        return "n/a"
    if score >= 90:
        return "A+"
    if score >= 80:
        return "A"
    if score >= 70:
        return "B"
    if score >= 60:
        return "C"
    if score >= 50:
        return "D"
    return "F"


def grade_word(score: Optional[float]) -> str:
    if score is None:
        return "not measured"
    if score >= 90:
        return "excellent"
    if score >= 80:
        return "strong"
    if score >= 70:
        return "decent"
    if score >= 60:
        return "thin"
    if score >= 50:
        return "weak"
    return "toothless"
