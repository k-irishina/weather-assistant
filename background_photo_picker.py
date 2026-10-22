import calendar
import random
from datetime import datetime, time
from typing import NamedTuple, Optional

DAY_PARTS = ("morning", "day", "sunset", "evening", "night")
CONDITION_WORDS = ("sunny", "clear", "cloudy", "fog", "rain", "heavyrain", "snow", "heavysnow")
PHOTO_EXTENSIONS = ("jpg", "jpeg", "png", "webp")

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
    # sleet counts as snow for now
    if "sleet" in base:
        return [("snow",)]
    if "snow" in base:
        return [("heavysnow",), ("snow",)] if base.startswith("heavy") else [("snow",)]
    if base == "rain" or base.startswith("lightrain"):
        return [("rain",)]
    if base.startswith(("heavyrain", "rainshowers", "rainandthunder")):
        return [("heavyrain",), ("rain",), ("",)]
    return [("",)]


def day_part(now: time, sunrise: time, sunset: time) -> str:
    # evening the 2 hours before sunset, night 30 min before&after sunrise/sunset
    now = now.hour * 60 + now.minute
    sunrise = sunrise.hour * 60 + sunrise.minute
    sunset = sunset.hour * 60 + sunset.minute
    if now >= sunset + 30 or now < sunrise - 30:
        return "night"
    if now >= sunset - 45:
        return "sunset"
    if now >= sunset - 120:
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


def pick_photo(names: dict[str, str], symbol_code: str, local_now: datetime, sunrise: time, sunset: time) -> Optional[str]:
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

    for folder in folders:
        for group in condition_groups:
            doesfit = [
                photo.name for photo in photos
                if (photo.folder == folder or (photo.folder == "common" and folder != "night"))
                and (photo.part == part or (photo.part is None and part != "sunset"))
                # for now, sunset photos fit any weather
                and (part == "sunset" or fits_weather_conditions(photo, group))
            ]
            if doesfit:
                return random.choice(doesfit)
    return None
