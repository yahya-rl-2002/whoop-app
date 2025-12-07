
import asyncio
from bleak import BleakScanner, BleakClient

async def run():
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
            print("✅ Connecté. Listing des services...")
            for service in client.services:
                print(f"\n📡 Service: {service.uuid} ({service.description})")
                for char in service.characteristics:
                    print(f"   🔹 Char: {char.uuid} ({char.description}) - Props: {char.properties}")
                    
    except Exception as e:
        print(f"Erreur: {e}")

if __name__ == "__main__":
    asyncio.run(run())
