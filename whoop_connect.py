
import asyncio
import sys
from bleak import BleakScanner, BleakClient
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

# UUID Standard pour le service de fréquence cardiaque (Heart Rate Service)
# UUID complet: 0000180d-0000-1000-8000-00805f9b34fb mais on écoute la caractéristique Heart Rate Measurement
HEART_RATE_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"

def notification_handler(sender, data: bytearray):
    """
    Callback déclenché à chaque réception de notification de fréquence cardiaque.
    Décode les données selon le standard BLE Heart Rate Measurement.
    """
    # Le premier octet contient les flags
    flags = data[0]
    
    # Vérification du format de la valeur de fréquence cardiaque (Bit 0)
    # 0 = UINT8 (1 octet), 1 = UINT16 (2 octets)
    hr_format_uint16 = flags & 0x01
    
    if hr_format_uint16:
        # Format UINT16: On lit les octets 1 et 2 (Little Endian)
        hr_value = int.from_bytes(data[1:3], byteorder='little')
        # info_offset sert si on voulait lire d'autres données après (Energy Expended, RR-Intervals...)
        # info_offset = 3 
    else:
        # Format UINT8: On lit l'octet 1
        hr_value = data[1]
        # info_offset = 2

    # Affichage joli dans la console
    print(f"❤️ BPM: {hr_value}")

async def run():
    print("🔍 Démarrage du scan Bluetooth...")
    print("   Recherche d'un appareil contenant 'Whoop'...")

    target_device: BLEDevice | None = None

    # Etape 1: Scan intelligent
    # Nous utilisons un callback de détection pour arrêter le scan dès qu'on trouve le device
    stop_event = asyncio.Event()

    def detection_callback(device: BLEDevice, advertisement_data: AdvertisementData):
        nonlocal target_device
        # Vérification si le nom du device existe et contient "Whoop" (insensible à la casse)
        if device.name and "whoop" in device.name.lower():
            print(f"✅ Appareil trouvé : {device.name} ({device.address})")
            target_device = device
            stop_event.set()

    scanner = BleakScanner(detection_callback)
    
    try:
        await scanner.start()
        # On scanne pendant max 10 secondes ou jusqu'à ce que stop_event soit activé
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            pass # Le timeout est géré après
        
        await scanner.stop()

    except Exception as e:
        print(f"❌ Erreur lors du scan: {e}")
        return

    # Etape 2: Gestion d'erreur si non trouvé
    if not target_device:
        print("\n⚠️  Aucun appareil 'Whoop' n'a été trouvé.")
        print("   Assurez-vous que :")
        print("   1. Le mode 'Diffusion de la fréquence cardiaque' est ACTIVÉ dans l'app Whoop.")
        print("   2. Le bracelet est chargé et à proximité.")
        print("   3. Le Bluetooth de votre ordinateur est activé.")
        return

    # Etape 3: Connexion et Abonnement
    print(f"🔗 Connexion à {target_device.name}...")
    
    try:
        async with BleakClient(target_device) as client:
            if not client.is_connected:
                print("❌ Échec de la connexion.")
                return
            
            print(f"✅ Connecté ! Abonnement au service Heart Rate...")
            
            # Abonnement aux notifications sur la caractéristique Heart Rate Measurement
            await client.start_notify(HEART_RATE_MEASUREMENT_UUID, notification_handler)
            
            print("📡 Lecture du flux en temps réel. Maintien de la connexion... (Ctrl+C pour arrêter)")
            
            # Boucle infinie pour maintenir le script en vie et recevoir les notifs
            while True:
                await asyncio.sleep(1)

    except asyncio.CancelledError:
        # Géré lors du Ctrl+C si on clean up proprement
        print("\n🛑 Arrêt demandé par l'utilisateur.")
    except Exception as e:
        print(f"\n❌ Une erreur est survenue pendant la connexion : {e}")

if __name__ == "__main__":
    try:
        # Exécution de la boucle asynchrone
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n👋 Fin du programme. Au revoir !")
        sys.exit(0)
