import requests
import yaml
import area
from datetime import date

config = yaml.safe_load(open("config.yml"))

user_agent = config['met-api']['user-agent-header']


## todo: combine into one with input compact/complete
def get_weather_compact(area : area.Area):
    base_url = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
    query_params = {'lat': round(area.latitude, 4), 'lon': round(area.longtitude, 4)}
    headers = {'User-Agent': user_agent}
    response = requests.get(base_url, params=query_params, headers=headers)
    return response

def get_weather_complete(area: area.Area, last_modified=None):
    base_url = "https://api.met.no/weatherapi/locationforecast/2.0/complete"
    query_params = {'lat': round(area.latitude, 4), 'lon': round(area.longtitude, 4)}
    headers = {'User-Agent': user_agent}
    if last_modified:
        headers['If-Modified-Since'] = last_modified
    response = requests.get(base_url, params=query_params, headers=headers)
    return response

def get_celestial(area: area.Area, date: date, last_modified=None):
    base_url = "https://api.met.no/weatherapi/sunrise/3.0/sun"
    query_params = {'lat': round(area.latitude, 4), 'lon': round(area.longtitude, 4), 'date': date.isoformat()}
    headers = {'User-Agent': user_agent}
    if last_modified:
        headers['If-Modified-Since'] = last_modified
    response = requests.get(base_url, params=query_params, headers=headers)
    return response
