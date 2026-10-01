from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from auctions.auth import CurrentAccount, current_account, ensure_role
from auctions.dependencies import DbSession
from auctions.models import AccountRole, Auction, Lot, Seller
from auctions.routers.web import web_lots
from auctions.schemas import AuctionCreate, AuctionRead, LotCreate, LotRead

router = APIRouter(tags=["catalog"], dependencies=[Depends(current_account)])


@router.post("/auctions", response_model=AuctionRead, status_code=status.HTTP_201_CREATED)
def create_auction(payload: AuctionCreate, account: CurrentAccount, session: DbSession) -> Auction:
    ensure_role(account, AccountRole.ADMIN)
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
def create_lot(payload: LotCreate, account: CurrentAccount, session: DbSession) -> Lot:
    if account.role != AccountRole.ADMIN and (
        account.seller_id is None or payload.seller_id != account.seller_id
    ):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
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
def list_lots(account: CurrentAccount, session: DbSession) -> list[Lot]:
    return web_lots(account, session)


@router.get("/lots/{lot_id}", response_model=LotRead)
def get_lot(lot_id: int, account: CurrentAccount, session: DbSession) -> Lot:
    lot = session.get(Lot, lot_id)
    if lot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Лот не найден")
    if account.role != AccountRole.ADMIN:
        allowed = (account.seller_id is not None and lot.seller_id == account.seller_id) or (
            account.buyer_id is not None and lot.status == "available"
        )
        if not allowed:
            raise HTTPException(status_code=403, detail="Недостаточно прав")
    return lot
