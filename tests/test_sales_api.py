from decimal import Decimal

from fastapi.testclient import TestClient


def create_sale_payload(api_client: TestClient) -> tuple[dict[str, int | str], int]:
    seller_response = api_client.post(
        "/sellers",
        json={"name": "Анна", "email": "api-sale-seller@example.com"},
    )
    buyer_response = api_client.post(
        "/buyers",
        json={"name": "Борис", "email": "api-sale-buyer@example.com"},
    )
    auction_response = api_client.post(
        "/auctions",
        json={
            "name": "Осенний аукцион",
            "starts_at": "2026-10-01T10:00:00Z",
            "ends_at": "2026-10-01T18:00:00Z",
        },
    )
    assert seller_response.status_code == 201
    assert buyer_response.status_code == 201
    assert auction_response.status_code == 201

    lot_response = api_client.post(
        "/lots",
        json={
            "auction_id": auction_response.json()["id"],
            "seller_id": seller_response.json()["id"],
            "name": "Картина",
            "description": "Картина современного художника",
            "starting_price": "1000.00",
        },
    )
    assert lot_response.status_code == 201

    payload: dict[str, int | str] = {
        "lot_id": lot_response.json()["id"],
        "buyer_id": buyer_response.json()["id"],
        "final_price": "1250.00",
    }
    return payload, lot_response.json()["id"]


def test_create_and_read_sale_and_revenue(api_client: TestClient) -> None:
    payload, lot_id = create_sale_payload(api_client)

    create_response = api_client.post("/sales", json=payload)

    assert create_response.status_code == 201
    sale = create_response.json()
    assert Decimal(sale["final_price"]) == Decimal("1250.00")
    assert Decimal(sale["revenue"]["commission_rate"]) == Decimal("10.00")
    assert Decimal(sale["revenue"]["amount"]) == Decimal("125.00")

    get_sale_response = api_client.get(f"/sales/{sale['id']}")
    list_sales_response = api_client.get("/sales")
    get_revenue_response = api_client.get(f"/revenues/{sale['revenue']['id']}")
    list_revenues_response = api_client.get("/revenues")
    get_lot_response = api_client.get(f"/lots/{lot_id}")

    assert get_sale_response.json() == sale
    assert list_sales_response.json() == [sale]
    assert get_revenue_response.json() == sale["revenue"]
    assert list_revenues_response.json() == [sale["revenue"]]
    assert get_lot_response.json()["status"] == "sold"


def test_reject_sale_below_starting_price(api_client: TestClient) -> None:
    payload, _ = create_sale_payload(api_client)
    payload["final_price"] = "999.99"

    response = api_client.post("/sales", json=payload)

    assert response.status_code == 400
    assert response.json() == {"detail": "Итоговая цена ниже начальной цены лота"}


def test_reject_repeated_sale(api_client: TestClient) -> None:
    payload, _ = create_sale_payload(api_client)
    first_response = api_client.post("/sales", json=payload)

    second_response = api_client.post("/sales", json=payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json() == {"detail": "Лот уже продан"}


def test_reject_sale_with_unknown_lot(api_client: TestClient) -> None:
    payload, _ = create_sale_payload(api_client)
    payload["lot_id"] = 999999

    response = api_client.post("/sales", json=payload)

    assert response.status_code == 404
    assert response.json() == {"detail": "Лот не найден"}


def test_reject_sale_with_unknown_buyer(api_client: TestClient) -> None:
    payload, _ = create_sale_payload(api_client)
    payload["buyer_id"] = 999999

    response = api_client.post("/sales", json=payload)

    assert response.status_code == 404
    assert response.json() == {"detail": "Покупатель не найден"}


def test_reject_invalid_sale_payload(api_client: TestClient) -> None:
    response = api_client.post(
        "/sales",
        json={"lot_id": 0, "buyer_id": 0, "final_price": "-1.00"},
    )

    assert response.status_code == 422


def test_get_unknown_sale_and_revenue(api_client: TestClient) -> None:
    sale_response = api_client.get("/sales/999999")
    revenue_response = api_client.get("/revenues/999999")

    assert sale_response.status_code == 404
    assert sale_response.json() == {"detail": "Продажа не найдена"}
    assert revenue_response.status_code == 404
    assert revenue_response.json() == {"detail": "Доход не найден"}
