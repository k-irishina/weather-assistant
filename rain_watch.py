"""Watch the radar for rain the morning forecast did not promise."""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import NamedTuple, Optional

from telegram import Bot

import analysis_constants as constants
import app_config
import area
import db_connector as db
import near_term_forecast
import scheduler
import web_push

log = logging.getLogger(__name__)

TEST_USERS = app_config.users["test-users"]

# Heavy enough to matter no matter what the morning forecast was
HEAVY = "heavy"
# Rain the morning forecast did not call for
UNFORESEEN = "unforeseen"


class RainAlert(NamedTuple):
    kind: str
    starts_at: datetime  # UTC
    peak_rate: float  # mm/h
    minutes: int


def decide(
    series: near_term_forecast.NearTermSeries,
    baseline: Optional[dict[datetime, float]],
) -> Optional[RainAlert]:
    runs = near_term_forecast.rain_periods(series.steps, constants.rain_starting_rate)
    qualifying = [run for run in runs if len(run) >= constants.min_wet_steps]
    if not qualifying:
        return None

    run = qualifying[0]
    alert = RainAlert(
        kind=HEAVY,
        starts_at=run[0].time,
        peak_rate=near_term_forecast.peak_rate(run),
        minutes=len(run) * near_term_forecast.STEP_MINUTES,
    )

    if alert.peak_rate >= constants.heavy_rain_rate:
        return alert

    if baseline is None:
        return None

    hours = {step.time.replace(minute=0, second=0, microsecond=0) for step in run}
    promised = [baseline[hour] for hour in hours if hour in baseline]
    if not promised:
        log.debug("No baseline covering %s, staying quiet", sorted(hours))
        return None

    if max(promised) >= constants.min_precipitation_probability:
        # the morning forecast already told them about this hour
        return None

    return alert._replace(kind=UNFORESEEN)


WATCHED_AREAS = [
    area_obj for area_obj in area.areas.values() if near_term_forecast.is_covered(area_obj)
]

CHECK_INTERVAL_SECONDS = 10 * 60
FIRST_CHECK_AFTER_SECONDS = 60


def _in_overnight_window(local_now: datetime, start: int, end: int) -> bool:
    return local_now.hour >= start or local_now.hour < end


def in_quiet_hours(local_now: datetime) -> bool:
    return _in_overnight_window(
        local_now, constants.quiet_hours_start, constants.quiet_hours_end)


def in_radar_pause(local_now: datetime) -> bool:
    return _in_overnight_window(
        local_now, constants.radar_pause_start, constants.radar_pause_end)


def baseline_cutoff(area_obj: area.Area, local_now: datetime) -> datetime:
    """The instant whose forecast the reader would have seen.

    After the last morning push, that is the run it was built from, the earlier
    pushes are at most one MET update older, which rarely changes a rain call.
    """
    sent_at = datetime.combine(
        local_now.date(), max(constants.morning_push_times), tzinfo=local_now.tzinfo
    )
    return local_now if local_now < sent_at else sent_at


def told_with_radar(
    area_obj: area.Area, baseline: Optional[dict[datetime, float]], cutoff: datetime
) -> Optional[dict[datetime, float]]:
    """The morning forecast corrected by the radar"""
    if baseline is None:
        return None
    radar = near_term_forecast.latest_series(area_obj, as_of=cutoff)
    if radar is None or not near_term_forecast.is_fresh(radar, cutoff):
        return baseline
    return near_term_forecast.apply_radar(baseline, near_term_forecast.radar_hours(radar))


def alert_text(alert: RainAlert, area_obj: area.Area) -> tuple[str, str]:
    timezone = area_obj.region.timezone
    when = near_term_forecast.local_hhmm(alert.starts_at, timezone)
    if alert.kind == HEAVY:
        title = "Heavy rain incoming"
        body = (f"{alert.peak_rate:g} mm/h from about {when} in "
                f"{area_obj.display_name}, for around {alert.minutes} minutes.")
    else:
        title = "Rain the forecast missed"
        body = (f"Rain from about {when} in "
                f"{area_obj.display_name} ({alert.peak_rate:g} mm/h, around "
                f"{alert.minutes} minutes). This morning's forecast did not "
                "call for it.")
    return title, body


def check_area_for_rain(area_obj: area.Area) -> Optional[RainAlert]:
    """Check for unpredicted rain and alert if so"""
    local_now = area_obj.region.now()
    if in_radar_pause(local_now):
        return None

    series = near_term_forecast.fetch_and_store(area_obj)
    if series is None:
        return None

    if in_quiet_hours(local_now):
        log.debug("%s is in quiet hours, not sending",
                  area_obj.display_name)
        return None

    cutoff = baseline_cutoff(area_obj, local_now)
    baseline = told_with_radar(
        area_obj, db.morning_baseline_precipitation(area_obj, cutoff), cutoff)

    alert = decide(series, baseline)
    if alert is None:
        return None

    last_sent = db.last_rain_alert_at(area_obj)
    cooldown = timedelta(minutes=constants.rain_alert_cooldown_minutes)
    if last_sent is not None and local_now - last_sent < cooldown:
        log.info("Rain alert for %s suppressed, last one was %s",
                 area_obj.display_name, last_sent)
        return None

    title, body = alert_text(alert, area_obj)
    recipients = web_push.send_to_rain_subscribers(area_obj, title, body)
    db.log_rain_alert(
        area_obj, alert.kind, alert.starts_at, alert.peak_rate, recipients)
    return alert


async def notify_telegram_subscribers(area_obj: area.Area, alert: RainAlert, bot: Bot) -> None:
    _, body = alert_text(alert, area_obj)
    for user_id in db.dynamic_update_users():
        if user_id not in TEST_USERS:
            continue
        if db.fetch_user_location(user_id) != area_obj.id:
            continue
        try:
            await bot.send_message(user_id, text=body)
        except Exception:
            log.exception("Could not send rain alert to %s", user_id)


async def watch(bot: Optional[Bot]) -> None:
    for area_obj in WATCHED_AREAS:
        try:
            # blocking network and database work, off the event loop
            alert = await asyncio.to_thread(check_area_for_rain, area_obj)
        except Exception:
            log.exception("Rain watch failed for %s", area_obj.display_name)
            continue
        if alert is not None and bot is not None:
            await notify_telegram_subscribers(area_obj, alert, bot)


def schedule(bot: Optional[Bot]) -> list:
    return [
        scheduler.run_repeating(
            lambda: watch(bot),
            interval_seconds=CHECK_INTERVAL_SECONDS,
            first_seconds=FIRST_CHECK_AFTER_SECONDS,
            name="radar-rain-watch",
        )
    ]
