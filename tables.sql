-- Execute these queries in your DB to create all necessary tables. --

CREATE TABLE forecast_complete(
             id SERIAL PRIMARY KEY,
             forecast_created_at timestamptz,
             forecast_time timestamptz,
             area integer,
             forecast_data jsonb);

CREATE TABLE app_profiles(
             user_id bigint PRIMARY KEY,
             area integer,
             dynamic_sun_updates boolean);

CREATE TABLE forecast_update_log(
             id SERIAL PRIMARY KEY,
             forecast_created_at timestamptz NOT NULL,
             forecast_last_modified timestamptz,
             forecast_expire_time timestamptz,
             area integer NOT NULL);

CREATE TABLE sunrise(
             id SERIAL PRIMARY KEY,
             sunrise_time timestamptz NOT NULL,
             sunset_time timestamptz NOT NULL,
             for_date date NOT NULL,
             region_id integer NOT NULL);

CREATE INDEX region_id_for_date ON sunrise(for_date, region_id);
CREATE INDEX idx_forecast_update_log_area ON forecast_update_log(area);

CREATE INDEX idx_forecast_complete_area_time ON forecast_complete(area, forecast_time);

CREATE TABLE web_subscriptions(
             id SERIAL PRIMARY KEY,
             endpoint text UNIQUE NOT NULL,
             p256dh text NOT NULL,
             auth text NOT NULL,
             area integer NOT NULL DEFAULT 1,
             created_at timestamptz NOT NULL DEFAULT now(),
             last_seen timestamptz,
             is_admin boolean NOT NULL DEFAULT false);
