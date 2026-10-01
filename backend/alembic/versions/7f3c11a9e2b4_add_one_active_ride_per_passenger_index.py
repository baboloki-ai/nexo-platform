"""Add one active ride per passenger partial unique index

Revision ID: 7f3c11a9e2b4
Revises: 681302fa2545
Create Date: 2026-08-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7f3c11a9e2b4"
down_revision: Union[str, Sequence[str], None] = "681302fa2545"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "uq_ride_requests_one_active_per_passenger"
ACTIVE_RIDE_STATUS_PREDICATE = sa.text(
    "status IN ("
    "'pending', "
    "'pending_driver_acceptance', "
    "'accepted', "
    "'driver_arriving', "
    "'driver_arrived', "
    "'in_progress'"
    ")"
)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        INDEX_NAME,
        "ride_requests",
        ["passenger_id"],
        unique=True,
        postgresql_where=ACTIVE_RIDE_STATUS_PREDICATE,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        INDEX_NAME,
        table_name="ride_requests",
    )
