
import asyncio
import sys
import csv
import datetime
from bleak import BleakScanner, BleakClient
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

# UUID Standard pour le service de fréquence cardiaque (Heart Rate Service)
HEART_RATE_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"

class WhoopLogger:
    """
    Classe gérant l'enregistrement des données cardiaques dans un fichier CSV.
    """
    def __init__(self):
        # Génération dynamique du nom de fichier avec la date et l'heure actuelle
        now = datetime.datetime.now()
        self.filename = f"whoop_session_{now.strftime('%Y-%m-%d_%H-%M-%S')}.csv"
        self.file = None
        self.writer = None

    def start(self):
        """Ouvre le fichier CSV et écrit les en-têtes."""
        try:
            # newline='' est recommandé par la doc csv de Python pour éviter les sauts de ligne doubles sous Windows
            self.file = open(self.filename, mode='w', newline='', encoding='utf-8')
            self.writer = csv.writer(self.file)
            
            # Écriture de l'en-tête
            headers = ["Timestamp", "BPM"]
            self.writer.writerow(headers)
            self.file.flush() # Force l'écriture sur le disque
            
            print(f"📁 Fichier de log créé : {self.filename}")
        except IOError as e:
            print(f"❌ Erreur lors de la création du fichier CSV : {e}")
            sys.exit(1)

    def stop(self):
        """Ferme proprement le fichier CSV."""
        if self.file:
            self.file.close()
            print(f"📁 Fichier {self.filename} fermé.")

    def notification_handler(self, sender, data: bytearray):
        """
        Callback appelé par Bleak à chaque notification.
        Parse les données et les enregistre dans le CSV.
        """
        # Parsing standard BLE Heart Rate (identique au script précédent)
        flags = data[0]
        hr_format_uint16 = flags & 0x01
        
        if hr_format_uint16:
            hr_value = int.from_bytes(data[1:3], byteorder='little')
        else:
            hr_value = data[1]

        # Récupération du timestamp actuel précis
        current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3] # Millisecondes
        
        # Affichage Console
        print(f"❤️ BPM: {hr_value}  (Rec: {current_time})")

        # Enregistrement CSV
        if self.writer and self.file:
            try:
                self.writer.writerow([current_time, hr_value])
                self.file.flush() # CRITIQUE : Assure que la donnée est physiquement écrite
            except IOError as e:
                print(f"❌ Erreur d'écriture dans le CSV : {e}")

async def run():
    print("🔍 Démarrage du logger Whoop...")
    
    # Instanciation de notre logger
    logger = WhoopLogger()
    logger.start()

    print("   Recherche du bracelet Whoop...")
    target_device: BLEDevice | None = None
    stop_event = asyncio.Event()

    def detection_callback(device: BLEDevice, advertisement_data: AdvertisementData):
        nonlocal target_device
        if device.name and "whoop" in device.name.lower():
            print(f"✅ Whoop trouvé : {device.name} ({device.address})")
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

    except Exception as e:
        print(f"❌ Erreur scan : {e}")
        logger.stop()
        return

    if not target_device:
        print("⚠️  Whoop introuvable. Vérifiez le mode broadcast.")
        logger.stop()
        return

    print(f"🔗 Connexion à {target_device.name}...")
    
    try:
        async with BleakClient(target_device) as client:
            if not client.is_connected:
                print("❌ Echec connexion.")
                logger.stop()
                return
            
            print(f"✅ Connecté ! Enregistrement en cours dans {logger.filename}...")
            
            # On passe la méthode de notre instance logger comme callback
            await client.start_notify(HEART_RATE_MEASUREMENT_UUID, logger.notification_handler)
            
            print("📡 Enregistrement actif. Appuyez sur Ctrl+C pour arrêter et sauvegarder.")
            
            while True:
                await asyncio.sleep(1)

    except asyncio.CancelledError:
        print("\n🛑 Arrêt demandé.")
    except Exception as e:
        print(f"\n❌ Erreur : {e}")
    finally:
        # Bloc finally pour garantir la fermeture du fichier quoi qu'il arrive
        logger.stop()

if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass # Déjà géré mais on évite la stacktrace
    except Exception as e:
        print(f"Erreur fatale : {e}")
