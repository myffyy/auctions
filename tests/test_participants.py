from fastapi.testclient import TestClient


def test_create_and_get_seller(api_client: TestClient) -> None:
    create_response = api_client.post(
        "/sellers",
        json={"name": "Анна", "email": "anna@example.com"},
    )

    assert create_response.status_code == 201
    seller = create_response.json()
    assert seller["name"] == "Анна"
    assert seller["email"] == "anna@example.com"

    get_response = api_client.get(f"/sellers/{seller['id']}")

    assert get_response.status_code == 200
    assert get_response.json() == seller


def test_list_sellers(api_client: TestClient) -> None:
    api_client.post(
        "/sellers",
        json={"name": "Борис", "email": "boris@example.com"},
    )

    response = api_client.get("/sellers")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["email"] == "boris@example.com"


def test_reject_duplicate_seller_email(api_client: TestClient) -> None:
    payload = {"name": "Анна", "email": "duplicate@example.com"}
    first_response = api_client.post("/sellers", json=payload)

    second_response = api_client.post("/sellers", json=payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json() == {"detail": "Продавец с таким email уже существует"}


def test_get_unknown_seller(api_client: TestClient) -> None:
    response = api_client.get("/sellers/999999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Продавец не найден"}


def test_create_and_list_buyers(api_client: TestClient) -> None:
    create_response = api_client.post(
        "/buyers",
        json={"name": "Виктор", "email": "viktor@example.com"},
    )

    assert create_response.status_code == 201

    list_response = api_client.get("/buyers")

    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["email"] == "viktor@example.com"

    buyer_id = create_response.json()["id"]
    get_response = api_client.get(f"/buyers/{buyer_id}")

    assert get_response.status_code == 200
    assert get_response.json() == create_response.json()


def test_reject_duplicate_buyer_email(api_client: TestClient) -> None:
    payload = {"name": "Виктор", "email": "buyer-duplicate@example.com"}
    first_response = api_client.post("/buyers", json=payload)

    second_response = api_client.post("/buyers", json=payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json() == {"detail": "Покупатель с таким email уже существует"}


def test_get_unknown_buyer(api_client: TestClient) -> None:
    response = api_client.get("/buyers/999999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Покупатель не найден"}
