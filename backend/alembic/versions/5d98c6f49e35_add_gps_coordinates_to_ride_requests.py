"""Add GPS coordinates to ride requests

Revision ID: 5d98c6f49e35
Revises: 4d3b479c141d
Create Date: 2026-07-31

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5d98c6f49e35"
down_revision: Union[str, Sequence[str], None] = "4d3b479c141d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ride_requests",
        sa.Column("pickup_latitude", sa.Float(), nullable=True),
    )

    op.add_column(
        "ride_requests",
        sa.Column("pickup_longitude", sa.Float(), nullable=True),
    )

    op.add_column(
        "ride_requests",
        sa.Column("destination_latitude", sa.Float(), nullable=True),
    )

    op.add_column(
        "ride_requests",
        sa.Column("destination_longitude", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ride_requests", "destination_longitude")
    op.drop_column("ride_requests", "destination_latitude")
    op.drop_column("ride_requests", "pickup_longitude")
    op.drop_column("ride_requests", "pickup_latitude")