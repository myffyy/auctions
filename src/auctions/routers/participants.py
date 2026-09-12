from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auctions.dependencies import get_db_session
from auctions.models import Buyer, Seller
from auctions.schemas import BuyerCreate, BuyerRead, SellerCreate, SellerRead

router = APIRouter(tags=["participants"])
DbSession = Annotated[Session, Depends(get_db_session)]


def commit_unique(session: Session, detail: str) -> None:
    """Сохранить изменения или сообщить о конфликте уникальности."""

    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from error


@router.post("/sellers", response_model=SellerRead, status_code=status.HTTP_201_CREATED)
def create_seller(payload: SellerCreate, session: DbSession) -> Seller:
    seller = Seller(**payload.model_dump())
    session.add(seller)
    commit_unique(session, "Продавец с таким email уже существует")
    session.refresh(seller)
    return seller


@router.get("/sellers", response_model=list[SellerRead])
def list_sellers(session: DbSession) -> list[Seller]:
    return list(session.scalars(select(Seller).order_by(Seller.id)).all())


@router.get("/sellers/{seller_id}", response_model=SellerRead)
def get_seller(seller_id: int, session: DbSession) -> Seller:
    seller = session.get(Seller, seller_id)
    if seller is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Продавец не найден")
    return seller


@router.post("/buyers", response_model=BuyerRead, status_code=status.HTTP_201_CREATED)
def create_buyer(payload: BuyerCreate, session: DbSession) -> Buyer:
    buyer = Buyer(**payload.model_dump())
    session.add(buyer)
    commit_unique(session, "Покупатель с таким email уже существует")
    session.refresh(buyer)
    return buyer


@router.get("/buyers", response_model=list[BuyerRead])
def list_buyers(session: DbSession) -> list[Buyer]:
    return list(session.scalars(select(Buyer).order_by(Buyer.id)).all())


@router.get("/buyers/{buyer_id}", response_model=BuyerRead)
def get_buyer(buyer_id: int, session: DbSession) -> Buyer:
    buyer = session.get(Buyer, buyer_id)
    if buyer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Покупатель не найден")
    return buyer
