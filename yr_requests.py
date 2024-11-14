import requests
import yaml
import area

config = yaml.safe_load(open("config.yml"))

## todo: combine into one with input compact/complete
def get_weather_compact(area : area.Area):
    user_agent = config['met-api']['user-agent-header']
    base_url = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
    query_params = {'lat': round(area.latitude, 4), 'lon': round(area.longtitude, 4)}
    headers = {'User-Agent': user_agent}
    response = requests.get(base_url, params=query_params, headers=headers)
    return response

def get_weather_complete(area: area.Area, last_modified=None):
    user_agent = config['met-api']['user-agent-header']
    base_url = "https://api.met.no/weatherapi/locationforecast/2.0/complete"
    query_params = {'lat': round(area.latitude, 4), 'lon': round(area.longtitude, 4)}
    headers = {'User-Agent': user_agent}
    if last_modified:
        headers['If-Modified-Since'] = last_modified
    response = requests.get(base_url, params=query_params, headers=headers)
    return response