import unittest

from check_path_portability import find_path_errors


class PathPortabilityTests(unittest.TestCase):
    def assert_violation(self, message: str, *paths: str) -> None:
        errors = find_path_errors(paths)
        self.assertTrue(
            any(message in error for error in errors),
            f"Expected {message!r} in {errors!r}",
        )

    def test_accepts_portable_paths(self) -> None:
        self.assertEqual(
            find_path_errors(["README.md", ".github/workflows/ci.yml", "docs/résumé.md"]),
            [],
        )

    def test_rejects_leading_or_trailing_space_and_period(self) -> None:
        self.assert_violation("Leading space", "docs/ example.md")
        self.assert_violation("Trailing space or period", "docs/example.md ")
        self.assert_violation("Trailing space or period", "docs/example.")

    def test_rejects_reserved_device_names(self) -> None:
        for path in ("CON", "docs/nul.txt", "data/COM9.json", "data/LPT¹.csv"):
            with self.subTest(path=path):
                self.assert_violation("reserved device name", path)

    def test_rejects_control_characters(self) -> None:
        self.assert_violation("U+0009", "docs/bad\tname.md")
        self.assert_violation("U+001F", "docs/bad\x1fname.md")

    def test_rejects_windows_invalid_characters(self) -> None:
        for character in '<>:"\\|?*':
            with self.subTest(character=character):
                self.assert_violation("Windows-invalid character", f"docs/bad{character}name.md")

    def test_rejects_case_and_trim_collisions(self) -> None:
        self.assert_violation(
            "Windows-normalized path collision",
            "Docs/Example.md",
            "docs/example.MD",
        )
        self.assert_violation(
            "Windows-normalized path collision",
            "docs/example/file.json",
            "docs/example /file.json",
        )


if __name__ == "__main__":
    unittest.main()
