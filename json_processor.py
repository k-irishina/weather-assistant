from datetime import datetime, timezone


def parse_utc(iso_str: str) -> datetime:
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_http_date(header_value: str) -> datetime:
    return datetime.strptime(header_value, "%a, %d %b %Y %H:%M:%S GMT").replace(
        tzinfo=timezone.utc
    )


def created_at_utc(response_json) -> datetime:
    return parse_utc(response_json['properties']['meta']['updated_at'])


def restructure_next_x_hours(block):
    if block is not None:
        details = block.get('details')
        next_hours = {'symbol_code': block.get('summary').get('symbol_code'),
                      'symbol_confidence': block.get('summary').get('symbol_confidence'),
                      'probability_of_precipitation': details.get('probability_of_precipitation'),
                      'probability_of_thunder': details.get('probability_of_thunder'),
                      'precipitation_amount': details.get('precipitation_amount'),
                      # the band around the expected amount - an expected 0.0 with a
                      # max of 0.4 is a shower the model cannot place, not a dry hour
                      'precipitation_amount_min': details.get('precipitation_amount_min'),
                      'precipitation_amount_max': details.get('precipitation_amount_max'),
                      }
        return next_hours


DETAILS_FIELDS = ('air_pressure_at_sea_level',
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
                  'wind_speed_of_gust',
                  'wind_speed_percentile_10',
                  'wind_speed_percentile_90')


def create_data_json(response_json):
    timeseries = response_json['properties']['timeseries']
    result_list = []
    for entry in timeseries:
        instant_data = entry['data']['instant']['details']
        result_dic = {key: value for key, value in instant_data.items()
                      if key in DETAILS_FIELDS}
        result_dic['forecast_time'] = entry['time']

        result_dic['next_1_hours'] = restructure_next_x_hours(entry.get('data').get('next_1_hours'))
        result_dic['next_6_hours'] = restructure_next_x_hours(entry.get('data').get('next_6_hours'))
        result_dic['next_12_hours'] = restructure_next_x_hours(entry.get('data').get('next_12_hours'))

        result_list.append(result_dic)
    return result_list
