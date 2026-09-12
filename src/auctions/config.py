from decimal import Decimal
from functools import cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения, получаемые из переменных окружения."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://auctions:auctions@localhost:5432/auctions"
    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    commission_rate: Decimal = Field(default=Decimal("10.00"), ge=0, le=100)


@cache
def get_settings() -> Settings:
    """Вернуть единый объект настроек приложения."""

    return Settings()
