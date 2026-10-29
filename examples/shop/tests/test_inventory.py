import unittest

from shop.inventory import Inventory


class TestInventory(unittest.TestCase):
    def test_add_and_take(self):
        inventory = Inventory()
        inventory.add("widget", 5)
        inventory.take("widget", 3)
        self.assertEqual(inventory.available("widget"), 2)

    def test_cannot_take_more_than_available(self):
        inventory = Inventory()
        inventory.add("widget", 5)
        with self.assertRaises(ValueError):
            inventory.take("widget", 10)


if __name__ == "__main__":
    unittest.main()
