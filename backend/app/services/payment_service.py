from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.constants.payment import (
    PaymentCurrency,
    PaymentFailureCode,
    PaymentMethod,
    PaymentProviderName,
    PaymentStatus,
    RefundStatus,
    SettlementStatus,
)
from app.constants.ride_status import RideStatus
from app.models.payment import (
    UQ_PAYMENTS_ONE_OPEN_PER_RIDE,
    UQ_PAYMENTS_ONE_PAID_PER_RIDE,
    UQ_PAYMENTS_PROVIDER_REFERENCE,
    Payment,
)
from app.models.ride_request import RideRequest
from app.models.user import User
from app.schemas.payment import PaymentPublic
from app.services.notification_service import NotificationService
from app.utils.money import quantize_pula

_PG_UNIQUE_VIOLATION = "23505"
_PAYMENT_CONSTRAINTS = (
    UQ_PAYMENTS_ONE_PAID_PER_RIDE,
    UQ_PAYMENTS_ONE_OPEN_PER_RIDE,
    UQ_PAYMENTS_PROVIDER_REFERENCE,
)
_NOT_ASSIGNED = "You are not assigned to this ride."
_AMOUNT_MISMATCH = "Payment amount does not match agreed fare."


class PaymentProvider(ABC):
    """Processor adapter. Implementations must not make network requests
    until an external provider is explicitly integrated."""

    @abstractmethod
    def initiate(self, payment: Payment, ride: RideRequest) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def parse_webhook(self, payload: Any) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def verify_signature(
        self,
        payload: Any,
        headers: dict[str, str] | None = None,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    def refund(self, payment: Payment, amount: Any = None) -> dict[str, Any]:
        raise NotImplementedError


class CashProvider(PaymentProvider):
    """In-app cash confirmation. No processor, no network."""

    def initiate(self, payment: Payment, ride: RideRequest) -> dict[str, Any]:
        return {
            "accepted": True,
            "status": PaymentStatus.PENDING,
            "provider": PaymentProviderName.NEXO_CASH,
            "provider_reference": None,
        }

    def parse_webhook(self, payload: Any) -> dict[str, Any] | None:
        return None

    def verify_signature(
        self,
        payload: Any,
        headers: dict[str, str] | None = None,
    ) -> bool:
        return False

    def refund(self, payment: Payment, amount: Any = None) -> dict[str, Any]:
        raise HTTPException(
            status_code=400,
            detail="Cash refunds are not implemented.",
        )


class PaymentService:
    """Payment state machine. Amount is the locked agreed_fare snapshot."""

    _cash_provider = CashProvider()

    @staticmethod
    def is_constraint_violation(exc: IntegrityError) -> bool:
        orig = getattr(exc, "orig", None)
        haystack = str(orig if orig is not None else exc)
        sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
        if sqlstate is not None and str(sqlstate) != _PG_UNIQUE_VIOLATION:
            return False
        diag = getattr(orig, "diag", None)
        name = getattr(diag, "constraint_name", None) if diag is not None else None
        if name in _PAYMENT_CONSTRAINTS:
            return True
        return any(constraint in haystack for constraint in _PAYMENT_CONSTRAINTS)

    @staticmethod
    def serialize(payment: Payment | None) -> PaymentPublic | None:
        if payment is None:
            return None
        return PaymentPublic.model_validate(payment)

    @staticmethod
    def current_for_ride(db: Session, ride_id: int) -> Payment | None:
        open_row = (
            db.query(Payment)
            .filter(
                Payment.ride_id == ride_id,
                Payment.status.in_(PaymentStatus.OPEN),
            )
            .order_by(Payment.id.desc())
            .first()
        )
        if open_row is not None:
            return open_row
        return (
            db.query(Payment)
            .filter(Payment.ride_id == ride_id)
            .order_by(Payment.id.desc())
            .first()
        )

    @staticmethod
    def create_pending_cash(db: Session, ride: RideRequest) -> Payment:
        if ride.id is None:
            raise HTTPException(
                status_code=400,
                detail="Ride is not ready for payment.",
            )
        if ride.agreed_fare is None:
            raise HTTPException(
                status_code=400,
                detail="Ride has no agreed fare.",
            )

        amount = quantize_pula(ride.agreed_fare)
        now = datetime.utcnow()
        payment = Payment(
            ride_id=ride.id,
            amount=amount,
            currency=PaymentCurrency.BWP,
            method=PaymentMethod.CASH,
            status=PaymentStatus.PENDING,
            provider=PaymentProviderName.NEXO_CASH,
            provider_reference=None,
            idempotency_key=f"nexo_cash:{ride.id}:1",
            attempt_number=1,
            created_at=now,
            updated_at=now,
            settlement_status=SettlementStatus.DRIVER_COLLECTED,
            refund_status=RefundStatus.NONE,
        )
        db.add(payment)
        db.flush()
        PaymentService._cash_provider.initiate(payment, ride)
        return payment

    @staticmethod
    def cancel_open_for_ride(db: Session, ride: RideRequest) -> Payment | None:
        if ride.id is None:
            return None
        now = datetime.utcnow()
        result = db.execute(
            update(Payment)
            .where(
                Payment.ride_id == ride.id,
                Payment.status.in_(PaymentStatus.OPEN),
            )
            .values(
                status=PaymentStatus.CANCELLED,
                updated_at=now,
            )
            .execution_options(synchronize_session="fetch")
        )
        if result.rowcount < 1:
            return None
        return PaymentService.current_for_ride(db, ride.id)

    @staticmethod
    def confirm_cash(
        db: Session,
        payment_id: int,
        current_user: User,
    ) -> PaymentPublic:
        payment = (
            db.query(Payment)
            .filter(Payment.id == payment_id)
            .first()
        )
        if payment is None:
            raise HTTPException(status_code=404, detail="Payment not found.")

        ride = (
            db.query(RideRequest)
            .filter(RideRequest.id == payment.ride_id)
            .with_for_update()
            .first()
        )
        if ride is None:
            db.rollback()
            raise HTTPException(status_code=404, detail="Ride not found.")

        payment = (
            db.query(Payment)
            .filter(Payment.id == payment_id)
            .with_for_update()
            .first()
        )
        if payment is None:
            db.rollback()
            raise HTTPException(status_code=404, detail="Payment not found.")

        if (
            current_user.role != "driver"
            or ride.accepted_driver_id != current_user.id
        ):
            db.rollback()
            raise HTTPException(status_code=403, detail=_NOT_ASSIGNED)

        if payment.method != PaymentMethod.CASH:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail="Only cash payments can be confirmed this way.",
            )

        if payment.status == PaymentStatus.PAID:
            db.commit()
            db.refresh(payment)
            serialized = PaymentService.serialize(payment)
            if serialized is None:
                raise HTTPException(status_code=404, detail="Payment not found.")
            return serialized

        if ride.status in RideStatus.PAYMENT_CONFIRMATION_BLOCKED:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail="Payment cannot be confirmed.",
            )

        if payment.status != PaymentStatus.PENDING:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail="Payment cannot be confirmed.",
            )

        if ride.agreed_fare is None or quantize_pula(payment.amount) != quantize_pula(
            ride.agreed_fare
        ):
            now = datetime.utcnow()
            db.execute(
                update(Payment)
                .where(
                    Payment.id == payment.id,
                    Payment.status == PaymentStatus.PENDING,
                )
                .values(
                    status=PaymentStatus.FAILED,
                    failed_at=now,
                    failure_code=PaymentFailureCode.AMOUNT_MISMATCH,
                    failure_message=_AMOUNT_MISMATCH,
                    updated_at=now,
                )
                .execution_options(synchronize_session=False)
            )
            db.commit()
            raise HTTPException(status_code=400, detail=_AMOUNT_MISMATCH)

        now = datetime.utcnow()
        result = db.execute(
            update(Payment)
            .where(
                Payment.id == payment.id,
                Payment.ride_id == ride.id,
                Payment.method == PaymentMethod.CASH,
                Payment.status == PaymentStatus.PENDING,
            )
            .values(
                status=PaymentStatus.PAID,
                cash_confirmed_at=now,
                cash_confirmed_by_user_id=current_user.id,
                paid_at=now,
                settlement_status=SettlementStatus.DRIVER_COLLECTED,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            db.flush()
            db.refresh(payment)
            if payment.status == PaymentStatus.PAID:
                db.commit()
                serialized = PaymentService.serialize(payment)
                if serialized is None:
                    raise HTTPException(status_code=404, detail="Payment not found.")
                return serialized
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail="Payment cannot be confirmed.",
            )

        db.commit()
        db.refresh(payment)
        serialized = PaymentService.serialize(payment)
        if serialized is None:
            raise HTTPException(status_code=404, detail="Payment not found.")
        NotificationService.notify_payment_updated(
            passenger_id=ride.passenger_id,
            driver_id=ride.accepted_driver_id,
            ride_id=ride.id,
            payment_id=payment.id,
            status=payment.status,
        )
        return serialized
