import unittest

from shop.pricing import discount_for, shipping_fee


class TestPricing(unittest.TestCase):
    def test_gold_gets_volume_discount(self):
        self.assertEqual(discount_for(200.0, "gold"), 30.0)

    def test_silver_gets_base_discount(self):
        self.assertEqual(discount_for(200.0, "silver"), 10.0)

    def test_standard_shipping_is_charged_below_threshold(self):
        self.assertEqual(shipping_fee(20.0), 4.99)

    def test_shipping_is_free_above_threshold(self):
        self.assertEqual(shipping_fee(150.0), 0.0)


if __name__ == "__main__":
    unittest.main()
