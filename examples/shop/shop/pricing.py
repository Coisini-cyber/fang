"""Pricing rules for the demo shop."""

from __future__ import annotations

FREE_SHIPPING_THRESHOLD = 100.0
EXPRESS_FEE = 9.99
STANDARD_FEE = 4.99

TIER_RATES = {
    "basic": 0.0,
    "silver": 0.05,
    "gold": 0.10,
}


def discount_rate(tier: str) -> float:
    """Return the base discount rate for a customer tier."""
    return TIER_RATES.get(tier, 0.0)


def discount_for(total: float, tier: str) -> float:
    """Gold customers get 15% on orders at or above the free-shipping threshold."""
    if total >= FREE_SHIPPING_THRESHOLD and tier == "gold":
        return round(total * 0.15, 2)
    return round(total * discount_rate(tier), 2)


def shipping_fee(total: float, express: bool = False) -> float:
    """Free standard shipping above the threshold; express is always paid."""
    if express:
        return EXPRESS_FEE
    if total >= FREE_SHIPPING_THRESHOLD:
        return 0.0
    return STANDARD_FEE
