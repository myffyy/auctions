"""Изолированная конфигурация автоматических тестов."""

import os
from decimal import Decimal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

from auctions.config import Settings, get_settings


class IsolatedTestSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.test", env_file_encoding="utf-8", env_prefix="TEST_", extra="ignore"
    )

    database_url: str = (
        "postgresql+psycopg://auctions_test:auctions_test@localhost:5432/auctions_test"
    )
    commission_rate: Decimal = Field(default=Decimal("10.00"), ge=0, le=100)
    session_secret: str = "isolated-test-session-secret"
    admin_last_name: str = "Тестов"
    admin_first_name: str = "Администратор"
    admin_middle_name: str = "Тестович"
    admin_username: str = "test-admin"
    admin_password: str = "test-admin-password"


def validate_database_url(test_url: str, application_url: str) -> None:
    """Отклонить рабочую БД и неоднозначные параметры до подключения."""
    test = make_url(test_url)
    application = make_url(application_url)
    if (
        test.drivername != "postgresql+psycopg"
        or not test.username
        or not test.database
        or not test.database.endswith("_test")
        or test.database == application.database
        or test.query
    ):
        raise ValueError(
            "TEST_DATABASE_URL должен задавать PostgreSQL, пользователя и отдельную БД "
            "с суффиксом _test, без параметров запроса. Имя рабочей БД использовать запрещено."
        )


def load_test_settings() -> IsolatedTestSettings:
    settings = IsolatedTestSettings()
    validate_database_url(settings.database_url, Settings().database_url)
    return settings


def apply_test_settings(settings: IsolatedTestSettings) -> None:
    """Настроить приложение до импорта engine и HTTP-маршрутов."""
    for name, value in settings.model_dump().items():
        os.environ[name.upper()] = str(value)
    get_settings.cache_clear()
