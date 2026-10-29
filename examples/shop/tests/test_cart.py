import unittest

from shop.cart import Cart


class TestCart(unittest.TestCase):
    def test_empty_cart(self):
        self.assertEqual(Cart().total(), 4.99)

    def test_total_adds_shipping(self):
        cart = Cart()
        cart.add("mug", 20.0, 2)
        self.assertEqual(cart.subtotal(), 40.0)
        self.assertEqual(cart.total(), 44.99)

    def test_gold_cart_applies_discount(self):
        cart = Cart(tier="gold")
        cart.add("desk", 200.0)
        self.assertEqual(cart.total(), 170.0)

    def test_len(self):
        cart = Cart()
        cart.add("pen", 1.0)
        self.assertEqual(len(cart), 1)


if __name__ == "__main__":
    unittest.main()
