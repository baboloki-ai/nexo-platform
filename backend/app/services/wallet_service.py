from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.constants.wallet import WalletEntryType
from app.models.driver_wallet import DriverWallet
from app.models.ride_request import RideRequest
from app.models.user import User
from app.models.wallet_ledger_entry import (
    UQ_WALLET_LEDGER_ONE_COMMISSION_PER_RIDE,
    WalletLedgerEntry,
)
from app.utils.money import (
    DRIVER_WALLET_BELOW_MINIMUM,
    LAUNCH_SEED_AMOUNT,
    MIN_DRIVER_WALLET,
    calculate_commission,
    driver_wallet_meets_minimum,
    money_float,
    quantize_pula,
)

_PG_UNIQUE_VIOLATION = "23505"


class WalletService:
    """Driver wallet ledger, above-P0 operating gate, and exactly-once 8% commission."""

    @staticmethod
    def _is_unique_violation(exc: IntegrityError, constraint_name: str) -> bool:
        orig = getattr(exc, "orig", None)
        if orig is None:
            return constraint_name in str(exc)
        sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
        if sqlstate is not None and str(sqlstate) != _PG_UNIQUE_VIOLATION:
            return False
        diag = getattr(orig, "diag", None)
        name = getattr(diag, "constraint_name", None) if diag is not None else None
        if name == constraint_name:
            return True
        return constraint_name in str(orig)

    @staticmethod
    def ensure_wallet(db: Session, driver_id: int) -> DriverWallet:
        wallet = (
            db.query(DriverWallet)
            .filter(DriverWallet.driver_id == driver_id)
            .first()
        )
        if wallet is not None:
            return wallet
        now = datetime.utcnow()
        seed = quantize_pula(LAUNCH_SEED_AMOUNT)
        try:
            with db.begin_nested():
                wallet = DriverWallet(
                    driver_id=driver_id,
                    available_balance=seed,
                    updated_at=now,
                )
                db.add(wallet)
                db.add(
                    WalletLedgerEntry(
                        driver_id=driver_id,
                        ride_id=None,
                        entry_type=WalletEntryType.LAUNCH_SEED,
                        amount=seed,
                        balance_after=seed,
                        created_at=now,
                    )
                )
                db.flush()
        except IntegrityError:
            wallet = (
                db.query(DriverWallet)
                .filter(DriverWallet.driver_id == driver_id)
                .first()
            )
        if wallet is None:
            raise HTTPException(
                status_code=500,
                detail="Driver wallet could not be created.",
            )
        return wallet

    @staticmethod
    def lock_wallet(db: Session, driver_id: int) -> DriverWallet:
        WalletService.ensure_wallet(db, driver_id)
        wallet = (
            db.query(DriverWallet)
            .filter(DriverWallet.driver_id == driver_id)
            .with_for_update()
            .first()
        )
        if wallet is None:
            raise HTTPException(
                status_code=500,
                detail="Driver wallet could not be locked.",
            )
        return wallet

    @staticmethod
    def require_minimum_for_online(db: Session, driver_id: int) -> DriverWallet:
        wallet = WalletService.lock_wallet(db, driver_id)
        if not WalletService.meets_minimum(wallet.available_balance):
            raise HTTPException(
                status_code=400,
                detail=DRIVER_WALLET_BELOW_MINIMUM,
            )
        return wallet

    @staticmethod
    def meets_minimum(balance: Decimal | None) -> bool:
        return driver_wallet_meets_minimum(balance)

    @staticmethod
    def apply_offline_if_below_minimum(
        db: Session,
        driver_id: int,
        resulting_balance: Decimal | None = None,
    ) -> None:
        """L4.1.6: persist offline when the resulting wallet is P0 or negative.

        Any balance strictly above P0 does not force offline. Already-offline
        drivers are left unchanged. Only availability_status is written.
        """
        balance = resulting_balance
        if balance is None:
            wallet = (
                db.query(DriverWallet)
                .filter(DriverWallet.driver_id == driver_id)
                .first()
            )
            if wallet is None:
                return
            balance = wallet.available_balance
        if WalletService.meets_minimum(balance):
            return
        driver = db.get(User, driver_id)
        if driver is None or driver.availability_status == "offline":
            return
        driver.availability_status = "offline"

    @staticmethod
    def credit(
        db: Session,
        driver_id: int,
        amount: Decimal,
        entry_type: str = WalletEntryType.CREDIT,
        ride_id: int | None = None,
        commit: bool = True,
    ) -> DriverWallet:
        credit_amount = quantize_pula(amount)
        if credit_amount <= 0:
            raise HTTPException(
                status_code=400,
                detail="Credit amount must be greater than zero.",
            )
        if entry_type not in (WalletEntryType.CREDIT, WalletEntryType.LAUNCH_SEED):
            raise HTTPException(status_code=400, detail="Invalid credit entry type.")

        wallet = WalletService.lock_wallet(db, driver_id)
        new_balance = quantize_pula(wallet.available_balance) + credit_amount
        db.add(
            WalletLedgerEntry(
                driver_id=driver_id,
                ride_id=ride_id,
                entry_type=entry_type,
                amount=credit_amount,
                balance_after=new_balance,
            )
        )
        result = db.execute(
            update(DriverWallet)
            .where(DriverWallet.id == wallet.id)
            .values(
                available_balance=new_balance,
                updated_at=datetime.utcnow(),
            )
            .execution_options(synchronize_session="fetch")
        )
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail="Wallet could not be updated.",
            )
        if commit:
            db.commit()
            db.refresh(wallet)
        else:
            db.flush()
            db.refresh(wallet)
        return wallet

    @staticmethod
    def _existing_commission(
        db: Session,
        ride_id: int,
    ) -> WalletLedgerEntry | None:
        return (
            db.query(WalletLedgerEntry)
            .filter(
                WalletLedgerEntry.ride_id == ride_id,
                WalletLedgerEntry.entry_type == WalletEntryType.COMMISSION,
            )
            .first()
        )

    @staticmethod
    def post_completion_commission(db: Session, ride: RideRequest) -> Decimal:
        locked_ride = (
            db.query(RideRequest)
            .filter(RideRequest.id == ride.id)
            .with_for_update()
            .first()
        )
        if locked_ride is None:
            raise HTTPException(status_code=404, detail="Ride not found.")
        if locked_ride.accepted_driver_id is None:
            raise HTTPException(
                status_code=400,
                detail="Ride has no assigned driver.",
            )
        if locked_ride.agreed_fare is None:
            raise HTTPException(
                status_code=400,
                detail="Ride has no agreed fare.",
            )

        commission = calculate_commission(locked_ride.agreed_fare)
        # Ride lock then wallet lock: serialize completion posting for this trip.
        wallet = WalletService.lock_wallet(db, locked_ride.accepted_driver_id)

        existing = WalletService._existing_commission(db, locked_ride.id)
        if existing is not None:
            return quantize_pula(abs(existing.amount))

        new_balance = quantize_pula(wallet.available_balance) - commission
        try:
            with db.begin_nested():
                db.add(
                    WalletLedgerEntry(
                        driver_id=locked_ride.accepted_driver_id,
                        ride_id=locked_ride.id,
                        entry_type=WalletEntryType.COMMISSION,
                        amount=-commission,
                        balance_after=new_balance,
                    )
                )
                result = db.execute(
                    update(DriverWallet)
                    .where(DriverWallet.id == wallet.id)
                    .values(
                        available_balance=new_balance,
                        updated_at=datetime.utcnow(),
                    )
                    .execution_options(synchronize_session="fetch")
                )
                if result.rowcount != 1:
                    raise HTTPException(
                        status_code=400,
                        detail="Wallet could not be updated.",
                    )
                WalletService.apply_offline_if_below_minimum(
                    db,
                    locked_ride.accepted_driver_id,
                    resulting_balance=new_balance,
                )
                db.flush()
        except IntegrityError as exc:
            if WalletService._is_unique_violation(
                exc,
                UQ_WALLET_LEDGER_ONE_COMMISSION_PER_RIDE,
            ):
                duplicate = WalletService._existing_commission(db, locked_ride.id)
                if duplicate is not None:
                    return quantize_pula(abs(duplicate.amount))
            raise

        db.refresh(wallet)
        return commission

    @staticmethod
    def list_ledger(
        db: Session,
        driver_id: int,
        limit: int = 100,
    ) -> list[WalletLedgerEntry]:
        WalletService.ensure_wallet(db, driver_id)
        return (
            db.query(WalletLedgerEntry)
            .filter(WalletLedgerEntry.driver_id == driver_id)
            .order_by(
                WalletLedgerEntry.created_at.desc(),
                WalletLedgerEntry.id.desc(),
            )
            .limit(limit)
            .all()
        )

    @staticmethod
    def serialize_ledger_entry(entry: WalletLedgerEntry) -> dict:
        return {
            "id": entry.id,
            "driver_id": entry.driver_id,
            "ride_id": entry.ride_id,
            "entry_type": entry.entry_type,
            "amount": money_float(entry.amount),
            "balance_after": money_float(entry.balance_after),
            "created_at": entry.created_at,
        }

    @staticmethod
    def serialize_wallet(
        wallet: DriverWallet,
        ledger: list[WalletLedgerEntry] | None = None,
    ) -> dict:
        balance = quantize_pula(wallet.available_balance)
        payload = {
            "driver_id": wallet.driver_id,
            "available_balance": money_float(balance),
            "minimum_balance": money_float(MIN_DRIVER_WALLET),
            "meets_minimum": WalletService.meets_minimum(balance),
            "updated_at": wallet.updated_at,
        }
        if ledger is not None:
            payload["ledger"] = [
                WalletService.serialize_ledger_entry(entry) for entry in ledger
            ]
        return payload

    @staticmethod
    def commission_total_for_rides(
        db: Session,
        driver_id: int,
        ride_ids: list[int],
    ) -> Decimal:
        if not ride_ids:
            return quantize_pula(0)
        total = (
            db.query(func.coalesce(func.sum(WalletLedgerEntry.amount), 0))
            .filter(
                WalletLedgerEntry.driver_id == driver_id,
                WalletLedgerEntry.entry_type == WalletEntryType.COMMISSION,
                WalletLedgerEntry.ride_id.in_(ride_ids),
            )
            .scalar()
        )
        return quantize_pula(total)
