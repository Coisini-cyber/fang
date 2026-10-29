"""A deliberately small in-memory inventory."""

from __future__ import annotations

from typing import Dict


class Inventory:
    def __init__(self) -> None:
        self.stock: Dict[str, int] = {}

    def add(self, sku: str, count: int) -> None:
        if count < 0:
            raise ValueError("cannot add a negative count")
        self.stock[sku] = self.stock.get(sku, 0) + count

    def take(self, sku: str, count: int) -> bool:
        available = self.stock.get(sku, 0)
        if count > available:
            raise ValueError("not enough stock for %s" % sku)
        self.stock[sku] = available - count
        return True

    def available(self, sku: str) -> int:
        return self.stock.get(sku, 0)
