"""Проверить миграции на двух отдельных временных базах PostgreSQL."""

import json
import os
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import psycopg
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from psycopg import sql
from scripts.setup import administrative_url, connect
from sqlalchemy import Connection, Engine, MetaData, Table, create_engine, inspect, select, text
from sqlalchemy.engine import URL, make_url
from tests.configuration import load_test_settings

from auctions.auth import hash_password

ROOT = Path(__file__).resolve().parents[1]


def migration_config(connection: Connection) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


@contextmanager
def temporary_database(
    admin: psycopg.Connection, test_url: URL, purpose: str = "migration"
) -> Iterator[Engine]:
    name = f"auctions_{purpose}_{uuid4().hex}_test"
    admin.execute(
        sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0").format(
            sql.Identifier(name), sql.Identifier(test_url.username)
        )
    )
    engine = None
    try:
        engine = create_engine(test_url.set(database=name))
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))


def columns(connection: Connection) -> dict[str, list[str]]:
    inspector = inspect(connection)
    return {
        name: [column["name"] for column in inspector.get_columns(name)]
        for name in inspector.get_table_names()
        if name != "alembic_version"
    }


def read_data(
    connection: Connection, existing_columns: dict[str, list[str]]
) -> dict[str, list[dict]]:
    metadata = MetaData()
    metadata.reflect(connection)
    return {
        name: [
            dict(row)
            for row in connection.execute(
                select(*(metadata.tables[name].c[column] for column in names)).order_by(
                    *metadata.tables[name].primary_key.columns
                )
            ).mappings()
        ]
        for name, names in existing_columns.items()
    }


def insert(connection: Connection, table: Table, **values: object) -> int:
    return connection.execute(table.insert().values(**values).returning(table.c.id)).scalar_one()


def seed_initial(connection: Connection) -> dict[str, int]:
    metadata = MetaData()
    metadata.reflect(connection)
    tables = metadata.tables
    seller = insert(connection, tables["sellers"], name="Продавец миграций")
    buyer = insert(connection, tables["buyers"], name="Покупатель миграций")
    starts_at = datetime(2026, 10, 14, 10, tzinfo=UTC)
    auction = insert(
        connection,
        tables["auctions"],
        name="Контрольный аукцион",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=8),
        status="planned",
    )
    lot_ids = []
    for status in ["available", "sold"]:
        lot_ids.append(
            insert(
                connection,
                tables["lots"],
                auction_id=auction,
                seller_id=seller,
                name=f"Контрольный лот {status}",
                description="Данные должны сохраниться после миграций",
                starting_price=Decimal("1000.00"),
                status=status,
            )
        )
    sale = insert(
        connection,
        tables["sales"],
        lot_id=lot_ids[1],
        buyer_id=buyer,
        final_price=Decimal("1250.00"),
    )
    insert(
        connection,
        tables["revenues"],
        sale_id=sale,
        commission_rate=Decimal("10.00"),
        amount=Decimal("125.00"),
    )
    return {"seller": seller, "buyer": buyer, "lot": lot_ids[0]}


def seed_new_tables(connection: Connection, revision: str, ids: dict[str, int]) -> None:
    metadata = MetaData()
    metadata.reflect(connection)
    if revision == "20260917_0002":
        insert(
            connection,
            metadata.tables["accounts"],
            last_name="Тестов",
            first_name="Продавец",
            middle_name="Миграций",
            username="migration-seller",
            password_hash=hash_password(secrets.token_urlsafe(24)),
            role="user",
            seller_id=ids["seller"],
        )
    elif revision == "20260917_0003":
        insert(
            connection,
            metadata.tables["purchase_requests"],
            lot_id=ids["lot"],
            buyer_id=ids["buyer"],
            offered_price=Decimal("1100.00"),
            status="pending",
        )
        insert(
            connection,
            metadata.tables["purchase_requests"],
            lot_id=ids["lot"],
            buyer_id=ids["buyer"],
            offered_price=Decimal("1000.00"),
            status="rejected",
            reviewed_at=datetime(2026, 10, 14, 12, tzinfo=UTC),
        )
    elif revision == "20261014_0004":
        requests = metadata.tables["purchase_requests"]
        legacy = connection.execute(select(requests.c.rejection_reason)).scalars().all()
        require(
            len(legacy) == 2 and all(reason is None for reason in legacy),
            "Причины старых заявок должны остаться NULL.",
        )
        insert(
            connection,
            requests,
            lot_id=ids["lot"],
            buyer_id=ids["buyer"],
            offered_price=Decimal("1200.00"),
            status="rejected",
            reviewed_at=datetime(2026, 10, 14, 13, tzinfo=UTC),
            rejection_reason="Контрольная причина отклонения",
        )


def current_revision(connection: Connection) -> str:
    return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def verify_head(connection: Connection, head: str) -> None:
    require(current_revision(connection) == head, "БД не обновлена до head.")
    command.check(migration_config(connection))
    existing_columns = columns(connection)
    before = read_data(connection, existing_columns)
    command.upgrade(migration_config(connection), "head")
    require(read_data(connection, existing_columns) == before, "Повторный upgrade изменил данные.")


def check_clean(admin: psycopg.Connection, test_url: URL, head: str) -> dict:
    with temporary_database(admin, test_url) as engine, engine.begin() as connection:
        require(not inspect(connection).get_table_names(), "Временная БД не пустая.")
        command.upgrade(migration_config(connection), "head")
        verify_head(connection, head)
        return {"scenario": "clean_database", "status": "passed", "head": head}


def check_populated(
    admin: psycopg.Connection, test_url: URL, revisions: list[str], head: str
) -> dict:
    stages = []
    with temporary_database(admin, test_url) as engine:
        with engine.begin() as connection:
            command.upgrade(migration_config(connection), revisions[0])
            ids = seed_initial(connection)
        for revision in revisions[1:]:
            with engine.begin() as connection:
                existing_columns = columns(connection)
                before = read_data(connection, existing_columns)
                command.upgrade(migration_config(connection), revision)
                require(
                    current_revision(connection) == revision, "Не применена очередная миграция."
                )
                require(
                    read_data(connection, existing_columns) == before,
                    f"Миграция {revision} изменила существующие записи.",
                )
                seed_new_tables(connection, revision, ids)
                stages.append(
                    {"revision": revision, "records_preserved": sum(map(len, before.values()))}
                )
        with engine.begin() as connection:
            verify_head(connection, head)
            counts = {
                name: len(rows) for name, rows in read_data(connection, columns(connection)).items()
            }
        return {
            "scenario": "populated_database",
            "status": "passed",
            "stages": stages,
            "final_records": counts,
        }


def main() -> None:
    os.chdir(ROOT)
    report = {"status": "running", "scenarios": []}
    try:
        settings = load_test_settings()
        test_url = make_url(settings.database_url)
        script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
        require(len(script.get_heads()) == 1, "Ожидается одна последовательная цепочка миграций.")
        chain = list(reversed(list(script.walk_revisions())))
        require(len(chain) >= 3, "Необходимо не менее трёх миграций.")
        for index, revision in enumerate(chain):
            previous = chain[index - 1].revision if index else None
            require(revision.down_revision == previous, "Цепочка миграций должна быть линейной.")
        revisions = [revision.revision for revision in chain]
        report["revisions"] = revisions
        with connect(administrative_url(test_url)) as admin:
            report["scenarios"].append(check_clean(admin, test_url, revisions[-1]))
            report["scenarios"].append(check_populated(admin, test_url, revisions, revisions[-1]))
        report["status"] = "passed"
        print("Миграции чистой и заполненной БД проверены. Отчёт: reports/migrations.json")
    except Exception as error:
        report["status"] = "failed"
        report["error_type"] = type(error).__name__
        raise
    finally:
        reports = ROOT / "reports"
        reports.mkdir(exist_ok=True)
        (reports / "migrations.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
