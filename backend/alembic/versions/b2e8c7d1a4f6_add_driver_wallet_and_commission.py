"""Add driver wallets and commission ledger

Revision ID: b2e8c7d1a4f6
Revises: 9d1f4b8c2a70
Create Date: 2026-08-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2e8c7d1a4f6"
down_revision: Union[str, Sequence[str], None] = "9d1f4b8c2a70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COMMISSION_INDEX = "uq_wallet_ledger_one_commission_per_ride"


def upgrade() -> None:
    op.create_table(
        "driver_wallets",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "driver_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("available_balance", sa.Numeric(12, 2), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_driver_wallets_id", "driver_wallets", ["id"])
    op.create_index(
        "ix_driver_wallets_driver_id",
        "driver_wallets",
        ["driver_id"],
        unique=True,
    )

    op.create_table(
        "wallet_ledger_entries",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "driver_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "ride_id",
            sa.Integer(),
            sa.ForeignKey("ride_requests.id"),
            nullable=True,
        ),
        sa.Column("entry_type", sa.String(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("balance_after", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_wallet_ledger_entries_id",
        "wallet_ledger_entries",
        ["id"],
    )
    op.create_index(
        "ix_wallet_ledger_entries_driver_id",
        "wallet_ledger_entries",
        ["driver_id"],
    )
    op.create_index(
        "ix_wallet_ledger_entries_ride_id",
        "wallet_ledger_entries",
        ["ride_id"],
    )
    op.create_index(
        COMMISSION_INDEX,
        "wallet_ledger_entries",
        ["ride_id"],
        unique=True,
        postgresql_where=sa.text(
            "entry_type = 'commission' AND ride_id IS NOT NULL"
        ),
    )

    op.execute(
        """
        INSERT INTO driver_wallets (driver_id, available_balance, updated_at)
        SELECT id, 40.00, CURRENT_TIMESTAMP
        FROM users
        WHERE role = 'driver'
          AND NOT EXISTS (
            SELECT 1 FROM driver_wallets w WHERE w.driver_id = users.id
          )
        """
    )
    op.execute(
        """
        INSERT INTO wallet_ledger_entries (
            driver_id, ride_id, entry_type, amount, balance_after, created_at
        )
        SELECT driver_id, NULL, 'launch_seed', 40.00, 40.00, updated_at
        FROM driver_wallets
        WHERE NOT EXISTS (
            SELECT 1
            FROM wallet_ledger_entries e
            WHERE e.driver_id = driver_wallets.driver_id
              AND e.entry_type = 'launch_seed'
        )
        """
    )


def downgrade() -> None:
    op.drop_index(COMMISSION_INDEX, table_name="wallet_ledger_entries")
    op.drop_index(
        "ix_wallet_ledger_entries_ride_id",
        table_name="wallet_ledger_entries",
    )
    op.drop_index(
        "ix_wallet_ledger_entries_driver_id",
        table_name="wallet_ledger_entries",
    )
    op.drop_index("ix_wallet_ledger_entries_id", table_name="wallet_ledger_entries")
    op.drop_table("wallet_ledger_entries")
    op.drop_index("ix_driver_wallets_driver_id", table_name="driver_wallets")
    op.drop_index("ix_driver_wallets_id", table_name="driver_wallets")
    op.drop_table("driver_wallets")
