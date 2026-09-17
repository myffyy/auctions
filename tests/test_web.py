from fastapi.testclient import TestClient

from auctions.config import get_settings


def login_as_admin(api_client: TestClient) -> None:
    settings = get_settings()
    response = api_client.post(
        "/auth/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    )
    assert response.status_code == 200


def test_admin_creates_user_then_registers_seller(api_client: TestClient) -> None:
    login_as_admin(api_client)

    account_response = api_client.post(
        "/web/admin/accounts",
        json={
            "last_name": "Иванов",
            "first_name": "Иван",
            "middle_name": "Иванович",
            "username": "ivanov-test",
            "password": "password123!",
            "role": "user",
        },
    )
    assert account_response.status_code == 201
    account_id = account_response.json()["id"]

    seller_response = api_client.post(
        "/web/admin/participants",
        json={"account_id": account_id, "profile": "seller"},
    )
    assert seller_response.status_code == 201
    assert seller_response.json()["name"] == "Иванов Иван Иванович"

    buyer_response = api_client.post(
        "/web/admin/participants",
        json={"account_id": account_id, "profile": "buyer"},
    )
    assert buyer_response.status_code == 409

    api_client.post("/auth/logout")
    user_login = api_client.post(
        "/auth/login",
        json={"username": "ivanov-test", "password": "password123!"},
    )
    assert user_login.status_code == 200
    assert api_client.get("/auth/me").json()["profile"] == "seller"


def test_user_cannot_create_another_account(api_client: TestClient) -> None:
    login_as_admin(api_client)
    api_client.post(
        "/web/admin/accounts",
        json={
            "last_name": "Петров",
            "first_name": "Пётр",
            "middle_name": "Петрович",
            "username": "petrov-test",
            "password": "password123!",
            "role": "user",
        },
    )
    api_client.post("/auth/logout")
    api_client.post(
        "/auth/login",
        json={"username": "petrov-test", "password": "password123!"},
    )

    response = api_client.post(
        "/web/admin/accounts",
        json={
            "last_name": "Сидоров",
            "first_name": "Сидор",
            "middle_name": "Сидорович",
            "username": "sidorov-test",
            "password": "password123!",
            "role": "user",
        },
    )
    assert response.status_code == 403


def test_buyer_request_requires_admin_approval(api_client: TestClient) -> None:
    login_as_admin(api_client)
    account_ids: dict[str, int] = {}
    for profile, username in (("seller", "seller-request"), ("buyer", "buyer-request")):
        account_response = api_client.post(
            "/web/admin/accounts",
            json={
                "last_name": "Тестов",
                "first_name": profile,
                "middle_name": "Участник",
                "username": username,
                "password": "password123!",
                "role": "user",
            },
        )
        account_ids[profile] = account_response.json()["id"]
        participant_response = api_client.post(
            "/web/admin/participants",
            json={"account_id": account_ids[profile], "profile": profile},
        )
        assert participant_response.status_code == 201

    auction_response = api_client.post(
        "/web/admin/auctions",
        json={
            "name": "Аукцион заявок",
            "starts_at": "2026-10-01T10:00:00Z",
            "ends_at": "2026-10-01T18:00:00Z",
        },
    )
    api_client.post("/auth/logout")

    api_client.post("/auth/login", json={"username": "seller-request", "password": "password123!"})
    lot_response = api_client.post(
        "/web/seller/lots",
        json={
            "auction_id": auction_response.json()["id"],
            "seller_id": 1,
            "name": "Лот для заявки",
            "description": "Проверка подтверждения администратором",
            "starting_price": "1000.00",
        },
    )
    api_client.post("/auth/logout")

    api_client.post("/auth/login", json={"username": "buyer-request", "password": "password123!"})
    request_response = api_client.post(
        "/web/buyer/purchase-requests",
        json={"lot_id": lot_response.json()["id"], "offered_price": "1200.00"},
    )
    assert request_response.status_code == 201
    assert request_response.json()["status"] == "pending"
    assert api_client.get("/web/sales").json() == []
    api_client.post("/auth/logout")

    login_as_admin(api_client)
    approval_response = api_client.post(
        f"/web/admin/purchase-requests/{request_response.json()['id']}/approve"
    )
    assert approval_response.status_code == 200
    assert approval_response.json()["final_price"] == "1200.00"
    assert api_client.get(f"/lots/{lot_response.json()['id']}").json()["status"] == "sold"
