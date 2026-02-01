from zoneinfo import ZoneInfo
from dataclasses import dataclass

@dataclass(frozen=True)
class City:
    city_id: int
    timezone: ZoneInfo

class Area:
    def __init__(self, latitude, longtitude, id, display_name, city: City):
        self.latitude = latitude
        self.longtitude = longtitude
        self.id = id
        self.display_name = display_name
        self.city = city


# broad metropolitan areas, f.ex Lillestrøm and Fornebu is still considered Oslo.
OSLO = City(city_id=101, timezone=ZoneInfo("Europe/Oslo"))
RIGA = City(city_id=102, timezone=ZoneInfo("Europe/Riga"))

areas =  {1: Area(59.9325, 10.7613, 1, 'Oslo - Torshov', OSLO), 
          2: Area(59.9029, 10.6302, 2, 'Bærum - Fornebuparken', OSLO),
          3: Area(56.96619506296, 24.134153506848776, 3, 'Riga - quiet centre', RIGA),
          4: Area(59.9253054287, 10.711930759461595, 4, 'Oslo - Frognerparken', OSLO),
          5: Area(59.893646, 10.621711, 5, 'Fornebu', OSLO),
          6: Area(59.960171729794176, 10.787701743038276, 6, 'Oslo - Kjelsås', OSLO)}

