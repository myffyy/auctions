from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from auctions.dependencies import get_db_session
from auctions.models import Auction, Lot, Seller
from auctions.schemas import AuctionCreate, AuctionRead, LotCreate, LotRead

router = APIRouter(tags=["catalog"])
DbSession = Annotated[Session, Depends(get_db_session)]


@router.post("/auctions", response_model=AuctionRead, status_code=status.HTTP_201_CREATED)
def create_auction(payload: AuctionCreate, session: DbSession) -> Auction:
    auction = Auction(**payload.model_dump())
    session.add(auction)
    session.commit()
    session.refresh(auction)
    return auction


@router.get("/auctions", response_model=list[AuctionRead])
def list_auctions(session: DbSession) -> list[Auction]:
    return list(session.scalars(select(Auction).order_by(Auction.id)).all())


@router.get("/auctions/{auction_id}", response_model=AuctionRead)
def get_auction(auction_id: int, session: DbSession) -> Auction:
    auction = session.get(Auction, auction_id)
    if auction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Аукцион не найден")
    return auction


@router.post("/lots", response_model=LotRead, status_code=status.HTTP_201_CREATED)
def create_lot(payload: LotCreate, session: DbSession) -> Lot:
    if session.get(Auction, payload.auction_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Аукцион не найден")
    if session.get(Seller, payload.seller_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Продавец не найден")

    lot = Lot(**payload.model_dump())
    session.add(lot)
    session.commit()
    session.refresh(lot)
    return lot


@router.get("/lots", response_model=list[LotRead])
def list_lots(session: DbSession) -> list[Lot]:
    return list(session.scalars(select(Lot).order_by(Lot.id)).all())


@router.get("/lots/{lot_id}", response_model=LotRead)
def get_lot(lot_id: int, session: DbSession) -> Lot:
    lot = session.get(Lot, lot_id)
    if lot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Лот не найден")
    return lot
