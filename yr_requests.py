import logging
from datetime import date, datetime
from typing import Optional

import requests

import app_config
import area
from json_processor import parse_utc

log = logging.getLogger(__name__)

user_agent = app_config.met_api['user-agent-header']
timeout = 20

## todo: combine into one with input compact/complete
def get_weather_compact(area : area.Area):
    base_url = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
    query_params = {'lat': round(area.latitude, 4), 'lon': round(area.longtitude, 4)}
    headers = {'User-Agent': user_agent}
    response = requests.get(base_url, params=query_params, headers=headers, timeout=timeout)
    return response

def get_weather_complete(area: area.Area, last_modified=None):
    base_url = "https://api.met.no/weatherapi/locationforecast/2.0/complete"
    query_params = {'lat': round(area.latitude, 4), 'lon': round(area.longtitude, 4)}
    headers = {'User-Agent': user_agent}
    if last_modified:
        headers['If-Modified-Since'] = last_modified
    print("Requesting forecast")
    response = requests.get(base_url, params=query_params, headers=headers, timeout=timeout)
    return response

def get_sun_times(area: area.Area, date: date) -> Optional[tuple[datetime, datetime]]:
    base_url = "https://api.met.no/weatherapi/sunrise/3.0/sun"
    query_params = {'lat': round(area.latitude, 4), 'lon': round(area.longtitude, 4), 'date': date.isoformat()}
    headers = {'User-Agent': user_agent}
    try:
        response = requests.get(base_url, params=query_params, headers=headers, timeout=timeout)
    except requests.RequestException:
        log.exception("Could not reach celestial API")
        return None
    if response.status_code != 200:
        log.error("Celestial API returned %s", response.status_code)
        return None
    sun = response.json()["properties"]
    return parse_utc(sun["sunrise"]["time"]), parse_utc(sun["sunset"]["time"])

def get_nowcast(area: area.Area, last_modified=None):
    base_url = "https://api.met.no/weatherapi/nowcast/2.0/complete"
    query_params = {'lat': round(area.latitude, 4), 'lon': round(area.longtitude, 4)}
    headers = {'User-Agent': user_agent}
    if last_modified:
        headers['If-Modified-Since'] = last_modified
    response = requests.get(base_url, params=query_params, headers=headers, timeout=timeout)
    return response