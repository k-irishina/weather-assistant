import forecast_json_processor
import db_connector as db
import json
import area
import yr_requests
import sys
from datetime import datetime

def fetch_forecast_for_area_id(area_id, conn=db.connect_to_db()):
    user_area = area.cities2.get(area_id, area.cities2[1])

    last_fetched = db.last_fetch(user_area)
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
    
    # temporarily also storing it into a file
    jsonname = datetime.today().strftime('/usr/local/python-weather/data/%d-%m-%Y-%H:%M-') + user_area.human_name + '-complete.json'
    with open(jsonname, 'w') as f:
        json.dump(response.json(), f, indent=4)
    
    # for local file debugging
    ##with open('/usr/local/python-weather/10-11-2024-oslo-lower-torshov-complete.json', 'r') as f:
    #    data = json.load(f)
    
    forecast_created_at = forecast_json_processor.forecast_created_at(data)
    # this is a *list* of jsons!
    db_data = forecast_json_processor.create_data_json(data)
    
    # audit
    last_modified_header = datetime.strptime(response.headers['Last-Modified'], "%a, %d %b %Y %H:%M:%S GMT")
    db.log_forecast(forecast_created_at, str(last_modified_header), user_area)
    
    for time in db_data:
        db.insert_into_table(conn, forecast_created_at, time.get('forecast_time'), user_area, json.dumps(time, indent=4))

def fetch_forecast_for_user(user_id):
    area_id = db.fetch_user_location(user_id)
    if area_id == 0:
        sys.exit("No area registered for user")
    return fetch_forecast_for_area_id(area_id)
