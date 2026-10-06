import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize(
    "path",
    [
        "/lots",
        "/lots/1",
        "/auctions",
        "/auctions/1",
        "/sellers",
        "/sellers/1",
        "/buyers",
        "/buyers/1",
        "/sales",
        "/sales/1",
        "/revenues",
        "/revenues/1",
        "/web/lots",
        "/web/sales",
        "/web/purchase-requests",
    ],
)
def test_anonymous_reads_denied(api_client: TestClient, path: str) -> None:
    assert api_client.get(path).status_code == 401


@pytest.mark.parametrize("path", ["/lots", "/auctions", "/sales", "/web/lots", "/auth/me"])
def test_anonymous_browser_navigation_redirects_to_login(api_client: TestClient, path: str) -> None:
    response = api_client.get(path, headers={"Accept": "text/html"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


@pytest.mark.parametrize("path", ["/lots", "/auctions", "/sellers", "/buyers", "/sales"])
def test_anonymous_writes_denied(api_client: TestClient, path: str) -> None:
    assert api_client.post(path, json={}).status_code == 401


def test_unregistered_user_cannot_access_admin_data(admin_client: TestClient) -> None:
    response = admin_client.post(
        "/web/admin/accounts",
        json={
            "last_name": "Тест",
            "first_name": "Тест",
            "middle_name": "Тест",
            "username": "authorization-test",
            "password": "password123!",
            "role": "user",
        },
    )
    assert response.status_code == 201
    admin_client.post("/auth/logout")
    assert (
        admin_client.post(
            "/auth/login",
            json={
                "username": "authorization-test",
                "password": "password123!",
            },
        ).status_code
        == 200
    )
    for path in ("/sellers", "/buyers", "/revenues", "/revenues/1"):
        assert admin_client.get(path).status_code == 403
    assert admin_client.get("/lots").json() == []
    assert admin_client.get("/sales").json() == []
    assert (
        admin_client.post(
            "/auctions",
            json={
                "name": "Тест",
                "starts_at": "2026-10-01T10:00:00Z",
                "ends_at": "2026-10-01T18:00:00Z",
            },
        ).status_code
        == 403
    )
