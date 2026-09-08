
#!/usr/bin/env python
# pylint: disable=unused-argument

import logging
from datetime import time
from functools import wraps

from telegram import (ForceReply, InlineKeyboardButton, InlineKeyboardMarkup,
                      Update)
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, ConversationHandler, MessageHandler,
                          filters)

import analysis_constants
import app_config
import area
import assistant
import db_connector as db

LIST_OF_ADMINS = app_config.users["admin-users"]
TEST_USERS = app_config.users["test-users"]

# todo: daily jobs run on the default area's timezone.
# Per-user send times would need one job per user
SCHEDULE_TIMEZONE = area.areas[analysis_constants.default_area_id].region.timezone

def restricted(func):
    @wraps(func)
    def wrapped(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in LIST_OF_ADMINS:
            print("Unauthorized access denied for {}.".format(user_id))
            return
        return func(update, context, *args, **kwargs)
    return wrapped

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
level=logging.DEBUG,  # Set the logging level to DEBUG
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
# logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        rf"""Hi {user.mention_html()}, welcome to your Weather Assistant Bot! 🌤\n
        Type /help to see what I can do.""",
        reply_markup=ForceReply(selective=True),
    )

async def select_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = []
    sorted_areas = sorted(area.areas.values(), key=lambda x: x.display_name, reverse=False)
    for area_obj in sorted_areas:
        keyboard.append([InlineKeyboardButton(area_obj.display_name, callback_data=area_obj.id)])
    await update.message.reply_text(
        "Hi 🌞 Select the location for your predictions:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )

async def select_location_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    location_id = update.callback_query.data

    # CallbackQueries need to be answered, even if no notification to the user is needed
    
    for key, area_obj in area.areas.items():
        if area_obj.id == int(location_id):
            logger.debug("User %s selected area %s", query.from_user.id, area_obj.id)
            assistant.assign_user_location(query.from_user.id, area_obj)
            await query.answer(text="Great! Your location is set to " + area_obj.display_name)
            await query.edit_message_text(text="Your location: " + area_obj.display_name)
            return

    await query.answer("Location is invalid, please choose from selection.")


async def see_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    area_name = assistant.fetch_user_location(user_id)
    await update.message.reply_text("Your current location is " + area_name)

async def toggle_updates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    text = "on" if assistant.toggle_updates(user_id) else "off"
    await update.message.reply_text("Dynamic updates are now " + text)

async def receive_forecast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = assistant.morning_forecast(update.message.from_user.id)
    await update.message.reply_text(text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("""This bot is supposed to be your guide in following the weather forecast.
Current functionality is still quite limited, but nice nevertheless!
/location lets you set the location for which you would like to receive forecasts and alerts.
/forecast provides you with today's forecast - or tomorrow's, if requested after 6PM.
If I don't respond to your command, I'm probably asleep.
                                    """)

def schedule_sun_update(app: Application) -> None:
    target_time = time(12, 15, tzinfo=SCHEDULE_TIMEZONE)

    app.job_queue.run_daily(
        send_sun_update, target_time, name='admin-daily-sun')

async def send_sun_update(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Running sun forecast analysis...")
    for user_id in db.dynamic_update_users():
        if user_id not in TEST_USERS:
            continue
        try:
            sun_change_text = assistant.detect_sun_change(user_id)
        except Exception:
            logger.exception("Could not analyse sun change for %s", user_id)
            continue
        # None means "nothing changed worth reporting", which is the usual case
        if sun_change_text:
            await context.bot.send_message(user_id, text=sun_change_text)

def schedule_morning_forecast(app: Application) -> None:
    target_time = time(7, 15, tzinfo=SCHEDULE_TIMEZONE)

    app.job_queue.run_daily(
        send_morning_forecast, target_time, name='admin-morning-forecast')


async def send_morning_forecast(context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("Sending scheduled morning forecast...")
    for user_id in db.dynamic_update_users():
        if user_id not in TEST_USERS:
            continue
        try:
            text = assistant.morning_forecast(user_id)
        except Exception:
            logger.exception("Could not build morning forecast for %s", user_id)
            continue
        if text:
            await context.bot.send_message(user_id, text=text)

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled error while processing update", exc_info=context.error)

    message = getattr(update, "effective_message", None)
    if message is not None:
        await message.reply_text(
            "Something went wrong working out your forecast. Please try again in a bit."
        )


# arguments for the polling for both standalone bot and web app
POLLING_KWARGS = dict(
    allowed_updates=Update.ALL_TYPES,
    poll_interval=5.0,
    read_timeout=20.0,
    connect_timeout=20.0,
    write_timeout=20.0,
)


def build_application() -> Application:
    token = app_config.telegram['token']
    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("forecast", receive_forecast))
    application.add_handler(CommandHandler("location", select_location))
    application.add_handler(CommandHandler("see_location", see_location))
    application.add_handler(CommandHandler("updates", toggle_updates))
    application.add_handler(CallbackQueryHandler(select_location_callback))

    application.add_error_handler(on_error)

    schedule_sun_update(application)
    schedule_morning_forecast(application)

    return application


def main() -> None:
    build_application().run_polling(**POLLING_KWARGS)

if __name__ == "__main__":
    main()