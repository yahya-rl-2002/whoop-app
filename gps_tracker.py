import math
import time

HAS_GPS = False
try:
    from CoreLocation import CLLocationManager, kCLLocationAccuracyBest, kCLDistanceFilterNone
    from PyObjCTools import AppHelper
    from Foundation import NSObject
    HAS_GPS = True
except ImportError:
    print("⚠️ Module CoreLocation introuvable. Le GPS sera désactivé.")
    # On définit des mocks pour éviter NameError dans la classe
    NSObject = object
    CLLocationManager = None

class GPSHandler(NSObject):
    def init(self):
        self = super(GPSHandler, self).init()
        self.coordinates = None
        self.last_update = time.time()
        return self
        
    def locationManager_didUpdateLocations_(self, manager, locations):
        loc = locations[-1]
        self.coordinates = (loc.coordinate().latitude, loc.coordinate().longitude)
        self.last_update = time.time()

class GPSTracker:
    def __init__(self):
        self.running = False
        self.start_coords = None
        self.total_distance = 0.0
        self.last_coords = None
        self.manager = None
        self.handler = None

        if HAS_GPS:
            try:
                self.handler = GPSHandler.alloc().init()
                self.manager = CLLocationManager.alloc().init()
                self.manager.setDelegate_(self.handler)
                self.manager.setDesiredAccuracy_(kCLLocationAccuracyBest)
                self.manager.setDistanceFilter_(kCLDistanceFilterNone)
            except Exception as e:
                print(f"⚠️ Erreur init GPS: {e}")
                
    def start(self):
        if self.manager and HAS_GPS:
            self.manager.startUpdatingLocation()
            self.running = True
            print("📡 GPS Tracker Démarré")
        else:
            print("📡 GPS Indisponible (Simulation Off)")

    def stop(self):
        if self.manager and HAS_GPS:
            self.manager.stopUpdatingLocation()
            self.running = False
            print("📡 GPS Tracker Arrêté")

    def get_current_location(self):
        """Retourne (lat, lon) ou None. Requis par whoop_logger."""
        if not self.handler or not HAS_GPS:
            return None
        return self.handler.coordinates
            
    def get_distance(self):
        if not self.running or not self.handler or not HAS_GPS:
            return 0.0
            
        coords = self.handler.coordinates
        if not coords: return self.total_distance
        
        if self.last_coords:
            dist = self.haversine(self.last_coords, coords)
            # Filtre bruit GPS (< 2m)
            if dist > 2.0:
                self.total_distance += dist
                self.last_coords = coords
        else:
            self.last_coords = coords
            
        return self.total_distance

    def haversine(self, prev_loc, curr_loc):
        """Haversine formula pour distance en mètres"""
        if not prev_loc or not curr_loc:
            return 0
        
        lat1, lon1 = prev_loc
        lat2, lon2 = curr_loc
        
        R = 6371000 # Rayon Terre (m)
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)

        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2) * math.sin(dlambda/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

        return R * c
