"""Synthetic inventory helpers; no customer or production data."""


def available_units(stock: int, reserved: int) -> int:
    """Return the non-negative quantity available for a synthetic order."""
    return max(stock - reserved, 0)
