"""Add driver identity and vehicle verification fields

Revision ID: 8c4e2a91b7d3
Revises: 7f3c11a9e2b4
Create Date: 2026-08-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8c4e2a91b7d3"
down_revision: Union[str, Sequence[str], None] = "7f3c11a9e2b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("profile_photo_url", sa.String(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("verification_status", sa.String(), nullable=True),
    )
    # Existing C0–C2 drivers stay operable after migrate.
    # New registrations set pending in the user-create path.
    op.execute(
        sa.text(
            "UPDATE users SET verification_status = 'approved' "
            "WHERE role = 'driver' AND verification_status IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE users SET updated_at = created_at "
            "WHERE updated_at IS NULL"
        )
    )

    op.add_column(
        "vehicles",
        sa.Column(
            "verification_status",
            sa.String(),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "vehicles",
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "vehicles",
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE vehicles SET created_at = NOW() "
            "WHERE created_at IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE vehicles SET updated_at = created_at "
            "WHERE updated_at IS NULL"
        )
    )


def downgrade() -> None:
    op.drop_column("vehicles", "updated_at")
    op.drop_column("vehicles", "created_at")
    op.drop_column("vehicles", "verification_status")
    op.drop_column("users", "verification_status")
    op.drop_column("users", "profile_photo_url")
    op.drop_column("users", "updated_at")
