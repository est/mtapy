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
    print(f"\n[SCAN] 🔍 Scanning for {timeout}s...")
    ble = get_macos_ble_provider()
    found_any = False

    async def on_device_found(device):
        nonlocal found_any
        found_any = True
        is_5ghz = "5GHz" if device.supports_5ghz else "2.4GHz"
        print(f"[SCAN] 📱 {device.rssi}dBm | {device.name:<20} | {device.address} | {is_5ghz}")

    try:
        await ble.start_scan(on_device_found, timeout=timeout)
    finally:
        pass # No catch, let it crash

    if not found_any:
        print("[SCAN] ⚠️  No devices found.")
    else:
        print("[SCAN] ✅ Scan complete.")


async def listen_for_transfers(device_name: str = "MacBook (mtapy)", timeout: float = 600.0):
    """Listen for incoming file transfers."""
    print(f"[RECV] 📡 Advertising as '{device_name}' | Waiting for Android...")

    ble = get_macos_ble_provider()
    output_dir = Path("./received_files")
    output_dir.mkdir(exist_ok=True)

    async def on_request(request: SendRequest) -> bool:
        print(f"[RECV] 📥 {request.sender_name} -> {request.file_name} ({request.file_count} files, {request.total_size} bytes) | Auto-accepting...")
        return True

    async def on_text(text: str):
        print(f"[TEXT] 💬 {text}")

    async def on_p2p(p2p: P2pInfo):
        print(f"[WIFI] 📶 Connect to SSID: '{p2p.ssid}' | PSK: '{p2p.psk}'")
        
        if args.auto_connect:
            print("[WIFI] 🤖 Auto-connecting...")
            # Run blocking call in executor
            success = await asyncio.get_event_loop().run_in_executor(
                None, 
                lambda: connect_to_wifi(p2p.ssid, p2p.psk)
            )
            if success:
                print("[WIFI] 🚀 Auto-connected! Starting transfer in 2s...")
                await asyncio.sleep(2.0)
                return

        def wait_input():
            input("[WIFI] ⌨️  Press ENTER once connected to start download...")
        await asyncio.get_event_loop().run_in_executor(None, wait_input)

    receiver = MTAReceiver(
        output_dir=output_dir,
        on_request=on_request,
        on_text=on_text,
    )

    # Note: Removed try-except to expose errors as requested
    files = await receiver.listen(
        device_name=device_name, 
        on_p2p=on_p2p,
        timeout=timeout
    )
    
    if files:
        print(f"[RECV] ✅ Success! {len(files)} file(s) received.")
        for f in files:
            print(f"[FILE] 💾 {f.name} ({f.size} bytes) -> {f.path}")
    else:
        print("[RECV] ⏹️  Session ended.")




async def run_combined(device_name: str = "MacBook (mtapy)", timeout: float = 600.0):
    """Run both scanner and receiver concurrently."""
    print("=" * 60)
    print(f"  MTAPY DEMO | Name: {device_name} | Timeout: {timeout}s")
    print("=" * 60)

    # Start the receiver (Advertiser + GATT Server)
    receiver_task = asyncio.create_task(listen_for_transfers(device_name, timeout))
    
    # Start the scanner loop
    async def scanner_loop():
        while True:
            # Scan for 10 seconds, then wait 5 seconds
            await scan_for_devices(timeout=10.0)
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
    from mtapy import get_macos_ble_provider, MTAReceiver, SendRequest, P2pInfo
    from mtapy.wifi_helper import connect_to_wifi

    parser = argparse.ArgumentParser(description="mtapy macOS Demo")
    parser.add_argument("--name", type=str, default="MacBook Pro", help="Name to display when receiving")
    parser.add_argument("--timeout", type=float, default=3600.0, help="Timeout for the operation (default 1 hour)")
    parser.add_argument("--auto-connect", action="store_true", help="Automatically connect to P2P WiFi (macOS only)")
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
        # Use a list to store exception, avoiding nonlocal issue in some contexts
        bg_exception_container = []
        
        def bg_thread():
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(run_combined(device_name=args.name, timeout=args.timeout))
            except asyncio.CancelledError:
                pass  # Graceful exit
            except RuntimeError:
                pass  # Loop stopped
            except Exception as e:
                # Store exception for re-raising in main thread
                bg_exception_container.append(e)
                # Print immediately so user sees it even if main loop is stuck
                print(f"\n[ERROR] Background thread crashed: {e}")
            finally:
                # Stop the main loop when async work is done (e.g. timeout or crash)
                AppHelper.stopEventLoop()

        t = threading.Thread(target=bg_thread, daemon=True)
        t.start()
        
        # Install a Python signal handler to catch Ctrl+C ensuring AppHelper stops
        import signal
        def handle_sigint(signum, frame):
            print("\n[SIGINT] Stopping...", file=sys.stderr)
            AppHelper.stopEventLoop()
            
            # Cancel all tasks on the background loop to unblock run_until_complete
            def cancel_all():
                for task in asyncio.all_tasks(loop):
                    task.cancel()
            
            loop.call_soon_threadsafe(cancel_all)
            
        signal.signal(signal.SIGINT, handle_sigint)

        try:
            # this blocks until AppHelper.stopEventLoop() is called
            # installInterrupt=False because we use our own signal handler
            AppHelper.runConsoleEventLoop(installInterrupt=False)
        except KeyboardInterrupt:
            pass
        except Exception as e:
            print(f"[MAIN] RunLoop error: {e}")

        # Check for background exception and re-raise if present (for pdb)
        if bg_exception_container:
            print("\nRe-raising background exception for pdb...")
            raise bg_exception_container[0]

    else:
        try:
            # Standard mode (may hang on macOS without queue fix)
            asyncio.run(run_combined(device_name=args.name, timeout=args.timeout))
        except KeyboardInterrupt:
            print("\n\nStopped by user.")
