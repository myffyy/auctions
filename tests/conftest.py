from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from auctions.config import get_settings
from tests.configuration import apply_test_settings, load_test_settings


def pytest_configure() -> None:
    """Изолировать настройки до импорта приложения при сборе тестов."""
    try:
        settings = load_test_settings()
    except ValueError as error:
        raise pytest.UsageError(str(error)) from None
    apply_test_settings(settings)


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    """Применить миграции только к тестовой БД."""
    from auctions.database import engine

    try:
        command.upgrade(Config("alembic.ini"), "head")
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(test_engine: Engine) -> Iterator[Session]:
    """Гарантировать откат изменений даже при падении теста."""
    with test_engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                yield session
        finally:
            transaction.rollback()


@pytest.fixture
def test_app() -> FastAPI:
    from auctions.main import app

    return app


@pytest.fixture
def api_client(db_session: Session, test_app: FastAPI) -> Iterator[TestClient]:
    """Подменить сессию и восстановить зависимости при любом исходе теста."""
    from auctions.dependencies import get_db_session

    def override_db_session() -> Iterator[Session]:
        yield db_session

    original_overrides = test_app.dependency_overrides.copy()
    test_app.dependency_overrides[get_db_session] = override_db_session
    try:
        with TestClient(test_app) as client:
            yield client
    finally:
        test_app.dependency_overrides.clear()
        test_app.dependency_overrides.update(original_overrides)


@pytest.fixture
def admin_client(api_client: TestClient) -> TestClient:
    settings = get_settings()
    response = api_client.post(
        "/auth/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    )
    assert response.status_code == 200
    return api_client
