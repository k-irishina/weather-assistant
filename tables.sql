-- Execute these queries in your DB to create all necessary tables. --

CREATE TABLE forecast_complete(
             id SERIAL PRIMARY KEY,
             forecast_created_at timestamp,
             forecast_time timestamp,
             area integer,
             forecast_data jsonb);

CREATE TABLE app_profiles(
             user_id bigint PRIMARY KEY,
             area integer,
             dynamic_sun_updates boolean);

CREATE TABLE forecast_update_log(
            id SERIAL PRIMARY KEY,
            forecast_created_at timestamp,
            forecast_last_modified timestamp,
            area integer)
