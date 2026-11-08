import logging
from typing import NamedTuple, Optional

import requests

import app_config

log = logging.getLogger(__name__)


class Place(NamedTuple):
    name: str
    municipality: str  # SSB number, f.ex "3207"
    county: int  # SSB number, f.ex 32
    county_name: str


def _get_json(url: str, params: dict) -> Optional[dict]:
    headers = {'User-Agent': app_config.met_api['user-agent-header']}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
    except requests.RequestException as error:
        log.error("Could not reach %s: %s", url, error)
        return None
    # 404 means nothing at this point, f.ex outside Norway
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        log.error("%s returned %s", response.url, response.status_code)
        return None
    try:
        data = response.json()
    except requests.exceptions.JSONDecodeError:
        log.error("%s sent invalid JSON: %r", response.url, response.text[:300])
        return None
    if not isinstance(data, dict):
        log.error("%s sent an unexpected answer: %r", response.url, str(data)[:300])
        return None
    return data


def place_for(latitude: float, longitude: float) -> Optional[Place]:
    point = {'nord': latitude, 'ost': longitude, 'koordsys': 4258}
    municipality = _get_json("https://api.kartverket.no/kommuneinfo/v1/punkt", point)
    if not municipality or "kommunenummer" not in municipality:
        return None

    # the nearest town or district within 1.5 km; the closest names are usually streets
    names = _get_json("https://api.kartverket.no/stedsnavn/v1/punkt", {**point, 'radius': 1500, 'treffPerSide': 500})
    towns = [
        entry for entry in (names or {}).get("navn", [])
        if entry.get("navneobjekttype") in ("By", "Tettsted", "Tettsteddel", "Bydel", "Tettbebyggelse")
        and entry.get("stedsnavn")
    ]
    nearest_town = min(towns, key=lambda entry: entry.get("meterFraPunkt", 0), default=None)
    name = nearest_town["stedsnavn"][0]["skrivemåte"] if nearest_town else municipality["kommunenavn"]

    return Place(
        name=name,
        municipality=municipality["kommunenummer"],
        county=int(municipality["fylkesnummer"]),
        county_name=municipality["fylkesnavn"],
    )
