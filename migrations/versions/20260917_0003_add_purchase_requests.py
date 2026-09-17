"""Добавить заявки покупателей на подтверждение продажи."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260917_0003"
down_revision: str | Sequence[str] | None = "20260917_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "purchase_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lot_id", sa.Integer(), nullable=False),
        sa.Column("buyer_id", sa.Integer(), nullable=False),
        sa.Column("offered_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "offered_price > 0", name=op.f("ck_purchase_requests_offered_price_positive")
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name=op.f("ck_purchase_requests_purchase_request_status"),
        ),
        sa.ForeignKeyConstraint(
            ["buyer_id"],
            ["buyers.id"],
            name=op.f("fk_purchase_requests_buyer_id_buyers"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["lot_id"],
            ["lots.id"],
            name=op.f("fk_purchase_requests_lot_id_lots"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_purchase_requests")),
    )
    op.create_index(op.f("ix_purchase_requests_buyer_id"), "purchase_requests", ["buyer_id"])
    op.create_index(op.f("ix_purchase_requests_lot_id"), "purchase_requests", ["lot_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_purchase_requests_lot_id"), table_name="purchase_requests")
    op.drop_index(op.f("ix_purchase_requests_buyer_id"), table_name="purchase_requests")
    op.drop_table("purchase_requests")
