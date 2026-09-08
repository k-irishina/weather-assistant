"""HTTP endpoints for the web front end.

The page is the same assistant as the Telegram bot, for people who don't use
Telegram.
"""
import logging
from datetime import time
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import analysis_constants as constants
import app_config
import area
import assistant
import db_connector as db
import web_push

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

DEFAULT_AREA = area.areas[constants.default_area_id]


def resolve_area(area_id: Optional[int]) -> area.Area:
    if area_id is None:
        return DEFAULT_AREA
    chosen = area.areas.get(area_id)
    if chosen is None:
        raise HTTPException(status_code=400, detail=f"Unknown area {area_id}.")
    return chosen


class SubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class Subscription(BaseModel):
    endpoint: str = Field(min_length=1)
    keys: SubscriptionKeys
    area: Optional[int] = None


class AreaChange(BaseModel):
    endpoint: str = Field(min_length=1)
    area: int


class Unsubscribe(BaseModel):
    endpoint: str = Field(min_length=1)


def _hour(value: time) -> str:
    return value.strftime("%H:%M")


def _number(value) -> Optional[float]:
    return None if value is None else float(value)


def forecast_payload(report: assistant.ForecastReport) -> dict:
    cutoff = report["from_hour"]
    temperatures = {
        key: _number(report["temperatures"][key]["avg_temperature"])
        for _, key, until in assistant.temperature_periods
        if key in report["temperatures"] and (cutoff is None or until > cutoff)
    }

    wind = [
        {
            "hour": _hour(hour),
            "speed": _number(reading.speed),
            "gust": _number(reading.gust),
            "strength": constants.wind_strength(
                reading.speed, reading.gust, reading.percentile_90
            ),
        }
        for hour, reading in sorted(report["wind_by_hour"].items())
    ]

    uv_index = report["uv_index"]
    greeting = assistant.get_greeting(report["local_now"].hour)

    return {
        "area": report["area_name"],
        "day": report["forecast_day"].isoformat(),
        "generated_at": report["local_now"].isoformat(),
        "greeting": greeting,
        "temperatures": temperatures,
        # None when the forecast table has no rows for the day yet
        "uv_index": None if uv_index is None else round(_number(uv_index)),
        "sunrise": _hour(report["sunrise_sunset"]["sunrise_time"]),
        "sunset": _hour(report["sunrise_sunset"]["sunset_time"]),
        "sunny_hours": [_hour(hour) for hour in sorted(report["sunny_times"])],
        "precipitation": {
            "kind": report["precipitation"]["name"],
            "emoji": report["precipitation"]["emoji_active"],
            "likely": [_hour(hour) for hour in sorted(report["precipitation_high"])],
            "possible": [_hour(hour) for hour in sorted(report["precipitation_possible"])],
        },
        "wind": wind,
        "text": assistant.format_forecast_text(report, greeting),
    }


@router.get("/forecast")
def get_forecast(area: Optional[int] = None) -> dict:
    return forecast_payload(assistant.forecast_for_area(resolve_area(area)))


@router.get("/areas")
def get_areas() -> dict:
    return {
        "default": DEFAULT_AREA.id,
        "areas": [
            {"id": area_obj.id, "name": area_obj.display_name}
            for area_obj in sorted(area.areas.values(), key=lambda a: a.display_name)
        ],
    }


@router.get("/vapid-key")
def get_vapid_key() -> dict:
    """The browser needs this to subscribe, and it is public by design."""
    public_key = (app_config.web.get("vapid") or {}).get("public-key")
    if not public_key:
        raise HTTPException(
            status_code=503,
            detail="Push is not configured on this server (web.vapid in config.yml).",
        )
    return {"public_key": public_key}


@router.post("/subscribe", status_code=201)
def subscribe(subscription: Subscription) -> dict:
    chosen = resolve_area(subscription.area)
    db.save_web_subscription(
        subscription.endpoint,
        subscription.keys.p256dh,
        subscription.keys.auth,
        chosen,
    )
    log.info("Stored web push subscription for %s", chosen.display_name)
    return {"status": "subscribed", "area": chosen.id, "area_name": chosen.display_name}


@router.post("/area")
def change_area(body: AreaChange) -> dict:
    chosen = resolve_area(body.area)
    if not db.update_web_subscription_area(body.endpoint, chosen):
        raise HTTPException(status_code=404, detail="No such subscription.")
    log.info("Web subscription moved to %s", chosen.display_name)
    return {"status": "updated", "area": chosen.id, "area_name": chosen.display_name}


@router.post("/unsubscribe")
def unsubscribe(body: Unsubscribe) -> dict:
    db.delete_web_subscription(body.endpoint)
    log.info("Removed a web push subscription")
    return {"status": "unsubscribed"}


@router.post("/me")
def whoami(body: Unsubscribe) -> dict:
    # enables the test push button
    subscription = db.find_web_subscription(body.endpoint)
    return {
        "known": subscription is not None,
        "is_admin": bool(subscription and subscription.is_admin),
        "area": subscription.area if subscription else None,
    }


@router.post("/test-push")
def test_push(body: Unsubscribe) -> dict:
    # test push to debug
    subscription = db.find_web_subscription(body.endpoint)
    if subscription is None or not subscription.is_admin:
        raise HTTPException(status_code=403, detail="Not a test device.")

    delivered = web_push.send_to_subscription(
        subscription,
        "Test notification",
        "If you can read this, push works. ☆*: .｡. o(≧▽≦)o .｡.:*☆",
        tag="test",
    )
    if not delivered:
        raise HTTPException(
            status_code=502,
            detail="push rejected by service",
        )
    return {"status": "sent"}
