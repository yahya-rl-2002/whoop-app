
import asyncio
from bleak import BleakScanner, BleakClient

# UUID du service propriétaire Whoop découvert
PROPRIETARY_CHAR_UUID = "61080003-8d6d-82b8-614a-1c8cb0f8dcc6"

async def run():
    print("🕵️  Mode HACK : Sniffing du service propriétaire Whoop...")
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
        print("❌ Whoop introuvable.")
        return

    print(f"🔗 Connexion à {target.name}...")
    
    def raw_callback(sender, data: bytearray):
        # Affichage HEX brut pour analyse
        hex_data = data.hex(' ').upper()
        # Essai de décodage ASCII (souvent inutile mais on sait jamais)
        try: ascii = data.decode('utf-8')
        except: ascii = "."
        
        print(f"📡 DATA [{len(data)} octets]: {hex_data}  |  (Ints: {list(data)})")

    try:
        async with BleakClient(target) as client:
            print("✅ Connecté au canal caché. Écoute en cours... (Secouez le bras !)")
            
            try:
                await client.start_notify(PROPRIETARY_CHAR_UUID, raw_callback)
                # On reste en ligne 20 secondes pour voir passer des trucs
                await asyncio.sleep(20)
            except Exception as e:
                print(f"❌ Échec de l'abonnement : {e}")
                print("Le service est peut-être protégé/crypté ou nécessite un handshake.")

    except Exception as e:
        print(f"Erreur globale : {e}")

if __name__ == "__main__":
    asyncio.run(run())
