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
    def __init__(self, latitude, longtitude, id, display_name, region: Region, municipality: str = "",
                 temporary: bool = False):
        self.latitude = latitude
        self.longtitude = longtitude
        self.id = id
        self.display_name = display_name
        self.region = region
        self.municipality = municipality
        self.temporary = temporary

    def group_and_short_name(self) -> tuple[str, str]:
        group, dash, short_name = self.display_name.partition(" - ")
        return (group, short_name) if dash else (self.region.name, self.display_name)


# broad areas: a region groups the places sharing a timezone and SSB county
OSLO = Region(name="Oslo", region_id=101, ssb_county=3, timezone=ZoneInfo("Europe/Oslo"))
RIGA = Region(name="Riga", region_id=102, ssb_county=0, timezone=ZoneInfo("Europe/Riga"))
ROGALAND = Region(name="Rogaland", region_id=103, ssb_county=11, timezone=ZoneInfo("Europe/Oslo"))
AKERSHUS = Region(name="Akershus", region_id=104, ssb_county=32, timezone=ZoneInfo("Europe/Oslo"))
BUSKERUD = Region(name="Buskerud", region_id=105, ssb_county=33, timezone=ZoneInfo("Europe/Oslo"))
AGDER = Region(name="Agder", region_id=106, ssb_county=42, timezone=ZoneInfo("Europe/Oslo"))
TRONDELAG = Region(name="Trøndelag", region_id=107, ssb_county=50, timezone=ZoneInfo("Europe/Oslo"))
INNLANDET = Region(name="Innlandet", region_id=108, ssb_county=34, timezone=ZoneInfo("Europe/Oslo"))

# SSB municipality numbers
OSLO_KOMMUNE = "0301"
LILLESTROM = "3205"
BAERUM = "3201"
STAVANGER = "1103"
SANDNES = "1108"
DRAMMEN = "3301"
KRISTIANSAND = "4204"
TRONDHEIM = "5001"
EIDSVOLL = "3240"
LORENSKOG = "3222"
NORDRE_FOLLO = "3207"
HAMAR = "3403"

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
          16: Area(59.963, 10.668, 16, 'Oslo - Holmenkollen', OSLO, OSLO_KOMMUNE),
          17: Area(58.8517, 5.7369, 17, 'Sandnes', ROGALAND, SANDNES),
          18: Area(58.948, 5.645, 18, 'Madla', ROGALAND, STAVANGER),
          19: Area(59.744, 10.2045, 19, 'Drammen', BUSKERUD, DRAMMEN),
          20: Area(58.1467, 7.9956, 20, 'Kristiansand', AGDER, KRISTIANSAND),
          21: Area(63.4305, 10.3951, 21, 'Trondheim', TRONDELAG, TRONDHEIM),
          22: Area(60.3305, 11.2615, 22, 'Eidsvoll', AKERSHUS, EIDSVOLL),
          23: Area(60.2755, 11.1795, 23, 'Råholt', AKERSHUS, EIDSVOLL),
          24: Area(59.927, 10.961, 24, 'Lørenskog', AKERSHUS, LORENSKOG),
          25: Area(59.7195, 10.8355, 25, 'Ski', AKERSHUS, NORDRE_FOLLO),
          26: Area(60.7945, 11.068, 26, 'Hamar', INNLANDET, HAMAR)
        }

