"""Создать начальную схему базы данных."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260912_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создать таблицы предметной области."""

    op.create_table(
        "sellers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sellers")),
        sa.UniqueConstraint("email", name=op.f("uq_sellers_email")),
    )
    op.create_table(
        "buyers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_buyers")),
        sa.UniqueConstraint("email", name=op.f("uq_buyers_email")),
    )
    op.create_table(
        "auctions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("ends_at > starts_at", name=op.f("ck_auctions_dates")),
        sa.CheckConstraint(
            "status IN ('planned', 'active', 'completed')",
            name=op.f("ck_auctions_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auctions")),
    )
    op.create_table(
        "lots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("auction_id", sa.Integer(), nullable=False),
        sa.Column("seller_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("starting_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "starting_price > 0",
            name=op.f("ck_lots_starting_price_positive"),
        ),
        sa.CheckConstraint("status IN ('available', 'sold')", name=op.f("ck_lots_status")),
        sa.ForeignKeyConstraint(
            ["auction_id"],
            ["auctions.id"],
            name=op.f("fk_lots_auction_id_auctions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["seller_id"],
            ["sellers.id"],
            name=op.f("fk_lots_seller_id_sellers"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lots")),
    )
    op.create_index(op.f("ix_lots_auction_id"), "lots", ["auction_id"])
    op.create_index(op.f("ix_lots_seller_id"), "lots", ["seller_id"])
    op.create_table(
        "sales",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lot_id", sa.Integer(), nullable=False),
        sa.Column("buyer_id", sa.Integer(), nullable=False),
        sa.Column("final_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "sold_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("final_price > 0", name=op.f("ck_sales_final_price_positive")),
        sa.ForeignKeyConstraint(
            ["buyer_id"],
            ["buyers.id"],
            name=op.f("fk_sales_buyer_id_buyers"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["lot_id"],
            ["lots.id"],
            name=op.f("fk_sales_lot_id_lots"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sales")),
        sa.UniqueConstraint("lot_id", name=op.f("uq_sales_lot_id")),
    )
    op.create_index(op.f("ix_sales_buyer_id"), "sales", ["buyer_id"])
    op.create_table(
        "revenues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sale_id", sa.Integer(), nullable=False),
        sa.Column("commission_rate", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("amount >= 0", name=op.f("ck_revenues_amount_non_negative")),
        sa.CheckConstraint(
            "commission_rate >= 0 AND commission_rate <= 100",
            name=op.f("ck_revenues_commission_rate_range"),
        ),
        sa.ForeignKeyConstraint(
            ["sale_id"],
            ["sales.id"],
            name=op.f("fk_revenues_sale_id_sales"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_revenues")),
        sa.UniqueConstraint("sale_id", name=op.f("uq_revenues_sale_id")),
    )


def downgrade() -> None:
    """Удалить таблицы предметной области."""

    op.drop_table("revenues")
    op.drop_index(op.f("ix_sales_buyer_id"), table_name="sales")
    op.drop_table("sales")
    op.drop_index(op.f("ix_lots_seller_id"), table_name="lots")
    op.drop_index(op.f("ix_lots_auction_id"), table_name="lots")
    op.drop_table("lots")
    op.drop_table("auctions")
    op.drop_table("buyers")
    op.drop_table("sellers")
