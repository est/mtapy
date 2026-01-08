#!/usr/bin/env python3
"""
mtapy macOS Demo - Combined Scanner and Receiver

This script demonstrates both scanning for MTA devices AND listening
as a receiver to accept file transfers.

Usage:
    python3 demo.py scan     # Scan for MTA devices (sender mode)
    python3 demo.py listen   # Listen for transfers (receiver mode)
    python3 demo.py          # Interactive menu

Requirements:
    pip install bleak cryptography websockets
    pip install pyobjc-framework-CoreBluetooth  # For receiver mode
"""

import asyncio
import sys
import os
from pathlib import Path

# Add current directory to path so we can import mtapy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from mtapy import get_ble_provider, MTAReceiver, SendRequest, P2pInfo
    from mtapy.interfaces import DiscoveredDevice
except ImportError as e:
    print(f"Error: {e}")
    print("Make sure you are running from the project root.")
    print("Install dependencies: pip install bleak cryptography websockets")
    sys.exit(1)


async def scan_devices(timeout: float = 20.0):
    """Scan for MTA-compatible devices."""
    print("\n--- Scanning for MTA Devices ---")
    print(f"Duration: {timeout} seconds")
    print("Make sure your phone has 'Fast Share' or similar enabled.")
    print("-" * 50)

    try:
        ble = get_ble_provider()
        print(f"Using BLE provider: {type(ble).__name__}")
    except Exception as e:
        print(f"Failed to initialize BLE: {e}")
        return

    devices_found: list[DiscoveredDevice] = []

    async def on_device(device: DiscoveredDevice):
        if device.address not in [d.address for d in devices_found]:
            devices_found.append(device)
            print(f"\n[Device Found]")
            print(f"  Name:    {device.name}")
            print(f"  Address: {device.address}")
            print(f"  RSSI:    {device.rssi} dBm")
            if device.brand:
                print(f"  Brand:   {device.brand}")
            print(f"  5GHz:    {device.supports_5ghz}")

    try:
        await ble.start_scan(on_device, timeout=timeout)
    except Exception as e:
        print(f"\nError during scan: {e}")
    finally:
        await ble.stop_scan()

    print("-" * 50)
    if not devices_found:
        print("No MTA devices found.")
    else:
        print(f"Found {len(devices_found)} device(s).")


async def listen_for_transfers(device_name: str = "MacBook (mtapy)", timeout: float = 300.0):
    """Listen for incoming file transfers."""
    print("\n--- Listening for Transfers ---")
    print(f"Advertising as: {device_name}")
    print(f"Timeout: {timeout} seconds")
    print("-" * 50)

    # Check if macOS GATT server is available
    try:
        ble = get_ble_provider()
        print(f"Using BLE provider: {type(ble).__name__}")
        
        if type(ble).__name__ == "BleakBLEProvider":
            print("\n⚠️  WARNING: BleakBLEProvider cannot act as a GATT server.")
            print("   To enable receiver mode on macOS, install:")
            print("   pip install pyobjc-framework-CoreBluetooth")
            return
    except Exception as e:
        print(f"Failed to initialize BLE: {e}")
        return

    output_dir = Path("./received_files")
    output_dir.mkdir(exist_ok=True)

    async def on_request(request: SendRequest) -> bool:
        print(f"\n[Incoming Transfer]")
        print(f"  From:  {request.sender_name}")
        print(f"  File:  {request.file_name}")
        print(f"  Total: {request.file_count} file(s), {request.total_size} bytes")
        print("  → Auto-accepting...")
        return True

    async def on_text(text: str):
        print(f"\n[Text Received]")
        print(f"  Content: {text}")

    async def on_p2p(p2p: P2pInfo):
        print("\n" + "!" * 50)
        print("  WIFI CONNECTION REQUIRED")
        print("!" * 50)
        print(f"  SSID: {p2p.ssid}")
        print(f"  PSK:  {p2p.psk}")
        print("-" * 50)
        print("  On your Mac:")
        print("  1. Click the WiFi icon in the menu bar.")
        print(f"  2. Connect to '{p2p.ssid}'.")
        print(f"  3. Use the password: {p2p.psk}")
        print("-" * 50)
        
        # Use a separate thread for input to avoid blocking the event loop
        # But since we are in async, we can just use loop.run_in_executor
        def wait_input():
            input("\n  >>> PRESS ENTER ONCE CONNECTED TO WIFI to start transfer...")
            
        await asyncio.get_event_loop().run_in_executor(None, wait_input)

    receiver = MTAReceiver(
        output_dir=output_dir,
        on_request=on_request,
        on_text=on_text,
    )

    print("\nWaiting for sender...")
    print("Open 'Fast Share' or 'MTA Share' on your Android phone.")
    print("-" * 50)

    try:
        files = await receiver.listen(
            device_name=device_name, 
            on_p2p=on_p2p,
            timeout=timeout
        )
        
        if files:
            print(f"\n✅ Received {len(files)} file(s):")
            for f in files:
                print(f"   {f.name} ({f.size} bytes) → {f.path}")
        else:
            print("\nSession ended (text share or cancelled).")
            
    except asyncio.TimeoutError:
        print("\n⏱️ Timed out waiting for sender.")
    except NotImplementedError as e:
        print(f"\n❌ GATT server not supported: {e}")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


def print_menu():
    """Print interactive menu."""
    print("\n" + "=" * 50)
    print("  mtapy macOS Demo")
    print("=" * 50)
    print("\n  [1] Scan for MTA devices (20 seconds)")
    print("  [2] Listen for transfers (5 minutes)")
    print("  [3] Quick scan (10 seconds)")
    print("  [q] Quit")
    print()


async def interactive_menu():
    """Run interactive menu."""
    while True:
        print_menu()
        choice = input("  Select option: ").strip().lower()
        
        if choice == "1":
            await scan_devices(timeout=20.0)
        elif choice == "2":
            await listen_for_transfers(timeout=300.0)
        elif choice == "3":
            await scan_devices(timeout=10.0)
        elif choice in ("q", "quit", "exit"):
            print("\nGoodbye!")
            break
        else:
            print("  Invalid option. Try again.")


async def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "scan":
            await scan_devices()
        elif cmd == "listen":
            await listen_for_transfers()
        elif cmd == "help":
            print(__doc__)
        else:
            print(f"Unknown command: {cmd}")
            print("Usage: python3 demo.py [scan|listen|help]")
    else:
        await interactive_menu()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
