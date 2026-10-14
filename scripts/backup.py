"""Создать или восстановить custom-архив PostgreSQL."""

import argparse
import os
import shutil

# Запуск только системных pg_dump/pg_restore без оболочки; см. docs/sast.md.
import subprocess  # nosec B404
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, Literal
from uuid import uuid4

from psycopg.conninfo import make_conninfo
from sqlalchemy.engine import URL, make_url

from auctions.config import Settings

ROOT = Path(__file__).resolve().parents[1]


class BackupError(RuntimeError):
    """Ошибка копирования или восстановления PostgreSQL."""


def connection_parameters(url: URL) -> tuple[str, dict[str, str]]:
    if url.drivername != "postgresql+psycopg" or not url.database or not url.username:
        raise ValueError("DATABASE_URL должен задавать PostgreSQL, пользователя и БД.")
    parameters = url.translate_connect_args(username="user", database="dbname")
    parameters.update(url.query)
    password = parameters.pop("password", None)
    parameters.setdefault("connect_timeout", "5")
    env = dict(os.environ)
    env.pop("PGPASSWORD", None)
    if password is not None:
        env["PGPASSWORD"] = password
    return make_conninfo(**parameters), env


def run_tool(
    tool: Literal["pg_dump", "pg_restore"],
    arguments: list[str],
    url: URL | None = None,
    stdout: BinaryIO | int = subprocess.DEVNULL,
) -> None:
    executable = shutil.which(tool)
    if executable is None:
        raise BackupError(f"Не найден {tool}. Установите клиентские утилиты PostgreSQL.")
    env = dict(os.environ)
    if url is not None:
        connection, env = connection_parameters(url)
        arguments = ["--dbname", connection, "--no-password", *arguments]
    # Исполняемый файл найден в PATH, аргументы передаются списком, пароль только в env.
    result = subprocess.run(  # nosec B603
        [executable, *arguments],
        shell=False,
        env=env,
        stdout=stdout,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise BackupError(f"{tool} завершился с ошибкой: {message}")


def validate_archive(path: Path) -> None:
    with path.open("rb") as archive:
        if archive.read(5) != b"PGDMP":
            raise BackupError("Ожидается custom-архив, созданный командой make backup.")
    run_tool("pg_restore", ["--list", str(path)])


def create_backup(url: URL, output: Path) -> Path:
    output = output.resolve()
    if output.exists():
        raise FileExistsError("Файл копии уже существует; выберите другое имя.")
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as archive:
            run_tool("pg_dump", ["--format=custom", "--no-owner", "--no-privileges"], url, archive)
        validate_archive(temporary_path)
        os.link(temporary_path, output)
    finally:
        temporary_path.unlink(missing_ok=True)
    return output


def restore_backup(url: URL, archive: Path) -> None:
    archive = archive.resolve()
    validate_archive(archive)
    run_tool(
        "pg_restore",
        [
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-privileges",
            "--single-transaction",
            "--exit-on-error",
            str(archive),
        ],
        url,
    )


def main() -> None:
    os.chdir(ROOT)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "restore"])
    parser.add_argument("--file", default=os.environ.get("BACKUP_FILE"))
    args = parser.parse_args()
    url = make_url(Settings().database_url)
    try:
        if args.action == "create":
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            output = (
                Path(args.file)
                if args.file
                else ROOT / "backups" / f"auctions_{stamp}_{uuid4().hex[:8]}.dump"
            )
            path = create_backup(url, output)
            print(f"Резервная копия создана: {path}")
        else:
            if not args.file:
                parser.error("Для восстановления задайте BACKUP_FILE или --file.")
            restore_backup(url, Path(args.file))
            print("Схема и данные БД восстановлены из резервной копии.")
    except (BackupError, OSError, ValueError) as error:
        raise SystemExit(str(error)) from None


if __name__ == "__main__":
    main()
