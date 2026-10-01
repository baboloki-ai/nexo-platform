from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric
from sqlalchemy.orm import relationship

from app.constants.wallet import WalletEntryType
from app.database.base import Base
from app.models.wallet_ledger_entry import WalletLedgerEntry
from app.utils.money import LAUNCH_SEED_AMOUNT, quantize_pula


class DriverWallet(Base):
    __tablename__ = "driver_wallets"

    id = Column(Integer, primary_key=True, index=True)
    driver_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    available_balance = Column(Numeric(12, 2), nullable=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    driver = relationship(
        "User",
        back_populates="wallet",
        lazy="noload",
    )


def seed_driver_wallet(connection, driver_id: int) -> None:
    now = datetime.utcnow()
    seed = quantize_pula(LAUNCH_SEED_AMOUNT)
    connection.execute(
        DriverWallet.__table__.insert().values(
            driver_id=driver_id,
            available_balance=seed,
            updated_at=now,
        )
    )
    connection.execute(
        WalletLedgerEntry.__table__.insert().values(
            driver_id=driver_id,
            ride_id=None,
            entry_type=WalletEntryType.LAUNCH_SEED,
            amount=seed,
            balance_after=seed,
            created_at=now,
        )
    )
