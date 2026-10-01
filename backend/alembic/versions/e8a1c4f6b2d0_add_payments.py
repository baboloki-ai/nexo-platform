"""Add dedicated payments table

Revision ID: e8a1c4f6b2d0
Revises: d4b7e2c8a1f9
Create Date: 2026-09-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8a1c4f6b2d0"
down_revision: Union[str, Sequence[str], None] = "d4b7e2c8a1f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UQ_PAYMENTS_ONE_PAID_PER_RIDE = "uq_payments_one_paid_per_ride"
UQ_PAYMENTS_ONE_OPEN_PER_RIDE = "uq_payments_one_open_per_ride"
UQ_PAYMENTS_PROVIDER_REFERENCE = "uq_payments_provider_reference"


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "ride_id",
            sa.Integer(),
            sa.ForeignKey("ride_requests.id"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "currency",
            sa.String(),
            nullable=False,
            server_default="BWP",
        ),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("provider_reference", sa.String(), nullable=True),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column(
            "attempt_number",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("failed_at", sa.DateTime(), nullable=True),
        sa.Column("failure_code", sa.String(), nullable=True),
        sa.Column("failure_message", sa.String(), nullable=True),
        sa.Column("cash_confirmed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "cash_confirmed_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("settlement_status", sa.String(), nullable=False),
        sa.Column("settled_at", sa.DateTime(), nullable=True),
        sa.Column(
            "refund_status",
            sa.String(),
            nullable=False,
            server_default="none",
        ),
        sa.Column("refunded_at", sa.DateTime(), nullable=True),
        sa.Column("refund_provider_reference", sa.String(), nullable=True),
        sa.Column("refund_amount", sa.Numeric(10, 2), nullable=True),
    )
    op.create_index("ix_payments_id", "payments", ["id"])
    op.create_index("ix_payments_ride_id", "payments", ["ride_id"])
    op.create_index(
        UQ_PAYMENTS_ONE_PAID_PER_RIDE,
        "payments",
        ["ride_id"],
        unique=True,
        postgresql_where=sa.text("status = 'paid'"),
    )
    op.create_index(
        UQ_PAYMENTS_ONE_OPEN_PER_RIDE,
        "payments",
        ["ride_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'processing')"),
    )
    op.create_index(
        UQ_PAYMENTS_PROVIDER_REFERENCE,
        "payments",
        ["provider", "provider_reference"],
        unique=True,
        postgresql_where=sa.text("provider_reference IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(UQ_PAYMENTS_PROVIDER_REFERENCE, table_name="payments")
    op.drop_index(UQ_PAYMENTS_ONE_OPEN_PER_RIDE, table_name="payments")
    op.drop_index(UQ_PAYMENTS_ONE_PAID_PER_RIDE, table_name="payments")
    op.drop_index("ix_payments_ride_id", table_name="payments")
    op.drop_index("ix_payments_id", table_name="payments")
    op.drop_table("payments")
