from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from auctions.schemas import AuctionCreate, LotCreate, SellerCreate


def test_seller_schema_accepts_valid_data() -> None:
    seller = SellerCreate(name="  Анна  ", email="anna@example.com")

    assert seller.name == "Анна"
    assert seller.email == "anna@example.com"


def test_seller_schema_rejects_invalid_email() -> None:
    with pytest.raises(ValidationError):
        SellerCreate(name="Анна", email="incorrect-email")


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
