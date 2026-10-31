from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Region:
    name: str
    region_id: int
    ssb_county: int # 0 - not applicable
    timezone: ZoneInfo

    def now(self) -> datetime:
        return datetime.now(self.timezone)

    def today(self) -> date:
        return self.now().date()

class Area:
    def __init__(self, latitude, longtitude, id, display_name, region: Region, municipality: str = ""):
        self.latitude = latitude
        self.longtitude = longtitude
        self.id = id
        self.display_name = display_name
        self.region = region
        self.municipality = municipality


# broad areas: a region groups the places sharing a timezone and SSB county
OSLO = Region(name="Oslo", region_id=101, ssb_county=3, timezone=ZoneInfo("Europe/Oslo"))
RIGA = Region(name="Riga", region_id=102, ssb_county=0, timezone=ZoneInfo("Europe/Riga"))
ROGALAND = Region(name="Rogaland", region_id=103, ssb_county=11, timezone=ZoneInfo("Europe/Oslo"))
AKERSHUS = Region(name="Akershus", region_id=104, ssb_county=32, timezone=ZoneInfo("Europe/Oslo"))

# SSB municipality numbers
OSLO_KOMMUNE = "0301"
LILLESTROM = "3205"
BAERUM = "3201"
STAVANGER = "1103"

areas =  {1: Area(59.9325, 10.7613, 1, 'Oslo - Torshov', OSLO, OSLO_KOMMUNE), 
          2: Area(59.9549, 11.0622, 2, 'Lillestrøm', AKERSHUS, LILLESTROM),
          #3: Area(56.96619506296, 24.134153506848776, 3, 'Riga - Centre', RIGA),
          4: Area(59.8731, 10.8089, 4, 'Oslo - Lambertseter', OSLO, OSLO_KOMMUNE),
          5: Area(58.9594, 5.7333, 5, 'Stavanger', ROGALAND, STAVANGER),
          6: Area(59.960171729794176, 10.787701743038276, 6, 'Oslo - Kjelsås', OSLO, OSLO_KOMMUNE),
          7: Area(59.92362, 10.74004, 7, 'Oslo - St.Hanshaugen', OSLO, OSLO_KOMMUNE),
          8: Area(59.9131, 10.7198, 8, 'Oslo - Vika', OSLO, OSLO_KOMMUNE),
          9: Area(59.9192, 10.7091, 9, 'Oslo - Frogner', OSLO, OSLO_KOMMUNE),
          10: Area(59.9621, 10.9234, 10, 'Oslo - Stovner', OSLO, OSLO_KOMMUNE),
          11: Area(59.8948, 10.6217, 11, 'Oslo - Fornebu', AKERSHUS, BAERUM),
          12: Area(59.893003, 10.526977, 12, 'Sandvika', AKERSHUS, BAERUM),
          13: Area(59.950569, 10.644542, 13, 'Oslo - Røa', OSLO, OSLO_KOMMUNE),
          14: Area(59.930, 10.865, 14, 'Oslo - Alna', OSLO, OSLO_KOMMUNE),
          15: Area(59.842, 10.812, 15, 'Oslo - Søndre Nordstrand', OSLO, OSLO_KOMMUNE),
          16: Area(59.963, 10.668, 16, 'Oslo - Holmenkollen', OSLO, OSLO_KOMMUNE)
        }

