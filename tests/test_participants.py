from fastapi.testclient import TestClient


def test_create_and_get_seller(api_client: TestClient) -> None:
    create_response = api_client.post(
        "/sellers",
        json={"name": "Анна"},
    )

    assert create_response.status_code == 201
    seller = create_response.json()
    assert seller["name"] == "Анна"

    get_response = api_client.get(f"/sellers/{seller['id']}")

    assert get_response.status_code == 200
    assert get_response.json() == seller


def test_list_sellers(api_client: TestClient) -> None:
    api_client.post(
        "/sellers",
        json={"name": "Борис"},
    )

    response = api_client.get("/sellers")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["name"] == "Борис"


def test_get_unknown_seller(api_client: TestClient) -> None:
    response = api_client.get("/sellers/999999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Продавец не найден"}


def test_create_and_list_buyers(api_client: TestClient) -> None:
    create_response = api_client.post(
        "/buyers",
        json={"name": "Виктор"},
    )

    assert create_response.status_code == 201

    list_response = api_client.get("/buyers")

    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["name"] == "Виктор"

    buyer_id = create_response.json()["id"]
    get_response = api_client.get(f"/buyers/{buyer_id}")

    assert get_response.status_code == 200
    assert get_response.json() == create_response.json()


def test_get_unknown_buyer(api_client: TestClient) -> None:
    response = api_client.get("/buyers/999999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Покупатель не найден"}
