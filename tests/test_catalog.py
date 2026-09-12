from decimal import Decimal

from fastapi.testclient import TestClient


def auction_payload() -> dict[str, str]:
    return {
        "name": "Осенний аукцион",
        "starts_at": "2026-10-01T10:00:00+03:00",
        "ends_at": "2026-10-01T18:00:00+03:00",
    }


def create_seller(api_client: TestClient) -> int:
    response = api_client.post(
        "/sellers",
        json={"name": "Анна", "email": "catalog-seller@example.com"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def create_auction(api_client: TestClient) -> int:
    response = api_client.post("/auctions", json=auction_payload())
    assert response.status_code == 201
    return response.json()["id"]


def test_create_get_and_list_auctions(api_client: TestClient) -> None:
    create_response = api_client.post("/auctions", json=auction_payload())

    assert create_response.status_code == 201
    auction = create_response.json()
    assert auction["status"] == "planned"

    get_response = api_client.get(f"/auctions/{auction['id']}")
    list_response = api_client.get("/auctions")

    assert get_response.status_code == 200
    assert get_response.json() == auction
    assert list_response.status_code == 200
    assert list_response.json() == [auction]


def test_get_unknown_auction(api_client: TestClient) -> None:
    response = api_client.get("/auctions/999999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Аукцион не найден"}


def test_create_get_and_list_lots(api_client: TestClient) -> None:
    seller_id = create_seller(api_client)
    auction_id = create_auction(api_client)
    payload = {
        "auction_id": auction_id,
        "seller_id": seller_id,
        "name": "Картина",
        "description": "Картина современного художника",
        "starting_price": "1000.00",
    }

    create_response = api_client.post("/lots", json=payload)

    assert create_response.status_code == 201
    lot = create_response.json()
    assert lot["status"] == "available"
    assert Decimal(lot["starting_price"]) == Decimal("1000.00")

    get_response = api_client.get(f"/lots/{lot['id']}")
    list_response = api_client.get("/lots")

    assert get_response.status_code == 200
    assert get_response.json() == lot
    assert list_response.status_code == 200
    assert list_response.json() == [lot]


def test_reject_lot_with_unknown_auction(api_client: TestClient) -> None:
    seller_id = create_seller(api_client)
    response = api_client.post(
        "/lots",
        json={
            "auction_id": 999999,
            "seller_id": seller_id,
            "name": "Картина",
            "description": "Описание",
            "starting_price": "1000.00",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Аукцион не найден"}


def test_reject_lot_with_unknown_seller(api_client: TestClient) -> None:
    auction_id = create_auction(api_client)
    response = api_client.post(
        "/lots",
        json={
            "auction_id": auction_id,
            "seller_id": 999999,
            "name": "Картина",
            "description": "Описание",
            "starting_price": "1000.00",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Продавец не найден"}


def test_get_unknown_lot(api_client: TestClient) -> None:
    response = api_client.get("/lots/999999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Лот не найден"}
