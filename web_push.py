#Sending web push notifications to browsers
import asyncio
import json
import logging
from typing import Optional

from pywebpush import WebPushException, webpush

import app_config
import area
import assistant
import db_connector as db

log = logging.getLogger(__name__)

# How long a push service should hold a notification for a device that is
# offline. 30 minutes is enough.
TTL_SECONDS = 30 * 60

# Push services return these when a subscription is permanently gone: the
# browser was uninstalled, site data cleared, or the endpoint rotated.
GONE_STATUSES = (404, 410)


def _vapid() -> tuple[str, str]:
    vapid = app_config.web.get("vapid") or {}
    private_key = vapid.get("private-key")
    contact = vapid.get("contact")
    if not private_key or not contact:
        raise RuntimeError(
            "Web push is not configured: set web.vapid private-key and contact "
            "in config.yml, or VAPID_PRIVATE_KEY and VAPID_CONTACT."
        )
    return private_key, contact


def send_to_subscription(
    subscription: db.WebSubscription,
    title: str,
    body: str,
    tag: Optional[str] = None,
) -> bool:
    """Push one notification. False means the subscription is gone.

    A dead subscription is deleted rather than retried - there is no way back
    from it, and the row would otherwise be tried again every morning.
    """
    private_key, contact = _vapid()
    payload = {"title": title, "body": body}
    if tag:
        payload["tag"] = tag

    try:
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=json.dumps(payload),
            vapid_private_key=private_key,
            vapid_claims={"sub": contact},
            ttl=TTL_SECONDS,
        )
        return True
    except WebPushException as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status in GONE_STATUSES:
            log.info("Subscription gone (%s), removing it", status)
            db.delete_web_subscription(subscription.endpoint)
            return False
        log.exception("Push failed with status %s", status)
        return False
    except Exception:
        # A malformed row (bad p256dh/auth) raises before any request is made.
        # Swallowed so one bad subscription cannot abort the whole fan-out.
        log.exception("Could not build a push for %s", subscription.endpoint)
        return False


def send_to_area(area_obj: area.Area, title: str, body: str, tag: Optional[str] = None) -> int:
    """Push to every browser subscribed for an area. Returns how many landed."""
    subscriptions = db.web_subscriptions_for_area(area_obj)
    delivered = sum(
        send_to_subscription(subscription, title, body, tag)
        for subscription in subscriptions
    )
    log.info(
        "Web push for %s: %s of %s delivered",
        area_obj.display_name, delivered, len(subscriptions),
    )
    return delivered


def subscribed_areas() -> list[area.Area]:
    return [
        area.areas[area_id]
        for area_id in db.areas_with_web_subscribers()
        if area_id in area.areas
    ]


async def push_morning_forecast() -> None:
    for area_obj in subscribed_areas():
        try:
            report = assistant.forecast_for_area(area_obj)
            text = assistant.format_forecast_text(report)
        except Exception:
            log.exception("Could not build forecast for %s", area_obj.display_name)
            continue
        await asyncio.to_thread(
            send_to_area,
            area_obj,
            f"Forecast for {area_obj.display_name}",
            text.strip(),
            "morning-forecast",
        )


def send_to_rain_subscribers(area_obj: area.Area, title: str, body: str) -> int:
    subscriptions = db.rain_alert_subscriptions_for_area(area_obj)
    delivered = sum(
        send_to_subscription(subscription, title, body, "rain-alert")
        for subscription in subscriptions
    )
    log.info(
        "Rain alert for %s: %s of %s delivered",
        area_obj.display_name, delivered, len(subscriptions),
    )
    return delivered


async def push_sun_update() -> None:
    for area_obj in subscribed_areas():
        try:
            sun_change_text = assistant.detect_sun_change_for_area(area_obj)
        except Exception:
            log.exception("Could not analyse sun change for %s", area_obj.display_name)
            continue
        # None is the usual case: nothing changed worth reporting
        if sun_change_text:
            await asyncio.to_thread(
                send_to_area,
                area_obj,
                "Sunshine update",
                sun_change_text.strip(),
                "sun-update",
            )
