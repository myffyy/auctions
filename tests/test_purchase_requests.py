"""Правила подачи и рассмотрения заявок с настоящей PostgreSQL."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from auctions.auth import hash_password
from auctions.models import Account, AccountRole, Lot, LotStatus, PurchaseRequest, Revenue, Sale
from auctions.schemas import SaleCreate
from auctions.services.sales import register_sale
from tests.test_sales_service import create_sale_context
from tests.test_web import login_as_admin


@pytest.fixture
def buyer_context(db_session: Session, api_client: TestClient) -> tuple[TestClient, Lot, int]:
    lot, buyer = create_sale_context(db_session)
    account = Account(
        last_name="Тестов",
        first_name="Покупатель",
        middle_name="Тестович",
        username="request-buyer",
        password_hash=hash_password("buyer-test-password"),
        role=AccountRole.USER,
        buyer_id=buyer.id,
    )
    db_session.add(account)
    db_session.commit()
    response = api_client.post(
        "/auth/login", json={"username": account.username, "password": "buyer-test-password"}
    )
    assert response.status_code == 200
    return api_client, lot, buyer.id


def send_request(client: TestClient, lot_id: int, price: str = "1000.00") -> dict:
    response = client.post(
        "/web/buyer/purchase-requests", json={"lot_id": lot_id, "offered_price": price}
    )
    assert response.status_code == 201
    return response.json()


def assert_no_sale(db_session: Session, lot_id: int) -> None:
    assert db_session.scalar(select(func.count()).select_from(Sale)) == 0
    assert db_session.scalar(select(func.count()).select_from(Revenue)) == 0
    assert db_session.get(Lot, lot_id).status == LotStatus.AVAILABLE


def test_request_at_starting_price_does_not_create_sale(
    buyer_context: tuple[TestClient, Lot, int], db_session: Session
) -> None:
    client, lot, buyer_id = buyer_context
    request = send_request(client, lot.id)

    assert request["status"] == "pending"
    assert request["buyer_id"] == buyer_id
    assert request["offered_price"] == "1000.00"
    assert request["reviewed_at"] is None
    assert_no_sale(db_session, lot.id)


def test_reject_duplicate_pending_request(
    buyer_context: tuple[TestClient, Lot, int], db_session: Session
) -> None:
    client, lot, _ = buyer_context
    send_request(client, lot.id)
    response = client.post(
        "/web/buyer/purchase-requests", json={"lot_id": lot.id, "offered_price": "1100.00"}
    )

    assert response.status_code == 409
    assert db_session.scalar(select(func.count()).select_from(PurchaseRequest)) == 1
    assert_no_sale(db_session, lot.id)


def test_reject_request_below_starting_price(
    buyer_context: tuple[TestClient, Lot, int], db_session: Session
) -> None:
    client, lot, _ = buyer_context
    response = client.post(
        "/web/buyer/purchase-requests", json={"lot_id": lot.id, "offered_price": "999.99"}
    )

    assert response.status_code == 400
    assert db_session.scalar(select(func.count()).select_from(PurchaseRequest)) == 0
    assert_no_sale(db_session, lot.id)


def test_rejected_request_is_kept_and_allows_resubmission(
    buyer_context: tuple[TestClient, Lot, int], db_session: Session
) -> None:
    client, lot, _ = buyer_context
    request = send_request(client, lot.id)
    login_as_admin(client)
    response = client.post(f"/web/admin/purchase-requests/{request['id']}/reject")

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["reviewed_at"] is not None
    assert_no_sale(db_session, lot.id)

    client.post("/auth/logout")
    client.post(
        "/auth/login", json={"username": "request-buyer", "password": "buyer-test-password"}
    )
    new_request = send_request(client, lot.id, "1100.00")

    assert new_request["id"] != request["id"]
    history = client.get("/web/purchase-requests").json()
    assert {item["status"] for item in history} == {"pending", "rejected"}
    assert len(history) == 2
    assert_no_sale(db_session, lot.id)


@pytest.mark.parametrize("first_action", ["approve", "reject"])
@pytest.mark.parametrize("second_action", ["approve", "reject"])
def test_reject_repeated_review(
    buyer_context: tuple[TestClient, Lot, int],
    db_session: Session,
    first_action: str,
    second_action: str,
) -> None:
    client, lot, _ = buyer_context
    request = send_request(client, lot.id)
    login_as_admin(client)
    initial = client.post(f"/web/admin/purchase-requests/{request['id']}/{first_action}")
    assert initial.status_code == 200
    history_before = client.get("/web/purchase-requests").json()

    repeated = client.post(f"/web/admin/purchase-requests/{request['id']}/{second_action}")

    assert repeated.status_code == 409
    assert client.get("/web/purchase-requests").json() == history_before
    if first_action == "reject":
        assert_no_sale(db_session, lot.id)
    else:
        assert history_before[0]["status"] == "approved"
        assert history_before[0]["reviewed_at"] is not None
        assert db_session.get(Lot, lot.id).status == LotStatus.SOLD
        assert db_session.scalar(select(func.count()).select_from(Sale)) == 1
        revenue = db_session.scalar(select(Revenue))
        assert revenue.amount == Decimal("100.00")
        assert db_session.scalar(select(func.count()).select_from(Revenue)) == 1


def test_buyer_cannot_review_request(buyer_context: tuple[TestClient, Lot, int]) -> None:
    client, lot, _ = buyer_context
    request = send_request(client, lot.id)
    for action in ["approve", "reject"]:
        response = client.post(f"/web/admin/purchase-requests/{request['id']}/{action}")
        assert response.status_code == 403
    assert client.get("/web/purchase-requests").json()[0]["status"] == "pending"


def test_reject_request_for_sold_lot(
    buyer_context: tuple[TestClient, Lot, int], db_session: Session
) -> None:
    client, lot, buyer_id = buyer_context
    register_sale(
        db_session,
        SaleCreate(lot_id=lot.id, buyer_id=buyer_id, final_price=lot.starting_price),
        Decimal("10.00"),
    )
    response = client.post(
        "/web/buyer/purchase-requests", json={"lot_id": lot.id, "offered_price": "1100.00"}
    )

    assert response.status_code == 409
    assert db_session.scalar(select(func.count()).select_from(PurchaseRequest)) == 0
    assert db_session.scalar(select(func.count()).select_from(Sale)) == 1


def test_failed_approval_keeps_request_pending(
    buyer_context: tuple[TestClient, Lot, int], db_session: Session
) -> None:
    from sqlalchemy import event

    client, lot, _ = buyer_context
    request = send_request(client, lot.id)
    login_as_admin(client)

    def invalidate_revenue(session: Session, context: object, instances: object) -> None:
        for record in session.new:
            if isinstance(record, Revenue):
                record.amount = Decimal("-0.01")

    event.listen(db_session, "before_flush", invalidate_revenue)
    try:
        response = client.post(f"/web/admin/purchase-requests/{request['id']}/approve")
    finally:
        event.remove(db_session, "before_flush", invalidate_revenue)

    assert response.status_code == 409
    history = client.get("/web/purchase-requests").json()
    assert history[0]["status"] == "pending"
    assert history[0]["reviewed_at"] is None
    assert_no_sale(db_session, lot.id)
