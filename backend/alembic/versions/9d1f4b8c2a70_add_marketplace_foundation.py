"""Add marketplace foundation tables and fare columns

Revision ID: 9d1f4b8c2a70
Revises: 8c4e2a91b7d3
Create Date: 2026-08-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9d1f4b8c2a70"
down_revision: Union[str, Sequence[str], None] = "8c4e2a91b7d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DRIVER_ACTIVE_INDEX = "uq_ride_requests_one_active_per_driver"
DRIVER_ACTIVE_PREDICATE = sa.text(
    "accepted_driver_id IS NOT NULL AND status IN ("
    "'accepted', "
    "'driver_arriving', "
    "'driver_arrived', "
    "'in_progress'"
    ")"
)
OPEN_RESPONSE_INDEX = "uq_driver_responses_one_open_per_driver_ride"


def upgrade() -> None:
    op.add_column(
        "ride_requests",
        sa.Column("recommended_fare", sa.Numeric(10, 2), nullable=True),
    )
    op.add_column(
        "ride_requests",
        sa.Column("passenger_current_offer", sa.Numeric(10, 2), nullable=True),
    )
    op.add_column(
        "ride_requests",
        sa.Column(
            "passenger_offer_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "ride_requests",
        sa.Column("agreed_fare", sa.Numeric(10, 2), nullable=True),
    )
    op.add_column(
        "ride_requests",
        sa.Column("trip_distance_km", sa.Numeric(8, 3), nullable=True),
    )
    op.add_column(
        "ride_requests",
        sa.Column("selected_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "ride_requests",
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )

    op.execute(
        """
        UPDATE ride_requests
        SET passenger_current_offer = CAST(proposed_fare AS numeric(10, 2))
        WHERE passenger_current_offer IS NULL
        """
    )
    op.execute(
        """
        UPDATE ride_requests
        SET agreed_fare = CAST(proposed_fare AS numeric(10, 2))
        WHERE agreed_fare IS NULL
          AND status IN (
            'accepted',
            'driver_arriving',
            'driver_arrived',
            'in_progress',
            'completed'
          )
        """
    )
    op.alter_column(
        "ride_requests",
        "passenger_current_offer",
        existing_type=sa.Numeric(10, 2),
        nullable=False,
    )

    op.create_index(
        DRIVER_ACTIVE_INDEX,
        "ride_requests",
        ["accepted_driver_id"],
        unique=True,
        postgresql_where=DRIVER_ACTIVE_PREDICATE,
    )

    op.create_table(
        "driver_responses",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("ride_id", sa.Integer(), sa.ForeignKey("ride_requests.id"), nullable=False),
        sa.Column("driver_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("response_type", sa.String(), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("passenger_offer_version_at_submit", sa.Integer(), nullable=False),
        sa.Column("passenger_offer_amount_at_submit", sa.Numeric(10, 2), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("pickup_distance_km", sa.Numeric(8, 3), nullable=True),
        sa.Column("pickup_eta_seconds", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("responded_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_driver_responses_id", "driver_responses", ["id"])
    op.create_index("ix_driver_responses_ride_id", "driver_responses", ["ride_id"])
    op.create_index("ix_driver_responses_driver_id", "driver_responses", ["driver_id"])
    op.create_index(
        OPEN_RESPONSE_INDEX,
        "driver_responses",
        ["ride_id", "driver_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )

    op.create_table(
        "negotiation_events",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("ride_id", sa.Integer(), sa.ForeignKey("ride_requests.id"), nullable=False),
        sa.Column("actor_type", sa.String(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("driver_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("resulting_ride_status", sa.String(), nullable=True),
        sa.Column("resulting_response_status", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_negotiation_events_id", "negotiation_events", ["id"])
    op.create_index(
        "ix_negotiation_events_ride_id",
        "negotiation_events",
        ["ride_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_negotiation_events_ride_id", table_name="negotiation_events")
    op.drop_index("ix_negotiation_events_id", table_name="negotiation_events")
    op.drop_table("negotiation_events")

    op.drop_index(OPEN_RESPONSE_INDEX, table_name="driver_responses")
    op.drop_index("ix_driver_responses_driver_id", table_name="driver_responses")
    op.drop_index("ix_driver_responses_ride_id", table_name="driver_responses")
    op.drop_index("ix_driver_responses_id", table_name="driver_responses")
    op.drop_table("driver_responses")

    op.drop_index(DRIVER_ACTIVE_INDEX, table_name="ride_requests")
    op.drop_column("ride_requests", "completed_at")
    op.drop_column("ride_requests", "selected_at")
    op.drop_column("ride_requests", "trip_distance_km")
    op.drop_column("ride_requests", "agreed_fare")
    op.drop_column("ride_requests", "passenger_offer_version")
    op.drop_column("ride_requests", "passenger_current_offer")
    op.drop_column("ride_requests", "recommended_fare")
