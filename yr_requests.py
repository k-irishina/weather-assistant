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

def met_get(url: str, params: dict, last_modified: Optional[str] = None) -> Optional[requests.Response]:
    headers = {'User-Agent': user_agent}
    if last_modified:
        headers['If-Modified-Since'] = last_modified
    try:
        return requests.get(url, params=params, headers=headers, timeout=timeout)
    except requests.RequestException as error:
        log.error("Could not reach %s: %s", url, error)
        return None


def valid_met_json(response: Optional[requests.Response], required_key: str) -> Optional[dict]:
    if response is None:
        return None
    if response.status_code != 200:
        log.error("%s returned %s", response.url, response.status_code)
        return None
    try:
        data = response.json()
    except requests.exceptions.JSONDecodeError:
        log.error("%s sent invalid JSON: %r", response.url, response.text[:300])
        return None
    if not isinstance(data, dict) or required_key not in data:
        log.error("%s sent no %r: %r", response.url, required_key, str(data)[:300])
        return None
    return data


## todo: combine into one with input compact/complete
def get_weather_compact(area : area.Area):
    base_url = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
    query_params = {'lat': round(area.latitude, 4), 'lon': round(area.longtitude, 4)}
    headers = {'User-Agent': user_agent}
    response = requests.get(base_url, params=query_params, headers=headers, timeout=timeout)
    return response

def get_weather_complete(area: area.Area, last_modified=None) -> Optional[requests.Response]:
    base_url = "https://api.met.no/weatherapi/locationforecast/2.0/complete"
    query_params = {'lat': round(area.latitude, 4), 'lon': round(area.longtitude, 4)}
    return met_get(base_url, query_params, last_modified)

def get_sun_times(area: area.Area, date: date) -> Optional[tuple[datetime, datetime]]:
    base_url = "https://api.met.no/weatherapi/sunrise/3.0/sun"
    query_params = {'lat': round(area.latitude, 4), 'lon': round(area.longtitude, 4), 'date': date.isoformat()}
    data = valid_met_json(met_get(base_url, query_params), "properties")
    if data is None:
        return None
    sun = data["properties"]
    try:
        return parse_utc(sun["sunrise"]["time"]), parse_utc(sun["sunset"]["time"])
    except (KeyError, TypeError):
        log.error("Celestial API returned invalid data: %r", str(sun)[:300])
        return None

def get_metalerts(county: int) -> Optional[list[dict]]:
    """MET's current land warnings in English. None if MET can't be reached."""
    base_url = "https://api.met.no/weatherapi/metalerts/2.0/current.json"
    query_params = {'county': str(county), 'geographicDomain': 'land', 'lang': 'en'}
    data = valid_met_json(met_get(base_url, query_params), "features")
    return None if data is None else data["features"]


def get_nowcast(area: area.Area, last_modified=None) -> Optional[requests.Response]:
    base_url = "https://api.met.no/weatherapi/nowcast/2.0/complete"
    query_params = {'lat': round(area.latitude, 4), 'lon': round(area.longtitude, 4)}
    return met_get(base_url, query_params, last_modified)