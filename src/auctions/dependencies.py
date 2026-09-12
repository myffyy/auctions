from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from auctions.database import SessionLocal


def get_db_session() -> Iterator[Session]:
    """Предоставить сессию базы данных на время HTTP-запроса."""

    with SessionLocal() as session:
        yield session


DbSession = Annotated[Session, Depends(get_db_session)]
