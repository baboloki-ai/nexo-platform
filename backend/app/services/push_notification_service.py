from __future__ import annotations

import json
from typing import Any

from app import config
from app.constants.push import (
    PUSH_MESSAGE,
    PUSH_NOTIFICATION_TYPE,
    PUSH_OPEN_URL,
    PUSH_TITLE,
)
from app.database.database import SessionLocal
from app.models.driver_push_subscription import DriverPushSubscription


class PushSubscriptionGone(Exception):
    """The push service reported the subscription is gone."""


def send_web_push(*, subscription_info: dict[str, Any], payload: str) -> Any:
    """
    Deliver one Web Push message.

    Tests patch this function. Production uses VAPID via pywebpush.
    A missing provider or delivery error must not raise out of send_ride_request.
    """
    from pywebpush import WebPushException, webpush

    try:
        # pywebpush defaults ttl=0, which FCM discards unless the browser is
        # connected at that instant. Ride-request offers remain relevant for
        # RIDE_OFFER_TTL_SECONDS; Urgency=high asks Chrome not to delay.
        response = webpush(
            subscription_info=subscription_info,
            data=payload,
            vapid_private_key=config.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": config.VAPID_CLAIM_EMAIL},
            ttl=config.RIDE_OFFER_TTL_SECONDS,
            headers={"Urgency": "high"},
        )
        return response
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (404, 410):
            raise PushSubscriptionGone from exc
        raise


def ride_request_push_payload(ride_id: int) -> dict[str, Any]:
    return {
        "type": PUSH_NOTIFICATION_TYPE,
        "ride_id": ride_id,
        "title": PUSH_TITLE,
        "message": PUSH_MESSAGE,
        "url": PUSH_OPEN_URL,
    }


class PushNotificationService:
    """Best-effort Web Push for marketplace ride-request broadcasts."""

    @staticmethod
    def send_ride_request(driver_id: int, ride_id: int) -> None:
        if not config.VAPID_PUBLIC_KEY or not config.VAPID_PRIVATE_KEY:
            return

        payload = json.dumps(ride_request_push_payload(ride_id))
        db = SessionLocal()
        try:
            subscriptions = (
                db.query(DriverPushSubscription)
                .filter(DriverPushSubscription.driver_id == driver_id)
                .order_by(DriverPushSubscription.updated_at.desc())
                .all()
            )
            stale_ids: list[int] = []
            for subscription in subscriptions:
                try:
                    response = send_web_push(
                        subscription_info={
                            "endpoint": subscription.endpoint,
                            "keys": {
                                "p256dh": subscription.p256dh,
                                "auth": subscription.auth,
                            },
                        },
                        payload=payload,
                    )
                    status = getattr(response, "status_code", None)
                    print(
                        "Push delivery succeeded for ride "
                        f"{ride_id} driver {driver_id} subscription {subscription.id}"
                        + (f" HTTP {status}" if status is not None else "")
                    )
                except PushSubscriptionGone:
                    stale_ids.append(subscription.id)
                except Exception as exc:
                    response = getattr(exc, "response", None)
                    status = getattr(response, "status_code", None)
                    try:
                        body = response.text if response is not None else None
                    except Exception:
                        body = None
                    print(
                        "Push delivery failed for ride "
                        f"{ride_id} driver {driver_id} subscription {subscription.id}: "
                        f"{type(exc).__name__}: {exc}"
                        + (f" HTTP {status}" if status is not None else "")
                        + (f" body={body[:500]}" if body else "")
                    )
            if stale_ids:
                (
                    db.query(DriverPushSubscription)
                    .filter(DriverPushSubscription.id.in_(stale_ids))
                    .delete(synchronize_session=False)
                )
                db.commit()
        except Exception as exc:
            print(
                "Ride-request push failed for ride "
                f"{ride_id} driver {driver_id}: {type(exc).__name__}: {exc}"
            )
            db.rollback()
        finally:
            db.close()
