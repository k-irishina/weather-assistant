from typing import Optional

default_area_id = 1

max_total_clouds = 30.0
percentage_total_clouds = 35.0
max_total_clouds_when_weighted = 80.0
low_cloud_weight = 0.7
medium_cloud_weight = 0.3

min_precipitation_probability = 20.0  # below this, not worth mentioning
high_possibility_precipitation = 50.0

moderate_wind_speed = 6.0
strong_wind_speed = 8.0

gust_intercept = 0.36
gust_slope = 1.78
percentile_90_intercept = 1.19
percentile_90_slope = 0.95
gust_excess_weight = 0.5
percentile_90_excess_weight = 0.3

CALM = "calm"
MODERATE = "moderate"
STRONG = "strong"


def felt_wind_speed(
    speed: Optional[float],
    gust: Optional[float] = None,
    percentile_90: Optional[float] = None,
) -> Optional[float]:
    if speed is None:
        # No wind stored - read the other values
        if gust is not None:
            return (float(gust) - gust_intercept) / gust_slope
        if percentile_90 is not None:
            return (
                float(percentile_90) - percentile_90_intercept
            ) / percentile_90_slope
        return None

    speed = float(speed)
    felt = speed
    if gust is not None:
        expected_gust = gust_intercept + gust_slope * speed
        felt += gust_excess_weight * max(0.0, float(gust) - expected_gust)
    if percentile_90 is not None:
        expected_p90 = percentile_90_intercept + percentile_90_slope * speed
        felt += percentile_90_excess_weight * max(
            0.0, float(percentile_90) - expected_p90
        )
    return felt


def wind_strength(
    speed: Optional[float],
    gust: Optional[float] = None,
    percentile_90: Optional[float] = None,
) -> str:
    felt = felt_wind_speed(speed, gust, percentile_90)
    if felt is None:
        return CALM
    if felt >= strong_wind_speed:
        return STRONG
    if felt >= moderate_wind_speed:
        return MODERATE
    return CALM


def is_sunny(
    total: Optional[float],
    low: Optional[float],
    medium: Optional[float],
) -> bool:
    """Whether a given hour counts as sunny, from its cloud area fractions.
    """
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
