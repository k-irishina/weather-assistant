import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

import requests

import app_config
import area
from met_alerts import Alert

log = logging.getLogger(__name__)

_fetched: dict[tuple[str, str], tuple] = {}

def get_warnings(kind: str, municipality: str) -> Optional[list]:
    url = f"https://api01.nve.no/hydrology/forecast/{kind}/v1.0.10/api/Warning/Municipality/{municipality}/2"
    headers = {"User-Agent": app_config.met_api["user-agent-header"], "Accept": "application/json"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
    except requests.RequestException:
        log.warning("NVE %s warnings could not be fetched", kind, exc_info=True)
        return None
    if response.status_code != 200:
        log.warning("NVE %s warnings returned %s", kind, response.status_code)
        return None
    return response.json()


def warnings_for(area_obj: area.Area, day: date) -> list[Alert]:
    if not area_obj.municipality:
        return []
    today = area_obj.region.today()
    day_start = datetime.combine(day, time.min, tzinfo=area_obj.region.timezone)
    day_end = day_start + timedelta(days=1)
    not_before = max(day_start, datetime.now(timezone.utc))

    alerts = []
    for kind in ("flood", "landslide"):
        key = (kind, area_obj.municipality)
        if key not in _fetched or _fetched[key][0] != today:
            warnings = get_warnings(kind, area_obj.municipality)
            if warnings is None:
                continue
            _fetched[key] = (today, warnings)

        for warning in _fetched[key][1]:
            color = {2: "yellow", 3: "orange", 4: "red"}.get(int(warning["ActivityLevel"]))
            if color is None:
                continue
            starts = datetime.fromisoformat(warning["ValidFrom"]).replace(tzinfo=area.OSLO.timezone)
            ends = datetime.fromisoformat(warning["ValidTo"]).replace(tzinfo=area.OSLO.timezone)
            if starts < day_end and ends > not_before:
                alerts.append(Alert(
                    name=warning["DangerTypeName"],
                    kind=kind,
                    event=kind,
                    color=color,
                    severity={"yellow": "Moderate", "orange": "Severe", "red": "Extreme"}[color],
                    starts=starts.astimezone(timezone.utc),
                    ends=ends.astimezone(timezone.utc),
                    instruction=warning["AdviceText"] or "",
                ))
    return alerts
