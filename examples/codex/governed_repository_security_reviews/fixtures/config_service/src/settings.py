"""Synthetic, deliberately non-sensitive feature settings."""

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def page_size(requested: int) -> int:
    return max(1, min(requested, MAX_PAGE_SIZE))
