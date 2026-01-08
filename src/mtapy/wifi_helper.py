import subprocess
import shutil
import time
import sys
import re
import logging

logger = logging.getLogger(__name__)

def get_wifi_interface() -> str:
    """
    Detect the Wi-Fi interface (e.g. en0) on macOS using networksetup.
    """
    if sys.platform != "darwin":
        return "wlan0" # Fallback guess for Linux

    try:
        # List all hardware ports
        output = subprocess.check_output(
            ["networksetup", "-listallhardwareports"], 
            encoding="utf-8"
        )
        
        # Parse output to find "Wi-Fi" or "Airport"
        # Format is:
        # Hardware Port: Wi-Fi
        # Device: en0
        lines = output.splitlines()
        for i, line in enumerate(lines):
            if "Hardware Port: Wi-Fi" in line or "Hardware Port: AirPort" in line:
                # The next line should be "Device: enX"
                if i + 1 < len(lines):
                    device_line = lines[i+1]
                    match = re.search(r"Device: (en\d+)", device_line)
                    if match:
                        return match.group(1)
                        
    except Exception as e:
        logger.warning("[WIFI] ⚠️  Could not detect Wi-Fi interface: %s", e)
        
    return "en0" # Default fallback


def connect_to_wifi(ssid: str, password: str) -> bool:
    """
    Connect to a Wi-Fi network using networksetup on macOS.
    Returns True if successful.
    """
    if sys.platform != "darwin":
        logger.error("[WIFI] ❌ Auto-connect only supported on macOS")
        return False

    interface = get_wifi_interface()
    logger.info("[WIFI] 🔄 Connecting to '%s' on %s...", ssid, interface)
    
    try:
        # networksetup -setairportnetwork <device> <network> <password>
        # Note: networksetup can print "Could not find network" to stderr but return 0
        result = subprocess.run(
            ["networksetup", "-setairportnetwork", interface, ssid, password],
            capture_output=True,
            text=True
        )
        
        output = result.stdout + result.stderr
        
        # Check for known failure strings
        if "Could not find network" in output or "Error" in output:
            logger.error("[WIFI] ❌ %s", output.strip())
            return False
            
        if result.returncode != 0:
            logger.error("[WIFI] ❌ Command failed: %s", output.strip())
            return False

        logger.info("[WIFI] ✅ Connected to '%s'", ssid)
        # Give it a moment to acquire IP
        time.sleep(2.0)
        return True
    except Exception as e:
        logger.error("[WIFI] ❌ Failed to connect: %s", e)
        return False
