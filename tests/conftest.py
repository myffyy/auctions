from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from auctions.database import engine
from auctions.dependencies import get_db_session
from auctions.main import app


@pytest.fixture
def db_session() -> Iterator[Session]:
    """Откатить все изменения базы после каждого теста."""

    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()


@pytest.fixture
def api_client(db_session: Session) -> Iterator[TestClient]:
    """Подменить сессию приложения тестовой транзакцией."""

    def override_db_session() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_db_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_db_session, None)
