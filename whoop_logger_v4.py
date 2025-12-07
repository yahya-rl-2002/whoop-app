
import asyncio
import sys
import datetime
import yaml # Ajout YAML
from bleak import BleakScanner, BleakClient
from database_manager import DatabaseManager
from gps_tracker import GPSTracker # Ajout GPS

# Chargement de la config
try:
    with open("config.yaml", "r") as f:
        CONFIG = yaml.safe_load(f)
except Exception as e:
    print(f"⚠️ Erreur lecture config.yaml: {e}")
    CONFIG = {"device": {"name_filter": "whoop"}, "user": {"height": 175}}

# UUIDs Standards
HEART_RATE_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL_UUID = "00002a19-0000-1000-8000-00805f9b34fb"

class WhoopLoggerV4:
    def __init__(self):
        # Initialisation DB
        self.db = DatabaseManager()
        self.gps = GPSTracker() # GPS
        self.current_battery = 0
        self.session_id = None
        self.last_gps_coords = None
        
        # Longueur de foulée (Estimation : Taille * 0.415)
        user_height_cm = CONFIG.get('user', {}).get('height', 175)
        self.stride_length_m = (user_height_cm / 100.0) * 0.415

    def start(self):
        # Création d'une nouvelle session en DB
        try:
            self.session_id = self.db.create_session(device_name="Whoop 4.0")
            print(f"🗄️  Session créée en base de données (ID: {self.session_id})")
            self.gps.start()
        except Exception as e:
            print(f"❌ Erreur DB : {e}")
            sys.exit(1)

    def stop(self):
        if self.session_id:
            self.db.end_session(self.session_id)
            print(f"🏁 Session {self.session_id} clôturée.")
            self.gps.stop()

    def battery_handler(self, sender, data: bytearray):
        """Met à jour la variable batterie"""
        level = int(data[0])
        self.current_battery = level
        print(f"🔋 Batterie : {level}%")

    def hr_handler(self, sender, data: bytearray):
        """Gestionnaire principal (activé à chaque battement)"""
        flags = data[0]
        hr_fmt_16 = (flags & 0x01) > 0
        rr_present = (flags & 0x10) > 0
        offset = 1
        
        # Lecture BPM
        if hr_fmt_16:
            hr_val = int.from_bytes(data[offset:offset+2], byteorder='little')
            offset += 2
        else:
            hr_val = data[offset]
            offset += 1
            
        if (flags & 0x08) > 0: offset += 2
            
        # Lecture RR
        rr_intervals = []
        if rr_present:
            while offset + 1 < len(data):
                val = int.from_bytes(data[offset:offset+2], byteorder='little')
                ms = int(val * 1000 / 1024)
                if ms > 0: rr_intervals.append(ms)
                offset += 2

        # Estimation Pas V3 (Hybride : GPS + Cardio)
        steps_increment = 0
        
        # 1. Essai GPS (Prioritaire pour la distance réelle)
        current_loc = self.gps.get_current_location()
        gps_distance = 0
        if self.last_gps_coords and current_loc:
            gps_distance = self.gps.calculate_distance(self.last_gps_coords, current_loc)
        
        # Mise à jour coordonnées (si valide)
        if current_loc: self.last_gps_coords = current_loc
        
        # Si on a parcouru une distance significative (> 5m pour filtrer le jitter GPS)
        # On ne veut pas compter des pas si on est assis dans un train (vitesse trop grande ?)
        # Ici on fait simple : Distance / Foulée
        if gps_distance > 5.0:
            gps_steps = int(gps_distance / self.stride_length_m)
            steps_increment = gps_steps
            # print(f"📍 GPS Mouvement: {gps_distance:.1f}m -> {gps_steps} pas")
        else:
            # 2. Fallback Cardio (Tapis de course / Intérieur)
            # On augmente le seuil pour éviter les faux positifs assis
            # Marche active commence souvent > 90-100 BPM
            rest_hr = CONFIG['user'].get('rest_hr', 50)
            move_threshold = rest_hr + 40 # Seuil plus strict (ex: 90 bpm) 
            
            if hr_val > move_threshold:
                 cadence_min = 60
                 estimated_cadence = cadence_min + (hr_val - move_threshold) * 1.2
                 if estimated_cadence > 200: estimated_cadence = 200
                 
                 steps_per_sec = estimated_cadence / 60.0
                 steps_increment = int(steps_per_sec) 
                 if steps_per_sec > 0.5 and steps_increment == 0: steps_increment = 1

        # Enregistrement en DB
        if hr_val > 0 and self.session_id:
            rr_str = ";".join(map(str, rr_intervals))
            
            try:
                self.db.insert_measurement(
                    session_id=self.session_id,
                    bpm=hr_val,
                    rr_str=rr_str,
                    battery=self.current_battery,
                    steps=steps_increment
                )
            except Exception as e:
                print(f"⚠️ Erreur insert DB: {e}")

async def run():
    logger = WhoopLoggerV4()
    logger.start()
    
    print(f"🔍 Recherche du Whoop (Filtre: '{CONFIG['device']['name_filter']}')...")
    target = None
    stop_event = asyncio.Event()

    def detection_callback(dev, adv):
        nonlocal target
        # Utilisation du nom défini dans la config
        target_name_filter = CONFIG['device']['name_filter'].lower()
        if dev.name and target_name_filter in dev.name.lower():
            target = dev
            stop_event.set()

    scanner = BleakScanner(detection_callback)
    await scanner.start()
    try: await asyncio.wait_for(stop_event.wait(), timeout=10.0)
    except asyncio.TimeoutError: pass
    await scanner.stop()

    if not target:
        print("❌ Introuvable.")
        return

    print(f"🔗 Connexion à {target.name}...")
    try:
        async with BleakClient(target) as client:
            if client.is_connected:
                print("✅ Connecté ! Enregistrement SQL actif.")
                
                # Batterie
                try:
                    await client.start_notify(BATTERY_LEVEL_UUID, logger.battery_handler)
                    # Lecture initiale forcée
                    batt = await client.read_gatt_char(BATTERY_LEVEL_UUID)
                    logger.current_battery = int(batt[0])
                except: pass

                # Heart Rate
                await client.start_notify(HEART_RATE_UUID, logger.hr_handler)
                
                while True: await asyncio.sleep(1)
    except Exception as e:
        print(f"Erreur: {e}")
    finally:
        logger.stop()

if __name__ == "__main__":
    try: asyncio.run(run())
    except KeyboardInterrupt: pass
