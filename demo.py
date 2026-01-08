import asyncio
import sys
import os
from pathlib import Path
import argparse
import concurrent.futures
import logging

# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ],
    datefmt='%Y%m%d %H%M%S',

)
logger = logging.getLogger(__name__)

# Add src directory to path so we can import mtapy
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from mtapy import get_macos_ble_provider, MTAReceiver, SendRequest, P2pInfo

async def scan_for_devices(timeout: float = 10.0):
    """Scan for nearby MTA devices."""
    logger.info("[SCAN] 🔍 Scanning for %ss...", timeout)
    ble = get_macos_ble_provider()
    found_any = False

    async def on_device_found(device):
        nonlocal found_any
        found_any = True
        is_5ghz = "5GHz" if device.supports_5ghz else "2.4GHz"
        logger.info("[SCAN] 📱 %sdBm | %s | %s | %-20s ", device.rssi, is_5ghz, device.address, device.name)

    await ble.start_scan(on_device_found, timeout=timeout)

    if not found_any:
        logger.warning("[SCAN] ⚠️  No devices found.")
    else:
        logger.info("[SCAN] ✅ Scan complete.")


async def listen_for_transfers(device_name: str = "MacBook (mtapy)", timeout: float = 600.0):
    """Listen for incoming file transfers."""
    logger.info("[RECV] 📡 Advertising as '%s' | Waiting for Android...", device_name)

    ble = get_macos_ble_provider()
    output_dir = Path("./received_files")
    output_dir.mkdir(exist_ok=True)

    async def on_request(request: SendRequest) -> bool:
        logger.info("[RECV] 📥 %s -> %s (%s files, %s bytes) | Auto-accepting...", request.sender_name, request.file_name, request.file_count, request.total_size)
        return True

    async def on_text(text: str):
        logger.info("[TEXT] 💬 %s", text)

    async def on_p2p(p2p: P2pInfo):
        logger.info("[WIFI] 📶 Connect to SSID: '%s' | PSK: '%s'", p2p.ssid, p2p.psk)
        
        if args.auto_connect:
            logger.info("[WIFI] 🤖 Auto-connecting...")
            # Run blocking call in executor
            success = await asyncio.get_event_loop().run_in_executor(
                None, 
                lambda: connect_to_wifi(p2p.ssid, p2p.psk)
            )
            if success:
                logger.info("[WIFI] 🚀 Auto-connected! Starting transfer in 2s...")
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
        logger.info("[RECV] ✅ Success! %s file(s) received.", len(files))
        for f in files:
            logger.info("[FILE] 💾 %s (%s bytes) -> %s", f.name, f.size, f.path)
    else:
        logger.info("[RECV] ⏹️  Session ended.")




async def run_combined(device_name: str = "MacBook (mtapy)", timeout: float = 600.0):
    """Run both scanner and receiver concurrently."""
    logger.info("  MTAPY DEMO | Name: %s | Timeout: %ss", device_name, timeout)

    # Start the receiver (Advertiser + GATT Server)
    receiver_task = asyncio.create_task(listen_for_transfers(device_name, timeout))
    
    # Start the scanner loop
    async def scanner_loop():
        while True:
            # Scan for 10 seconds, then wait 5 seconds
            await scan_for_devices(timeout=10.0)
            await asyncio.sleep(0.5)

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
    logger.info("  MTAPY DEMO STARTING...")
    
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
            logger.warning("Warning: PyObjCTools not found. Callbacks might hang.")
    
    if use_runloop:
        logger.debug("DEBUG: Running asyncio in background thread + Main Thread RunLoop")
        
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
                logger.error("[ERROR] Background thread crashed: %s", e)
            finally:
                # Stop the main loop when async work is done (e.g. timeout or crash)
                AppHelper.stopEventLoop()

        t = threading.Thread(target=bg_thread, daemon=True)
        t.start()
        
        # Install a Python signal handler to catch Ctrl+C ensuring AppHelper stops
        import signal
        def handle_sigint(signum, frame):
            logger.warning("\n[SIGINT] Stopping...")
            
            # Cancel all tasks and stop the background loop first
            def cancel_and_stop():
                for task in asyncio.all_tasks(loop):
                    task.cancel()
                loop.stop()
            
            loop.call_soon_threadsafe(cancel_and_stop)
            
            # Stop the main thread's event loop
            AppHelper.stopEventLoop()
            
        signal.signal(signal.SIGINT, handle_sigint)

        try:
            # this blocks until AppHelper.stopEventLoop() is called
            # installInterrupt=False because we use our own signal handler
            AppHelper.runConsoleEventLoop(installInterrupt=False)
        except KeyboardInterrupt:
            pass
        except Exception as e:
            logger.error("[MAIN] RunLoop error: %s", e)

        # Check for background exception and re-raise if present (for pdb)
        if bg_exception_container:
            logger.error("\nRe-raising background exception for pdb...")
            raise bg_exception_container[0]

    else:
        try:
            # Standard mode (may hang on macOS without queue fix)
            asyncio.run(run_combined(device_name=args.name, timeout=args.timeout))
        except KeyboardInterrupt:
            logger.warning("\n\nStopped by user.")
