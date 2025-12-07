import asyncio
import sys
import csv
import datetime
import os
from bleak import BleakScanner, BleakClient

# UUIDs Standards
HEART_RATE_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL_UUID = "00002a19-0000-1000-8000-00805f9b34fb"

class WhoopLoggerV4:
    def __init__(self):
        if not os.path.exists('data'):
            os.makedirs('data')
            
        now = datetime.datetime.now()
        self.filename = f"data/session_{now.strftime('%Y-%m-%d_%H-%M-%S')}.csv"
        self.file = None
        self.writer = None
        self.current_battery = 0 # Stocke le niveau actuel

    def start(self):
        try:
            self.file = open(self.filename, mode='w', newline='', encoding='utf-8')
            self.writer = csv.writer(self.file)
            # Ajout de la colonne "Battery"
            self.writer.writerow(["Timestamp", "BPM", "RR_Intervals", "Battery"])
            self.file.flush()
            print(f"💾 Enregistrement V4 (avec Batterie) : {self.filename}")
        except IOError as e:
            print(f"❌ Erreur fichier : {e}")
            sys.exit(1)

    def stop(self):
        if self.file:
            self.file.close()
            print(f"📁 Fichier fermé.")

    def battery_handler(self, sender, data: bytearray):
        """Met à jour la variable batterie quand le niveau change"""
        level = int(data[0])
        self.current_battery = level
        print(f"🔋 Batterie mise à jour : {level}%")

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

        # Enregistrement (Si BPM valide)
        if hr_val > 0:
            timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            rr_str = ";".join(map(str, rr_intervals))
            
            # On écrit la dernière valeur de batterie connue
            if self.writer:
                try:
                    self.writer.writerow([timestamp, hr_val, rr_str, self.current_battery])
                    self.file.flush()
                except: pass
            
            # Affichage console (optionnel pour ne pas spammer)
            # print(f"❤️ {hr_val} | 🔋 {self.current_battery}%", end="\r")

async def run():
    logger = WhoopLoggerV4()
    logger.start()
    
    print("🔍 Recherche du Whoop...")
    target = None
    stop_event = asyncio.Event()

    def detection_callback(dev, adv):
        nonlocal target
        if dev.name and "whoop" in dev.name.lower():
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
                print("✅ Connecté ! Lecture BPM + Batterie...")
                
                # 1. Lecture initiale de la batterie
                try:
                    batt_bytes = await client.read_gatt_char(BATTERY_LEVEL_UUID)
                    logger.current_battery = int(batt_bytes[0])
                    print(f"🔋 Niveau initial : {logger.current_battery}%")
                except:
                    print("⚠️ Impossible de lire la batterie initiale.")

                # 2. Abonnement aux mises à jour batterie (Notification)
                try:
                    await client.start_notify(BATTERY_LEVEL_UUID, logger.battery_handler)
                except:
                    print("⚠️ Notifications batterie non supportées, seule la valeur initiale sera utilisée.")

                # 3. Abonnement cardiaque (Le flux principal)
                await client.start_notify(HEART_RATE_UUID, logger.hr_handler)
                
                while True: await asyncio.sleep(1)
    except Exception as e:
        print(f"Erreur: {e}")
    finally:
        logger.stop()

if __name__ == "__main__":
    try: asyncio.run(run())
    except KeyboardInterrupt: pass