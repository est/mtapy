"""
Default BLE implementation using the `bleak` library.

Provides device discovery and GATT operations for Windows/macOS/Linux.
"""

import asyncio
import struct
from typing import Callable, Awaitable, Optional, List
import json

from .interfaces import BLEProvider, BLEConnection, DiscoveredDevice
from .models import DeviceInfo, P2pInfo
from .constants import ADV_SERVICE_UUID, SERVICE_UUID, CHAR_STATUS_UUID, CHAR_P2P_UUID


def parse_scan_response(data: bytes) -> tuple[str, Optional[str], bool]:
    """
    Parse MTA scan response data.
    
    The scan response contains:
    - 8 bytes: unknown/padding
    - 2 bytes: random data
    - up to 16 bytes: device name (UTF-8, may end with \t if truncated)
    - 1 byte: flags (bit 0 = supports 5GHz)
    
    Returns:
        Tuple of (name, brand, supports_5ghz)
    """
    if len(data) < 27:
        return ("Unknown", None, True)
    
    # Extract name (bytes 10-25)
    name_bytes = data[10:26]
    try:
        name = name_bytes.rstrip(b"\x00").decode("utf-8")
        # Remove trailing tab (indicates truncation)
        if name.endswith("\t"):
            name = name[:-1] + "..."
    except UnicodeDecodeError:
        name = "Unknown"
    
    # Check 5GHz support (byte 26, bit 0)
    supports_5ghz = (data[26] & 0x01) != 0
    
    return (name, None, supports_5ghz)


class BleakBLEProvider(BLEProvider):
    """
    BLE provider using the `bleak` library.
    
    Works on Windows, macOS, and Linux.
    """

    def __init__(self):
        self._scanner = None
        self._scanning = False

    async def start_scan(
        self,
        on_device_found: Callable[[DiscoveredDevice], Awaitable[None]],
        timeout: float = 30.0,
    ) -> None:
        """Start scanning for MTA devices."""
        # Import here to make bleak optional
        from bleak import BleakScanner
        from bleak.backends.device import BLEDevice
        from bleak.backends.scanner import AdvertisementData
        
        seen_devices = set()
        
        def detection_callback(device: BLEDevice, adv_data: AdvertisementData):
            # Check if this is an MTA device
            service_uuid_str = str(ADV_SERVICE_UUID)
            if service_uuid_str not in adv_data.service_uuids:
                return
            
            if device.address in seen_devices:
                return
            seen_devices.add(device.address)
            
            # Parse scan response data
            name = device.name or "Unknown"
            supports_5ghz = True
            
            # Try to extract from service data
            scan_resp_uuid = "0000ffff-0000-1000-8000-00805f9b34fb"
            if scan_resp_uuid in adv_data.service_data:
                raw_data = adv_data.service_data[scan_resp_uuid]
                name, _, supports_5ghz = parse_scan_response(raw_data)
            
            discovered = DiscoveredDevice(
                address=device.address,
                name=name,
                rssi=adv_data.rssi or -100,
                supports_5ghz=supports_5ghz,
            )
            
            # Schedule the callback
            asyncio.create_task(on_device_found(discovered))
        
        self._scanner = BleakScanner(detection_callback=detection_callback)
        self._scanning = True
        
        try:
            await self._scanner.start()
            await asyncio.sleep(timeout)
        finally:
            await self.stop_scan()

    async def stop_scan(self) -> None:
        """Stop scanning for devices."""
        if self._scanner and self._scanning:
            await self._scanner.stop()
            self._scanning = False

    async def connect(self, address: str) -> "BLEConnection":
        """Connect to a device by address."""
        from bleak import BleakClient
        
        client = BleakClient(address)
        await client.connect()
        return BleakBLEConnection(client)


class BleakBLEConnection(BLEConnection):
    """BLE connection using bleak."""

    def __init__(self, client):
        self._client = client

    async def read_device_info(self) -> DeviceInfo:
        """Read DeviceInfo from CHAR_STATUS characteristic."""
        data = await self._client.read_gatt_char(str(CHAR_STATUS_UUID))
        return DeviceInfo.from_json(data.decode("utf-8"))

    async def write_p2p_info(self, p2p_info: P2pInfo) -> None:
        """Write P2pInfo to CHAR_P2P characteristic."""
        data = p2p_info.to_json().encode("utf-8")
        await self._client.write_gatt_char(str(CHAR_P2P_UUID), data)

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        await self._client.disconnect()


def get_default_ble_provider() -> BLEProvider:
    """Get the default BLE provider (bleak-based)."""
    return BleakBLEProvider()
