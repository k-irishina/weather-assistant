class Area:
    def __init__(self, latitude, longtitude, db_int, human_name):
        self.latitude = latitude
        self.longtitude = longtitude
        self.db_int = db_int
        self.human_name = human_name

# deprecated, avoid using!
cities = {'oslo_lower_torshov': Area(59.9325, 10.7613, 1, 'Oslo - lower Torshov'), 
          'baerum_fornebuparken': Area(59.9029, 10.6302, 2, 'Bærum - Fornebuparken'),
          'riga_quiet_centre': Area(56.96619506296441, 24.134153506848776, 3, 'Riga - quiet centre'),
          'oslo_frognerparken': Area(59.92530542866893, 10.711930759461595, 4, 'Oslo - Frognerparken'),
          'hovik_verk': Area(59.8932496990082, 10.568069863801814, 5, 'Høvik Verk'),
          'oslo_kjelsas': Area(59.960171729794176, 10.787701743038276, 6, 'Oslo - Kjelsås')}

cities2 = {1: Area(59.9325, 10.7613, 1, 'Oslo - lower Torshov'), 
           2: Area(59.9029, 10.6302, 2, 'Bærum - Fornebuparken'),
           3: Area(56.96619506296441, 24.134153506848776, 3, 'Riga - quiet centre'),
           4: Area(59.92530542866893, 10.711930759461595, 4, 'Oslo - Frognerparken'),
           5: Area(59.8932496990082, 10.568069863801814, 5, 'Høvik Verk'),
           6: Area(59.960171729794176, 10.787701743038276, 6, 'Oslo - Kjelsås')}