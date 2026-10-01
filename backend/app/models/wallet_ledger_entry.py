from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    text,
)
from sqlalchemy.orm import relationship

from app.constants.wallet import WalletEntryType
from app.database.base import Base

UQ_WALLET_LEDGER_ONE_COMMISSION_PER_RIDE = (
    "uq_wallet_ledger_one_commission_per_ride"
)


class WalletLedgerEntry(Base):
    __tablename__ = "wallet_ledger_entries"

    __table_args__ = (
        Index(
            UQ_WALLET_LEDGER_ONE_COMMISSION_PER_RIDE,
            "ride_id",
            unique=True,
            postgresql_where=text(
                f"entry_type = '{WalletEntryType.COMMISSION}' "
                "AND ride_id IS NOT NULL"
            ),
        ),
        Index("ix_wallet_ledger_entries_driver_id", "driver_id"),
        Index("ix_wallet_ledger_entries_ride_id", "ride_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    driver_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
    )
    ride_id = Column(
        Integer,
        ForeignKey("ride_requests.id"),
        nullable=True,
    )
    entry_type = Column(String, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    balance_after = Column(Numeric(12, 2), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    wallet_driver = relationship(
        "User",
        foreign_keys=[driver_id],
        lazy="noload",
        viewonly=True,
    )
    ride = relationship("RideRequest", lazy="noload", viewonly=True)
