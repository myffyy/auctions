from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from auctions.auth import CurrentAccount, current_account, ensure_role
from auctions.config import get_settings
from auctions.dependencies import DbSession
from auctions.models import AccountRole, Lot, Revenue, Sale
from auctions.routers.web import web_sales
from auctions.schemas import RevenueRead, SaleCreate, SaleRead
from auctions.services.sales import (
    BuyerNotFoundError,
    LotAlreadySoldError,
    LotNotFoundError,
    PriceBelowStartingError,
    register_sale,
)

router = APIRouter(tags=["sales"], dependencies=[Depends(current_account)])


@router.post("/sales", response_model=SaleRead, status_code=status.HTTP_201_CREATED)
def create_sale(payload: SaleCreate, account: CurrentAccount, session: DbSession) -> Sale:
    ensure_role(account, AccountRole.ADMIN)
    try:
        return register_sale(session, payload, get_settings().commission_rate)
    except LotNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Лот не найден"
        ) from error
    except BuyerNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Покупатель не найден",
        ) from error
    except LotAlreadySoldError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Лот уже продан"
        ) from error
    except PriceBelowStartingError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Итоговая цена ниже начальной цены лота",
        ) from error


@router.get("/sales", response_model=list[SaleRead])
def list_sales(account: CurrentAccount, session: DbSession) -> list[Sale]:
    return web_sales(account, session)


@router.get("/sales/{sale_id}", response_model=SaleRead)
def get_sale(sale_id: int, account: CurrentAccount, session: DbSession) -> Sale:
    statement = select(Sale).options(selectinload(Sale.revenue)).where(Sale.id == sale_id)
    sale = session.scalar(statement)
    if sale is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Продажа не найдена")
    if account.role != AccountRole.ADMIN:
        lot = session.get(Lot, sale.lot_id)
        allowed = (account.buyer_id is not None and sale.buyer_id == account.buyer_id) or (
            account.seller_id is not None and lot is not None and lot.seller_id == account.seller_id
        )
        if not allowed:
            raise HTTPException(status_code=403, detail="Недостаточно прав")
    return sale


@router.get("/revenues", response_model=list[RevenueRead])
def list_revenues(account: CurrentAccount, session: DbSession) -> list[Revenue]:
    ensure_role(account, AccountRole.ADMIN)
    return list(session.scalars(select(Revenue).order_by(Revenue.id)).all())


@router.get("/revenues/{revenue_id}", response_model=RevenueRead)
def get_revenue(revenue_id: int, account: CurrentAccount, session: DbSession) -> Revenue:
    ensure_role(account, AccountRole.ADMIN)
    revenue = session.get(Revenue, revenue_id)
    if revenue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Доход не найден")
    return revenue
