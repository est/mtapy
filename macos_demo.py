import asyncio
import sys
import os

# Add src directory to path so we can import mtapy
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

try:
    from mtapy import get_ble_provider
    from mtapy.interfaces import DiscoveredDevice
except ImportError as e:
    print(f"Error: Could not import mtapy. Make sure you are in the project root. {e}")
    sys.exit(1)

async def main():
    print("--- mtapy macOS BLE Scanner ---")
    
    try:
        ble = get_ble_provider()
    except Exception as e:
        print(f"Failed to initialize BLE. Check if Bluetooth is enabled and bleak is installed. {e}")
        return

    print("Scanning for MTA-compatible devices for 20 seconds...")
    print("(Make sure your phone has 'Fast Share' or similar enabled and is searching for devices)")
    print("-" * 40)

    devices_found = []

    async def on_device(device: DiscoveredDevice):
        if device.address not in [d.address for d in devices_found]:
            devices_found.append(device)
            print(f"Found Device!")
            print(f"  Name:    {device.name}")
            print(f"  Address: {device.address}")
            print(f"  RSSI:    {device.rssi} dBm")
            if device.brand:
                print(f"  Brand:   {device.brand}")
            print(f"  5GHz:    {device.supports_5ghz}")
            print("-" * 40)

    try:
        await ble.start_scan(on_device, timeout=20.0)
    except KeyboardInterrupt:
        print("\nScan stopped by user.")
    except Exception as e:
        print(f"Error during scan: {e}")
    finally:
        await ble.stop_scan()

    if not devices_found:
        print("No MTA devices found. Try moving closer or toggling Bluetooth on your phone.")
    else:
        print(f"Scan complete. Found {len(devices_found)} device(s).")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
