"""Проверки правил продажи без подключения к PostgreSQL."""

from decimal import Decimal
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from auctions.models import Buyer, Lot, LotStatus
from auctions.schemas import SaleCreate
from auctions.services.sales import (
    BuyerNotFoundError,
    LotAlreadySoldError,
    LotNotFoundError,
    PriceBelowStartingError,
    register_sale,
)


@pytest.fixture
def sale_context() -> tuple[Mock, Lot, SaleCreate]:
    lot = Lot(id=1, starting_price=Decimal("100.00"), status=LotStatus.AVAILABLE)
    session = Mock(spec=Session)
    session.scalar.return_value = lot
    session.get.return_value = Buyer(id=2, name="Покупатель")
    payload = SaleCreate(lot_id=1, buyer_id=2, final_price=Decimal("100.00"))
    return session, lot, payload


@pytest.mark.parametrize(
    ("price", "rate", "expected"),
    [
        ("100.00", "10.00", "10.00"),
        ("100.05", "10.00", "10.01"),
        ("100.04", "10.00", "10.00"),
        ("100.06", "10.00", "10.01"),
        ("100.05", "0.00", "0.00"),
        ("100.05", "100.00", "100.05"),
        ("120.00", "12.50", "15.00"),
    ],
)
def test_sale_price_and_commission(
    sale_context: tuple[Mock, Lot, SaleCreate], price: str, rate: str, expected: str
) -> None:
    session, lot, payload = sale_context
    payload.final_price = Decimal(price)

    sale = register_sale(session, payload, Decimal(rate))

    assert sale.lot_id == lot.id
    assert sale.buyer_id == payload.buyer_id
    assert sale.final_price == Decimal(price)
    assert sale.revenue.commission_rate == Decimal(rate)
    assert sale.revenue.amount == Decimal(expected)
    assert lot.status == LotStatus.SOLD


@pytest.mark.parametrize(
    ("invalid_case", "error"),
    [
        ("missing_lot", LotNotFoundError),
        ("missing_buyer", BuyerNotFoundError),
        ("sold_lot", LotAlreadySoldError),
        ("low_price", PriceBelowStartingError),
    ],
)
def test_rejected_sale_has_no_writes(
    sale_context: tuple[Mock, Lot, SaleCreate], invalid_case: str, error: type[Exception]
) -> None:
    session, lot, payload = sale_context
    if invalid_case == "missing_lot":
        session.scalar.return_value = None
    elif invalid_case == "missing_buyer":
        session.get.return_value = None
    elif invalid_case == "sold_lot":
        lot.status = LotStatus.SOLD
    else:
        payload.final_price = Decimal("99.99")
    original_status = lot.status

    with pytest.raises(error):
        register_sale(session, payload, Decimal("10.00"))

    assert lot.status == original_status
    session.add.assert_not_called()
    session.commit.assert_not_called()
    session.flush.assert_not_called()
