from datetime import date, datetime, time, timedelta
from typing import Optional, TypedDict, NamedTuple

import psycopg_pool
from psycopg.conninfo import make_conninfo

import analysis_constants
import area
import app_config

database_config = app_config.database
pool_config = database_config["pool"]


if database_config.get("url"):
    strconn = make_conninfo(database_config["url"])
else:
    strconn = make_conninfo(
        dbname=database_config["name"],
        user=database_config["user"],
        host=database_config["host"],
        password=database_config["password"],
        port=database_config["port"],
    )

connpool = psycopg_pool.ConnectionPool(
    conninfo=strconn, timeout=pool_config["timeout"], max_size=pool_config["max_size"]
)


def local_day_bounds(area: area.Area, target_date: date) -> tuple[datetime, datetime]:
    timezone = area.region.timezone
    start = datetime.combine(target_date, time.min, tzinfo=timezone)
    end = datetime.combine(target_date + timedelta(days=1), time.min, tzinfo=timezone)
    return start, end


class WindReading(NamedTuple):
    speed: Optional[float]
    gust: Optional[float]
    percentile_10: Optional[float]
    percentile_90: Optional[float]


class ForecastFetch(NamedTuple):
    last_modified: datetime
    expire_time: datetime


def insert_forecast_rows(created_at, area: area.Area, rows) -> int:
    values = [(created_at, forecast_time, area.id, data) for forecast_time, data in rows]
    if not values:
        return 0
    with connpool.connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO forecast_complete(forecast_created_at, forecast_time, area, forecast_data)
                VALUES(%s, %s, %s, %s)
                """,
                values,
            )
        conn.commit()
    return len(values)


def select_previous_forecast_for_x_hrs(area: area.Area, next_hours=12, hour_offset=0):
    query = """
                SELECT forecast_created_at, forecast_time, forecast_data
                FROM forecast_complete
                WHERE area = %(area)s
                  AND forecast_created_at = (
                      SELECT MAX(forecast_created_at)
                      FROM forecast_complete
                      WHERE forecast_created_at <= NOW() - make_interval(hours => %(hour_offset)s)
                        AND area = %(area)s
                  )
                  AND forecast_time BETWEEN NOW() AND NOW() + make_interval(hours => %(next_hours)s)
            """

    timezone = area.region.timezone
    with connpool.connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                query,
                {
                    "area": area.id,
                    "hour_offset": hour_offset,
                    "next_hours": next_hours,
                },
            )
            records = cursor.fetchall()

            formatted_records = []
            for created_at, forecast_time, data in records:
                formatted_records.append(
                    {
                        "created_at": created_at.astimezone(timezone).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),
                        "forecast_time": forecast_time.astimezone(timezone).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),
                        "data": data,
                    }
                )

    return formatted_records


def select_related_temperatures(area: area.Area, date):
    timezone = str(area.region.timezone)
    day_start, day_end = local_day_bounds(area, date)
    query = """
    WITH localized_data AS (
        SELECT
            (forecast_time AT TIME ZONE %(tz)s) AS local_ts,
            forecast_data,
            id,
            forecast_time
        FROM forecast_complete
        WHERE area = %(area)s
    ),
    latest_rows AS (
        SELECT *
        FROM localized_data
        WHERE forecast_time >= %(day_start)s AND forecast_time < %(day_end)s
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
                query,
                {
                    "tz": timezone,
                    "area": area.id,
                    "day_start": day_start,
                    "day_end": day_end,
                },
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
    day_start, day_end = local_day_bounds(area, date)
    with connpool.connection() as conn:
        with conn.cursor() as cursor:
            query = """
                    WITH latest_data AS (
                        SELECT forecast_time, forecast_data->>'cloud_area_fraction' AS clouds_total,
                        forecast_data->>'cloud_area_fraction_low' AS clouds_low,
                        forecast_data->>'cloud_area_fraction_medium' AS clouds_medium
                        FROM forecast_complete
                        WHERE forecast_time >= %(day_start)s AND forecast_time < %(day_end)s
                          AND (forecast_time AT TIME ZONE %(tz)s)::time BETWEEN %(sunrise)s AND %(sunset)s
                          AND area = %(area)s
                          AND id IN (
                              SELECT MAX(id)
                              FROM forecast_complete
                              WHERE forecast_time >= %(day_start)s AND forecast_time < %(day_end)s
                                AND area = %(area)s
                              GROUP BY forecast_time
                          )
                    )
                    SELECT (forecast_time AT TIME ZONE %(tz)s)::time,
                           clouds_total::numeric, clouds_low::numeric, clouds_medium::numeric
                    FROM latest_data
                    ORDER BY forecast_time;
                """
            cursor.execute(
                query,
                {
                    "tz": timezone,
                    "day_start": day_start,
                    "day_end": day_end,
                    "sunrise": sunrise.strftime("%H:%M:%S"),
                    "sunset": sunset.strftime("%H:%M:%S"),
                    "area": area.id,
                },
            )
            results = cursor.fetchall()

            unique_cloud_coverage = {
                hour: total
                for hour, total, low, medium in results
                if analysis_constants.is_sunny(total, low, medium)
            }

    return unique_cloud_coverage


def evaluate_precipitation(area: area.Area, date: date) -> dict[time, float]:
    timezone = str(area.region.timezone)
    day_start, day_end = local_day_bounds(area, date)
    with connpool.connection() as conn:
        with conn.cursor() as cursor:
            query = """
                    WITH latest_data AS (
                    SELECT forecast_time, forecast_data->'next_1_hours'->>'probability_of_precipitation' AS precip
                        FROM forecast_complete
                        WHERE forecast_time >= %(day_start)s AND forecast_time < %(day_end)s
                          AND area = %(area)s
                          AND id IN (
                              SELECT MAX(id)
                              FROM forecast_complete
                              WHERE forecast_time >= %(day_start)s AND forecast_time < %(day_end)s
                                AND area = %(area)s
                              GROUP BY forecast_time
                          )
                    )
                    SELECT (forecast_time AT TIME ZONE %(tz)s)::time, precip::numeric
                    FROM latest_data
                    WHERE precip::numeric >= %(min_probability)s
                    ORDER BY forecast_time;
                """
            cursor.execute(
                query,
                {
                    "tz": timezone,
                    "day_start": day_start,
                    "day_end": day_end,
                    "area": area.id,
                    "min_probability": analysis_constants.min_precipitation_probability,
                },
            )
            results = cursor.fetchall()

            precip_results = {row[0]: row[1] for row in results}

    return precip_results


def evaluate_wind(area: area.Area, date: date) -> dict[time, WindReading]:
    timezone = str(area.region.timezone)
    day_start, day_end = local_day_bounds(area, date)
    with connpool.connection() as conn:
        with conn.cursor() as cursor:
            query = """
                WITH latest_data AS (
                    SELECT forecast_time,
                           forecast_data->>'wind_speed' AS wind_speed,
                           forecast_data->>'wind_speed_of_gust' AS gust,
                           forecast_data->>'wind_speed_percentile_10' AS p10,
                           forecast_data->>'wind_speed_percentile_90' AS p90
                    FROM forecast_complete
                    WHERE forecast_time >= %(day_start)s AND forecast_time < %(day_end)s
                      AND area = %(area)s
                      AND id IN (
                          SELECT MAX(id)
                          FROM forecast_complete
                          WHERE forecast_time >= %(day_start)s AND forecast_time < %(day_end)s
                            AND area = %(area)s
                          GROUP BY forecast_time
                      )
                )
                SELECT (forecast_time AT TIME ZONE %(tz)s)::time,
                       wind_speed::numeric, gust::numeric, p10::numeric, p90::numeric
                FROM latest_data
                ORDER BY forecast_time;
            """
            cursor.execute(
                query,
                {
                    "tz": timezone,
                    "day_start": day_start,
                    "day_end": day_end,
                    "area": area.id,
                },
            )
            return {
                hour: WindReading(speed=speed, gust=gust, percentile_10=p10, percentile_90=p90)
                for hour, speed, gust, p10, p90 in cursor.fetchall()
            }


def highest_uv_index(area: area.Area, date: date):
    timezone = str(area.region.timezone)
    day_start, day_end = local_day_bounds(area, date)
    with connpool.connection() as conn:
        with conn.cursor() as cursor:
            query = """
                    SELECT MAX((forecast_data->>'ultraviolet_index_clear_sky')::numeric) AS uv_index
                    FROM forecast_complete
                    WHERE forecast_time >= %(day_start)s AND forecast_time < %(day_end)s
                      AND area = %(area)s
                      AND id IN (
                          SELECT MAX(id)
                          FROM forecast_complete
                          WHERE forecast_time >= %(day_start)s AND forecast_time < %(day_end)s
                            AND area = %(area)s
                          GROUP BY forecast_time
                      )
                """
            cursor.execute(
                query,
                {
                    "tz": timezone,
                    "day_start": day_start,
                    "day_end": day_end,
                    "area": area.id,
                },
            )
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
            if result is None or result[0] not in area.areas:
                return analysis_constants.default_area_id # user has no location assigned, using default
            return result[0]


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

                sunrise = sunrise_utc.astimezone(area.region.timezone).time()
                sunset = sunset_utc.astimezone(area.region.timezone).time()

                return SunriseTimes(sunrise_time=sunrise, sunset_time=sunset)
            return None


def toggle_updates(user_id) -> bool:
    with connpool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO app_profiles(user_id, dynamic_sun_updates)
                VALUES (%s, TRUE)
                ON CONFLICT (user_id) DO UPDATE
                SET dynamic_sun_updates = NOT COALESCE(app_profiles.dynamic_sun_updates, FALSE)
                RETURNING dynamic_sun_updates
                """,
                (user_id,),
            )
            enabled = cur.fetchone()[0]
            conn.commit()
            return enabled


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


class WebSubscription(NamedTuple):
    endpoint: str
    p256dh: str
    auth: str
    is_admin: bool = False
    area: Optional[int] = None


def save_web_subscription(endpoint: str, p256dh: str, auth: str, area: area.Area):
    with connpool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO web_subscriptions(endpoint, p256dh, auth, area, last_seen)
                VALUES(%s, %s, %s, %s, now())
                ON CONFLICT (endpoint) DO UPDATE SET
                    p256dh = EXCLUDED.p256dh,
                    auth = EXCLUDED.auth,
                    area = EXCLUDED.area,
                    last_seen = now();
                """,
                (endpoint, p256dh, auth, area.id),
            )
            conn.commit()


def web_subscriptions_for_area(area: area.Area) -> list[WebSubscription]:
    with connpool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT endpoint, p256dh, auth, is_admin
                FROM web_subscriptions
                WHERE area = %s
                """,
                (area.id,),
            )
            return [WebSubscription(*row) for row in cur.fetchall()]


def find_web_subscription(endpoint: str) -> Optional[WebSubscription]:
    with connpool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT endpoint, p256dh, auth, is_admin, area
                FROM web_subscriptions
                WHERE endpoint = %s
                """,
                (endpoint,),
            )
            row = cur.fetchone()
            return WebSubscription(*row) if row else None


def delete_web_subscription(endpoint: str) -> None:
    with connpool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """DELETE FROM web_subscriptions WHERE endpoint = %s""",
                (endpoint,),
            )
            conn.commit()


def update_web_subscription_area(endpoint: str, area: area.Area) -> bool:
    """Point a browser's subscription at a different area. False if unknown."""
    with connpool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE web_subscriptions
                SET area = %s, last_seen = now()
                WHERE endpoint = %s
                """,
                (area.id, endpoint),
            )
            updated = cur.rowcount
        conn.commit()
    return updated > 0


def areas_with_web_subscribers() -> list[int]:
    # we only care for areas that have people subscribed
    with connpool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT area FROM web_subscriptions")
            return [row[0] for row in cur.fetchall()]
