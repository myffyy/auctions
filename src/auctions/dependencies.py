from collections.abc import Iterator

from sqlalchemy.orm import Session

from auctions.database import SessionLocal


def get_db_session() -> Iterator[Session]:
    """Предоставить сессию базы данных на время HTTP-запроса."""

    with SessionLocal() as session:
        yield session
