import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import area
import db_connector as db
import kartverket
import web_push

log = logging.getLogger(__name__)


def temporary_area(requested: db.RequestedArea) -> area.Area:
    region = area.Region(
        name=requested.county_name, region_id=requested.area_id, ssb_county=0, timezone=ZoneInfo("Europe/Oslo"),
    )
    return area.Area(
        requested.latitude, requested.longitude, requested.area_id, requested.display_name, region, temporary=True,
    )


def area_py_line(requested: db.RequestedArea) -> str:
    # the line to paste into area.py, with the region constant for the county when there is one
    region_name = next(
        (name for name, value in vars(area).items() if isinstance(value, area.Region) and value.ssb_county == requested.county),
        f"NEW_REGION_FOR_{requested.county_name.upper()}",
    )
    display_name = f"Oslo - {requested.display_name}" if requested.municipality == "0301" else requested.display_name
    return (
        f'{requested.area_id}: Area({requested.latitude}, {requested.longitude}, {requested.area_id}, '
        f'\'{display_name}\', {region_name}, "{requested.municipality}"),'
    )


def load_and_promote() -> None:
    # at startup temporary areas join area.areas
    for requested in db.requested_areas():
        if requested.area_id in area.areas:
            promoted = area.areas[requested.area_id]
            short_name = promoted.group_and_short_name()[1]
            web_push.send_to_area(
                promoted,
                f"{short_name} is fully supported",
                "Rain alerts, the two-hour rain chart and weather warnings are now on.",
                tag="location-supported",
            )
            db.delete_requested_area(requested.area_id)
            log.info("Requested area %s is now in area.py", requested.area_id)
        if requested.area_id not in area.areas:
            area.areas[requested.area_id] = temporary_area(requested)


def add(latitude: float, longitude: float) -> Optional[area.Area]:
    added_today = db.requested_areas_added_since(datetime.now(timezone.utc) - timedelta(days=1))
    if added_today >= 10:
        web_push.send_to_admins("Location requested", f"Not added, 10 a day reached: {latitude}, {longitude}")
        return None

    place = kartverket.place_for(latitude, longitude)
    if place is None:
        web_push.send_to_admins("Location requested", f"Not added, outside Norway or Kartverket unavailable: {latitude}, {longitude}")
        return None

    requested = db.add_requested_area(latitude, longitude, place.name, place.municipality, place.county, place.county_name)
    new_area = temporary_area(requested)
    area.areas[requested.area_id] = new_area
    web_push.send_to_admins(f'Requested area "{place.name}" added', area_py_line(requested))
    log.info("Added requested area %s: %s", requested.area_id, place.name)
    return new_area
