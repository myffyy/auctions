"""Маршруты браузерного интерфейса с проверкой прав на сервере."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from auctions.auth import CurrentAccount, ensure_role, hash_password, verify_password
from auctions.config import get_settings
from auctions.dependencies import DbSession
from auctions.models import (
    Account,
    AccountRole,
    Auction,
    Buyer,
    Lot,
    LotStatus,
    PurchaseRequest,
    PurchaseRequestStatus,
    Revenue,
    Sale,
    Seller,
)
from auctions.schemas import (
    AuctionCreate,
    AuctionRead,
    BuyerRead,
    LotCreate,
    LotRead,
    PurchaseRequestCreate,
    PurchaseRequestRead,
    RevenueRead,
    SaleCreate,
    SaleRead,
    SellerRead,
)
from auctions.services.sales import (
    BuyerNotFoundError,
    LotAlreadySoldError,
    LotNotFoundError,
    PriceBelowStartingError,
    register_sale,
)

router = APIRouter(tags=["web"])
static_dir = Path(__file__).resolve().parent.parent / "static"


class LoginPayload(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class AccountCreate(BaseModel):
    last_name: str = Field(min_length=1, max_length=100)
    first_name: str = Field(min_length=1, max_length=100)
    middle_name: str = Field(min_length=1, max_length=100)
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, max_length=200)
    role: AccountRole


class ParticipantCreate(BaseModel):
    account_id: int = Field(gt=0)
    profile: Literal["seller", "buyer"]


@router.get("/", include_in_schema=False)
def index(request: Request) -> RedirectResponse:
    return RedirectResponse("/app" if request.session.get("account_id") else "/login")


@router.get("/login", include_in_schema=False)
def login_page() -> FileResponse:
    return FileResponse(static_dir / "login.html")


@router.get("/app", include_in_schema=False, response_model=None)
def app_page(request: Request, session: DbSession) -> FileResponse | RedirectResponse:
    if not isinstance(request.session.get("account_id"), int):
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    if session.get(Account, request.session["account_id"]) is None:
        request.session.clear()
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    return FileResponse(static_dir / "app.html")


@router.post("/auth/login")
def login(payload: LoginPayload, request: Request, session: DbSession) -> dict[str, str]:
    settings = get_settings()
    if session.scalar(select(Account).where(Account.role == AccountRole.ADMIN)) is None:
        session.add(
            Account(
                last_name=settings.admin_last_name,
                first_name=settings.admin_first_name,
                middle_name=settings.admin_middle_name,
                username=settings.admin_username,
                password_hash=hash_password(settings.admin_password),
                role=AccountRole.ADMIN,
            )
        )
        session.commit()
    account = session.scalar(select(Account).where(Account.username == payload.username))
    if account is None or not verify_password(payload.password, account.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный логин или пароль"
        )
    request.session.clear()
    request.session["account_id"] = account.id
    return {
        "username": account.username,
        "role": account.role,
        "full_name": f"{account.last_name} {account.first_name} {account.middle_name}",
    }


@router.post("/auth/logout")
def logout(request: Request) -> dict[str, str]:
    request.session.clear()
    return {"status": "ok"}


@router.get("/auth/me")
def current_user(account: CurrentAccount) -> dict[str, int | str | None]:
    profile = "admin"
    if account.role == AccountRole.USER:
        profile = "seller" if account.seller_id else "buyer" if account.buyer_id else "unregistered"
    return {
        "username": account.username,
        "last_name": account.last_name,
        "first_name": account.first_name,
        "middle_name": account.middle_name,
        "full_name": f"{account.last_name} {account.first_name} {account.middle_name}",
        "role": account.role,
        "profile": profile,
        "seller_id": account.seller_id,
        "buyer_id": account.buyer_id,
    }


@router.get("/web/auctions", response_model=list[AuctionRead])
def web_auctions(_: CurrentAccount, session: DbSession) -> list[Auction]:
    return list(session.scalars(select(Auction).order_by(Auction.id)).all())


@router.get("/web/lots", response_model=list[LotRead])
def web_lots(account: CurrentAccount, session: DbSession) -> list[Lot]:
    statement = select(Lot).order_by(Lot.id)
    if account.role == AccountRole.USER and account.seller_id is not None:
        statement = statement.where(Lot.seller_id == account.seller_id)
    elif account.role == AccountRole.USER and account.buyer_id is not None:
        statement = statement.where(Lot.status == "available")
    elif account.role == AccountRole.USER:
        statement = statement.where(Lot.id < 0)
    return list(session.scalars(statement).all())


@router.get("/web/sales", response_model=list[SaleRead])
def web_sales(account: CurrentAccount, session: DbSession) -> list[Sale]:
    statement = select(Sale).options(selectinload(Sale.revenue)).order_by(Sale.id)
    if account.role == AccountRole.USER and account.buyer_id is not None:
        statement = statement.where(Sale.buyer_id == account.buyer_id)
    elif account.role == AccountRole.USER and account.seller_id is not None:
        statement = statement.join(Lot).where(Lot.seller_id == account.seller_id)
    elif account.role == AccountRole.USER:
        statement = statement.where(Sale.id < 0)
    return list(session.scalars(statement).all())


@router.get("/web/purchase-requests", response_model=list[PurchaseRequestRead])
def web_purchase_requests(account: CurrentAccount, session: DbSession) -> list[PurchaseRequest]:
    statement = select(PurchaseRequest).order_by(PurchaseRequest.id.desc())
    if account.role == AccountRole.USER and account.buyer_id is not None:
        statement = statement.where(PurchaseRequest.buyer_id == account.buyer_id)
    elif account.role == AccountRole.USER and account.seller_id is not None:
        statement = statement.join(Lot).where(Lot.seller_id == account.seller_id)
    elif account.role == AccountRole.USER:
        statement = statement.where(PurchaseRequest.id < 0)
    return list(session.scalars(statement).all())


@router.get("/web/revenues", response_model=list[RevenueRead])
def web_revenues(account: CurrentAccount, session: DbSession) -> list[Revenue]:
    ensure_role(account, AccountRole.ADMIN)
    return list(session.scalars(select(Revenue).order_by(Revenue.id)).all())


@router.get("/web/admin/sellers", response_model=list[SellerRead])
def web_sellers(account: CurrentAccount, session: DbSession) -> list[Seller]:
    ensure_role(account, AccountRole.ADMIN)
    return list(session.scalars(select(Seller).order_by(Seller.id)).all())


@router.get("/web/admin/buyers", response_model=list[BuyerRead])
def web_buyers(account: CurrentAccount, session: DbSession) -> list[Buyer]:
    ensure_role(account, AccountRole.ADMIN)
    return list(session.scalars(select(Buyer).order_by(Buyer.id)).all())


@router.get("/web/admin/accounts")
def web_accounts(account: CurrentAccount, session: DbSession) -> list[dict[str, int | str | None]]:
    ensure_role(account, AccountRole.ADMIN)
    accounts = session.scalars(select(Account).order_by(Account.id)).all()
    return [
        {
            "id": item.id,
            "full_name": f"{item.last_name} {item.first_name} {item.middle_name}",
            "username": item.username,
            "role": item.role,
            "profile": "seller" if item.seller_id else "buyer" if item.buyer_id else "—",
        }
        for item in accounts
    ]


@router.post("/web/admin/participants", status_code=status.HTTP_201_CREATED)
def web_create_participant(
    payload: ParticipantCreate, account: CurrentAccount, session: DbSession
) -> dict[str, int | str]:
    ensure_role(account, AccountRole.ADMIN)
    user = session.get(Account, payload.account_id)
    if user is None or user.role != AccountRole.USER:
        raise HTTPException(status_code=422, detail="Выберите существующего пользователя")
    if user.seller_id is not None or user.buyer_id is not None:
        raise HTTPException(status_code=409, detail="У пользователя уже есть профиль")
    full_name = f"{user.last_name} {user.first_name} {user.middle_name}"
    participant: Seller | Buyer
    participant = Seller(name=full_name) if payload.profile == "seller" else Buyer(name=full_name)
    session.add(participant)
    try:
        session.flush()
        if payload.profile == "seller":
            user.seller_id = participant.id
        else:
            user.buyer_id = participant.id
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail="У пользователя уже есть профиль") from error
    return {"id": participant.id, "name": participant.name, "profile": payload.profile}


@router.post("/web/admin/auctions", response_model=AuctionRead, status_code=status.HTTP_201_CREATED)
def web_create_auction(
    payload: AuctionCreate, account: CurrentAccount, session: DbSession
) -> Auction:
    ensure_role(account, AccountRole.ADMIN)
    auction = Auction(**payload.model_dump())
    session.add(auction)
    session.commit()
    session.refresh(auction)
    return auction


@router.post("/web/admin/accounts", status_code=status.HTTP_201_CREATED)
def web_create_account(
    payload: AccountCreate, account: CurrentAccount, session: DbSession
) -> dict[str, int | str]:
    ensure_role(account, AccountRole.ADMIN)
    if session.scalar(select(Account).where(Account.username == payload.username)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Такой логин уже существует"
        )
    new_account = Account(
        last_name=payload.last_name,
        first_name=payload.first_name,
        middle_name=payload.middle_name,
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    session.add(new_account)
    try:
        session.commit()
    except Exception as error:
        session.rollback()
        raise HTTPException(status_code=409, detail="Такой логин уже существует") from error
    return {"id": new_account.id, "username": new_account.username, "role": new_account.role}


@router.post("/web/seller/lots", response_model=LotRead, status_code=status.HTTP_201_CREATED)
def web_create_lot(payload: LotCreate, account: CurrentAccount, session: DbSession) -> Lot:
    ensure_role(account, AccountRole.USER)
    if account.seller_id is None:
        raise HTTPException(status_code=403, detail="К учётной записи не привязан продавец")
    if session.get(Auction, payload.auction_id) is None:
        raise HTTPException(status_code=404, detail="Аукцион не найден")
    lot = Lot(**payload.model_dump(exclude={"seller_id"}), seller_id=account.seller_id)
    session.add(lot)
    session.commit()
    session.refresh(lot)
    return lot


@router.post(
    "/web/buyer/purchase-requests",
    response_model=PurchaseRequestRead,
    status_code=status.HTTP_201_CREATED,
)
def web_create_purchase_request(
    payload: PurchaseRequestCreate, account: CurrentAccount, session: DbSession
) -> PurchaseRequest:
    ensure_role(account, AccountRole.USER)
    if account.buyer_id is None:
        raise HTTPException(status_code=403, detail="К учётной записи не привязан покупатель")
    lot = session.scalar(select(Lot).where(Lot.id == payload.lot_id).with_for_update())
    if lot is None:
        raise HTTPException(status_code=404, detail="Лот не найден")
    if lot.status != LotStatus.AVAILABLE:
        raise HTTPException(status_code=409, detail="Лот уже продан")
    if payload.offered_price < lot.starting_price:
        raise HTTPException(status_code=400, detail="Предложенная цена ниже начальной цены лота")
    pending = session.scalar(
        select(PurchaseRequest).where(
            PurchaseRequest.lot_id == lot.id,
            PurchaseRequest.status == PurchaseRequestStatus.PENDING,
        )
    )
    if pending is not None:
        raise HTTPException(
            status_code=409, detail="Для этого лота уже есть заявка на рассмотрении"
        )
    purchase_request = PurchaseRequest(
        lot_id=lot.id,
        buyer_id=account.buyer_id,
        offered_price=payload.offered_price,
    )
    session.add(purchase_request)
    session.commit()
    session.refresh(purchase_request)
    return purchase_request


@router.post(
    "/web/admin/purchase-requests/{request_id}/approve",
    response_model=SaleRead,
)
def approve_purchase_request(request_id: int, account: CurrentAccount, session: DbSession) -> Sale:
    ensure_role(account, AccountRole.ADMIN)
    purchase_request = session.scalar(
        select(PurchaseRequest).where(PurchaseRequest.id == request_id).with_for_update()
    )
    if purchase_request is None:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if purchase_request.status != PurchaseRequestStatus.PENDING:
        raise HTTPException(status_code=409, detail="Заявка уже рассмотрена")
    payload = SaleCreate(
        lot_id=purchase_request.lot_id,
        buyer_id=purchase_request.buyer_id,
        final_price=purchase_request.offered_price,
    )
    try:
        sale = register_sale(session, payload, get_settings().commission_rate, commit=False)
        purchase_request.status = PurchaseRequestStatus.APPROVED
        purchase_request.reviewed_at = datetime.now(UTC)
        session.commit()
        session.refresh(sale)
        return sale
    except (LotNotFoundError, BuyerNotFoundError) as error:
        session.rollback()
        raise HTTPException(status_code=404, detail="Лот или покупатель не найден") from error
    except LotAlreadySoldError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail="Лот уже продан") from error
    except PriceBelowStartingError as error:
        session.rollback()
        raise HTTPException(status_code=400, detail="Цена ниже начальной цены лота") from error


@router.post(
    "/web/admin/purchase-requests/{request_id}/reject",
    response_model=PurchaseRequestRead,
)
def reject_purchase_request(
    request_id: int, account: CurrentAccount, session: DbSession
) -> PurchaseRequest:
    ensure_role(account, AccountRole.ADMIN)
    purchase_request = session.scalar(
        select(PurchaseRequest).where(PurchaseRequest.id == request_id).with_for_update()
    )
    if purchase_request is None:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if purchase_request.status != PurchaseRequestStatus.PENDING:
        raise HTTPException(status_code=409, detail="Заявка уже рассмотрена")
    purchase_request.status = PurchaseRequestStatus.REJECTED
    purchase_request.reviewed_at = datetime.now(UTC)
    session.commit()
    session.refresh(purchase_request)
    return purchase_request
