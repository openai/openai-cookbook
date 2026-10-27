import unittest

from src.inventory import available_units


class InventoryTests(unittest.TestCase):
    def test_available_units(self):
        self.assertEqual(available_units(10, 3), 7)

    def test_never_negative(self):
        self.assertEqual(available_units(2, 8), 0)


if __name__ == "__main__":
    unittest.main()
