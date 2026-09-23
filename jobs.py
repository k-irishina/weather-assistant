"""Everything the app does on a timer, started once when the app boots."""
import asyncio
from datetime import time
from functools import partial
from typing import Awaitable, Callable

from telegram import Bot

import analysis_constants as constants
import area
import rain_watch
import scheduler
import telegram_updates
import web_push

# todo: every area is scheduled on Oslo time
SCHEDULE_TIMEZONE = area.areas[constants.default_area_id].region.timezone


def _daily(at: time, name: str, job: Callable[[], Awaitable[None]]) -> asyncio.Task:
    return scheduler.run_daily(job, at.replace(tzinfo=SCHEDULE_TIMEZONE), name)


def start(bot: Bot) -> list[asyncio.Task]:
    web_mornings = [
        _daily(at, f"web-morning-forecast-{at:%H%M}", partial(web_push.push_morning_forecast, at))
        for at in constants.morning_push_times
    ]
    return web_mornings + [
        _daily(constants.sun_update_at, "web-sun-update", web_push.push_sun_update),
        _daily(constants.default_morning_push_at, "telegram-morning-forecast",
               partial(telegram_updates.send_morning_forecasts, bot)),
        _daily(constants.sun_update_at, "telegram-sun-update",
               partial(telegram_updates.send_sun_updates, bot)),
    ] + rain_watch.schedule(bot)
