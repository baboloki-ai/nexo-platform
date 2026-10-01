from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import config
from app.database.dependencies import get_db
from app.models.driver_push_subscription import DriverPushSubscription
from app.models.user import User
from app.schemas.push import (
    PushSubscriptionDelete,
    PushSubscriptionIn,
    PushSubscriptionOut,
    VapidPublicKeyOut,
)
from app.utils.dependencies import require_driver

router = APIRouter(
    prefix="/drivers/push",
    tags=["Driver Push"],
)


@router.get("/vapid-public-key", response_model=VapidPublicKeyOut)
def get_vapid_public_key(
    _driver: User = Depends(require_driver),
):
    if not config.VAPID_PUBLIC_KEY:
        raise HTTPException(
            status_code=503,
            detail="Push notifications are not configured.",
        )
    return VapidPublicKeyOut(vapid_public_key=config.VAPID_PUBLIC_KEY)


@router.post("/subscriptions", response_model=PushSubscriptionOut)
def register_push_subscription(
    payload: PushSubscriptionIn,
    db: Session = Depends(get_db),
    driver: User = Depends(require_driver),
):
    endpoint = payload.endpoint.strip()
    p256dh = payload.keys.p256dh.strip()
    auth = payload.keys.auth.strip()
    if not endpoint or not p256dh or not auth:
        raise HTTPException(status_code=400, detail="Invalid push subscription.")

    now = datetime.utcnow()
    existing = (
        db.query(DriverPushSubscription)
        .filter(DriverPushSubscription.endpoint == endpoint)
        .first()
    )
    if existing is not None:
        existing.driver_id = driver.id
        existing.p256dh = p256dh
        existing.auth = auth
        existing.updated_at = now
        subscription = existing
    else:
        subscription = DriverPushSubscription(
            driver_id=driver.id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            created_at=now,
            updated_at=now,
        )
        db.add(subscription)

    db.commit()
    db.refresh(subscription)
    return PushSubscriptionOut(
        driver_id=subscription.driver_id,
        endpoint=subscription.endpoint,
    )


@router.delete("/subscriptions", response_model=PushSubscriptionOut)
def delete_push_subscription(
    payload: PushSubscriptionDelete,
    db: Session = Depends(get_db),
    driver: User = Depends(require_driver),
):
    endpoint = payload.endpoint.strip()
    subscription = (
        db.query(DriverPushSubscription)
        .filter(
            DriverPushSubscription.endpoint == endpoint,
            DriverPushSubscription.driver_id == driver.id,
        )
        .first()
    )
    if subscription is None:
        raise HTTPException(status_code=404, detail="Push subscription not found.")

    db.delete(subscription)
    db.commit()
    return PushSubscriptionOut(
        driver_id=driver.id,
        endpoint=endpoint,
    )
