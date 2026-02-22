from dataclasses import dataclass
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Region:
    region_id: int
    timezone: ZoneInfo

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
          2: Area(59.8344, 10.43521, 2, 'Asker sentrum', OSLO),
          3: Area(56.96619506296, 24.134153506848776, 3, 'Riga - Centre', RIGA),
          4: Area(59.9253054287, 10.711930759461595, 4, 'Oslo - Frognerparken', OSLO),
          5: Area(59.893646, 10.621711, 5, 'Fornebu', OSLO),
          6: Area(59.960171729794176, 10.787701743038276, 6, 'Oslo - Kjelsås', OSLO)}

