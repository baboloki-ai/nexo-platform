"""Add isolated driver Web Push subscriptions

Revision ID: d4b7e2c8a1f9
Revises: c3a9d5e8f1b2
Create Date: 2026-08-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4b7e2c8a1f9"
down_revision: Union[str, Sequence[str], None] = "c3a9d5e8f1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "driver_push_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "driver_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("endpoint", sa.String(), nullable=False),
        sa.Column("p256dh", sa.String(), nullable=False),
        sa.Column("auth", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_driver_push_subscriptions_id",
        "driver_push_subscriptions",
        ["id"],
    )
    op.create_index(
        "ix_driver_push_subscriptions_driver_id",
        "driver_push_subscriptions",
        ["driver_id"],
    )
    op.create_index(
        "ix_driver_push_subscriptions_endpoint",
        "driver_push_subscriptions",
        ["endpoint"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_driver_push_subscriptions_endpoint",
        table_name="driver_push_subscriptions",
    )
    op.drop_index(
        "ix_driver_push_subscriptions_driver_id",
        table_name="driver_push_subscriptions",
    )
    op.drop_index(
        "ix_driver_push_subscriptions_id",
        table_name="driver_push_subscriptions",
    )
    op.drop_table("driver_push_subscriptions")
