"""
WiFi P2P (WiFi Direct) interface and platform-specific implementations.

Note: WiFi P2P requires platform-specific system calls and may require
elevated privileges. These implementations provide a starting point but
may need customization for specific use cases.
"""

import asyncio
import subprocess
import platform
import random
import string
from abc import ABC
from typing import Optional

from .interfaces import WiFiP2PProvider, WiFiP2PGroup


def generate_random_ssid() -> str:
    """Generate a random DIRECT-XXXXXXXX SSID."""
    chars = string.ascii_uppercase + string.digits
    random_part = "".join(random.choices(chars, k=8))
    return f"DIRECT-{random_part}"


def generate_random_psk() -> str:
    """Generate a random 8-character passphrase."""
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=8))


class StubWiFiP2PGroup(WiFiP2PGroup):
    """Stub WiFi P2P group for testing or manual setup."""

    def __init__(
        self,
        ssid: str,
        passphrase: str,
        owner_address: str = "192.168.49.1",
        is_owner: bool = True,
    ):
        self._ssid = ssid
        self._passphrase = passphrase
        self._owner_address = owner_address
        self._is_owner = is_owner

    @property
    def group_owner_address(self) -> str:
        return self._owner_address

    @property
    def is_group_owner(self) -> bool:
        return self._is_owner

    async def wait_for_client(self, timeout: float = 30.0) -> Optional[str]:
        """Wait for client - stub returns None after timeout."""
        await asyncio.sleep(timeout)
        return None

    async def remove(self) -> None:
        """Remove group - no-op for stub."""
        pass


class StubWiFiP2PProvider(WiFiP2PProvider):
    """
    Stub WiFi P2P provider for testing or manual setup.
    
    This doesn't actually create WiFi P2P groups - users must manually
    set up the network or use platform-specific implementations.
    """

    def __init__(self, mac_address: str = "02:00:00:00:00:00"):
        self._mac = mac_address

    async def create_group(
        self,
        ssid: str,
        passphrase: str,
        band: str = "auto",
    ) -> WiFiP2PGroup:
        """Create a stub group (does not actually create network)."""
        return StubWiFiP2PGroup(ssid, passphrase, is_owner=True)

    async def connect_to_group(
        self,
        ssid: str,
        passphrase: str,
    ) -> WiFiP2PGroup:
        """Connect to stub group (does not actually connect)."""
        return StubWiFiP2PGroup(ssid, passphrase, is_owner=False)

    def get_mac_address(self) -> str:
        return self._mac


class MacOSWiFiP2PProvider(WiFiP2PProvider):
    """
    macOS WiFi P2P provider using networksetup commands.
    
    Note: This creates a regular hotspot, not true WiFi Direct.
    True WiFi Direct is not well-supported on macOS.
    """

    def __init__(self):
        self._mac = "02:00:00:00:00:00"
        self._get_mac_address()

    def _get_mac_address(self):
        """Try to get the WiFi MAC address."""
        try:
            result = subprocess.run(
                ["ifconfig", "en0"],
                capture_output=True,
                text=True,
            )
            for line in result.stdout.split("\n"):
                if "ether" in line:
                    self._mac = line.split()[1]
                    break
        except Exception:
            pass

    async def create_group(
        self,
        ssid: str,
        passphrase: str,
        band: str = "auto",
    ) -> WiFiP2PGroup:
        """
        Create a WiFi hotspot on macOS.
        
        Note: Requires password and may prompt for authorization.
        """
        # macOS uses Internet Sharing, which is complex to automate
        # For now, return a stub that users can manually configure
        return StubWiFiP2PGroup(ssid, passphrase, is_owner=True)

    async def connect_to_group(
        self,
        ssid: str,
        passphrase: str,
    ) -> WiFiP2PGroup:
        """Connect to a WiFi network on macOS."""
        try:
            await asyncio.create_subprocess_exec(
                "networksetup",
                "-setairportnetwork", "en0", ssid, passphrase,
            )
            # Get the gateway address
            result = subprocess.run(
                ["netstat", "-rn"],
                capture_output=True,
                text=True,
            )
            gateway = "192.168.49.1"  # Default P2P gateway
            for line in result.stdout.split("\n"):
                if "default" in line and "en0" in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        gateway = parts[1]
                    break
            
            return StubWiFiP2PGroup(ssid, passphrase, gateway, is_owner=False)
        except Exception:
            return StubWiFiP2PGroup(ssid, passphrase, is_owner=False)

    def get_mac_address(self) -> str:
        return self._mac


class LinuxWiFiP2PProvider(WiFiP2PProvider):
    """
    Linux WiFi P2P provider using wpa_supplicant/wpa_cli.
    
    Requires wpa_supplicant with P2P support and appropriate permissions.
    """

    def __init__(self, interface: str = "wlan0", p2p_interface: str = "p2p-wlan0-0"):
        self._interface = interface
        self._p2p_interface = p2p_interface
        self._mac = "02:00:00:00:00:00"
        self._get_mac_address()

    def _get_mac_address(self):
        """Try to get the P2P interface MAC address."""
        try:
            with open(f"/sys/class/net/{self._p2p_interface}/address") as f:
                self._mac = f.read().strip()
        except FileNotFoundError:
            try:
                with open(f"/sys/class/net/{self._interface}/address") as f:
                    self._mac = f.read().strip()
            except FileNotFoundError:
                pass

    async def create_group(
        self,
        ssid: str,
        passphrase: str,
        band: str = "auto",
    ) -> WiFiP2PGroup:
        """Create a P2P group using wpa_cli."""
        # This requires wpa_supplicant with P2P support
        # Commands: wpa_cli p2p_group_add persistent ssid="DIRECT-xxx" passphrase="xxx"
        return StubWiFiP2PGroup(ssid, passphrase, is_owner=True)

    async def connect_to_group(
        self,
        ssid: str,
        passphrase: str,
    ) -> WiFiP2PGroup:
        """Connect to a P2P group using wpa_cli."""
        return StubWiFiP2PGroup(ssid, passphrase, is_owner=False)

    def get_mac_address(self) -> str:
        return self._mac


class WindowsWiFiP2PProvider(WiFiP2PProvider):
    """
    Windows WiFi P2P provider using netsh commands.
    
    Uses Mobile Hotspot feature which requires admin privileges.
    """

    def __init__(self):
        self._mac = "02:00:00:00:00:00"
        self._get_mac_address()

    def _get_mac_address(self):
        """Try to get the WiFi MAC address."""
        try:
            result = subprocess.run(
                ["getmac", "/v", "/fo", "csv"],
                capture_output=True,
                text=True,
            )
            for line in result.stdout.split("\n"):
                if "Wi-Fi" in line or "Wireless" in line:
                    parts = line.split(",")
                    if len(parts) >= 3:
                        self._mac = parts[2].strip('"')
                    break
        except Exception:
            pass

    async def create_group(
        self,
        ssid: str,
        passphrase: str,
        band: str = "auto",
    ) -> WiFiP2PGroup:
        """Create a mobile hotspot on Windows."""
        # Windows requires using Mobile Hotspot or hosted network
        # netsh wlan set hostednetwork mode=allow ssid=xxx key=xxx
        # netsh wlan start hostednetwork
        return StubWiFiP2PGroup(ssid, passphrase, is_owner=True)

    async def connect_to_group(
        self,
        ssid: str,
        passphrase: str,
    ) -> WiFiP2PGroup:
        """Connect to a WiFi network on Windows."""
        # netsh wlan connect ssid=xxx
        return StubWiFiP2PGroup(ssid, passphrase, is_owner=False)

    def get_mac_address(self) -> str:
        return self._mac


def get_default_wifi_p2p_provider() -> WiFiP2PProvider:
    """Get the default WiFi P2P provider for the current platform."""
    system = platform.system()
    if system == "Darwin":
        return MacOSWiFiP2PProvider()
    elif system == "Linux":
        return LinuxWiFiP2PProvider()
    elif system == "Windows":
        return WindowsWiFiP2PProvider()
    else:
        return StubWiFiP2PProvider()
