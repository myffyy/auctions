from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auctions.models import Buyer, Lot, LotStatus, Revenue, Sale
from auctions.schemas import SaleCreate

CENT = Decimal("0.01")
HUNDRED = Decimal("100")


class SaleError(Exception):
    """Базовая ошибка регистрации продажи."""


class LotNotFoundError(SaleError):
    """Указанный лот не существует."""


class BuyerNotFoundError(SaleError):
    """Указанный покупатель не существует."""


class LotAlreadySoldError(SaleError):
    """Лот уже был продан."""


class PriceBelowStartingError(SaleError):
    """Итоговая цена ниже начальной."""


def register_sale(
    session: Session,
    payload: SaleCreate,
    commission_rate: Decimal,
) -> Sale:
    """Зарегистрировать продажу и доход одной транзакцией."""

    lot = session.scalar(select(Lot).where(Lot.id == payload.lot_id).with_for_update())
    if lot is None:
        raise LotNotFoundError

    buyer = session.get(Buyer, payload.buyer_id)
    if buyer is None:
        raise BuyerNotFoundError

    if lot.status != LotStatus.AVAILABLE:
        raise LotAlreadySoldError

    if payload.final_price < lot.starting_price:
        raise PriceBelowStartingError

    normalized_rate = commission_rate.quantize(CENT)
    revenue_amount = (payload.final_price * normalized_rate / HUNDRED).quantize(
        CENT,
        rounding=ROUND_HALF_UP,
    )

    sale = Sale(
        lot_id=lot.id,
        buyer_id=buyer.id,
        final_price=payload.final_price,
    )
    sale.revenue = Revenue(
        commission_rate=normalized_rate,
        amount=revenue_amount,
    )
    lot.status = LotStatus.SOLD
    session.add(sale)

    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise LotAlreadySoldError from error

    session.refresh(sale)
    return sale
