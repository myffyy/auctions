"""Подготовить конфигурацию и PostgreSQL перед первым запуском."""

import argparse
import getpass
import os
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy.engine import URL, make_url
from tests.configuration import apply_test_settings, load_test_settings

from auctions.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def prepare_env(name: str = ".env") -> None:
    """Создать локальную конфигурацию, сохранив существующий файл."""
    env_path = ROOT / name
    template = (ROOT / f"{name}.example").read_text(encoding="utf-8")
    try:
        descriptor = os.open(env_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
            destination.write(template)
        print(f"Создан {name} из {name}.example.")
    except FileExistsError:
        print(f"Используется существующий {name}.")


def connect(url: URL) -> psycopg.Connection:
    """Подключиться без вывода пароля и с ограничением времени ожидания."""
    return psycopg.connect(
        url.set(drivername="postgresql").render_as_string(hide_password=False),
        autocommit=True,
        connect_timeout=5,
    )


def prepare_database(url: URL) -> None:
    """Создать отсутствующие роль и БД; существующие данные не изменять."""
    if url.drivername != "postgresql+psycopg" or not url.database or not url.username:
        raise ValueError("DATABASE_URL должен задавать PostgreSQL, имя пользователя и БД.")

    try:
        with connect(url) as connection:
            connection.execute("SELECT 1")
        print("База данных уже доступна.")
        return
    except psycopg.OperationalError:
        pass

    admin_url = (
        make_url(os.environ["SETUP_DATABASE_URL"])
        if os.environ.get("SETUP_DATABASE_URL")
        else url.set(username=getpass.getuser(), password=None, database="postgres")
    )
    with connect(admin_url) as connection:
        if (
            connection.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = %s", (url.username,)
            ).fetchone()
            is None
        ):
            if not url.password:
                raise ValueError("Для создания роли задайте пароль в DATABASE_URL.")
            connection.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(url.username), sql.Literal(url.password)
                )
            )
            print("Создана роль приложения.")
        if (
            connection.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (url.database,)
            ).fetchone()
            is None
        ):
            connection.execute(
                sql.SQL("CREATE DATABASE {} OWNER {}").format(
                    sql.Identifier(url.database), sql.Identifier(url.username)
                )
            )
            print("Создана база данных приложения.")

    with connect(url) as connection:
        connection.execute("SELECT 1")


def main() -> None:
    os.chdir(ROOT)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", action="store_true", help="подготовить отдельную тестовую БД")
    args = parser.parse_args()
    prepare_env(".env.test" if args.test else ".env")
    try:
        if args.test:
            settings = load_test_settings()
            apply_test_settings(settings)
        prepare_database(make_url(Settings().database_url))
    except (psycopg.Error, ValueError):
        raise SystemExit(
            "Не удалось подготовить PostgreSQL. Проверьте, что сервер запущен, "
            "DATABASE_URL указан верно, а SETUP_DATABASE_URL задаёт подключение "
            "к этому же серверу с правами создания ролей и БД. "
            "Существующие пароли и владельцы автоматически не изменяются."
        ) from None
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    target = "make test" if args.test else "make run"
    print(f"Настройка завершена. Для запуска выполните {target}.")


if __name__ == "__main__":
    main()
