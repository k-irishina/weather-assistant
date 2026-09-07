import logging as log
import random
from datetime import datetime, time, timedelta
from statistics import mean
from typing import TypedDict

import analysis_constants as constants
import area
import db_connector
import retrieve_complete_forecast as rcf


def morning_forecast(user_id):
    # this needs to fetch fresh data
    area_id = db_connector.fetch_user_location(user_id)
    area_obj = area.areas.get(area_id, area.areas[constants.default_area_id])

    rcf.fetch_forecast_for_area_id(area_id)

    # if later in the day, provide tomorrow's forecast
    local_now = area_obj.region.now()
    if local_now.time() > time(18):
        forecast_day = local_now.date() + timedelta(days=1)
    else:
        forecast_day = local_now.date()

    # analysed values
    avg_temperatures = db_connector.select_related_temperatures(area_obj, forecast_day)
    sunrise_sunset = rcf.fetch_sunset_sunrise(user_id)
    sunny_times = db_connector.evaluate_clouds(
        area_obj,
        forecast_day,
        sunrise_sunset["sunrise_time"],
        sunrise_sunset["sunset_time"],
    )
    precipitation_pct_by_hour = db_connector.evaluate_precipitation(
        area_obj, forecast_day
    )
    uv_index = db_connector.highest_uv_index(area_obj, forecast_day)
    precipitation = precipitation_type(avg_temperatures)

    highprcpt = []
    potentialprcpt = []

    for hour, probability in precipitation_pct_by_hour.items():
        if probability > constants.high_possibility_precipitation:
            highprcpt.append(hour)
        else:
            potentialprcpt.append(hour)

    # Day of week name, numeric day of month, month name
    day_text = forecast_day.strftime('%A %d %B')

    # todo: add wind/wind gusts

    text = f"""
{get_greeting(local_now.hour)}

Forecast for {day_text}, {area_obj.display_name}:

Morning: {format_temperature(avg_temperatures['morning']['avg_temperature'])}
Afternoon: {format_temperature(avg_temperatures['midday']['avg_temperature'])}
Evening: {format_temperature(avg_temperatures['evening']['avg_temperature'])}

Max UV index: {round(uv_index)}

{compose_sunny_text(sunny_times)}
{compose_precipitation_text(highprcpt, potentialprcpt, precipitation)}
"""
    return text

def format_temperature(value) -> str:
    return "no data" if value is None else f"{value} °C"

def compose_precipitation_text(highprcpt, potentialprcpt, precipitation):
    text = ''
    if highprcpt:
        text += f'High potential for {precipitation["name"]} at {", ".join(hour.strftime("%I %p") for hour in highprcpt)} {precipitation["emoji_active"]}\n'
    if potentialprcpt:
        text += f'Possible {precipitation["name"]} at {", ".join(hour.strftime("%I %p") for hour in potentialprcpt)}.\n'
    if not highprcpt and not potentialprcpt:
        text += f'No {precipitation["name"]} in sight! {precipitation["emoji_inactive"]}\n'
    return text


def get_greeting(current_hour: int = None):
    if current_hour is None:
        current_hour = datetime.now().hour

    # Define the time ranges and their respective greeting phrases
    greetings = [
        (
            (5, 12),
            ["Goood morning! 🐦", "Good morning! ☀🐓", "Labrīt!"],
        ),
        (
            (12, 18),
            [
                "Good afternoon!",
                "Has your day been good to you so far?",
                "Enjoying the weather?",
            ],
        ),
        (
            (18, 23),
            [
                "Good evening 🌆",
                "Looking good over there!",
                "Glad to see you again!",
                "Ciao!",
                "Greetings, human!",
            ],
        ),
        (
            (23, 5),
            [
                "Shouldn't you be asleep? 🤨",
                "😪",
                "🦉",
                "It's a bit late, but sure...",
            ],
        ),
    ]

    # Find the matching greeting range and choose a random greeting
    for (start, end), phrases in greetings:
        if start <= current_hour < end or (
            start > end and (current_hour >= start or current_hour < end)
        ):
            return random.choice(phrases)


def detect_sun_change(user_id):
    int_location = db_connector.fetch_user_location(user_id)
    select_area = area.areas[int_location]
    # get previous forecast (time fetched < 10AM local time of the day)
    hours_since_cutoff = select_area.region.now().hour - time(hour=10, minute=0).hour

    if hours_since_cutoff < 0:
        log.debug('No changes to analyse yet, offset:' + str(hours_since_cutoff))
        return None

    previous_forecast = db_connector.select_previous_forecast_for_x_hrs(
        select_area, 12, hours_since_cutoff
    )
    latest_forecast = db_connector.select_previous_forecast_for_x_hrs(
        select_area, 12, 0
    )

    if not previous_forecast or not latest_forecast:
        log.info('Not enough stored forecasts to compare yet')
        return None

    previous_forecast_at = previous_forecast[0]['created_at']
    latest_forecast_at = latest_forecast[0]['created_at']
    log.info(f"previous forecast at: {previous_forecast_at}, last at {latest_forecast_at}")

    if previous_forecast_at == latest_forecast_at:
        log.debug('No changes to analyse yet')
        return None

    now_sunny_at = compare_two_forecasts(
        group_by_time(previous_forecast), group_by_time(latest_forecast)
    )
    if not now_sunny_at:
        log.info('No hours turned sunny between the two forecasts')
        return None

    hours = ", ".join(entry.strftime("%I %p") for entry in sorted(now_sunny_at))
    return f"""
Two forecasts were compared: {previous_forecast_at} and {latest_forecast_at}.
It is now going to be sunnier at {hours}
"""


def compare_two_forecasts(g_previous_forecast: dict, g_current_forecast: dict) -> list:
    now_sunny_at = []
    for timet in set(g_previous_forecast.keys()).union(g_current_forecast.keys()):
        json_previous = g_previous_forecast.get(timet)
        json_latest = g_current_forecast.get(timet)

        if not (json_previous and json_latest):
            log.debug(
                f"Time {timet} only present in "
                f"{'the earlier' if json_previous else 'the later'} forecast"
            )
            continue

        datetimet = datetime.fromisoformat(timet)
        if not (time(7, 0) <= datetimet.time() <= time(17, 0)):
            continue

        if not calculate_if_sunny(json_previous) and calculate_if_sunny(json_latest):
            log.info(f'Cloud change detected at {timet}')
            now_sunny_at.append(datetimet)

    return now_sunny_at


def compose_sunny_text(sunny_times: dict[time, float]) -> str:
    if not sunny_times:
        return 'No sunny times 😔'
    else:
        # current_sunny_times = filter(lambda sun_time : datetime.now().time() < sun_time, sunny_times.keys())
        current_sunny_times = sunny_times.keys()
        if current_sunny_times:
            return f'🌞 Expect sun at {", ".join([key.strftime("%I %p") for key in sunny_times.keys()])}'
        else:
            return "No more expected sunny times today. ☁"


def calculate_if_sunny(json_data) -> bool:
    return constants.is_sunny(
        json_data.get('cloud_area_fraction'),
        json_data.get('cloud_area_fraction_low'),
        json_data.get('cloud_area_fraction_medium'),
    )

class Precipitation(TypedDict):
    name: str
    emoji_active: str
    emoji_inactive: str


def precipitation_type(avg_temps: dict[str, dict[str, float]]) -> Precipitation:
    avg_temp = [
        float(value)
        for inner in avg_temps.values()
        for value in inner.values()
        if value is not None
    ]
    if not avg_temp:
        return {"name": "precipitation", "emoji_active": "🌧️", "emoji_inactive": "🌂"}
    if mean(avg_temp) > 1:
        return {"name": "rain", "emoji_active": "🌧️", "emoji_inactive": "🌂"}
    return {"name": "snow", "emoji_active": "☃️", "emoji_inactive": ""}


def group_by_time(data):
    grouped = {}
    for item in data:
        applicable_time = item['forecast_time']
        grouped[applicable_time] = item['data']
    return grouped

def assign_user_location(user_id, area: area.Area):
    db_connector.update_user_location(user_id, area)

def fetch_user_location(user_id) -> str:
    area_int = db_connector.fetch_user_location(user_id)
    return area.areas[area_int].display_name

def toggle_updates(user_id) -> bool:
    return db_connector.toggle_updates(user_id)

