from fastapi.testclient import TestClient

from auctions.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version_reports_image_revision(monkeypatch) -> None:
    revision = "a" * 40
    monkeypatch.setenv("RELEASE_REVISION", revision)

    response = client.get("/version")

    assert response.status_code == 200
    assert response.json() == {"revision": revision}
