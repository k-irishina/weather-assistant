import json
import logging
import sys
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import area
import db_connector as db
import json_processor
import yr_requests

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.DEBUG
)
log = logging.getLogger(__name__)

# todo: refactor this

def fetch_forecast_for_area_id(area_id):
    user_area = area.areas.get(area_id, area.areas[1])

    last_fetch = db.forecast_update_log(user_area)
    
    if last_fetch and last_fetch.expire_time:
        expires_dt = last_fetch.expire_time.replace(tzinfo=timezone.utc)
        if expires_dt > datetime.now(timezone.utc):
            log.info("Existing forecast still valid, skip calling API")
            return
    
    last_modified = None
    if last_fetch and last_fetch.last_modified:
        last_modified = last_fetch.last_modified.strftime("%a, %d %b %Y %H:%M:%S GMT")
        log.info(f"Last modified: {last_modified}")
    
    response = yr_requests.get_weather_complete(user_area, last_modified)
    if response.status_code == 304:
        return
    elif response.status_code != 200:
        return
    
    log.info('Response from API: ' + str(response.status_code))
    log.debug('Headers: ' + str(response.headers))
    
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
    forecast_expiry_time = datetime.strptime(response.headers['Expires'], "%a, %d %b %Y %H:%M:%S GMT")

    db.log_forecast(forecast_created_at, str(last_modified_header), str(forecast_expiry_time), user_area)
    
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
        log.info("returning stored sun data")
        return sunrise_sunset_stored
    else:
        log.info("fetching new sun data from MET")
        sunrise_sunset_response = yr_requests.get_celestial(user_area, date_today)
        if sunrise_sunset_response.status_code != 200:
            log.error("Failed to call Sunrise API, returning default")
            return {"sunrise_time": time(7, 00), "sunset_time": time(17, 00)}
        else:
            data = sunrise_sunset_response.json()
            sunrise_response = data["properties"]["sunrise"]["time"]
            sunset_response = data["properties"]["sunset"]["time"]
            sunrise = time_of_timezone(sunrise_response, user_area.region.timezone)
            sunset = time_of_timezone(sunset_response, user_area.region.timezone)
            log.info(f"sunrise={sunrise}")
            log.info(f"sunset={sunset}")
            log.info("Storing sun info to DB.")
            db.store_city_sunset_sunrise_times(user_area, date_today, datetime.fromisoformat(sunrise_response), datetime.fromisoformat(sunset_response))

            return {
                "sunrise_time": sunrise,
                "sunset_time": sunset
            }

def time_of_timezone(iso_str: str, tz: ZoneInfo) -> time:
    dt = datetime.fromisoformat(iso_str)

    if dt.tzinfo is None:
        from zoneinfo import ZoneInfo
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))

    # Convert to target timezone and return only time
    return dt.astimezone(tz).time()
