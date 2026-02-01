from datetime import datetime, time
import json

def restructure_next_x_hours(json):
    if json is not None:
        next_hours = {'symbol_code': json.get('summary').get('symbol_code'),
                      'symbol_confidence': json.get('summary').get('symbol_confidence'),
                      'probability_of_precipitation': json.get('details').get('probability_of_precipitation'),
                      'probability_of_thunder': json.get('details').get('probability_of_thunder'),
                      'precipitation_amount': json.get('details').get('precipitation_amount'),
                      }
        return next_hours
    
def forecast_created_at(response_json):
    forecast_created_at = response_json['properties']['meta']['updated_at']
    print('Created at: ' + forecast_created_at)
    return forecast_created_at

def create_data_json(response_json):
    timeseries = response_json['properties']['timeseries']
    result_list = []
    for time in timeseries:
        instant_data = time['data']['instant']['details']
        details_fields = ['air_pressure_at_sea_level',
                          'air_temperature',
                          'cloud_area_fraction',
                          'cloud_area_fraction_high',
                          'cloud_area_fraction_low',
                          'cloud_area_fraction_medium',
                          'dew_point_temperature',
                          'fog_area_fraction',
                          'relative_humidity',
                          'ultraviolet_index_clear_sky',
                          'wind_from_direction',
                          'wind_speed',
                          'wind_speed_of_gust']
        result_dic = {key:value for key, value in instant_data.items() if key in details_fields}
        result_dic['forecast_time'] = time['time']
    
        result_dic['next_1_hours'] = restructure_next_x_hours(time.get('data').get('next_1_hours'))
        result_dic['next_6_hours'] = restructure_next_x_hours(time.get('data').get('next_6_hours'))
        result_dic['next_12_hours'] = restructure_next_x_hours(time.get('data').get('next_12_hours'))

        result_list.append(result_dic)
    return result_list