"""Exclude a consented shared joiner from the one-active-driver index

Revision ID: a7d3e1c9b5f0
Revises: 5bb416fbfea4
Create Date: 2026-09-23

Consent assigns the joiner as accepted while the host ride is still
in_progress. That joiner must not count as a second active assignment.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7d3e1c9b5f0"
down_revision: Union[str, Sequence[str], None] = "5bb416fbfea4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DRIVER_ACTIVE_INDEX = "uq_ride_requests_one_active_per_driver"

PREVIOUS_ACTIVE_PREDICATE = sa.text(
    "accepted_driver_id IS NOT NULL "
    "AND is_next_ride IS NOT TRUE AND status IN ("
    "'accepted', "
    "'driver_arriving', "
    "'driver_arrived', "
    "'in_progress'"
    ")"
)
CURRENT_ACTIVE_PREDICATE = sa.text(
    "accepted_driver_id IS NOT NULL "
    "AND is_next_ride IS NOT TRUE "
    "AND NOT ("
    "shared_ride_with_id IS NOT NULL "
    "AND shared_ride_consent IS TRUE "
    "AND status = 'accepted'"
    ") "
    "AND status IN ("
    "'accepted', "
    "'driver_arriving', "
    "'driver_arrived', "
    "'in_progress'"
    ")"
)


def upgrade() -> None:
    op.drop_index(DRIVER_ACTIVE_INDEX, table_name="ride_requests")
    op.create_index(
        DRIVER_ACTIVE_INDEX,
        "ride_requests",
        ["accepted_driver_id"],
        unique=True,
        postgresql_where=CURRENT_ACTIVE_PREDICATE,
    )


def downgrade() -> None:
    op.drop_index(DRIVER_ACTIVE_INDEX, table_name="ride_requests")
    op.create_index(
        DRIVER_ACTIVE_INDEX,
        "ride_requests",
        ["accepted_driver_id"],
        unique=True,
        postgresql_where=PREVIOUS_ACTIVE_PREDICATE,
    )
