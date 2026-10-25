"""HTTP endpoints for the web front end.

The page is the same assistant as the Telegram bot, for people who don't use
Telegram.
"""
import logging
import re
from pathlib import Path
from datetime import datetime, time, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import analysis_constants as constants
import app_config
import area
import assistant
import background_photo_picker
import db_connector as db
import media_bucket
import met_alerts
import near_term_forecast
import nve_warnings
import retrieve_complete_forecast as rcf
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


class RainAlertChange(BaseModel):
    endpoint: str = Field(min_length=1)
    enabled: bool


class MorningTimeChange(BaseModel):
    endpoint: str = Field(min_length=1)
    time: str


class WeekendMorningChange(BaseModel):
    endpoint: str = Field(min_length=1)
    enabled: bool


class Unsubscribe(BaseModel):
    endpoint: str = Field(min_length=1)


def _hour(value: time) -> str:
    return value.strftime("%H:%M")


def _number(value) -> Optional[float]:
    return None if value is None else float(value)


def _temperature(value) -> Optional[int]:
    return None if value is None else assistant.round_temperature(value)


WEATHER_ICON_DIR = Path(__file__).resolve().parent / "static" / "icons" / "weather-icons"


ALERT_ICON_DIR = Path(__file__).resolve().parent / "static" / "icons" / "weather-alert-icons"
# best-effort matching of MET's eventAwarenessName to an icon
ALERT_ICON_ALIASES = {"gale": "wind", "icing": "ice", "blowingsnow": "snow", "snowice": "snow",
                      "thunderstorm": "lightning", "flooding": "flood"}


def _alert_icon(alert: met_alerts.Alert) -> str:
    if alert.severity == "Extreme":
        return "/icons/weather-alert-icons/icon-warning-extreme.svg"
    awareness = alert.kind.replace("-", "")
    for name in (alert.event, ALERT_ICON_ALIASES.get(alert.event),
                 awareness, ALERT_ICON_ALIASES.get(awareness), "generic"):
        if name and (ALERT_ICON_DIR / f"icon-warning-{name}-{alert.color}.svg").is_file():
            return f"/icons/weather-alert-icons/icon-warning-{name}-{alert.color}.svg"
    return "/icons/weather-alert-icons/icon-warning-generic-yellow.svg"


def _symbol_icon(symbol_code: Optional[str]) -> Optional[str]:
    if not symbol_code:
        return None
    if not (WEATHER_ICON_DIR / f"{symbol_code}.png").is_file():
        log.warning("No weather icon for symbol_code %r", symbol_code)
        return None
    return f"/icons/weather-icons/{symbol_code}.png"


FIRST_PERIOD_HOUR = time(6)


def _period_hours(report: assistant.ForecastReport, start: time, end: Optional[time]) -> list[dict]:
    return [
        {"hour": _hour(hour), "temperature": _temperature(temperature)}
        for hour, temperature in sorted(report["hourly_temperatures"].items())
        if start <= hour and (end is None or hour < end)
    ]


def forecast_payload(report: assistant.ForecastReport) -> dict:
    cutoff = report["from_hour"]
    periods = assistant.temperature_periods
    starts = [FIRST_PERIOD_HOUR] + [until for _, _, until in periods[:-1]]
    ends = [until for _, _, until in periods[:-1]] + [None]
    temperatures = {
        key: {
            "label": label,
            "temperature": _temperature(report["temperatures"][key]["avg_temperature"]),
            "symbol_code": report["temperatures"][key].get("symbol_code"),
            "icon": _symbol_icon(report["temperatures"][key].get("symbol_code")),
            "hours": _period_hours(report, start, end),
        }
        for start, end, (label, key, until) in zip(starts, ends, periods)
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
    conditions = assistant.conditions(
        report, min_moderate_wind_hours=constants.min_significant_moderate_wind_run_hours
    )
    for condition in conditions:
        for line in condition.details:
            line["icon"] = _symbol_icon(line["symbol"])

    return {
        "area": report["area_name"],
        "day": report["forecast_day"].isoformat(),
        "generated_at": report["local_now"].isoformat(),
        "updated_at": (
            None if report["forecast_checked_at"] is None
            else report["forecast_checked_at"].astimezone(report["local_now"].tzinfo).strftime("%H:%M")
        ),
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
            # set instead of the hour lists when the timing is unclear.
            "window_chance": (
                None
                if report["precipitation_window"] is None
                else round(_number(report["precipitation_window"]))
            ),
            "window_hours": [_hour(hour) for hour in report["precipitation_window_hours"]],
        },
        "wind": wind,
        "conditions": conditions,
        "right_now": report["right_now"],
    }


@router.get("/forecast")
def get_forecast(area: Optional[int] = None, day: str = "today") -> dict:
    if day not in ("today", "tomorrow"):
        raise HTTPException(status_code=400, detail="day must be 'today' or 'tomorrow'.")
    return forecast_payload(assistant.forecast_for_area(resolve_area(area), day=day))


@router.get("/near-term-forecast")
def get_near_term_forecast(area: Optional[int] = None) -> dict:
    chosen = resolve_area(area)
    series = near_term_forecast.latest_series(chosen)
    if series is not None:
        series = near_term_forecast.without_past_steps(series, datetime.now(timezone.utc))
    return near_term_forecast.page_payload(series, chosen)


@router.get("/background")
def get_background(area: Optional[int] = None) -> dict:
    chosen = resolve_area(area)
    if not media_bucket.configured():
        return {"area": chosen.id, "link": None}
    local_now = chosen.region.now()
    symbol = db.hourly_symbols(chosen, local_now.date()).get(time(local_now.hour), "")
    sun_times = rcf.fetch_sunset_sunrise_for_area(chosen)
    links = media_bucket.background_links()
    name = background_photo_picker.pick_photo(
        links, symbol, local_now, sun_times["sunrise_time"], sun_times["sunset_time"]
    )
    return {"area": chosen.id, "link": links.get(name)}


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


@router.post("/rain-alerts")
def change_rain_alerts(body: RainAlertChange) -> dict:
    if not db.set_rain_alerts(body.endpoint, body.enabled):
        raise HTTPException(status_code=404, detail="No such subscription.")
    log.info("Rain alerts %s for a web subscription",
             "enabled" if body.enabled else "disabled")
    return {"status": "updated", "rain_alerts": body.enabled}


@router.post("/morning-time")
def change_morning_time(body: MorningTimeChange) -> dict:
    chosen = next(
        (at for at in constants.morning_push_times if _hour(at) == body.time), None
    )
    if chosen is None:
        raise HTTPException(status_code=400, detail=f"Unsupported time {body.time!r}.")
    if not db.set_morning_push_at(body.endpoint, chosen):
        raise HTTPException(status_code=404, detail="No such subscription.")
    log.info("Web subscription morning push moved to %s", body.time)
    return {"status": "updated", "morning_push_at": body.time}


@router.post("/weekend-morning")
def change_weekend_morning(body: WeekendMorningChange) -> dict:
    if not db.set_weekend_morning_push(body.endpoint, body.enabled):
        raise HTTPException(status_code=404, detail="No such subscription.")
    log.info("Weekend morning push %s for a web subscription",
             "enabled" if body.enabled else "disabled")
    return {"status": "updated", "weekend_morning_push": body.enabled}


@router.post("/unsubscribe")
def unsubscribe(body: Unsubscribe) -> dict:
    db.delete_web_subscription(body.endpoint)
    log.info("Removed a web push subscription")
    return {"status": "unsubscribed"}


@router.post("/me")
def whoami(body: Unsubscribe) -> dict:
    subscription = db.find_web_subscription(body.endpoint)
    if subscription is not None:
        db.mark_web_subscription_seen(body.endpoint)
    return {
        "known": subscription is not None,
        "is_admin": bool(subscription and subscription.is_admin),
        "area": subscription.area if subscription else None,
        "rain_alerts": bool(subscription and subscription.rain_alerts),
        "morning_push_at": _hour(
            subscription.morning_push_at
            if subscription and subscription.morning_push_at
            else constants.default_morning_push_at
        ),
        "morning_push_options": [_hour(at) for at in constants.morning_push_times],
        "weekend_morning_push": subscription.weekend_morning_push if subscription else True,
    }


def _alert_duration_text(alert: met_alerts.Alert, local_now: datetime) -> str:
    today = local_now.date()
    tomorrow = today + timedelta(days=1)
    starts = alert.starts.astimezone(local_now.tzinfo)
    ends = alert.ends.astimezone(local_now.tzinfo)

    if ends.date() == today:
        until = f"until {ends:%H:%M}"
    elif ends.date() == tomorrow:
        until = "until tomorrow"
    else:
        until = f"until {ends:%A}"

    if starts <= local_now:
        start = ""
    elif starts.date() == today:
        start = f"from {starts:%H:%M} "
    elif starts.date() == tomorrow:
        start = f"from tomorrow {starts:%H:%M} "
    else:
        start = f"from {starts:%A %H:%M} "
    text = start + until
    return text[0].upper() + text[1:]


def _readable_instruction(text: str) -> str:
    skipped = ("municipalities", "stay informed", "keep yourself updated")
    paragraphs = []
    for paragraph in text.split("\n\n"):
        sentences = re.split(r"(?<=[.!?])\s+", paragraph.strip())
        kept = [sentence for sentence in sentences if not any(words in sentence.lower() for words in skipped)]
        if kept:
            paragraphs.append(" ".join(kept))
    return "\n\n".join(paragraphs)


@router.get("/warnings")
def get_warnings(area: Optional[int] = None, day: str = "today") -> dict:
    if day not in ("today", "tomorrow"):
        raise HTTPException(status_code=400, detail="day must be 'today' or 'tomorrow'.")
    chosen = resolve_area(area)
    local_now = chosen.region.now()
    shown_day = local_now.date() + timedelta(days=1 if day == "tomorrow" else 0)
    alerts = met_alerts.alerts_for(chosen, shown_day) + nve_warnings.warnings_for(chosen, shown_day)
    alerts.sort(key=lambda alert: ("Extreme", "Severe", "Moderate").index(alert.severity))
    return {"warnings": [
        {
            "name": alert.name,
            "icon": _alert_icon(alert),
            "when": _alert_duration_text(alert, local_now),
            "instruction": _readable_instruction(alert.instruction),
            "color": alert.color,
        }
        for alert in alerts
    ]}


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
