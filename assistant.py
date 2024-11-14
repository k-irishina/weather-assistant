import json
import area
import db_connector
import sys
import retrieve_complete_forecast as rcf
import analysis_constants
from datetime import date, datetime, time, timedelta

def morning_forecast(user_id):
    # also, this needs to fetch fresh data
    # now that I have control, can kind of trigger retrieve forecast on each
    conn = db_connector.connect_to_db()
    area_int = db_connector.fetch_user_location(user_id, conn)
    area_obj = area.cities2.get(area_int, area.cities2[analysis_constants.default_area_id])

    update_treshold = datetime.now() - timedelta(hours=3)
    # update forecast if old
    if db_connector.last_fetch(conn, area_obj) < update_treshold:
        print('Forecast outdated - fetching new...')
        rcf.fetch_forecast_for_area_id(area_int)

    # if later in the day, provide tomorrow's forecast
    if datetime.now().time() > time(18):
        forecast_day = date.today() + timedelta(days=1)
    else:
        forecast_day = date.today()

    # analysed values
    avg_temperatures = db_connector.select_related_temperatures(conn, area_obj, forecast_day)
    sunny_times = db_connector.evaluate_clouds(conn, area_obj, forecast_day)
    rains = db_connector.evaluate_rain(conn, area_obj, forecast_day)

    sun_text = compose_sunny_text(sunny_times)
    
    highrain = []
    potentialrain = []

    for key, value in rains.items():
        if key > 40:
            highrain.append(value.hour)
        else:
            potentialrain.append(value.hour)

    forecast_day_text = forecast_day.strftime('%A %d %B')

    # todo: add wind/wind gusts
    # todo: add UV index
        
    text = f"""
           Forecast for {forecast_day_text}, {area_obj.human_name}:

           Morning: {avg_temperatures['morning']['avg_temperature']} °C
           Afternoon: {avg_temperatures['midday']['avg_temperature']} °C
           Evening: {avg_temperatures['evening']['avg_temperature']} °C

           {sun_text}
           {f'High potential for rain at {highrain}' if highrain else ''}
           {f'Possible rain at {potentialrain}' if potentialrain else ''}
           {'No rain in sight!🌂' if not highrain and not potentialrain else ''}
           """
    return text

def detect_sun_change(user_id):

    conn = db_connector.connect_to_db()
    int_location = db_connector.fetch_user_location(user_id, conn)
    select_area = area.cities2[int_location]
    # get previous forecast (time fetched < 9AM of the day)
    timedelta = datetime.now().hour - time(hour=9, minute=0).hour

    if timedelta < 0: 
        print("No changes to analyse yet, timedelta:" + timedelta)
        return
    previous_forecast = db_connector.select_previous_forecast_for_x_hrs(conn, select_area, 12, timedelta)
    latest_forecast = db_connector.select_previous_forecast_for_x_hrs(conn, select_area, 12, 0)

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
        if (json_previous and json_latest) and (time(8, 0) <= datetimet.time() <= time(16,0)):
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
        if (json_previous and json_latest) and (time(8, 0) <= datetimet.time() <= time(16,0)):
          print(f"Comparison for time {timet}:")
          if not calculate_if_sunny(json_previous) and calculate_if_sunny(json_latest):
          #if float(jsondata2.get('cloud_area_fraction')) - float(jsondata1.get('cloud_area_fraction')) > 10:
              print("Cloud change detected" + str(timet))
              now_sunny_at.append(datetime.fromisoformat(timet))

        else:
            print(f"Data for time {timet} only found in {'Dataset 1' if json_previous else 'Dataset 2'}")
        
    return now_sunny_at

def compose_sunny_text(sunny_times: dict) -> str:
    if not sunny_times:
        return 'No sunny times 🤷‍♀️'
    else:
        current_sunny_times = filter(lambda sun_time : datetime.now().time() > sun_time, sunny_times.keys())
        if current_sunny_times:
            return f'🌞 Expect sun at {", ".join([key.strftime("%H %p") for key in sunny_times.keys()])}'
        else:
            return 'No more expected sunny times today. ☁'

def calculate_if_sunny(json_data:json) -> bool:
    low = json_data.get('cloud_area_fraction_low')
    medium = json_data.get('cloud_area_fraction_medium')
    total = json_data.get('cloud_area_fraction')
    return total < 30.0 or (low * 0.7 + medium * 0.3 < 35.0 and total < 70.0)

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
    return area.cities2[area_int].human_name

def toggle_updates(user_id) -> bool:
    return db_connector.toggle_updates(user_id)
