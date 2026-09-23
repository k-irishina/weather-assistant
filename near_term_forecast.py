import json
import logging
from datetime import datetime, timedelta
from typing import NamedTuple, Optional
from zoneinfo import ZoneInfo

import analysis_constants as constants
import area
import json_processor
import yr_requests

log = logging.getLogger(__name__)

STEP_MINUTES = 5

COVERED_REGIONS = frozenset({area.OSLO})

RAIN_DESCRIPTIONS = {
    "light": "light rain",
    "moderate": "moderate rain",
    "heavy": "heavy rain",
}


class RainStep(NamedTuple):
    time: datetime  # UTC
    rate: float  # mm/h


class NearTermSeries(NamedTuple):
    area_id: int
    created_at: datetime  # UTC, from properties.meta.updated_at
    radar_coverage: str
    steps: list[RainStep]


def is_covered(area_obj: area.Area) -> bool:
    return area_obj.region in COVERED_REGIONS


def parse_near_term_forecast(area_id: int, payload: dict) -> NearTermSeries:
    properties = payload["properties"]
    meta = properties.get("meta") or {}

    steps = []
    for entry in properties.get("timeseries") or []:
        details = entry["data"]["instant"]["details"]
        rate = details.get("precipitation_rate")
        if rate is None:
            continue
        steps.append(RainStep(time=json_processor.parse_utc(entry["time"]), rate=float(rate)))

    return NearTermSeries(
        area_id=area_id,
        created_at=json_processor.parse_utc(meta["updated_at"]),
        radar_coverage=meta.get("radar_coverage", "unknown"),
        steps=steps,
    )


def rain_periods(steps: list[RainStep], threshold: float) -> list[list[RainStep]]:
    periods: list[list[RainStep]] = []
    current: list[RainStep] = []
    for step in steps:
        if step.rate >= threshold:
            current.append(step)
        elif current:
            periods.append(current)
            current = []
    if current:
        periods.append(current)
    return periods


def peak_rate(steps: list[RainStep]) -> float:
    return max((step.rate for step in steps), default=0.0)


def total_precipitation(steps: list[RainStep]) -> float:
    return sum(step.rate * STEP_MINUTES / 60 for step in steps)


def level_of(rate: float) -> str:
    if rate >= constants.heavy_rain_rate:
        return "heavy"
    if rate >= constants.moderate_rain_rate:
        return "moderate"
    if rate >= constants.rain_starting_rate:
        return "light"
    return "dry"


def fetch_and_store(area_obj: area.Area):
    import db_connector as db

    if not is_covered(area_obj):
        log.debug("%s is outside radar coverage, skipping near-term forecast",
                  area_obj.display_name)
        return None

    response = yr_requests.get_nowcast(area_obj)
    if response.status_code != 200:
        log.warning("Near-term forecast for %s returned %s",
                    area_obj.display_name, response.status_code)
        return None

    series = parse_near_term_forecast(area_obj.id, response.json())
    if not series.steps:
        log.info("Near-term forecast for %s had no rain steps (coverage: %s)",
                    area_obj.display_name, series.radar_coverage)
        return None

    stored = db.insert_near_term_forecast_run(
        series.created_at,
        area_obj,
        series.radar_coverage,
        peak_rate(series.steps),
        total_precipitation(series.steps),
        serialise_steps(series.steps),
    )
    if stored:
        log.info("Stored near-term forecast for %s: %s steps, peak %.1f mm/h",
                 area_obj.display_name, len(series.steps), peak_rate(series.steps))
    return series


def serialise_steps(steps: list[RainStep]) -> str:
    return json.dumps([{"time": s.time.isoformat(), "rate": s.rate} for s in steps])


def latest_series(
    area_obj: area.Area, as_of: Optional[datetime] = None
) -> Optional[NearTermSeries]:
    import db_connector as db

    row = db.latest_near_term_forecast_run(area_obj, as_of)
    if row is None:
        return None

    created_at, coverage, steps = row
    return NearTermSeries(
        area_id=area_obj.id,
        created_at=created_at,
        radar_coverage=coverage,
        steps=[
            RainStep(time=datetime.fromisoformat(s["time"]), rate=float(s["rate"]))
            for s in steps
        ],
    )


def local_hhmm(moment: datetime, timezone: ZoneInfo) -> str:
    return moment.astimezone(timezone).strftime("%H:%M")


def compose_near_rain_text(series: NearTermSeries, timezone: ZoneInfo) -> str:
    periods = rain_periods(series.steps, constants.rain_starting_rate)
    if not periods:
        return ""

    period = periods[0]
    description = RAIN_DESCRIPTIONS[level_of(peak_rate(period))]

    if period[0] is series.steps[0]:
        opening = f"{description.capitalize()} now"
    else:
        opening = f"{description.capitalize()} from about {local_hhmm(period[0].time, timezone)}"

    if period[-1] is series.steps[-1]:
        closing = "continuing past the two-hour radar window"
    else:
        ends = period[-1].time + timedelta(minutes=STEP_MINUTES)
        closing = f"easing around {local_hhmm(ends, timezone)}"

    return f"{opening}, {closing}."


def page_payload(series: Optional[NearTermSeries], area_obj: area.Area) -> dict:
    if series is None or not series.steps or not is_covered(area_obj):
        return {"available": False}

    periods = rain_periods(series.steps, constants.rain_starting_rate)
    if not periods:
        return {"available": False}

    timezone = area_obj.region.timezone
    return {
        "available": True,
        "area": area_obj.display_name,
        "updated_at": local_hhmm(series.created_at, timezone),
        "raining_now": series.steps[0].rate >= constants.rain_starting_rate,
        "peak_rate": peak_rate(series.steps),
        "scale_floor": constants.heavy_rain_rate,
        "total_mm": total_precipitation(series.steps),
        "summary": compose_near_rain_text(series, timezone),
        "steps": [
            {
                "time": local_hhmm(step.time, timezone),
                "rate": step.rate,
                "level": level_of(step.rate),
            }
            for step in series.steps
        ],
    }


class RadarHours(NamedTuple):
    wet: frozenset[datetime]
    dry: frozenset[datetime]


def _hour_start(moment: datetime) -> datetime:
    return moment.replace(minute=0, second=0, microsecond=0)


def is_fresh(series: NearTermSeries, at: datetime) -> bool:
    return at - series.created_at <= timedelta(minutes=constants.radar_max_age_minutes)


def radar_hours(series: NearTermSeries) -> RadarHours:
    """Hours the radar says will be wet, and hours it is confident stay dry.
    Wet uses the rain-alert rule and counts anywhere in the window. Dry needs the
    radar to reach the end of the hour, and that end to fall within
    radar_trusted_dry_minutes of the run. An hour already under way when the run
    was made counts as covered, since only the rest of it still matters.
    """
    if not series.steps:
        return RadarHours(frozenset(), frozenset())

    wet = {
        _hour_start(step.time)
        for run in rain_periods(series.steps, constants.rain_starting_rate)
        if len(run) >= constants.min_wet_steps
        for step in run
    }

    step = timedelta(minutes=STEP_MINUTES)
    first, last = series.steps[0].time, series.steps[-1].time
    trusted_until = series.created_at + timedelta(minutes=constants.radar_trusted_dry_minutes)
    dry = set()
    hour = _hour_start(first)
    while hour + timedelta(hours=1) - step <= last:
        covered_from_start = first <= hour or hour <= series.created_at
        if hour not in wet and covered_from_start and hour + timedelta(hours=1) <= trusted_until:
            dry.add(hour)
        hour += timedelta(hours=1)
    return RadarHours(frozenset(wet), frozenset(dry))


def apply_radar(probabilities: dict[datetime, float], hours: RadarHours) -> dict[datetime, float]:
    adjusted = dict(probabilities)
    adjusted.update({hour: 0.0 for hour in hours.dry})
    adjusted.update({hour: 100.0 for hour in hours.wet})
    return adjusted
