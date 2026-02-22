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
             forecast_created_at timestamp NOT NULL,
             forecast_last_modified timestamp,
             forecast_expire_time timestamp,
             area integer NOT NULL);

CREATE TABLE sunrise(
             id SERIAL PRIMARY KEY,
             sunrise_time timestamp NOT NULL,
             sunset_time timestamp NOT NULL,
             for_date date NOT NULL,
             region_id integer NOT NULL)

CREATE INDEX region_id_for_date ON sunrise(for_date, region_id)
CREATE INDEX idx_forecast_update_log_area ON forecast_update_log(area);