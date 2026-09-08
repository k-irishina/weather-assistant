from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Region:
    region_id: int
    timezone: ZoneInfo

    def now(self) -> datetime:
        return datetime.now(self.timezone)

    def today(self) -> date:
        return self.now().date()

class Area:
    def __init__(self, latitude, longtitude, id, display_name, region: Region):
        self.latitude = latitude
        self.longtitude = longtitude
        self.id = id
        self.display_name = display_name
        self.region = region


# broad areas, f.ex Asker and Fornebu is still considered Oslo
OSLO = Region(region_id=101, timezone=ZoneInfo("Europe/Oslo"))
RIGA = Region(region_id=102, timezone=ZoneInfo("Europe/Riga"))

areas =  {1: Area(59.9325, 10.7613, 1, 'Oslo - Torshov', OSLO), 
          2: Area(59.9549, 11.0622, 2, 'Lillestrøm', OSLO),
          3: Area(56.96619506296, 24.134153506848776, 3, 'Riga - Centre', RIGA),
          4: Area(59.8731, 10.8089, 4, 'Oslo - Lambertseter', OSLO),
          6: Area(59.960171729794176, 10.787701743038276, 6, 'Oslo - Kjelsås', OSLO)}

