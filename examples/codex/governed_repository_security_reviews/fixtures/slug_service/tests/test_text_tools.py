import unittest

from src.text_tools import slugify


class ProtectedAcceptanceTests(unittest.TestCase):
    def test_ascii_title(self):
        self.assertEqual(slugify("Hello, World!"), "hello-world")

    def test_repeated_punctuation(self):
        self.assertEqual(slugify("  alpha --- beta  "), "alpha-beta")

    def test_empty_value(self):
        self.assertEqual(slugify(""), "")

    def test_unicode_acceptance(self):
        self.assertEqual(slugify("Crème Brûlée"), "creme-brulee")


if __name__ == "__main__":
    unittest.main()
