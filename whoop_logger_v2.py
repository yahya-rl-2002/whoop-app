import asyncio
import sys
import csv
import datetime
from bleak import BleakScanner, BleakClient
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

# UUID Standard pour le service de fréquence cardiaque
HEART_RATE_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"

class WhoopLoggerV2:
    def __init__(self):
        # Nom de fichier avec timestamp
        now = datetime.datetime.now()
        self.filename = f"whoop_session_{now.strftime('%Y-%m-%d_%H-%M-%S')}.csv"
        self.file = None
        self.writer = None

    def start(self):
        try:
            self.file = open(self.filename, mode='w', newline='', encoding='utf-8')
            self.writer = csv.writer(self.file)
            
            # NOUVEAU : On ajoute une colonne "RR_Intervals"
            headers = ["Timestamp", "BPM", "RR_Intervals"]
            self.writer.writerow(headers)
            self.file.flush()
            print(f"📁 Fichier HRV créé : {self.filename}")
        except IOError as e:
            print(f"❌ Erreur fichier : {e}")
            sys.exit(1)

    def stop(self):
        if self.file:
            self.file.close()
            print(f"📁 Fichier {self.filename} fermé.")

    def notification_handler(self, sender, data: bytearray):
        """Décodage complet (BPM + HRV)"""
        flags = data[0]
        
        # Analyse des bits pour savoir ce que contient le paquet
        hr_format_uint16 = (flags & 0x01) > 0
        rr_present = (flags & 0x10) > 0
        
        offset = 1
        
        # 1. Lecture BPM
        if hr_format_uint16:
            hr_value = int.from_bytes(data[offset:offset+2], byteorder='little')
            offset += 2
        else:
            hr_value = data[offset]
            offset += 1
            
        # S'il y a des données "Energy Expended", on les saute (2 octets)
        if (flags & 0x08) > 0:
            offset += 2
            
        # 2. Lecture RR-Intervals (La pépite !)
        rr_intervals = []
        if rr_present:
            while offset + 1 < len(data): # +1 pour éviter débordement
                rr_val_raw = int.from_bytes(data[offset:offset+2], byteorder='little')
                # Conversion standard BLE : raw * 1000 / 1024 pour avoir des ms
                rr_ms = int(rr_val_raw * 1000 / 1024)
                if rr_ms > 0: # On ignore les 0 parasites
                    rr_intervals.append(rr_ms)
                offset += 2

        # 3. Filtrage intelligent (Anti-Bruit)
        # On n'enregistre que si on a un pouls valide OU des données RR valides
        if hr_value > 0 or len(rr_intervals) > 0:
            current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            
            # Formatage des RR pour le CSV (séparés par des points-virgules)
            rr_str = ";".join(map(str, rr_intervals))
            
            # Affichage console enrichi
            rr_display = f" | HRV data: {rr_intervals}" if rr_intervals else ""
            print(f"❤️ {hr_value} BPM{rr_display}")

            if self.writer:
                try:
                    self.writer.writerow([current_time, hr_value, rr_str])
                    self.file.flush()
                except IOError:
                    pass

async def run():
    logger = WhoopLoggerV2()
    logger.start()

    print("🔍 Recherche du Whoop (Mode VFC)...")
    target_device = None
    stop_event = asyncio.Event()

    def detection_callback(device, advertisement_data):
        nonlocal target_device
        if device.name and "whoop" in device.name.lower():
            target_device = device
            stop_event.set()

    scanner = BleakScanner(detection_callback)
    
    try:
        await scanner.start()
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            pass
        await scanner.stop()

        if not target_device:
            print("⚠️ Whoop introuvable.")
            return

        print(f"🔗 Connexion à {target_device.name}...")
        async with BleakClient(target_device) as client:
            if not client.is_connected:
                print("❌ Échec connexion.")
                return
            
            print("✅ Connecté ! Enregistrement haute précision actif.")
            await client.start_notify(HEART_RATE_MEASUREMENT_UUID, logger.notification_handler)
            
            while True:
                await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("\n👋 Fin de session.")
    except Exception as e:
        print(f"❌ Erreur : {e}")
    finally:
        logger.stop()

if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass