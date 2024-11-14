import psycopg2
import area
import yaml
import analysis_constants
from datetime import date
from datetime import timedelta
from datetime import time

config = yaml.safe_load(open("config.yml"))
database_config = config["database"]


def connect_to_db():
    return psycopg2.connect(
        database=database_config["name"],
        user=database_config["user"],
        host=database_config["host"],
        password=database_config["password"],
        port=database_config["port"],
    )

# todo: this should REALLY not be a one-for-one insertion
def insert_into_table(conn, created_at, forecast_time, area: area.Area, data):
    cur = conn.cursor()
    cur.execute(
        """
                INSERT INTO forecast_complete(forecast_created_at, forecast_time, area, forecast_data)
                VALUES(%s, %s, %s, %s) 
                """,
        (created_at, forecast_time, area.db_int, data),
    )
    conn.commit()
    cur.close()


def select_all_from(conn):
    cur = conn.cursor()
    cur.execute(
        """
                SELECT * FROM forecast_complete
                """
    )
    result = cur.fetchall()
    cur.close()
    print(result)


def select_previous_forecast_for_x_hrs(
    conn, area: area.Area, next_hours=12, hour_offset=0
):

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

    try:
        # Create a cursor and execute the query
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
    finally:
        # Close the connection
        cursor.close()

    return formatted_records


def select_related_temperatures(conn, area: area.Area, date):
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

    try:
        with conn.cursor() as cursor:
            cursor.execute(query, (date, date, area.db_int))
            results = cursor.fetchall()

            # Process results into a dictionary
            formatted_results = {row[0]: {"avg_temperature": row[1]} for row in results}

            # Ensure all periods are present, even if no data was found for some
            for period in ["morning", "midday", "evening"]:
                formatted_results.setdefault(period, {"avg_temperature": None})

    finally:
        # Close the cursor
        cursor.close()

    return formatted_results

def evaluate_clouds(
    conn,
    area: area.Area,
    date: date,
    sunrise: time = time(8, 0),
    sunset: time = time(16, 0),
):
    # todo - sunrise/sunset times should be dynamic!
    # fetch from
    # https://docs.api.met.no/doc/sunrise/celestial.html
    cursor = conn.cursor()
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
            WHERE clouds_total::numeric < %s OR (clouds_low::numeric * 0.7 + clouds_medium::numeric * 0.3 < 35.0 AND clouds_total::numeric < 70.0)
            ORDER BY forecast_time;
        """

    try:
        with conn.cursor() as cursor:
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

    finally:
        cursor.close()

    return unique_cloud_coverage


def evaluate_rain(conn, area: area.Area, date: date):
    cursor = conn.cursor()
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
    cursor = conn.cursor()
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

def update_user_location(user_id, area: area.Area):
    conn = connect_to_db()
    cur = conn.cursor()
    cur.execute(
        f"INSERT INTO app_profiles(user_id, area) VALUES({user_id},{area.db_int}) ON CONFLICT (user_id) DO UPDATE SET area = EXCLUDED.area;"
    )
    conn.commit()
    cur.close()


def fetch_user_location(user_id, conn=connect_to_db()) -> int:
    cur = conn.cursor()
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


def log_forecast(conn, created_at, modified, area: area.Area):
    cur = conn.cursor()
    cur.execute(
        """
                INSERT INTO forecast_update_log(forecast_created_at, forecast_last_modified, area) 
                VALUES (%s, %s, %s)
                """,
        (created_at, modified, area.db_int),
    )
    conn.commit()
    cur.close()


def last_fetch(conn, area: area.Area):
    cur = conn.cursor()
    cur.execute(
        f"""
                SELECT forecast_last_modified from forecast_update_log
                WHERE area = {area.db_int}
                ORDER BY id DESC
                LIMIT 1
                """
    )
    result = cur.fetchone()
    if result is None:
        return 0
    return result[0]


def toggle_updates(user_id) -> bool:
    conn = connect_to_db()
    cur = conn.cursor()
    cur.execute(
        f"""
                SELECT dynamic_sun_updates from app_profiles
                WHERE user_id = {user_id}
                """
    )
    enabled = cur.fetchone()[0]
    cur.execute(
        f"""
                UPDATE app_profiles
                SET dynamic_sun_updates = {not enabled}
                WHERE user_id = {user_id}
                """
    )
    conn.commit()
    cur.close()
    return not enabled

def dynamic_update_users() -> list:
    conn = connect_to_db()
    cur = conn.cursor()
    cur.execute("""
                SELECT user_id FROM app_profiles WHERE dynamic_sun_updates = TRUE
                """)
    result = cur.fetchall()
    result_list = []
    for res in result:
        result_list.append(res[0])
    cur.close()
    return result_list


