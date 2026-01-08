import asyncio
import sys
import os
from pathlib import Path
import argparse

# Add src directory to path so we can import mtapy
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

try:
    from mtapy import get_macos_ble_provider, MTAReceiver, SendRequest, P2pInfo
except ImportError as e:
    print(f"Error: {e}")
    print("Make sure you are running from the project root.")
    print("Install dependencies: pip install pyobjc-framework-CoreBluetooth bleak cryptography websockets")
    sys.exit(1)

async def scan_for_devices(timeout: float = 10.0):
    """Scan for nearby MTA devices."""
    print("=" * 60)
    print("  MTA DEVICE SCANNER")
    print("=" * 60)
    print(f"\nScanning for nearby devices for {timeout} seconds...\n")

    ble = get_macos_ble_provider()
    
    found_any = False

    async def on_device_found(device):
        nonlocal found_any
        found_any = True
        print(f"FOUND: {device.name}")
        print(f"  Address: {device.address}")
        print(f"  RSSI:    {device.rssi} dBm")
        print(f"  5GHz:    {'Yes' if device.supports_5ghz else 'No'}")
        print("-" * 30)

    try:
        await ble.start_scan(on_device_found, timeout=timeout)
    except Exception as e:
        print(f"\n❌ Scan Error: {e}")

    if not found_any:
        print("\nNo MTA devices found. Make sure discovery is enabled on the target device.")
    else:
        print("\nScan complete.")


async def listen_for_transfers(device_name: str = "MacBook (mtapy)", timeout: float = 600.0):
    """Listen for incoming file transfers."""
    print("=" * 60)
    print("  MTA FILE RECEIVER (Android to Mac)")
    print("=" * 60)
    print(f"\n1. Advertising as: '{device_name}'")
    print(f"2. Open 'Fast Share' or 'MTA Share' on your Android phone.")
    print(f"3. Select this Mac from the device list.")
    print("-" * 60)

    ble = get_macos_ble_provider()
    output_dir = Path("./received_files")
    output_dir.mkdir(exist_ok=True)

    async def on_request(request: SendRequest) -> bool:
        print(f"\n[Incoming Transfer Request]")
        print(f"  From:  {request.sender_name}")
        print(f"  File:  {request.file_name}")
        print(f"  Total: {request.file_count} file(s), {request.total_size} bytes")
        print("  → Auto-accepting...")
        return True

    async def on_text(text: str):
        print(f"\n[Text Received]")
        print(f"  Content: {text}")

    async def on_p2p(p2p: P2pInfo):
        print("\n" + "!" * 60)
        print("  STEP: WIFI CONNECTION REQUIRED")
        print("!" * 60)
        print(f"  The sender has created a temporary hotspot:")
        print(f"  SSID: {p2p.ssid}")
        print(f"  PSK:  {p2p.psk}")
        print("-" * 60)
        print("  HOW TO CONNECT:")
        print("  1. Click the WiFi icon in your Mac's menu bar.")
        print(f"  2. Select and connect to network: '{p2p.ssid}'")
        print(f"  3. Enter password: {p2p.psk}")
        print("-" * 60)
        
        def wait_input():
            input("\n  >>> PRESS ENTER ONCE CONNECTED TO START FILE DOWNLOAD...")
            
        await asyncio.get_event_loop().run_in_executor(None, wait_input)

    receiver = MTAReceiver(
        output_dir=output_dir,
        on_request=on_request,
        on_text=on_text,
    )

    print("\nWaiting for connection...")

    try:
        files = await receiver.listen(
            device_name=device_name, 
            on_p2p=on_p2p,
            timeout=timeout
        )
        
        if files:
            print(f"\n✅ SUCCESS! Received {len(files)} file(s):")
            for f in files:
                print(f"   {f.name} ({f.size} bytes) → {f.path}")
        else:
            print("\nSession ended (text share or cancelled).")
            
    except asyncio.TimeoutError:
        print("\n⏱️ Timed out waiting for sender. Make sure Bluetooth is on.")
    except Exception as e:
        print(f"\n❌ Unexpected Error: {e}")
        import traceback
        traceback.print_exc()


async def run_combined(device_name: str = "MacBook (mtapy)", timeout: float = 600.0):
    """Run both scanner and receiver concurrently."""
    print("=" * 60)
    print("  MTAPY DEMO - SCANNER & RECEIVER")
    print("=" * 60)
    print(f"1. Advertising as: '{device_name}' (Discoverable by Android)")
    print("2. Scanning for nearby MTA devices...")
    print("-" * 60)

    # Start the receiver (Advertiser + GATT Server)
    receiver_task = asyncio.create_task(listen_for_transfers(device_name, timeout))
    
    # Start the scanner loop
    async def scanner_loop():
        while True:
            try:
                # Scan for 10 seconds, then wait 5 seconds
                await scan_for_devices(timeout=10.0)
                await asyncio.sleep(5.0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Scanner error: {e}")
                await asyncio.sleep(5.0)

    scanner_task = asyncio.create_task(scanner_loop())

    # Wait for receiver to finish (or scan loop to crash)
    try:
        await receiver_task
    except asyncio.CancelledError:
        pass
    finally:
        scanner_task.cancel()
        try:
            await scanner_task
        except asyncio.CancelledError:
            pass

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  MTAPY DEMO STARTING...")
    print("=" * 60)
    
    # Setup argparse
    parser = argparse.ArgumentParser(description="mtapy macOS Demo")
    parser.add_argument("--name", type=str, default="MacBook Pro", help="Name to display when receiving")
    parser.add_argument("--timeout", type=float, default=3600.0, help="Timeout for the operation (default 1 hour)")
    args = parser.parse_args()

    # On macOS, we SHOULD run the asyncio loop in a background thread 
    # so the Main Thread can pump the CFRunLoop for CoreBluetooth callbacks.
    # This prevents the "Hang" issue without needing complex dispatch_queues.
    import threading
    use_runloop = False
    if sys.platform == "darwin":
        try:
            from PyObjCTools import AppHelper
            use_runloop = True
        except ImportError:
            print("Warning: PyObjCTools not found. Callbacks might hang.")
    
    if use_runloop:
        print("DEBUG: Running asyncio in background thread + Main Thread RunLoop")
        
        loop = asyncio.new_event_loop()
        
        def bg_thread():
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(run_combined(device_name=args.name, timeout=args.timeout))
            except Exception as e:
                print(f"Background thread error: {e}")
            finally:
                # Stop the main loop when async work is done (e.g. timeout)
                AppHelper.stopEventLoop()

        t = threading.Thread(target=bg_thread, daemon=True)
        t.start()
        
        try:
            # This blocks until AppHelper.stopEventLoop() is called or Ctrl+C
            AppHelper.runConsoleEventLoop(installInterrupt=True)
        except KeyboardInterrupt:
            print("\nStopped by user.")
    else:
        try:
            # Standard mode (may hang on macOS without queue fix)
            asyncio.run(run_combined(device_name=args.name, timeout=args.timeout))
        except KeyboardInterrupt:
            print("\n\nStopped by user.")
