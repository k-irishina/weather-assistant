import logging as log
import math
import random
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from statistics import mean
from typing import NamedTuple, Optional, TypedDict

import analysis_constants as constants
import area
import db_connector
import near_term_forecast
import retrieve_complete_forecast as rcf


class Precipitation(TypedDict):
    name: str
    emoji_active: str
    emoji_inactive: str


class WeatherCondition(TypedDict):
    kind: str
    emoji: str
    text: str


class ForecastReport(TypedDict):
    area_id: int
    area_name: str
    forecast_day: date
    local_now: datetime
    # none when the report is for the next day
    from_hour: Optional[time]
    show_tomorrow: bool
    temperatures: dict
    hourly_temperatures: dict[time, float]
    forecast_checked_at: Optional[datetime]
    uv_index: float
    sunrise_sunset: db_connector.SunriseTimes
    sunny_times: dict[time, float]
    precipitation: Precipitation
    precipitation_high: list[time]
    precipitation_possible: list[time]
    precipitation_window: Optional[float]
    precipitation_window_hours: list[time]
    wind_by_hour: dict[time, db_connector.WindReading]


ICON_SUFFIXES = ("_day", "_night", "_polartwilight")


def split_symbol(code: str) -> tuple[str, str]:
    """"fair_night" -> ("fair", "_night"); symbols without a sun variant keep "" """
    for suffix in ICON_SUFFIXES:
        if code.endswith(suffix):
            return code[: -len(suffix)], suffix
    return code, ""


def daylight_minutes(first_hour: int, last_hour: int, sunrise: time, sunset: time) -> int:
    start = datetime.combine(date.min, time(first_hour))
    end = start + timedelta(hours=last_hour - first_hour + 1)
    rise = datetime.combine(date.min, sunrise.replace(tzinfo=None))
    sets = datetime.combine(date.min, sunset.replace(tzinfo=None))
    return max(0, int((min(end, sets) - max(start, rise)).total_seconds() // 60))


def period_symbol(symbols: dict[time, str], hours, tie_hour: int, daylight: int) -> Optional[str]:
    """The period's most common weather, as a day icon if the period has some daylight."""
    seen = [split_symbol(symbols[time(h)]) for h in hours if symbols.get(time(h))]
    if not seen:
        return None
    counts = Counter(base for base, _ in seen)
    top = max(counts.values())
    tied = [base for base in counts if counts[base] == top]
    tie_breaker = split_symbol(symbols[time(tie_hour)])[0] if symbols.get(time(tie_hour)) else None
    base = tie_breaker if tie_breaker in tied else tied[0]

    suffixes = [suffix for b, suffix in seen if b == base and suffix]
    if not suffixes:
        return base
    # minutes
    if daylight >= 30:
        return base + "_day"
    dark = [suffix for suffix in suffixes if suffix != "_day"]
    return base + (Counter(dark).most_common(1)[0][0] if dark else "_night")


def forecast_for_area(area_obj: area.Area, day: str = "today") -> ForecastReport:
    rcf.fetch_forecast_for_area_id(area_obj.id)

    local_now = area_obj.region.now()
    forecast_day = local_now.date() if day == "today" else local_now.date() + timedelta(days=1)
    tomorrow_available = local_now.time() >= time(17)

    # analysed values
    avg_temperatures = db_connector.select_related_temperatures(area_obj, forecast_day)
    sunrise_sunset = rcf.fetch_sunset_sunrise_for_area(area_obj)
    symbols = db_connector.hourly_symbols(area_obj, forecast_day)
    for key, (hours, tie_hour) in constants.forecast_period_hours.items():
        daylight = daylight_minutes(
            hours[0], hours[-1], sunrise_sunset["sunrise_time"], sunrise_sunset["sunset_time"])
        avg_temperatures[key]["symbol_code"] = period_symbol(symbols, hours, tie_hour, daylight)
    sunny_times = db_connector.evaluate_clouds(
        area_obj,
        forecast_day,
        sunrise_sunset["sunrise_time"],
        sunrise_sunset["sunset_time"],
    )
    precipitation_pct_by_hour = db_connector.precipitation_probabilities(
        area_obj, forecast_day, "next_1_hours"
    )
    if day == "today":
        precipitation_pct_by_hour = with_radar(area_obj, forecast_day, precipitation_pct_by_hour)
    window_pct_by_hour = db_connector.precipitation_probabilities(
        area_obj, forecast_day, "next_6_hours"
    )
    uv_index = db_connector.highest_uv_index(area_obj, forecast_day)
    forecast_checked_at = db_connector.latest_forecast_check_at(area_obj)
    wind_by_hour = db_connector.evaluate_wind(area_obj, forecast_day)
    hourly_temperatures = db_connector.hourly_temperatures(area_obj, forecast_day)

    from_hour = current_hour_cutoff(local_now, forecast_day)
    sunny_times = from_hour_onwards(sunny_times, from_hour)
    precipitation_pct_by_hour = from_hour_onwards(precipitation_pct_by_hour, from_hour)
    window_pct_by_hour = from_hour_onwards(window_pct_by_hour, from_hour)
    wind_by_hour = from_hour_onwards(wind_by_hour, from_hour)
    hourly_temperatures = from_hour_onwards(hourly_temperatures, from_hour)

    outlook = classify_precipitation(precipitation_pct_by_hour, window_pct_by_hour)

    return ForecastReport(
        area_id=area_obj.id,
        area_name=area_obj.display_name,
        forecast_day=forecast_day,
        local_now=local_now,
        from_hour=from_hour,
        show_tomorrow=tomorrow_available,
        temperatures=avg_temperatures,
        hourly_temperatures=hourly_temperatures,
        uv_index=uv_index,
        forecast_checked_at=forecast_checked_at,
        sunrise_sunset=sunrise_sunset,
        sunny_times=sunny_times,
        precipitation=precipitation_type(avg_temperatures),
        precipitation_high=outlook.high,
        precipitation_possible=outlook.possible,
        precipitation_window=outlook.window_probability,
        precipitation_window_hours=outlook.window_hours,
        wind_by_hour=wind_by_hour,
    )


def with_radar(area_obj: area.Area, forecast_day: date, hourly: dict[time, float]) -> dict[time, float]:
    if not near_term_forecast.is_covered(area_obj):
        return hourly
    series = near_term_forecast.latest_series(area_obj)
    if series is None or not near_term_forecast.is_fresh(series, datetime.now(timezone.utc)):
        return hourly

    tz = area_obj.region.timezone
    by_moment = {datetime.combine(forecast_day, hour, tzinfo=tz): p for hour, p in hourly.items()}
    adjusted = near_term_forecast.apply_radar(by_moment, near_term_forecast.radar_hours(series))
    return {
        moment.astimezone(tz).time(): probability
        for moment, probability in sorted(adjusted.items())
        if moment.astimezone(tz).date() == forecast_day
    }


class PrecipitationOutlook(NamedTuple):
    high: list[time]
    possible: list[time]
    # the two below are set instead of the hour lists when the timing is unresolved
    window_probability: Optional[float]
    window_hours: list[time]


# each next_6_hours value is the chance of rain in the six hours from its hour
WINDOW_HOURS = 6


def classify_precipitation(hourly: dict, window: dict) -> PrecipitationOutlook:
    named = {
        hour: probability
        for hour, probability in hourly.items()
        if probability >= constants.min_precipitation_probability
    }
    if max(named.values(), default=0) >= constants.confident_hour_probability:
        high = [
            hour
            for hour, probability in named.items()
            if probability > constants.high_possibility_precipitation
        ]
        possible = [hour for hour in named if hour not in high]
        return PrecipitationOutlook(high, possible, None, [])

    # fix the overlap with next day
    in_day = {
        hour: probability
        for hour, probability in window.items()
        if hour.hour <= 24 - WINDOW_HOURS
    }
    if max(in_day.values(), default=0) < constants.min_precipitation_probability:
        return PrecipitationOutlook([], [], None, [])
    peak_start = max(in_day, key=in_day.get)

    span = [
        hour
        for hour, probability in hourly.items()
        if probability >= constants.possible_hour_probability
    ]
    if not span:
        # the chance is too low, state the window
        span = [time(h) for h in range(peak_start.hour, peak_start.hour + WINDOW_HOURS)]
    return PrecipitationOutlook([], [], in_day[peak_start], sorted(span))


def format_forecast_text(report: ForecastReport, greeting: Optional[str] = None) -> str:
    # Day of week name, numeric day of month, month name
    day_text = report["forecast_day"].strftime('%A %-d %B')
    if greeting is None:
        greeting = get_greeting(report["local_now"].hour)

    return f"""
{greeting}

Forecast for {day_text}, {report["area_name"]}:

{compose_temperature_text(report["temperatures"], report["from_hour"])}

{compose_conditions_text(report)}
"""


def conditions(report: ForecastReport, min_moderate_wind_hours: int = 1) -> list["WeatherCondition"]:
    items = sunny_conditions(report["sunny_times"])
    items += precipitation_conditions(
        report["precipitation_high"], report["precipitation_possible"],
        report["precipitation_window"], report["precipitation_window_hours"],
        report["precipitation"],
    )
    items += wind_conditions(report["wind_by_hour"], min_moderate_wind_hours)
    uv_index = report["uv_index"]
    if uv_index is not None and float(uv_index) >= constants.min_shown_uv_index:
        items.append(WeatherCondition(
            kind="uv", emoji="🔸",
            text=f'Max UV index: {int(float(uv_index) + 0.5)}',
        ))
    return items


def compose_conditions_text(report: ForecastReport) -> str:
    return "\n".join(f'{item["emoji"]} {item["text"]}' for item in conditions(report))


def format_forecast_text_short(report: ForecastReport) -> str:
    """For push notification messages to be readable"""
    temps = report["temperatures"]
    temp_part = "/".join(
        compact_temperature(temps.get(key, {}).get("avg_temperature"))
        for _, key, _ in temperature_periods
    )

    lines = [f"{temp_part} {compact_precipitation_text(report)}"]

    if report["sunny_times"]:
        sunny_hours = bridge_gaps(sorted(report["sunny_times"]), constants.max_bridge_gap_hours)
        lines.append(f"🌞 {format_hours(sunny_hours)}")

    windy_hours = sorted({
        hour for hour, reading in report["wind_by_hour"].items()
        if constants.wind_strength(reading.speed, reading.gust, reading.percentile_90)
        in (constants.MODERATE, constants.STRONG)
    })
    if windy_hours:
        windy_hours = bridge_gaps(windy_hours, constants.max_bridge_gap_hours)
        lines.append(f"💨 {format_hours(windy_hours)}")

    return "\n".join(lines)


def round_temperature(value) -> int:
    return math.floor(float(value) + 0.5)


def compact_temperature(value: Optional[float]) -> str:
    return "–" if value is None else f"{round_temperature(value)}°"


def compact_precipitation_text(report: ForecastReport) -> str:
    precipitation = report["precipitation"]
    hours = sorted(set(report["precipitation_high"]) | set(report["precipitation_possible"]))
    if hours:
        hours = bridge_gaps(hours, constants.max_bridge_gap_hours)
        return f'{precipitation["emoji_active"]} {precipitation["name"]} {format_hours(hours)}'
    if report["precipitation_window_hours"]:
        window_hours = bridge_gaps(report["precipitation_window_hours"], constants.max_bridge_gap_hours)
        return (f'{precipitation["emoji_active"]} might {precipitation["name"]} '
                f'{format_hours(window_hours)}')
    return f'{precipitation["emoji_inactive"]} no {precipitation["name"]}'


def morning_forecast(user_id):
    area_id = db_connector.fetch_user_location(user_id)
    area_obj = area.areas.get(area_id, area.areas[constants.default_area_id])
    return format_forecast_text(forecast_for_area(area_obj))

# boundaries of when period is shown in the forecast
temperature_periods = (
    ("Morning", "morning", time(12)),
    ("Afternoon", "midday", time(18)),
    ("Evening", "evening", time(23)),
)

def compose_temperature_text(avg_temperatures: dict, cutoff: Optional[time]) -> str:
    return "\n".join(
        f"{label}: {format_temperature(avg_temperatures[key]['avg_temperature'])}"
        for label, key, until in temperature_periods
        if cutoff is None or until > cutoff
    )


def current_hour_cutoff(local_now: datetime, forecast_day) -> Optional[time]:
    if forecast_day != local_now.date():
        return None
    return local_now.time().replace(minute=0, second=0, microsecond=0)


def from_hour_onwards(by_hour: dict, cutoff: Optional[time]) -> dict:
    if cutoff is None:
        return by_hour
    return {hour: value for hour, value in by_hour.items() if hour >= cutoff}


def wind_conditions(wind_by_hour: dict, min_moderate_run_hours: int = 1) -> list["WeatherCondition"]:
    strong, moderate = [], []
    for hour, reading in sorted(wind_by_hour.items()):
        strength = constants.wind_strength(
            reading.speed, reading.gust, reading.percentile_90
        )
        if strength == constants.STRONG:
            strong.append(hour)
        elif strength == constants.MODERATE:
            moderate.append(hour)

    strong_set, moderate_set = frozenset(strong), frozenset(moderate)

    items = []
    if strong:
        strong = bridge_gaps(strong, constants.max_bridge_gap_hours, blocked=moderate_set)
        items.append(WeatherCondition(kind="wind", emoji="\U0001f32c\ufe0f",
                               text=f"Strong wind at {format_hours(strong)}."))

    moderate = bridge_gaps(moderate, constants.max_bridge_gap_hours, blocked=strong_set)
    moderate = significant_moderate_wind_hours(moderate, min_moderate_run_hours)
    if moderate:
        items.append(WeatherCondition(kind="wind", emoji="\U0001f4a8",
                               text=f"Moderate wind at {format_hours(moderate)}."))
    return items


def compose_wind_text(wind_by_hour: dict) -> str:
    return "\n".join(
        f'{item["emoji"]} {item["text"]}' for item in wind_conditions(wind_by_hour)
    )


def hour_runs(hours) -> list:
    if not hours:
        return []
    runs = [[hours[0]]]
    for hour in hours[1:]:
        if hour.hour == runs[-1][-1].hour + 1:
            runs[-1].append(hour)
        else:
            runs.append([hour])
    return runs


def significant_moderate_wind_hours(hours, min_run_hours: int) -> list:
    daytime = [hour for hour in hours if hour >= constants.moderate_wind_mentioned_from]
    return [hour for run in hour_runs(daytime) if len(run) >= min_run_hours for hour in run]


def bridge_gaps(hours, max_gap_hours: int, blocked=frozenset()) -> list:
    """Fill gaps of at most max_gap_hours between runs, e.g. [7,8,10] -> [7,8,9,10]."""
    runs = hour_runs(hours)
    if len(runs) <= 1:
        return hours

    merged = list(runs[0])
    for run in runs[1:]:
        gap_start, gap_end = merged[-1].hour + 1, run[0].hour
        gap_hours = [time(h) for h in range(gap_start, gap_end)]
        if gap_hours and len(gap_hours) <= max_gap_hours and not any(h in blocked for h in gap_hours):
            merged.extend(gap_hours)
        merged.extend(run)
    return merged


def format_hours(hours) -> str:
    return ", ".join(
        format_hour(run[0]) if len(run) == 1
        else f"{format_hour(run[0])}-{format_hour(run[-1])}"
        for run in hour_runs(hours)
    )


def format_hour(hour) -> str:
    return hour.strftime("%I %p").lstrip("0")

def format_temperature(value) -> str:
    return "no data" if value is None else f"{value} °C"

def precipitation_conditions(
    highprcpt, potentialprcpt, window_probability, window_hours, precipitation
) -> list["WeatherCondition"]:
    name = precipitation["name"]
    active, inactive = precipitation["emoji_active"], precipitation["emoji_inactive"]

    high_set, possible_set = frozenset(highprcpt), frozenset(potentialprcpt)

    items = []
    if highprcpt:
        high = bridge_gaps(sorted(highprcpt), constants.max_bridge_gap_hours, blocked=possible_set)
        items.append(WeatherCondition(
            kind="rain", emoji=active,
            text=f"High potential for {name} at {format_hours(high)}"))
    if potentialprcpt:
        possible = bridge_gaps(sorted(potentialprcpt), constants.max_bridge_gap_hours, blocked=high_set)
        items.append(WeatherCondition(
            kind="rain", emoji=active,
            text=f"Might {name} at {format_hours(possible)}."))
    if items:
        return items

    if window_probability is None:
        return [WeatherCondition(kind="rain", emoji=inactive, text=f"No {name} in sight!")]

    window_hours = bridge_gaps(window_hours, constants.max_bridge_gap_hours)
    span = f" {format_hours(window_hours)}" if window_hours else ""
    return [WeatherCondition(
        kind="rain", emoji=active,
        text=f"Potential for {name}{span} ({round(window_probability)}% chance)")]


def compose_precipitation_text(
    highprcpt, potentialprcpt, window_probability, window_hours, precipitation
) -> str:
    return "\n".join(
        f'{item["emoji"]} {item["text"]}'
        for item in precipitation_conditions(
            highprcpt, potentialprcpt, window_probability, window_hours, precipitation
        )
    )


def get_greeting(current_hour: int):
    # Define the time ranges and their respective greeting phrases
    greetings = [
        (
            (5, 12),
            ["Goood morning! 🐦", "Good morning! ☀🐓", "Labrīt!", "Coffee, tea, yerba mate..."],
        ),
        (
            (12, 18),
            [
                "Good afternoon!",
                "Has your day been good to you so far?",
                "Enjoying the weather?",
                "Well hello there!",
            ],
        ),
        (
            (18, 23),
            [
                "Good evening 🌆",
                "Looking good over there 😎",
                "Glad to see you again!",
                "Ciao!",
                "Greetings, human!",
            ],
        ),
        (
            (23, 5),
            [
                "Shouldn't you be asleep? 🤨",
                "😪",
                "🦉",
                "Still up?",
                "It's way past <b>my</b> bedtime!",
                "It's a bit late, but sure...",
            ],
        ),
    ]

    # Find the matching greeting range and choose a random greeting
    for (start, end), phrases in greetings:
        if start <= current_hour < end or (
            start > end and (current_hour >= start or current_hour < end)
        ):
            return random.choice(phrases)


def detect_sun_change(user_id):
    int_location = db_connector.fetch_user_location(user_id)
    return detect_sun_change_for_area(area.areas[int_location])


def detect_sun_change_for_area(select_area: area.Area):
    # get previous forecast (time fetched < 10AM local time of the day)
    hours_since_cutoff = select_area.region.now().hour - 10

    if hours_since_cutoff < 0:
        log.debug('No changes to analyse yet, offset:' + str(hours_since_cutoff))
        return None

    previous_forecast = db_connector.select_previous_forecast_for_x_hrs(
        select_area, 12, hours_since_cutoff
    )
    latest_forecast = db_connector.select_previous_forecast_for_x_hrs(
        select_area, 12, 0
    )

    if not previous_forecast or not latest_forecast:
        log.info('Not enough stored forecasts to compare yet')
        return None

    previous_forecast_at = previous_forecast[0]['created_at']
    latest_forecast_at = latest_forecast[0]['created_at']
    log.info(f"previous forecast at: {previous_forecast_at}, last at {latest_forecast_at}")

    if previous_forecast_at == latest_forecast_at:
        log.debug('No changes to analyse yet')
        return None

    now_sunny_at = compare_two_forecasts(
        group_by_time(previous_forecast), group_by_time(latest_forecast)
    )
    if not now_sunny_at:
        log.info('No hours turned sunny between the two forecasts')
        return None

    hours = ", ".join(format_hour(entry) for entry in sorted(now_sunny_at))
    return f"""
Two forecasts were compared: {previous_forecast_at} and {latest_forecast_at}.
It is now going to be sunnier at {hours}
"""


def compare_two_forecasts(g_previous_forecast: dict, g_current_forecast: dict) -> list:
    now_sunny_at = []
    for timet in set(g_previous_forecast.keys()).union(g_current_forecast.keys()):
        json_previous = g_previous_forecast.get(timet)
        json_latest = g_current_forecast.get(timet)

        if not (json_previous and json_latest):
            log.debug(
                f"Time {timet} only present in "
                f"{'the earlier' if json_previous else 'the later'} forecast"
            )
            continue

        datetimet = datetime.fromisoformat(timet)
        if not (time(7, 0) <= datetimet.time() <= time(17, 0)):
            continue

        if not calculate_if_sunny(json_previous) and calculate_if_sunny(json_latest):
            log.info(f'Cloud change detected at {timet}')
            now_sunny_at.append(datetimet)

    return now_sunny_at


def sunny_conditions(sunny_times: dict[time, float]) -> list["WeatherCondition"]:
    if not sunny_times:
        return [WeatherCondition(kind="sun", emoji="😔", text="No sunny times")]
    hours = bridge_gaps(sorted(sunny_times), constants.max_bridge_gap_hours)
    return [WeatherCondition(
        kind="sun", emoji="🌞",
        text=f"Expect sun at {format_hours(hours)}",
    )]


def compose_sunny_text(sunny_times: dict[time, float]) -> str:
    return "\n".join(
        f'{item["emoji"]} {item["text"]}' for item in sunny_conditions(sunny_times)
    )


def calculate_if_sunny(json_data) -> bool:
    return constants.is_sunny(
        json_data.get('cloud_area_fraction'),
        json_data.get('cloud_area_fraction_low'),
        json_data.get('cloud_area_fraction_medium'),
    )

def precipitation_type(avg_temps: dict[str, dict[str, float]]) -> Precipitation:
    avg_temp = [
        float(period["avg_temperature"])
        for period in avg_temps.values()
        if period.get("avg_temperature") is not None
    ]
    if not avg_temp:
        return {"name": "precipitation", "emoji_active": "🌧️", "emoji_inactive": "🌂"}
    if mean(avg_temp) > 1:
        return {"name": "rain", "emoji_active": "🌧️", "emoji_inactive": "🌂"}
    return {"name": "snow", "emoji_active": "☃️", "emoji_inactive": ""}


def group_by_time(data):
    return {item['forecast_time']: item['data'] for item in data}

def assign_user_location(user_id, area: area.Area):
    db_connector.update_user_location(user_id, area)

def fetch_user_location(user_id) -> str:
    area_int = db_connector.fetch_user_location(user_id)
    return area.areas[area_int].display_name

def toggle_updates(user_id) -> bool:
    return db_connector.toggle_updates(user_id)

