
#!/usr/bin/env python
# pylint: disable=unused-argument
# This program is dedicated to the public domain under the CC0 license.

"""
Usage:
Press Ctrl-C on the command line or send a signal to the process to stop the
bot.
"""

from datetime import datetime, timedelta, time
import logging

import pytz
import yaml
import assistant
import db_connector as db
import area

from telegram import ForceReply, InlineKeyboardButton, ReplyKeyboardMarkup, InlineKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, ConversationHandler, JobQueue, MessageHandler, filters
from functools import wraps

config = yaml.safe_load(open("config.yml"))

LIST_OF_ADMINS = config["users"]["admin-users"]
TEST_USERS =  config["users"]["test-users"]

UTC = pytz.UTC
OK = range(1)

def restricted(func):
    @wraps(func)
    def wrapped(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in LIST_OF_ADMINS:
            print("Unauthorized access denied for {}.".format(user_id))
            return
        return func(update, context, *args, **kwargs)
    return wrapped

@restricted
def my_handler(update, context):
    pass  # only accessible if `user_id` is in `LIST_OF_ADMINS`.

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Define a few command handlers. These usually take the two arguments update and
# context.
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}!",
        reply_markup=ForceReply(selective=True),
    )

async def select_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = []
    sorted_areas = sorted(area.cities.values(), key=lambda x: x.human_name, reverse=False)
    for area_obj in sorted_areas:
        keyboard.append([InlineKeyboardButton(area_obj.human_name, callback_data=area_obj.db_int)])
    await update.message.reply_text(
        "Hi 🌞 Select the location for your predictions:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )
    return OK

async def select_location_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    location_id = update.callback_query.data

    # CallbackQueries need to be answered, even if no notification to the user is needed
    
    for key, area_obj in area.cities.items():
        if area_obj.db_int == int(location_id):
            print(update.callback_query.from_user.id)
            print(area_obj.db_int)
            assistant.assign_user_location(update.callback_query.from_user.id, area_obj)
            await query.answer(text="Great! Your location is set to " + area_obj.human_name)
            await query.edit_message_text(text="Your location: " + area_obj.human_name)
            return ConversationHandler.END
        
    await query.answer(
    "Location is invalid, please choose from selection."
    )
    return ConversationHandler.END
    
async def see_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    area_name = assistant.fetch_user_location(user_id)
    await update.message.reply_text("Your current location is " + area_name)

async def toggle_updates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    text = "on" if assistant.toggle_updates(user_id) else "off"
    await update.message.reply_text("Dynamic updates are now " + text)

async def receive_forecast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # fetch user location from db. for now, default torshov
    text = assistant.morning_forecast(update.message.from_user.id)
    await update.message.reply_text(text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text("""This bot is supposed to be your guide in following the weather forecast.
Current functionality is still quite limited, but nice nevertheless!
/location lets you set the location for which you would like to receive forecasts and alerts.
/forecast provides you with today's forecast - or tomorrow's, if requested after 6PM.
If I don't respond to your command, I'm probably asleep.
                                    """)

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Echo the user message."""
    await update.message.reply_text(update.message.text)

def schedule_sun_update(app: Application) -> None:
    #job_time = datetime.now(UTC) + timedelta(minutes=1)
    local_timezone = pytz.timezone('Europe/Oslo')
    target_time = time(12, 15, tzinfo=local_timezone)

    app.job_queue.run_daily(
        send_sun_update, target_time, name='kristina-daily-sun', data=datetime.now() + timedelta(minutes=1))

async def send_sun_update(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Running sun forecast analysis...")
    # todo: check users for subscription, get their location, send
    for user_id in db.dynamic_update_users():
        if user_id in TEST_USERS:
            sun_change_text = assistant.detect_sun_change(user_id)
            await context.bot.send_message(user_id, text=sun_change_text)

def schedule_morning_forecast(app: Application) -> None:
    target_time = time(7, 15, tzinfo=pytz.timezone('Europe/Oslo'))

    app.job_queue.run_daily(
        receive_forecast, target_time, name='kristina-morning-forecast', data=datetime.now() + timedelta(minutes=1))

def main() -> None:
    """Starting weather assistant..."""

    token = config['telegram']['token']
    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("forecast", receive_forecast))
    application.add_handler(CommandHandler("location", select_location))
    application.add_handler(CommandHandler("see_location", see_location))
    application.add_handler(CommandHandler("updates", toggle_updates))
    application.add_handler(CallbackQueryHandler(select_location_callback))

    set_location_handler = ConversationHandler(
        entry_points=[CommandHandler("location", select_location)],
        states={
           OK: [MessageHandler(filters.TEXT, select_location_callback)],
        },
        fallbacks=[],
    )
    application.add_handler(set_location_handler)

    # Run the bot until the user presses Ctrl-C
    schedule_sun_update(application)
    schedule_morning_forecast(application)

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()