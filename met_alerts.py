from datetime import date, datetime, time, timedelta, timezone
from typing import NamedTuple

import area
import yr_requests
from json_processor import parse_utc

SEVERITIES = ("Moderate", "Severe", "Extreme")


class Alert(NamedTuple):
    name: str  # eventAwarenessName, f.ex "Heavy rain"
    kind: str  # awareness_type, "wind","rain", etc
    starts: datetime  # UTC
    ends: datetime  # UTC
    instruction: str


# county -> (local day, warnings): one request per county per day, made on first use
_fetched: dict[int, tuple] = {}


def alerts_for(area_obj: area.Area, day: date) -> list[Alert]:
    county = area_obj.region.ssb_county
    if not county:
        return []
    today = area_obj.region.today()
    if county not in _fetched or _fetched[county][0] != today:
        features = yr_requests.get_metalerts(county)
        if features is None:  # MET unreachable: try again next time
            return []
        _fetched[county] = (today, features)

    day_start = datetime.combine(day, time.min, tzinfo=area_obj.region.timezone)
    day_end = day_start + timedelta(days=1)
    not_before = max(day_start, datetime.now(timezone.utc))
    alerts = []
    for feature in _fetched[county][1]:
        alert = to_alert(feature)
        if (feature["properties"].get("severity") in SEVERITIES
                and alert.starts < day_end and alert.ends > not_before
                and covers(feature["geometry"], area_obj.longtitude, area_obj.latitude)):
            alerts.append(alert)
    return alerts


def to_alert(feature: dict) -> Alert:
    properties = feature["properties"]
    starts, ends = (parse_utc(moment) for moment in feature["when"]["interval"])
    kind = properties["awareness_type"].split(";")[1].strip().lower()  # "1; Wind" -> "wind"
    return Alert(
        name=properties["eventAwarenessName"],
        kind=kind,
        starts=starts,
        ends=ends,
        instruction=properties.get("instruction", "").strip(),
    )


def covers(geometry: dict, lon: float, lat: float) -> bool:
    """Whether the point lies in the coords from forecast"""
    if geometry["type"] == "Polygon":
        polygons = [geometry["coordinates"]]
    else:
        polygons = geometry["coordinates"]
    for outer, *holes in polygons:
        if inside(outer, lon, lat) and not any(inside(hole, lon, lat) for hole in holes):
            return True
    return False


def inside(ring: list, lon: float, lat: float) -> bool:
    crossings = 0
    for start, end in zip(ring, ring[1:]):
        lon1, lat1 = start[0], start[1]
        lon2, lat2 = end[0], end[1]
        if (lat1 > lat) != (lat2 > lat):
            crossing_lon = lon1 + (lat - lat1) * (lon2 - lon1) / (lat2 - lat1)
            if lon < crossing_lon:
                crossings += 1
    return crossings % 2 == 1
