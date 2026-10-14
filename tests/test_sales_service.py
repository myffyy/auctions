from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from auctions.models import Auction, Buyer, Lot, LotStatus, Revenue, Sale, Seller
from auctions.schemas import SaleCreate
from auctions.services.sales import (
    BuyerNotFoundError,
    LotAlreadySoldError,
    LotNotFoundError,
    PriceBelowStartingError,
    register_sale,
)


def create_sale_context(session: Session) -> tuple[Lot, Buyer]:
    starts_at = datetime(2026, 9, 12, 10, tzinfo=UTC)
    seller = Seller(name="Анна")
    buyer = Buyer(name="Борис")
    auction = Auction(
        name="Осенний аукцион",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=8),
    )
    lot = Lot(
        auction=auction,
        seller=seller,
        name="Картина",
        description="Картина современного художника",
        starting_price=Decimal("1000.00"),
    )
    session.add_all([buyer, lot])
    session.commit()
    return lot, buyer


def test_register_sale_creates_revenue_and_marks_lot_sold(db_session: Session) -> None:
    lot, buyer = create_sale_context(db_session)
    payload = SaleCreate(lot_id=lot.id, buyer_id=buyer.id, final_price=Decimal("1250.00"))

    sale = register_sale(db_session, payload, commission_rate=Decimal("10.00"))

    assert sale.final_price == Decimal("1250.00")
    assert sale.revenue.commission_rate == Decimal("10.00")
    assert sale.revenue.amount == Decimal("125.00")
    assert lot.status == LotStatus.SOLD
    assert db_session.scalar(select(func.count()).select_from(Sale)) == 1
    assert db_session.scalar(select(func.count()).select_from(Revenue)) == 1


def test_register_sale_rejects_price_below_starting(db_session: Session) -> None:
    lot, buyer = create_sale_context(db_session)
    payload = SaleCreate(lot_id=lot.id, buyer_id=buyer.id, final_price=Decimal("999.99"))

    with pytest.raises(PriceBelowStartingError):
        register_sale(db_session, payload, commission_rate=Decimal("10.00"))

    assert lot.status == LotStatus.AVAILABLE
    assert db_session.scalar(select(func.count()).select_from(Sale)) == 0
    assert db_session.scalar(select(func.count()).select_from(Revenue)) == 0


def test_register_sale_rejects_repeated_sale(db_session: Session) -> None:
    lot, buyer = create_sale_context(db_session)
    payload = SaleCreate(lot_id=lot.id, buyer_id=buyer.id, final_price=Decimal("1250.00"))
    register_sale(db_session, payload, commission_rate=Decimal("10.00"))

    with pytest.raises(LotAlreadySoldError):
        register_sale(db_session, payload, commission_rate=Decimal("1300.00"))


def test_register_sale_rejects_unknown_lot(db_session: Session) -> None:
    payload = SaleCreate(lot_id=999999, buyer_id=999999, final_price=Decimal("1250.00"))

    with pytest.raises(LotNotFoundError):
        register_sale(db_session, payload, commission_rate=Decimal("10.00"))


def test_register_sale_rejects_unknown_buyer(db_session: Session) -> None:
    lot, _ = create_sale_context(db_session)
    payload = SaleCreate(lot_id=lot.id, buyer_id=999999, final_price=Decimal("1250.00"))

    with pytest.raises(BuyerNotFoundError):
        register_sale(db_session, payload, commission_rate=Decimal("10.00"))


@pytest.mark.parametrize("commit", [True, False])
def test_sale_at_starting_price_is_allowed(db_session: Session, commit: bool) -> None:
    lot, buyer = create_sale_context(db_session)
    payload = SaleCreate(lot_id=lot.id, buyer_id=buyer.id, final_price=lot.starting_price)

    sale = register_sale(db_session, payload, Decimal("10.00"), commit=commit)

    assert sale.final_price == Decimal("1000.00")
    assert sale.revenue.amount == Decimal("100.00")
    assert db_session.scalar(select(func.count()).select_from(Sale)) == 1
    assert db_session.scalar(select(func.count()).select_from(Revenue)) == 1
    assert lot.status == LotStatus.SOLD


@pytest.mark.parametrize("commit", [True, False])
def test_failed_sale_rolls_back_all_changes(db_session: Session, commit: bool) -> None:
    lot, buyer = create_sale_context(db_session)
    lot_id = lot.id
    payload = SaleCreate(lot_id=lot.id, buyer_id=buyer.id, final_price=Decimal("1250.00"))

    def invalidate_revenue(session: Session, context: object, instances: object) -> None:
        for record in session.new:
            if isinstance(record, Revenue):
                record.amount = Decimal("-0.01")

    event.listen(db_session, "before_flush", invalidate_revenue)
    try:
        with pytest.raises(LotAlreadySoldError):
            register_sale(db_session, payload, Decimal("10.00"), commit=commit)
    finally:
        event.remove(db_session, "before_flush", invalidate_revenue)

    assert db_session.get(Lot, lot_id).status == LotStatus.AVAILABLE
    assert db_session.scalar(select(func.count()).select_from(Sale)) == 0
    assert db_session.scalar(select(func.count()).select_from(Revenue)) == 0
