from datetime import date, datetime, time, timedelta
from typing import Optional, TypedDict, NamedTuple

import psycopg_pool
import yaml

import analysis_constants
import area

config = yaml.safe_load(open("config.yml"))
database_config = config["database"]
pool_config = config["database"]["pool"]
strconn = """
        dbname=%s 
        user=%s 
        host=%s 
        password=%s 
        port=%s 
        """ % (
    database_config["name"],
    database_config["user"],
    database_config["host"],
    database_config["password"],
    database_config["port"],
)

connpool = psycopg_pool.ConnectionPool(
    conninfo=strconn, timeout=pool_config["timeout"], max_size=pool_config["max_size"]
)


class ForecastFetch(NamedTuple):
    last_modified: datetime
    expire_time: datetime


# todo: this should REALLY not be a one-for-one insertion
def insert_into_table(created_at, forecast_time, area: area.Area, data):
    with connpool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO forecast_complete(forecast_created_at, forecast_time, area, forecast_data)
                VALUES(%s, %s, %s, %s) 
                """,
                (created_at, forecast_time, area.id, data),
            )
            conn.commit()


def select_all_from():
    with connpool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                        SELECT * FROM forecast_complete
                        """
            )
            result = cur.fetchall()
            print(result)


def select_previous_forecast_for_x_hrs(area: area.Area, next_hours=12, hour_offset=0):

    query = """
                SELECT forecast_created_at, forecast_time, forecast_data
                FROM forecast_complete
                WHERE forecast_created_at = (
                    SELECT MAX(forecast_created_at)
                    FROM forecast_complete
                    WHERE forecast_created_at <= NOW() - (%s * INTERVAL '1 hour')
                    AND area = %s
                )
                AND forecast_time BETWEEN NOW() AND NOW() + INTERVAL '%s hours'
            """

    with connpool.connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, (hour_offset, area.id, next_hours))
            records = cursor.fetchall()

            if records:
                print("records found")
            else:
                print("no records")

            formatted_records = []
            for record in records:
                t_created_at = record[0].strftime("%Y-%m-%d %H:%M:%S")
                t_time = record[1].strftime("%Y-%m-%d %H:%M:%S")
                data = record[2]

                formatted_records.append(
                    {"created_at": t_created_at, "forecast_time": t_time, "data": data}
                )

    return formatted_records


def select_related_temperatures(area: area.Area, date):
    timezone = str(area.region.timezone)
    query = """
    WITH localized_data AS (
        SELECT
            (forecast_time AT TIME ZONE 'UTC' AT TIME ZONE %(tz)s::text) AS local_ts,
            forecast_data,
            id,
            forecast_time
        FROM forecast_complete
        WHERE area = %(area)s
    ),
    latest_rows AS (
        SELECT *
        FROM localized_data
        WHERE local_ts::date = %(target_date)s
            AND local_ts::time IN (
              '06:00:00', '07:00:00', '08:00:00',
              '12:00:00', '13:00:00', '14:00:00',
              '18:00:00', '19:00:00', '20:00:00'
            )
            AND id IN (
                SELECT MAX(id)
                FROM forecast_complete
                WHERE area = %(area)s
                GROUP BY forecast_time
            )
      )
    SELECT 
    CASE
        WHEN local_ts::time IN ('06:00:00', '07:00:00', '08:00:00') THEN 'morning'
        WHEN local_ts::time IN ('12:00:00', '13:00:00', '14:00:00') THEN 'midday'
        WHEN local_ts::time IN ('18:00:00', '19:00:00', '20:00:00') THEN 'evening'
    END AS time_period,
    ROUND(AVG((forecast_data->>'air_temperature')::numeric), 1) AS avg_temperature
    FROM latest_rows
    GROUP BY time_period;
"""

    with connpool.connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                query, ({"tz": timezone, "area": area.id, "target_date": date})
            )
            results = cursor.fetchall()

            # Process results into a dictionary
            formatted_results = {row[0]: {"avg_temperature": row[1]} for row in results}

            # in case of missing data
            for period in ["morning", "midday", "evening"]:
                formatted_results.setdefault(period, {"avg_temperature": None})

    return formatted_results


def evaluate_clouds(
    area: area.Area,
    date: date,
    sunrise: time,
    sunset: time,
) -> dict[time, float]:
    timezone = str(area.region.timezone)
    with connpool.connection() as conn:
        with conn.cursor() as cursor:
            # todo - sunrise/sunset times should be dynamic!
            # fetch from
            # https://docs.api.met.no/doc/sunrise/celestial.html
            query = """
                    WITH latest_data AS (
                        SELECT forecast_time, forecast_data->>'cloud_area_fraction' AS clouds_total,
                        forecast_data->>'cloud_area_fraction_low' AS clouds_low,
                        forecast_data->>'cloud_area_fraction_medium' AS clouds_medium
                        FROM forecast_complete
                        WHERE forecast_time::date = %s
                          AND (forecast_time AT TIME ZONE 'UTC' AT TIME ZONE %s)::time BETWEEN %s AND %s
                          AND id IN (
                              SELECT MAX(id)
                              FROM forecast_complete
                              WHERE forecast_time::date = %s AND area = %s
                              GROUP BY forecast_time
                          )
                    )
                    SELECT clouds_total::numeric, (forecast_time AT TIME ZONE 'UTC' AT TIME ZONE %s)::time
                    FROM latest_data
                    WHERE clouds_total::numeric < %s OR (clouds_low::numeric * 0.7 + clouds_medium::numeric * 0.3 < 35.0 AND clouds_total::numeric < 80.0)
                    ORDER BY forecast_time;
                """
            # Execute the query with the specified parameters
            cursor.execute(
                query,
                (
                    date,
                    timezone,
                    sunrise.strftime("%H:%M:%S"),
                    sunset.strftime("%H:%M:%S"),
                    date,
                    area.id,
                    timezone,
                    30.0,
                ),
            )
            results = cursor.fetchall()

            unique_cloud_coverage = {row[1]: row[0] for row in results}

    return unique_cloud_coverage


def evaluate_precipitation(area: area.Area, date: date):
    timezone = str(area.region.timezone)
    with connpool.connection() as conn:
        with conn.cursor() as cursor:
            query = """
                    WITH latest_data AS (
                    SELECT forecast_time, forecast_data->'next_1_hours'->>'probability_of_precipitation' AS precip
                        FROM forecast_complete
                        WHERE forecast_time::date = %s
                          AND id IN (
                              SELECT MAX(id)
                              FROM forecast_complete
                              WHERE forecast_time::date = %s AND area = %s
                              GROUP BY forecast_time
                          )
                    )
                    SELECT precip::numeric, (forecast_time AT TIME ZONE 'UTC' AT TIME ZONE %s)::time
                    FROM latest_data
                    WHERE precip::numeric >= %s
                    ORDER BY forecast_time;
                """
            cursor.execute(query, (date, date, area.id, timezone, 20.0))
            results = cursor.fetchall()

            # Convert results to a set of tuples for unique entries
            precip_results = {row[0]: row[1] for row in results}

    return precip_results


def evaluate_wind(area: area.Area, date: date):
    with connpool.connection() as conn:
        with conn.cursor() as cursor:
            # wind_speed is m/s
            query = """
                WITH latest_data AS (
                    SELECT forecast_time, forecast_data->>'wind_speed' AS wind_speed
                    FROM forecast_complete
                    WHERE forecast_time::date = %s
                      AND id IN (
                          SELECT MAX(id)
                          FROM forecast_complete
                          WHERE forecast_time::date = %s AND area = %s
                          GROUP BY forecast_time
                      )
                )
                SELECT forecast_time::time, wind_speed::numeric
                FROM latest_data
                WHERE wind_speed::numeric > %s
                ORDER BY forecast_time;
            """
            cursor.execute(
                query, (date, date, area.id, 5.0)
            )  # Example threshold: 5.0 m/s
            results = cursor.fetchall()

            wind_results = {row[0]: row[1] for row in results}

    return wind_results


def highest_uv_index(area: area.Area, date: date):
    with connpool.connection() as conn:
        with conn.cursor() as cursor:
            query = """
                    SELECT MAX((forecast_data->>'ultraviolet_index_clear_sky')::numeric) AS uv_index
                    FROM forecast_complete
                    WHERE forecast_time::date = %s
                      AND id IN (
                          SELECT MAX(id)
                          FROM forecast_complete
                          WHERE forecast_time::date = %s AND area = %s
                          GROUP BY forecast_time
                      )
                """
            cursor.execute(query, (date, date, area.id))
            results = cursor.fetchone()
            uv_result = results[0]
            return uv_result


def store_city_sunset_sunrise_times(
    area: area.Area, date: date, sunrise: datetime, sunset: datetime
):
    region_id = area.region.region_id
    with connpool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sunrise(sunrise_time, sunset_time, for_date, region_id)
                VALUES(%s, %s, %s, %s)
                """,
                (sunrise, sunset, date, region_id),
            )
            conn.commit()


def update_user_location(user_id, area: area.Area):
    with connpool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO app_profiles(user_id, area) 
                VALUES(%s, %s) 
                ON CONFLICT (user_id) DO UPDATE SET area = EXCLUDED.area;
                """,
                (user_id, area.id),
            )
            conn.commit()


def fetch_user_location(user_id) -> int:
    with connpool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT area 
                FROM app_profiles 
                WHERE user_id = %s
                """,
                (user_id,),
            )
            result = cur.fetchone()
            if result is None:
                return (
                    analysis_constants.default_area_id
                )  # user has no location assigned, using default
            for area_int in area.areas.keys():
                if area_int == result[0]:
                    return result[0]
            return 0


def log_forecast(created_at, modified, expires, area: area.Area):
    with connpool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO forecast_update_log(forecast_created_at, forecast_last_modified, forecast_expire_time, area) 
                VALUES (%s, %s, %s, %s)
                """,
                (created_at, modified, expires, area.id),
            )
            conn.commit()


def forecast_update_log(area: area.Area) -> Optional[ForecastFetch]:
    with connpool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT forecast_last_modified, forecast_expire_time
                FROM forecast_update_log
                WHERE area = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (area.id,),
            )
            result = cur.fetchone()
            if result is None:
                return None
            return ForecastFetch(result[0], result[1])


class SunriseTimes(TypedDict):
    sunrise_time: time
    sunset_time: time

def fetch_sunrise_sunset(
    area: area.Area, target_date: date, days_before: int = 1
) -> Optional[SunriseTimes]:
    start_date = target_date - timedelta(days=days_before)
    with connpool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                        SELECT sunrise_time, sunset_time
                        FROM sunrise
                        WHERE for_date BETWEEN %s AND %s
                            AND region_id = %s
                        ORDER BY for_date DESC
                        LIMIT 1
                        """,
                (start_date, target_date, area.region.region_id),
            )
            row = cur.fetchone()
            if row:
                sunrise_utc, sunset_utc = row

                # convert to Oslo timezone
                sunrise = sunrise_utc.astimezone(area.region.timezone).time()
                sunset = sunset_utc.astimezone(area.region.timezone).time()

                return SunriseTimes(sunrise_time=sunrise, sunset_time=sunset)


def toggle_updates(user_id) -> bool:
    with connpool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT dynamic_sun_updates FROM app_profiles
                WHERE user_id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()
            if row is None:
                enabled = False
            else:
                enabled = row[0]
            cur.execute(
                """
                UPDATE app_profiles
                SET dynamic_sun_updates = %s
                WHERE user_id = %s
                """,
                (not enabled, user_id),
            )
            conn.commit()
            return not enabled


def dynamic_update_users() -> list:
    with connpool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT user_id FROM app_profiles WHERE dynamic_sun_updates = TRUE"""
            )
            result = cur.fetchall()
            result_list = []
            for res in result:
                result_list.append(res[0])
            return result_list
