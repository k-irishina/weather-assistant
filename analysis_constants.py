from typing import Optional

default_area_id = 1

max_total_clouds = 30.0
percentage_total_clouds = 35.0
max_total_clouds_when_weighted = 80.0
low_cloud_weight = 0.7
medium_cloud_weight = 0.3

min_precipitation_probability = 20.0  # below this, not worth mentioning
high_possibility_precipitation = 50.0

min_wind_speed = 5.0

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
