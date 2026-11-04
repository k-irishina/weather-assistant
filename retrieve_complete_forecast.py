import json
import logging
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

import analysis_constants as constants
import app_config
import area
import db_connector as db
import json_processor
from json_processor import parse_http_date, parse_utc
import yr_requests

log = logging.getLogger(__name__)

_failed_at: dict[int, datetime] = {}

def hourly_entries(entries: list, user_area: area.Area) -> list:
    day_after_tomorrow = user_area.region.today() + timedelta(days=2)
    horizon = datetime.combine(day_after_tomorrow, time.min, tzinfo=user_area.region.timezone)
    return [e for e in entries if parse_utc(e['forecast_time']) < horizon]



def fetch_forecast_for_area_id(area_id):
    user_area = area.areas.get(area_id, area.areas[constants.default_area_id])

    failed_at = _failed_at.get(user_area.id)
    if failed_at and datetime.now(timezone.utc) - failed_at < timedelta(minutes=10):
        log.info("MET failed for %s, reusing the stored forecast", user_area.display_name)
        return

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
    if response is not None and response.status_code == 304:
        expires = response.headers.get('Expires')
        db.record_forecast_check(user_area, parse_http_date(expires) if expires else None)
        return

    data = yr_requests.valid_met_json(response, "properties")
    timeseries = data["properties"].get("timeseries") if data else None
    if not timeseries:
        log.error("Error payload %s, keeping old forecast", user_area.display_name)
        _failed_at[user_area.id] = datetime.now(timezone.utc)
        return
    _failed_at.pop(user_area.id, None)
    log.debug('Headers: ' + str(response.headers))

    # for now, also storing full data into a file
    BASE_DIR = Path(__file__).resolve().parent
    DATA_DIR = BASE_DIR / "data"
    DATA_DIR.mkdir(exist_ok=True)

    jsonname = datetime.today().strftime("%d-%m-%Y-%H:%M-") + f"{user_area.display_name}-complete.json"
    json_path = DATA_DIR / jsonname
    with json_path.open('w') as f:
        json.dump(data, f, indent=4)

    forecast_created_at = json_processor.created_at_utc(data)

    db_data = json_processor.create_data_json(data)

    # audit
    last_modified_text = response.headers.get('Last-Modified')
    expires_text = response.headers.get('Expires')
    last_modified_header = parse_http_date(last_modified_text) if last_modified_text else None
    forecast_expiry_time = parse_http_date(expires_text) if expires_text else None

    db.log_forecast(forecast_created_at, last_modified_header, forecast_expiry_time, user_area)

    hourly = hourly_entries(db_data, user_area)

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
    today = user_area.region.today()
    stored = db.fetch_sunrise_sunset(user_area, today)
    if stored:
        return stored

    sun = yr_requests.get_sun_times(user_area, today)
    if sun:
        db.store_city_sunset_sunrise_times(user_area, today, *sun)
    else:
        # if celestial is down, we reuse the last stored time
        db.reuse_sun_times_for(user_area, today)
    return db.fetch_sunrise_sunset(user_area, today) or {"sunrise_time": time(7, 0), "sunset_time": time(17, 0)}
