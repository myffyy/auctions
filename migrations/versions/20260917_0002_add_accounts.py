"""Добавить учётные записи веб-интерфейса."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260917_0002"
down_revision: str | Sequence[str] | None = "20260912_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("middle_name", sa.String(length=100), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("seller_id", sa.Integer(), nullable=True),
        sa.Column("buyer_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("role IN ('admin', 'user')", name=op.f("ck_accounts_account_role")),
        sa.ForeignKeyConstraint(
            ["seller_id"],
            ["sellers.id"],
            ondelete="RESTRICT",
            name=op.f("fk_accounts_seller_id_sellers"),
        ),
        sa.ForeignKeyConstraint(
            ["buyer_id"],
            ["buyers.id"],
            ondelete="RESTRICT",
            name=op.f("fk_accounts_buyer_id_buyers"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accounts")),
        sa.UniqueConstraint("username", name=op.f("uq_accounts_username")),
        sa.UniqueConstraint("seller_id", name=op.f("uq_accounts_seller_id")),
        sa.UniqueConstraint("buyer_id", name=op.f("uq_accounts_buyer_id")),
    )


def downgrade() -> None:
    op.drop_table("accounts")
