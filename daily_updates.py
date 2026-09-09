import logging
from datetime import time
from typing import Optional

from telegram import Bot

import analysis_constants
import app_config
import area
import assistant
import db_connector as db
import scheduler
import web_push

logger = logging.getLogger(__name__)

TEST_USERS = app_config.users["test-users"]

# todo: daily jobs run on the default area's timezone.
# Per-user send times would need one job per user
SCHEDULE_TIMEZONE = area.areas[analysis_constants.default_area_id].region.timezone

MORNING_FORECAST_AT = time(7, 15, tzinfo=SCHEDULE_TIMEZONE)
SUN_UPDATE_AT = time(12, 15, tzinfo=SCHEDULE_TIMEZONE)


def schedule(bot: Optional[Bot]) -> list:
    """Register daily jobs on the app-level scheduler"""
    return [
        scheduler.run_daily(
            lambda: send_morning_forecast(bot), MORNING_FORECAST_AT, "admin-morning-forecast"),
        scheduler.run_daily(
            lambda: send_sun_update(bot), SUN_UPDATE_AT, "admin-daily-sun"),
    ]


async def send_morning_forecast(bot: Optional[Bot]) -> None:
    logger.info("Sending scheduled morning forecast...")
    for user_id in db.dynamic_update_users():
        if user_id not in TEST_USERS:
            continue
        try:
            text = assistant.morning_forecast(user_id)
        except Exception:
            logger.exception("Could not build morning forecast for %s", user_id)
            continue
        if text and bot is not None:
            await bot.send_message(user_id, text=text)
    await web_push.push_morning_forecast()


async def send_sun_update(bot: Optional[Bot]) -> None:
    logger.info("Running sun forecast analysis...")
    for user_id in db.dynamic_update_users():
        if user_id not in TEST_USERS:
            continue
        try:
            sun_change_text = assistant.detect_sun_change(user_id)
        except Exception:
            logger.exception("Could not analyse sun change for %s", user_id)
            continue
        if sun_change_text and bot is not None:
            await bot.send_message(user_id, text=sun_change_text)

    await web_push.push_sun_update()
