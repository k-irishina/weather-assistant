import psycopg
import psycopg_pool
import area
import yaml
import analysis_constants
from datetime import date
from datetime import time
from datetime import datetime

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

connpool = psycopg_pool.ConnectionPool(conninfo=strconn, timeout=pool_config["timeout"], max_size=pool_config["max_size"])

# todo: this should REALLY not be a one-for-one insertion
def insert_into_table(created_at, forecast_time, area: area.Area, data):
    with connpool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO forecast_complete(forecast_created_at, forecast_time, area, forecast_data)
                VALUES(%s, %s, %s, %s) 
                """,
                (created_at, forecast_time, area.db_int, data),
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

    query = f"""
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
            cursor.execute(query, (hour_offset, area.db_int, next_hours))
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
    query = """
        WITH latest_data AS (
            SELECT forecast_time, forecast_data,
                   CASE
                       WHEN forecast_time::time IN ('06:00:00', '07:00:00', '08:00:00') THEN 'morning'
                       WHEN forecast_time::time IN ('12:00:00', '13:00:00', '14:00:00') THEN 'midday'
                       WHEN forecast_time::time IN ('18:00:00', '19:00:00', '20:00:00') THEN 'evening'
                   END AS time_period
            FROM forecast_complete
            WHERE forecast_time::date = %s
              AND forecast_time::time IN ('06:00:00', '07:00:00', '08:00:00',
                                       '12:00:00', '13:00:00', '14:00:00',
                                       '18:00:00', '19:00:00', '20:00:00')
              AND id IN (
                  SELECT MAX(id)
                  FROM forecast_complete
                  WHERE forecast_time::date = %s AND area =  %s
                  GROUP BY forecast_time
              )
        )
        SELECT time_period, ROUND(AVG((forecast_data->>'air_temperature')::numeric), 1) AS avg_temperature
        FROM latest_data
        GROUP BY time_period;
    """

    with connpool.connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, (date, date, area.db_int))
            results = cursor.fetchall()

            # Process results into a dictionary
            formatted_results = {row[0]: {"avg_temperature": row[1]} for row in results}

            # Ensure all periods are present, even if no data was found for some
            for period in ["morning", "midday", "evening"]:
                formatted_results.setdefault(period, {"avg_temperature": None})

    return formatted_results


def evaluate_clouds(
    area: area.Area,
    date: date,
    sunrise: time = time(8, 0),
    sunset: time = time(16, 0),
):
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
                          AND forecast_time::time BETWEEN %s AND %s
                          AND id IN (
                              SELECT MAX(id)
                              FROM forecast_complete
                              WHERE forecast_time::date = %s AND area = %s
                              GROUP BY forecast_time
                          )
                    )
                    SELECT clouds_total::numeric, forecast_time::time
                    FROM latest_data
                    WHERE clouds_total::numeric < %s OR (clouds_low::numeric * 0.7 + clouds_medium::numeric * 0.3 < 35.0 AND clouds_total::numeric < 80.0)
                    ORDER BY forecast_time;
                """
            # Execute the query with the specified parameters
            cursor.execute(
                query,
                (
                    date,
                    sunrise.strftime("%H:%M:%S"),
                    sunset.strftime("%H:%M:%S"),
                    date,
                    area.db_int,
                    30.0,
                ),
            )
            results = cursor.fetchall()

            unique_cloud_coverage = {row[1]: row[0] for row in results}

    return unique_cloud_coverage


def evaluate_rain(area: area.Area, date: date):
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
                    SELECT precip::numeric, forecast_time::time
                    FROM latest_data
                    WHERE precip::numeric > %s
                    ORDER BY forecast_time;
                """
            try:
                with conn.cursor() as cursor:
                    # Execute the query with the specified parameters
                    cursor.execute(query, (date, date, area.db_int, 40.0))
                    results = cursor.fetchall()

                    # Convert results to a set of tuples for unique entries
                    precip_results = {row[0]: row[1] for row in results}

            finally:
                cursor.close()

            return precip_results


def evaluate_wind(conn, area: area.Area, date: date):
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
            cursor.execute(query, (date, date, area.db_int))
            results = cursor.fetchone()
            uv_result = results[0]
            return uv_result


def update_user_location(user_id, area: area.Area):
    with connpool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO app_profiles(user_id, area) VALUES(%s,%s) ON CONFLICT (user_id) DO UPDATE SET area = EXCLUDED.area;",
                (user_id, area.db_int),
            )
            conn.commit()


def fetch_user_location(user_id) -> int:
    with connpool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT area FROM app_profiles WHERE user_id = %s", (user_id,))
            result = cur.fetchone()
            if result is None:
                return (
                    analysis_constants.default_area_id
                )  # user has no location assigned, using default
            for area_ in area.cities.values():
                if area_.db_int == result[0]:
                    return result[0]

            return 0


def log_forecast(created_at, modified, area: area.Area):
    with connpool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO forecast_update_log(forecast_created_at, forecast_last_modified, area) 
                VALUES (%s, %s, %s)
                """,
                (created_at, modified, area.db_int),
            )
            conn.commit()


def last_fetch(area: area.Area):
    with connpool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT forecast_last_modified from forecast_update_log
                WHERE area = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (area.db_int,),
            )
            result = cur.fetchone()
            if result is None:
                return datetime.min
            return result[0]


def toggle_updates(user_id) -> bool:
    with connpool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT dynamic_sun_updates from app_profiles
                WHERE user_id = %s
                """,
                (user_id,),
            )
            enabled = cur.fetchone()[0]
            cur.execute(
                """
                UPDATE app_profiles
                SET dynamic_sun_updates = %b
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
