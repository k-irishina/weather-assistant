from zoneinfo import ZoneInfo
import json_processor
import db_connector as db
import json
import area
import yr_requests
import sys
import logging
from datetime import datetime, time
from pathlib import Path
from datetime import date

# todo: refactor this

def fetch_forecast_for_area_id(area_id):
    user_area = area.areas.get(area_id, area.areas[1])

    last_fetched = db.last_forecast_fetch(user_area)
    if (last_fetched != 0):
    ## todo - avoid formatting/unformatting by storing it as a string
        last_fetched_string = last_fetched.strftime("%a, %d %b %Y %H:%M:%S GMT")
        print(last_fetched_string)
    else:
        last_fetched_string = None
    ## fetch data
    response = yr_requests.get_weather_complete(user_area, last_fetched_string)
    if response.status_code == 304:
        sys.exit("Forecast not yet updated, no new to store")
    elif response.status_code != 200:
        sys.exit("API fetch failed")
    
    print('Response from API:' + str(response.status_code))
    print('Headers:'+ str(response.headers))
    
    data = response.json()
    
    # for now, also storing it into a file
    BASE_DIR = Path(__file__).resolve().parent
    DATA_DIR = BASE_DIR / "data"
    DATA_DIR.mkdir(exist_ok=True)

    jsonname = datetime.today().strftime("%d-%m-%Y-%H:%M-") + f"{user_area.display_name}-complete.json"
    json_path = DATA_DIR / jsonname
    with json_path.open('w') as f:
        json.dump(response.json(), f, indent=4)
    
    forecast_created_at = json_processor.forecast_created_at(data)
    # this is a *list* of jsons!
    db_data = json_processor.create_data_json(data)
    
    # audit
    last_modified_header = datetime.strptime(response.headers['Last-Modified'], "%a, %d %b %Y %H:%M:%S GMT")
    db.log_forecast(forecast_created_at, str(last_modified_header), user_area)
    
    for time in db_data:
        db.insert_into_table(forecast_created_at, time.get('forecast_time'), user_area, json.dumps(time, indent=4))

def fetch_forecast_for_user(user_id):
    area_id = db.fetch_user_location(user_id)
    if area_id == 0:
        sys.exit("No area registered for user")
    return fetch_forecast_for_area_id(area_id)

# todo: replace with running https://github.com/metno/celestial
def fetch_sunset_sunrise(user_id) -> db.SunriseTimes:
    area_id = db.fetch_user_location(user_id)
    user_area = area.areas.get(area_id, area.areas[1])
    date_today = date.today()
    if area_id == 0:
        sys.exit("No area registered for user")
        # conversion is on db connector. that should be changed
        # we don't require high accuracy here, so 10 days is acceptable
    sunrise_sunset_stored = db.fetch_sunrise_sunset(user_area, date_today, 10)
    if sunrise_sunset_stored:
        logging.info("returning stored sun data")
        return sunrise_sunset_stored
    else:
        logging.info("fetching new sun data from MET")
        sunrise_sunset_response = yr_requests.get_celestial(user_area, date_today)
        if sunrise_sunset_response.status_code != 200:
            logging.error("Failed to call Sunrise API, returning default")
            return {"sunrise_time": time(7, 00), "sunset_time": time(17, 00)}
        else:
            data = sunrise_sunset_response.json()
            sunrise_response = data["properties"]["sunrise"]["time"]
            sunset_response = data["properties"]["sunset"]["time"]
            sunrise = convert_to_timezone(sunrise_response, user_area.city.timezone)
            sunset = convert_to_timezone(sunset_response, user_area.city.timezone)
            logging.info(f"sunrise={sunrise}")
            logging.info(f"sunset={sunset}")

            logging.info("Storing sun info to DB.")
            db.store_city_sunset_sunrise_times(user_area, date_today, datetime.fromisoformat(sunrise_response), datetime.fromisoformat(sunset_response))

            return {
                "sunrise_time": sunrise,
                "sunset_time": sunset
            }

def convert_to_timezone(iso_str: str, tz: ZoneInfo) -> time:
    dt = datetime.fromisoformat(iso_str)

    if dt.tzinfo is None:
        from zoneinfo import ZoneInfo
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))

    # Convert to target timezone and return only time
    return dt.astimezone(tz).time()
