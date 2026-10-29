"""A shopping cart."""

from __future__ import annotations

from typing import Dict, List

from .pricing import discount_for, shipping_fee


class Cart:
    def __init__(self, tier: str = "basic", express: bool = False) -> None:
        self.tier = tier
        self.express = express
        self.items: List[Dict[str, object]] = []

    def add(self, sku: str, price: float, quantity: int = 1) -> None:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        self.items.append({"sku": sku, "price": price, "quantity": quantity})

    def subtotal(self) -> float:
        return round(
            sum(float(item["price"]) * int(item["quantity"]) for item in self.items), 2
        )

    def total(self) -> float:
        subtotal = self.subtotal()
        discount = discount_for(subtotal, self.tier)
        shipping = shipping_fee(subtotal, self.express)
        return round(subtotal - discount + shipping, 2)

    def __len__(self) -> int:
        return len(self.items)
