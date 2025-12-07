
import asyncio
import sys
from bleak import BleakScanner, BleakClient
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

# UUID Standard Heart Rate
HEART_RATE_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"

def rr_notification_handler(sender, data: bytearray):
    """
    Callback avancé pour analyser les flags et extraire les RR-Intervals.
    """
    flags = data[0]
    
    # Analyse des bits
    hr_format_uint16 = (flags & 0x01) > 0       # Bit 0
    energy_present = (flags & 0x08) > 0         # Bit 3
    rr_present = (flags & 0x10) > 0             # Bit 4 (0x10 = 16)
    
    # Calcul de l'offset pour sauter les données déjà connues
    offset = 1 # On a lu le flag
    
    # Lecture de la HR
    if hr_format_uint16:
        hr_val = int.from_bytes(data[offset:offset+2], byteorder='little')
        offset += 2
    else:
        hr_val = data[offset]
        offset += 1
        
    # Skip Energy Expended si présent
    if energy_present:
        offset += 2
        
    # Vérification RR-Intervals
    if rr_present:
        rr_intervals = []
        # On lit tant qu'il reste des données
        while offset < len(data):
            # Les RR-Intervals sont toujours uint16 (résolution 1/1024 seconde)
            if offset + 2 <= len(data):
                rr_val = int.from_bytes(data[offset:offset+2], byteorder='little')
                # Conversion en millisecondes pour affichage (val * 1000 / 1024)
                rr_ms = int(rr_val * 1000 / 1024)
                rr_intervals.append(rr_ms)
                offset += 2
            else:
                break
                
        print(f"❤️ BPM: {hr_val} | ✅ RR-Intervals détectés : {rr_intervals} ms")
    else:
        print(f"❤️ BPM: {hr_val} | ❌ Pas de RR-Intervals (Bit 4 = 0)")

async def run_test():
    print("🔍 TEST RR-INTERVALS - Scan en cours...")
    
    target_device = None
    stop_scan_event = asyncio.Event()

    def detection_callback(device, advertisement_data):
        nonlocal target_device
        if device.name and "whoop" in device.name.lower():
            target_device = device
            stop_scan_event.set()

    scanner = BleakScanner(detection_callback)
    await scanner.start()
    
    try:
        await asyncio.wait_for(stop_scan_event.wait(), timeout=10.0)
    except asyncio.TimeoutError:
        print("❌ Timeout scan : Whoop non trouvé.")
        return

    await scanner.stop()
    print(f"🔗 Connexion à {target_device.name} pour 10 secondes de test...")

    async with BleakClient(target_device) as client:
        if not client.is_connected:
            print("❌ Echec connexion.")
            return

        print("✅ Connecté. Analyse des paquets en cours...")
        await client.start_notify(HEART_RATE_MEASUREMENT_UUID, rr_notification_handler)
        
        # On écoute pendant 10 secondes
        for i in range(10):
            await asyncio.sleep(1)
            print(f"   ⏱️ {10-i}s...", end="\r")
        
        print("\n🏁 Fin du test.")

if __name__ == "__main__":
    try:
        asyncio.run(run_test())
    except KeyboardInterrupt:
        pass
