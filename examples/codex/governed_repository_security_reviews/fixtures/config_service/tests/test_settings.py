import unittest

from src.settings import page_size


class SettingsTests(unittest.TestCase):
    def test_default_range(self):
        self.assertEqual(page_size(25), 25)

    def test_lower_bound(self):
        self.assertEqual(page_size(-4), 1)

    def test_upper_bound(self):
        self.assertEqual(page_size(400), 100)


if __name__ == "__main__":
    unittest.main()
