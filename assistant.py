import json
import random
import area
import db_connector
import retrieve_complete_forecast as rcf
import analysis_constants
from datetime import date, datetime, time, timedelta
from statistics import mean
from typing import TypedDict

def morning_forecast(user_id):
    # this needs to fetch fresh data
    area_int = db_connector.fetch_user_location(user_id)
    area_obj = area.areas.get(area_int, area.areas[analysis_constants.default_area_id])

    update_treshold = datetime.now() - timedelta(hours=3)
    # update forecast if old
    if db_connector.last_forecast_fetch(area_obj) < update_treshold:
        print('Forecast outdated - fetching new...')
        rcf.fetch_forecast_for_area_id(area_int)

    # if later in the day, provide tomorrow's forecast
    if datetime.now().time() > time(18):
        forecast_day = date.today() + timedelta(days=1)
    else:
        forecast_day = date.today()

    # analysed values
    avg_temperatures = db_connector.select_related_temperatures(area_obj, forecast_day)
    sunrise_sunset = rcf.fetch_sunset_sunrise(user_id)
    sunny_times = db_connector.evaluate_clouds(area_obj, forecast_day, sunrise_sunset["sunrise_time"], sunrise_sunset["sunset_time"])
    precipitation_pct_by_hour = db_connector.evaluate_precipitation(area_obj, forecast_day)
    uv_index = db_connector.highest_uv_index(area_obj, forecast_day)
    precipitation = precipitation_type(avg_temperatures)
    
    highprcpt = []
    potentialprcpt = []

    for key, value in precipitation_pct_by_hour.items():
        if key > 40:
            highprcpt.append(value.hour)
        else:
            potentialprcpt.append(value.hour)

    # Day of week name, numeric day of month, month name
    day_text = forecast_day.strftime('%A %d %B')

    # todo: add wind/wind gusts
        
    text = f"""
           {get_greeting()}

           Forecast for {day_text}, {area_obj.display_name}:

           Morning: {avg_temperatures['morning']['avg_temperature']} °C
           Afternoon: {avg_temperatures['midday']['avg_temperature']} °C
           Evening: {avg_temperatures['evening']['avg_temperature']} °C

           Max UV index: {round(uv_index)}

           {compose_sunny_text(sunny_times)}
           {f'High potential for {precipitation["name"]} at {highprcpt} {precipitation["emoji_active"]}\n' if highprcpt else ''}{f'Possible {precipitation["name"]} at {potentialprcpt}\n' if potentialprcpt else ''}
           {f'No {precipitation["name"]} in sight! {precipitation["emoji_inactive"]}\n' if not highprcpt and not potentialprcpt else ''}
           """
    return text

def get_greeting():
    current_hour = datetime.now().hour
    
    # Define the time ranges and their respective greeting phrases
    greetings = [
        ((5, 12), ["Goood morning! 🐦", "Good morning! ☀🐓", "Labrīt, as we say in Latvian."]),
        ((12, 18), ["Oh hey, good afternoon!", "Has your day been good to you so far?", "Enjoying the weather?"]),
        ((18, 23), ["Good evening 🌆", "Looking good over there!", "Glad to see you again!", "Ciao!", "Evening, human!"]),
        ((23, 5), ["Shouldn't you be sleeping? 🤨", "😪", "Good to see you!", "It's a bit late, but sure..."]),
    ]
    
    # Find the matching greeting range and choose a random greeting
    for (start, end), phrases in greetings:
        if start <= current_hour < end or (start > end and (current_hour >= start or current_hour < end)):
            return random.choice(phrases)

def detect_sun_change(user_id):
    int_location = db_connector.fetch_user_location(user_id)
    select_area = area.areas[int_location]
    # get previous forecast (time fetched < 9AM of the day)
    timedelta = datetime.now().hour - time(hour=10, minute=0).hour

    if timedelta < 0: 
        print("No changes to analyse yet, timedelta:" + str(timedelta))
        return
    previous_forecast = db_connector.select_previous_forecast_for_x_hrs(select_area, 12, timedelta)
    latest_forecast = db_connector.select_previous_forecast_for_x_hrs(select_area, 12, 0)

    previous_forecast_at = previous_forecast[0]['created_at']
    latest_forecast_at = latest_forecast[0]['created_at']
    print("previous forecast at: "+ previous_forecast_at + " , last at" + latest_forecast_at)

    if previous_forecast_at == latest_forecast_at:
        print("No changes to analyse yet")
        return
    
    g_previous_forecast = group_by_time(previous_forecast)
    g_latest_forecast = group_by_time(latest_forecast)

    now_sunny_at = []
    for timet in set(g_previous_forecast.keys()).union(g_latest_forecast.keys()):

        json_previous = json.loads(json.dumps(g_previous_forecast.get(timet, [])))
        json_latest = json.loads(json.dumps(g_latest_forecast.get(timet, [])))

        datetimet = datetime.fromisoformat(timet)
        if (json_previous and json_latest) and (time(7, 0) <= datetimet.time() <= time(17,0)):
          print(f"Comparison for time {timet}:")
          if not calculate_if_sunny(json_previous) and calculate_if_sunny(json_latest):
          #if float(jsondata2.get('cloud_area_fraction')) - float(jsondata1.get('cloud_area_fraction')) > 10:
              print("Cloud change detected" + str(timet))
              now_sunny_at.append(datetime.fromisoformat(timet))

        else:
            print(f"Data for time {timet} only found in {'Dataset 1' if json_previous else 'Dataset 2'}")

    sunny_times_text = f"""
Two forecasts were compared: {previous_forecast_at} and {latest_forecast_at}.
It is now going to be sunnier at {", ".join([entry.strftime("%H %p") for entry in now_sunny_at])}
"""
    return sunny_times_text

def compare_two_forecasts(g_previous_forecast:dict, g_current_forecast:dict):
    now_sunny_at = []
    for timet in set(g_previous_forecast.keys()).union(g_current_forecast.keys()):

        json_previous = json.loads(json.dumps(g_previous_forecast.get(timet, [])))
        json_latest = json.loads(json.dumps(g_current_forecast.get(timet, [])))

        datetimet = datetime.fromisoformat(timet)
        if (json_previous and json_latest) and (time(7,0) <= datetimet.time() <= time(17,0)):
          print(f"Comparison for time {timet}:")
          if not calculate_if_sunny(json_previous) and calculate_if_sunny(json_latest):
          #if float(jsondata2.get('cloud_area_fraction')) - float(jsondata1.get('cloud_area_fraction')) > 10:
              print("Cloud change detected" + str(timet))
              now_sunny_at.append(datetime.fromisoformat(timet))

        else:
            print(f"Data for time {timet} only found in {'Dataset 1' if json_previous else 'Dataset 2'}")
        
    return now_sunny_at

def compose_sunny_text(sunny_times: dict[time, float]) -> str:
    if not sunny_times:
        return 'No sunny times 😔'
    else:
        #current_sunny_times = filter(lambda sun_time : datetime.now().time() < sun_time, sunny_times.keys())
        current_sunny_times = sunny_times.keys()
        if current_sunny_times:
            return f'🌞 Expect sun at {", ".join([key.strftime("%H %p") for key in sunny_times.keys()])}'
        else:
            return 'No more expected sunny times today. ☁'

def calculate_if_sunny(json_data) -> bool:
    low = json_data.get('cloud_area_fraction_low')
    medium = json_data.get('cloud_area_fraction_medium')
    total = json_data.get('cloud_area_fraction')
    return total < 30.0 or (low * 0.7 + medium * 0.3 < 35.0 and total < 80.0)

class Precipitation(TypedDict):
    name: str
    emoji_active: str
    emoji_inactive: str

def precipitation_type(avg_temps: dict[str, dict[str, float]]) -> Precipitation:
    avg_temp = mean(
    value
    for inner in avg_temps.values()
    for value in inner.values()
    )
    if (avg_temp > 1):
        return {
            "name": "rain",
            "emoji_active": "🌧️",
            "emoji_inactive": "🌂"
        }
    else:
        return {
            "name": "snow",
            "emoji_active": "☃️",
            "emoji_inactive": ""
        }

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
