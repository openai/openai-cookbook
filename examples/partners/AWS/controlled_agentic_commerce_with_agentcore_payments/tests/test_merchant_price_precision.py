from decimal import Decimal

import pytest

from agentic_commerce.merchant import SyntheticMerchant
from agentic_commerce.payments import LocalPaymentProcessor


def test_synthetic_merchant_preserves_exact_usdc_atomic_amounts() -> None:
    one_atomic_unit = SyntheticMerchant(
        LocalPaymentProcessor(),
        price=Decimal("0.000001"),
    )
    normal_price = SyntheticMerchant(
        LocalPaymentProcessor(),
        price=Decimal("0.25"),
    )

    assert one_atomic_unit.requirement.amount == "1"
    assert normal_price.requirement.amount == "250000"


@pytest.mark.parametrize("price", [Decimal("0"), Decimal("-0.01")])
def test_synthetic_merchant_rejects_non_positive_prices(price: Decimal) -> None:
    with pytest.raises(ValueError, match="price must be positive"):
        SyntheticMerchant(LocalPaymentProcessor(), price=price)


@pytest.mark.parametrize(
    "price",
    [Decimal("0.0000009"), Decimal("0.1234567")],
)
def test_synthetic_merchant_rejects_fractional_atomic_units(price: Decimal) -> None:
    with pytest.raises(ValueError, match="at most 6 decimal places"):
        SyntheticMerchant(LocalPaymentProcessor(), price=price)
