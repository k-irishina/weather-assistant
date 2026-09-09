import json
import logging
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import analysis_constants as constants
import app_config
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

def parse_utc(iso_str: str) -> datetime:
    """Parse an ISO-8601 instant from MET into a tz-aware UTC datetime."""
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

STORED_FORECAST_HOURS = timedelta(hours=48)


def hourly_entries(entries: list) -> list:
    if not entries:
        return entries

    horizon = parse_utc(entries[0]['forecast_time']) + STORED_FORECAST_HOURS
    return [e for e in entries if parse_utc(e['forecast_time']) <= horizon]


def parse_http_date(header_value: str) -> datetime:
    """Parse an HTTP date header, which RFC 9110 defines as always GMT."""
    return datetime.strptime(header_value, "%a, %d %b %Y %H:%M:%S GMT").replace(
        tzinfo=timezone.utc
    )


def fetch_forecast_for_area_id(area_id):
    user_area = area.areas.get(area_id, area.areas[constants.default_area_id])

    last_fetch = db.forecast_update_log(user_area)
    
    if last_fetch and last_fetch.expire_time:
        if last_fetch.expire_time > datetime.now(timezone.utc):
            log.info("Existing forecast still valid, skip calling API")
            return

    last_modified = None
    if last_fetch and last_fetch.last_modified:
        last_modified = last_fetch.last_modified.astimezone(timezone.utc).strftime(
            "%a, %d %b %Y %H:%M:%S GMT"
        )
        log.info(f"Last modified: {last_modified}")
    
    response = yr_requests.get_weather_complete(user_area, last_modified)
    if response.status_code == 304:
        return
    elif response.status_code != 200:
        return
    
    log.info('Response from API: ' + str(response.status_code))
    log.debug('Headers: ' + str(response.headers))
    
    data = response.json()
    
    # for now, also storing full data into a file
    BASE_DIR = Path(__file__).resolve().parent
    DATA_DIR = BASE_DIR / "data"
    DATA_DIR.mkdir(exist_ok=True)

    jsonname = datetime.today().strftime("%d-%m-%Y-%H:%M-") + f"{user_area.display_name}-complete.json"
    json_path = DATA_DIR / jsonname
    with json_path.open('w') as f:
        json.dump(data, f, indent=4)

    forecast_created_at = parse_utc(json_processor.forecast_created_at(data))

    db_data = json_processor.create_data_json(data)

    # audit
    last_modified_header = parse_http_date(response.headers['Last-Modified'])
    forecast_expiry_time = parse_http_date(response.headers['Expires'])

    db.log_forecast(forecast_created_at, last_modified_header, forecast_expiry_time, user_area)

    hourly = hourly_entries(db_data)

    inserted = db.insert_forecast_rows(
        forecast_created_at,
        user_area,
        ((parse_utc(entry['forecast_time']), json.dumps(entry)) for entry in hourly),
    )
    log.info(f"Stored {inserted} forecast hours for {user_area.display_name}")

def fetch_forecast_for_user(user_id):
    return fetch_forecast_for_area_id(db.fetch_user_location(user_id))

# todo: replace with running https://github.com/metno/celestial
def fetch_sunset_sunrise(user_id) -> db.SunriseTimes:
    area_id = db.fetch_user_location(user_id)
    user_area = area.areas.get(area_id, area.areas[constants.default_area_id])
    return fetch_sunset_sunrise_for_area(user_area)


def fetch_sunset_sunrise_for_area(user_area: area.Area) -> db.SunriseTimes:
    date_today = user_area.region.today()
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
            db.store_city_sunset_sunrise_times(
                user_area,
                date_today,
                parse_utc(sunrise_response),
                parse_utc(sunset_response),
            )

            return {
                "sunrise_time": sunrise,
                "sunset_time": sunset
            }

def time_of_timezone(iso_str: str, tz: ZoneInfo) -> time:
    """Local time of an ISO-8601 instant, in timezone tz"""
    return parse_utc(iso_str).astimezone(tz).time()
