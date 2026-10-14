"""Проверки защит команд копирования без подключения к БД."""

from pathlib import Path

import pytest
from psycopg.conninfo import conninfo_to_dict
from scripts.backup import BackupError, connection_parameters, create_backup, restore_backup
from sqlalchemy.engine import URL, make_url

TEST_URL = make_url("postgresql+psycopg://tester:backup-password@127.0.0.1:1/backup_test")


@pytest.mark.parametrize("password", ["backup-password", "p@ss:' word"])
def test_password_is_not_in_command_arguments(password: str) -> None:
    url = URL.create(
        "postgresql+psycopg",
        username="tester",
        password=password,
        host="127.0.0.1",
        port=5432,
        database="backup_test",
    )
    connection, env = connection_parameters(url)

    assert "password" not in conninfo_to_dict(connection)
    assert password not in connection
    assert env["PGPASSWORD"] == password
    assert conninfo_to_dict(connection)["dbname"] == "backup_test"


def test_password_from_query_is_not_in_command_arguments() -> None:
    url = TEST_URL.update_query_dict({"password": "query-password"})
    connection, env = connection_parameters(url)

    assert "password" not in conninfo_to_dict(connection)
    assert "query-password" not in connection
    assert env["PGPASSWORD"] == "query-password"


def test_unrelated_password_is_not_inherited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PGPASSWORD", "unrelated-password")
    url = URL.create("postgresql+psycopg", username="tester", database="backup_test")
    _, env = connection_parameters(url)

    assert "PGPASSWORD" not in env


def test_existing_backup_is_not_replaced(tmp_path: Path) -> None:
    archive = tmp_path / "existing.dump"
    archive.write_bytes(b"existing backup")

    with pytest.raises(FileExistsError):
        create_backup(TEST_URL, archive)

    assert archive.read_bytes() == b"existing backup"


def test_invalid_archive_is_rejected_before_connection(tmp_path: Path) -> None:
    archive = tmp_path / "invalid.dump"
    archive.write_bytes(b"not a postgres archive")

    with pytest.raises(BackupError, match="custom-архив"):
        restore_backup(TEST_URL, archive)


def test_missing_archive_is_rejected_before_connection(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        restore_backup(TEST_URL, tmp_path / "missing.dump")
