import unittest

from shipping import shipping_cost  # type: ignore[import-not-found]


class ShippingTests(unittest.TestCase):
    def test_standard_shipping_is_free_over_100(self) -> None:
        self.assertEqual(shipping_cost(125), 0)

    def test_express_shipping_is_never_free(self) -> None:
        self.assertEqual(shipping_cost(125, express=True), 15)
