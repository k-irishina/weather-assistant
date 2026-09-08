from typing import Optional

default_area_id = 1

max_total_clouds = 30.0
percentage_total_clouds = 35.0
max_total_clouds_when_weighted = 80.0
low_cloud_weight = 0.7
medium_cloud_weight = 0.3

min_precipitation_probability = 20.0
high_possibility_precipitation = 50.0

moderate_wind_speed = 5.0
strong_wind_speed = 8.0


moderate_gust_speed = 6.5
strong_gust_speed = 9.0

CALM = "calm"
MODERATE = "moderate"
STRONG = "strong"


def static_wind_speed(
    speed: Optional[float],
    percentile_90: Optional[float] = None,
) -> Optional[float]:
    values = [float(v) for v in (speed, percentile_90) if v is not None]
    return max(values) if values else None


def _toValue(value: Optional[float], moderate: float, strong: float) -> str:
    if value is None:
        return CALM
    if value >= strong:
        return STRONG
    if value >= moderate:
        return MODERATE
    return CALM


def wind_strength(
    speed: Optional[float],
    gust: Optional[float] = None,
    percentile_90: Optional[float] = None,
) -> str:
    static = _toValue(
        static_wind_speed(speed, percentile_90),
        moderate_wind_speed,
        strong_wind_speed,
    )
    gusty = _toValue(
        None if gust is None else float(gust),
        moderate_gust_speed,
        strong_gust_speed,
    )

    for level in (STRONG, MODERATE):
        if level in (static, gusty):
            return level
    return CALM


def is_sunny(
    total: Optional[float],
    low: Optional[float],
    medium: Optional[float],
) -> bool:
    if total is None:
        return False
    if float(total) < max_total_clouds:
        return True

    if low is None or medium is None:
        return False

    weighted = float(low) * low_cloud_weight + float(medium) * medium_cloud_weight
    return (
        weighted < percentage_total_clouds
        and float(total) < max_total_clouds_when_weighted
    )
