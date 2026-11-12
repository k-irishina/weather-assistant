import calendar
import logging
import random
import re
from datetime import datetime, time
from typing import NamedTuple, Optional

DAY_PARTS = ("morning", "day", "sunset", "evening", "night")
CONDITION_WORDS = ("sunny", "clear", "cloudy", "fog", "rain", "heavyrain", "sleet", "snow", "heavysnow")
PHOTO_EXTENSIONS = ("jpg", "jpeg", "png", "webp")

log = logging.getLogger(__name__)


class Photo(NamedTuple):
    name: str
    folder: str
    part: Optional[str]
    conditions: tuple[str, ...]


def photo_conditions(base: str) -> list[tuple]:
    # "" is a generic month photo
    if base == "clearsky":
        return [("sunny", "clear")]
    if base == "fair":
        return [("sunny", "clear", "")]
    if base in ("partlycloudy", "cloudy"):
        return [("cloudy", "")]
    if base == "fog":
        return [("fog",)]
    if "sleet" in base:
        return [("sleet",), ("snow",)]
    if "snow" in base:
        return [("heavysnow",), ("snow",)] if base.startswith("heavy") else [("snow",)]
    if base == "rain" or base.startswith("lightrain"):
        return [("rain",)]
    if base.startswith(("heavyrain", "rainshowers", "rainandthunder")):
        return [("heavyrain",), ("rain",), ("",)]
    return [("",)]


def day_part(now: time, sunrise: time, sunset: time) -> str:
    # evening the 2 hours before sunset (not before 17:30, night 30 min before&after sunrise/sunset
    now = now.hour * 60 + now.minute
    sunrise = sunrise.hour * 60 + sunrise.minute
    sunset = sunset.hour * 60 + sunset.minute
    if now >= sunset + 30 or now < sunrise - 30:
        return "night"
    if now >= sunset - 45:
        return "sunset"
    if now >= max(sunset - 120, 17 * 60 + 30):
        return "evening"
    if now < 11 * 60:
        return "morning"
    return "day"


def photo_info(filename: str) -> Optional[Photo]:
    folder, slash, file_name = filename.lower().partition("/")
    stem, dot, extension = file_name.rpartition(".")
    if not slash or extension not in PHOTO_EXTENSIONS:
        return None
    description_words = stem.split("-")
    day_part = next((word for word in description_words if word in DAY_PARTS), None)
    conditions = tuple(word for word in description_words if word in CONDITION_WORDS)
    return Photo(filename, folder, day_part, conditions)


def fits_weather_conditions(photo: Photo, group: tuple) -> bool:
    return any(
        not photo.conditions if condition == "" else condition in photo.conditions
        for condition in group
    )


def pick_photo(
    names: dict[str, str], symbol_code: str, local_now: datetime, sunrise: time, sunset: time,
    current: Optional[str] = None,
) -> Optional[str]:
    basecondition = symbol_code.partition("_")[0]
    part = day_part(local_now.time(), sunrise, sunset)
    # so rain photos win over the sunset ones
    if part == "sunset" and "rain" in basecondition:
        part = "evening"
    condition_groups = photo_conditions(basecondition)
    if part == "night":
        # night photos without conditions fit everything
        condition_groups = [(*group, "") for group in condition_groups]

    photos = [photo for photo in map(photo_info, names) if photo]
    month = calendar.month_name[local_now.month].lower()
    other_months = {photo.folder for photo in photos} - {month, "night", "common"}
    folders = ["night"] if part == "night" else [month, *other_months]
    # if nothing fits: day photos of the same weather, then any time of day; no daylight photos at night
    parts_to_try = [part] if part == "night" else [part, "day", None]

    for wanted_part in parts_to_try:
        for folder in folders:
            for group in condition_groups:
                doesfit = [
                    photo.name for photo in photos
                    if (photo.folder == folder or (photo.folder == "common" and folder != "night"))
                    and (wanted_part is None or photo.part == wanted_part or (photo.part is None and wanted_part != "sunset"))
                    # for now, sunset photos fit any weather
                    and (wanted_part == "sunset" or fits_weather_conditions(photo, group))
                ]
                if current in doesfit:
                    return current
                if doesfit:
                    return random.choice(doesfit)
    return None



def relative_luminance(hex_colour: str) -> float:
    channels = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def readable_colours(colours, background: str, photo_name: str) -> Optional[list[str]]:
    if colours is None:
        return None
    valid = isinstance(colours, list) and len(colours) == 2 and all(
        isinstance(colour, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", colour) for colour in colours)
    if not valid:
        log.warning("Accent for %s should be two colours like [\"#3b5a8c\", \"#8a4f9e\"]: %r", photo_name, colours)
        return None
    for colour in colours:
        lighter, darker = sorted((relative_luminance(colour), relative_luminance(background)), reverse=True)
        contrast = (lighter + 0.05) / (darker + 0.05)
        if contrast < 4.5:
            log.warning("Accent %s for %s is hard to read on %s with contrast %.1f - need 4.5",
                        colour, photo_name, background, contrast)
            return None
    return colours
