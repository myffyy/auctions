"""Проверить копирование, повреждение и восстановление во временной БД."""

import json
import os
import tempfile
from decimal import Decimal
from pathlib import Path

from alembic import command
from scripts.backup import BackupError, create_backup, restore_backup, validate_archive
from scripts.check_migrations import (
    columns,
    current_revision,
    migration_config,
    read_data,
    require,
    seed_initial,
    seed_new_tables,
    temporary_database,
)
from scripts.setup import administrative_url, connect
from sqlalchemy import Connection, MetaData, func, select, text
from sqlalchemy.engine import make_url
from tests.configuration import load_test_settings

ROOT = Path(__file__).resolve().parents[1]


def verify_sequences(connection: Connection) -> list[str]:
    metadata = MetaData()
    metadata.reflect(connection)
    checked = []
    for name, table in metadata.tables.items():
        if name == "alembic_version":
            continue
        sequence = connection.execute(
            text("SELECT pg_get_serial_sequence(:table, 'id')"), {"table": f"public.{name}"}
        ).scalar_one()
        require(sequence is not None, f"Не найдена последовательность {name}.id.")
        next_id = connection.execute(
            text("SELECT nextval(CAST(:sequence AS regclass))"), {"sequence": sequence}
        ).scalar_one()
        maximum = connection.execute(select(func.max(table.c.id))).scalar_one() or 0
        require(next_id > maximum, f"Последовательность {name}.id не восстановлена.")
        checked.append(name)
    return sorted(checked)


def run_scenario() -> dict:
    test_url = make_url(load_test_settings().database_url)
    with (
        connect(administrative_url(test_url)) as admin,
        temporary_database(admin, test_url, purpose="backup") as engine,
        tempfile.TemporaryDirectory(prefix="auctions-backup-check-") as directory,
    ):
        with engine.begin() as connection:
            command.upgrade(migration_config(connection), "head")
            ids = seed_initial(connection)
            for revision in ["20260917_0002", "20260917_0003", "20261014_0004"]:
                seed_new_tables(connection, revision, ids)
            existing_columns = columns(connection)
            before = read_data(connection, existing_columns)
            revision = current_revision(connection)
        archive = Path(directory) / "original.dump"
        create_backup(engine.url, archive)
        require(archive.stat().st_mode & 0o777 == 0o600, "Копия должна иметь права 0600.")
        original_archive = archive.read_bytes()
        try:
            create_backup(engine.url, archive)
        except FileExistsError:
            pass
        else:
            raise RuntimeError("Существующая копия была перезаписана.")
        require(archive.read_bytes() == original_archive, "Существующая копия изменилась.")
        with engine.begin() as connection:
            metadata = MetaData()
            metadata.reflect(connection)
            connection.execute(metadata.tables["sellers"].update().values(name="Повреждено"))
            connection.execute(
                metadata.tables["lots"].update().values(starting_price=Decimal("1.00"))
            )
            connection.execute(metadata.tables["revenues"].delete())
            connection.execute(
                metadata.tables["purchase_requests"]
                .delete()
                .where(metadata.tables["purchase_requests"].c.rejection_reason.is_not(None))
            )
            damaged = read_data(connection, existing_columns)
            require(damaged != before, "Данные не были повреждены для проверки.")
        restore_backup(engine.url, archive)
        with engine.begin() as connection:
            require(
                read_data(connection, existing_columns) == before,
                "Данные восстановлены не полностью.",
            )
            require(current_revision(connection) == revision, "Ревизия Alembic не восстановлена.")
            command.check(migration_config(connection))
            sequences = verify_sequences(connection)
            sequence_values = connection.execute(
                text(
                    "SELECT sequencename, last_value FROM pg_sequences "
                    "WHERE schemaname = 'public' ORDER BY sequencename"
                )
            ).all()
        damaged_archive = Path(directory) / "truncated.dump"
        damaged_archive.write_bytes(original_archive[:-64])
        validate_archive(damaged_archive)
        try:
            restore_backup(engine.url, damaged_archive)
        except BackupError:
            pass
        else:
            raise RuntimeError("Восстановление усечённого архива ошибочно завершилось успешно.")
        with engine.begin() as connection:
            require(
                read_data(connection, existing_columns) == before,
                "Ошибка восстановления оставила частично изменённые данные.",
            )
            require(
                current_revision(connection) == revision, "Ошибка восстановления изменила ревизию."
            )
            command.check(migration_config(connection))
            require(
                connection.execute(
                    text(
                        "SELECT sequencename, last_value FROM pg_sequences "
                        "WHERE schemaname = 'public' ORDER BY sequencename"
                    )
                ).all()
                == sequence_values,
                "Ошибка восстановления изменила последовательности ID.",
            )
        return {
            "status": "passed",
            "revision": revision,
            "restored_records": {name: len(rows) for name, rows in before.items()},
            "sequences_checked": sequences,
            "existing_backup_preserved": True,
            "corrupted_archive_rolled_back": True,
        }


def main() -> None:
    os.chdir(ROOT)
    report = {"status": "running"}
    try:
        report = run_scenario()
        print("Копия, повреждение и восстановление проверены. Отчёт: reports/backup.json")
    except Exception as error:
        report = {"status": "failed", "error_type": type(error).__name__}
        raise
    finally:
        reports = ROOT / "reports"
        reports.mkdir(exist_ok=True)
        (reports / "backup.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
