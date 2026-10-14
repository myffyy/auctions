from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from auctions.schemas import AuctionCreate, LotCreate, SellerCreate


def test_seller_schema_accepts_valid_data() -> None:
    seller = SellerCreate(name="  Анна  ")

    assert seller.name == "Анна"


def test_auction_schema_normalizes_time_to_utc() -> None:
    moscow_time = timezone(timedelta(hours=3))

    auction = AuctionCreate(
        name="Осенний аукцион",
        starts_at=datetime(2026, 9, 12, 12, tzinfo=moscow_time),
        ends_at=datetime(2026, 9, 12, 14, tzinfo=moscow_time),
    )

    assert auction.starts_at == datetime(2026, 9, 12, 9, tzinfo=UTC)
    assert auction.ends_at == datetime(2026, 9, 12, 11, tzinfo=UTC)


def test_auction_schema_rejects_invalid_date_range() -> None:
    starts_at = datetime(2026, 9, 12, 12, tzinfo=UTC)

    with pytest.raises(ValidationError):
        AuctionCreate(
            name="Аукцион",
            starts_at=starts_at,
            ends_at=starts_at,
        )


def test_lot_schema_rejects_price_with_too_many_decimal_places() -> None:
    with pytest.raises(ValidationError):
        LotCreate(
            auction_id=1,
            seller_id=1,
            name="Картина",
            description="Картина современного художника",
            starting_price=Decimal("1000.999"),
        )


@pytest.mark.parametrize("name", ["", "   ", "А" * 201])
def test_seller_schema_rejects_invalid_name(name: str) -> None:
    with pytest.raises(ValidationError):
        SellerCreate(name=name)


@pytest.mark.parametrize("field", ["starts_at", "ends_at"])
def test_auction_schema_rejects_missing_timezone(field: str) -> None:
    payload = {
        "name": "Аукцион",
        "starts_at": datetime(2026, 10, 14, 10, tzinfo=UTC),
        "ends_at": datetime(2026, 10, 14, 18, tzinfo=UTC),
    }
    payload[field] = payload[field].replace(tzinfo=None)

    with pytest.raises(ValidationError):
        AuctionCreate(**payload)


@pytest.mark.parametrize("price", ["0", "-0.01", "NaN", "Infinity", "1000.001", "10000000000.00"])
def test_sale_schema_rejects_invalid_price(price: str) -> None:
    from auctions.schemas import SaleCreate

    with pytest.raises(ValidationError):
        SaleCreate(lot_id=1, buyer_id=1, final_price=Decimal(price))


@pytest.mark.parametrize("field", ["lot_id", "buyer_id"])
@pytest.mark.parametrize("identifier", [0, -1])
def test_sale_schema_rejects_non_positive_ids(field: str, identifier: int) -> None:
    from auctions.schemas import SaleCreate

    payload = {"lot_id": 1, "buyer_id": 1, "final_price": Decimal("1000.00")}
    payload[field] = identifier
    with pytest.raises(ValidationError):
        SaleCreate(**payload)


def test_sale_schema_accepts_maximum_price() -> None:
    from auctions.schemas import SaleCreate

    sale = SaleCreate(lot_id=1, buyer_id=1, final_price=Decimal("9999999999.99"))
    assert sale.final_price == Decimal("9999999999.99")


@pytest.mark.parametrize("price", ["0", "-0.01"])
def test_lot_schema_rejects_non_positive_price(price: str) -> None:
    with pytest.raises(ValidationError):
        LotCreate(
            auction_id=1,
            seller_id=1,
            name="Лот",
            description="Описание",
            starting_price=Decimal(price),
        )
