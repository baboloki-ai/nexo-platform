"""add shared ride fields

Revision ID: 5bb416fbfea4
Revises: e8a1c4f6b2d0
Create Date: 2026-09-14 20:43:27.510269

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5bb416fbfea4"
down_revision: Union[str, Sequence[str], None] = "e8a1c4f6b2d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "ride_requests",
        sa.Column(
            "shared_ride_with_id",
            sa.Integer(),
            sa.ForeignKey("ride_requests.id"),
            nullable=True,
        ),
    )

    op.add_column(
        "ride_requests",
        sa.Column(
            "shared_ride_consent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("ride_requests", "shared_ride_consent")
    op.drop_column("ride_requests", "shared_ride_with_id")