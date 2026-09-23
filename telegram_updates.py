"""Scheduled Telegram messages"""
import logging

from telegram import Bot

import app_config
import assistant
import db_connector as db

log = logging.getLogger(__name__)

TEST_USERS = app_config.users["test-users"]


def _recipients() -> list[int]:
    return [user_id for user_id in db.dynamic_update_users() if user_id in TEST_USERS]


async def send_morning_forecasts(bot: Bot) -> None:
    for user_id in _recipients():
        try:
            text = assistant.morning_forecast(user_id)
        except Exception:
            log.exception("Could not build morning forecast for %s", user_id)
            continue
        if text:
            await bot.send_message(user_id, text=text)


async def send_sun_updates(bot: Bot) -> None:
    for user_id in _recipients():
        try:
            text = assistant.detect_sun_change(user_id)
        except Exception:
            log.exception("Could not analyse sun change for %s", user_id)
            continue
        # None is the usual case, nothing changed
        if text:
            await bot.send_message(user_id, text=text)
