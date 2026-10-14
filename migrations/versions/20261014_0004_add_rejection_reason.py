"""Добавить причину отклонения заявки."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261014_0004"
down_revision: str | Sequence[str] | None = "20260917_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("purchase_requests", sa.Column("rejection_reason", sa.String(500), nullable=True))
    op.create_check_constraint(
        op.f("ck_purchase_requests_rejection_reason"),
        "purchase_requests",
        "rejection_reason IS NULL OR (status = 'rejected' AND length(btrim(rejection_reason)) > 0)",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_purchase_requests_rejection_reason"), "purchase_requests", type_="check"
    )
    op.drop_column("purchase_requests", "rejection_reason")
