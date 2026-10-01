"""Add Next Ride 1.0 assignment flag and one-next-ride index

Revision ID: c3a9d5e8f1b2
Revises: b2e8c7d1a4f6
Create Date: 2026-08-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3a9d5e8f1b2"
down_revision: Union[str, Sequence[str], None] = "b2e8c7d1a4f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DRIVER_ACTIVE_INDEX = "uq_ride_requests_one_active_per_driver"
DRIVER_NEXT_INDEX = "uq_ride_requests_one_next_per_driver"

PREVIOUS_ACTIVE_PREDICATE = sa.text(
    "accepted_driver_id IS NOT NULL AND status IN ("
    "'accepted', "
    "'driver_arriving', "
    "'driver_arrived', "
    "'in_progress'"
    ")"
)
CURRENT_ACTIVE_PREDICATE = sa.text(
    "accepted_driver_id IS NOT NULL "
    "AND is_next_ride IS NOT TRUE AND status IN ("
    "'accepted', "
    "'driver_arriving', "
    "'driver_arrived', "
    "'in_progress'"
    ")"
)
NEXT_ACTIVE_PREDICATE = sa.text(
    "accepted_driver_id IS NOT NULL "
    "AND is_next_ride IS TRUE "
    "AND status = 'accepted'"
)


def upgrade() -> None:
    op.add_column(
        "ride_requests",
        sa.Column(
            "is_next_ride",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.drop_index(DRIVER_ACTIVE_INDEX, table_name="ride_requests")
    op.create_index(
        DRIVER_ACTIVE_INDEX,
        "ride_requests",
        ["accepted_driver_id"],
        unique=True,
        postgresql_where=CURRENT_ACTIVE_PREDICATE,
    )
    op.create_index(
        DRIVER_NEXT_INDEX,
        "ride_requests",
        ["accepted_driver_id"],
        unique=True,
        postgresql_where=NEXT_ACTIVE_PREDICATE,
    )


def downgrade() -> None:
    op.drop_index(DRIVER_NEXT_INDEX, table_name="ride_requests")
    op.drop_index(DRIVER_ACTIVE_INDEX, table_name="ride_requests")
    op.create_index(
        DRIVER_ACTIVE_INDEX,
        "ride_requests",
        ["accepted_driver_id"],
        unique=True,
        postgresql_where=PREVIOUS_ACTIVE_PREDICATE,
    )
    op.drop_column("ride_requests", "is_next_ride")
