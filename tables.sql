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
             is_admin boolean NOT NULL DEFAULT false,
             rain_alerts boolean NOT NULL DEFAULT false);


CREATE TABLE near_term_forecast(
             id SERIAL PRIMARY KEY,
             created_at timestamptz NOT NULL,
             fetched_at timestamptz NOT NULL DEFAULT now(),
             area integer NOT NULL,
             radar_coverage text,
             peak_precipitation_rate numeric,
             total_precipitation numeric,
             -- [{"time": "2026-09-09T13:40:00+00:00", "rate": 0.2}, ...]
             series jsonb NOT NULL,
             UNIQUE (area, created_at));

CREATE INDEX idx_near_term_forecast_area_created
             ON near_term_forecast(area, created_at DESC);

CREATE TABLE rain_alert_log(
             id SERIAL PRIMARY KEY,
             area integer NOT NULL,
             sent_at timestamptz NOT NULL DEFAULT now(),
             kind text NOT NULL,
             starts_at timestamptz NOT NULL,
             peak_rate numeric NOT NULL,
             recipients integer NOT NULL DEFAULT 0);

CREATE INDEX idx_rain_alert_log_area_sent ON rain_alert_log(area, sent_at DESC);

