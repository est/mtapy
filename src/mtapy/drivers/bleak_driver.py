"""
Default BLE implementation using the `bleak` library.

Provides device discovery and GATT operations for Windows/macOS/Linux.
"""

import asyncio
import logging
import struct
from typing import Optional, Callable, Awaitable, List, Tuple, Dict
import json

logger = logging.getLogger(__name__)

from ..interfaces import BLEProvider, BLEConnection, DiscoveredDevice
from ..models import DeviceInfo, P2pInfo
from ..constants import ADV_SERVICE_UUID, SERVICE_UUID, CHAR_STATUS_UUID, CHAR_P2P_UUID


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
        self._gatt_server = None
        self._advertising = False
        self._on_read_callback = None
        self._on_write_callback = None

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

    async def start_advertising(
        self,
        name: str,
        service_uuid: str,
        service_data: Optional[Dict[str, bytes]] = None,
    ) -> None:
        """
        Start advertising as an MTA device.
        
        Note: Bleak 0.21+ supports GATT server but advertising support varies.
        On macOS, we use the device name and primary service UUID.
        """
        # Advertising is often started automatically when the GATT server
        # is started on many bleak backends, or requires platform-specific steps.
        # For now, we set the flag.
        self._advertising = True
        logger.debug("Starting advertising as '%s' with service %s", name, service_uuid)

    async def stop_advertising(self) -> None:
        """Stop BLE advertising."""
        self._advertising = False

    async def setup_gatt_server(
        self,
        service_uuid: str,
        characteristics: Dict[str, Tuple[bool, bool]],
        on_read: Callable[[str], Awaitable[bytes]],
        on_write: Callable[[str, bytes], Awaitable[None]],
    ) -> None:
        """
        Setup GATT server with specified characteristics.
        
        WARNING: Bleak is a BLE CLIENT library and does not support
        running as a BLE peripheral (GATT server).
        
        On macOS, use the pyobjc-based CoreBluetooth wrapper.
        On Linux, use bluez D-Bus APIs directly.
        """
        raise NotImplementedError(
            "Bleak does not support GATT server functionality. "
            "To receive files, you need a platform-specific BLE peripheral implementation. "
            "For macOS, consider using pyobjc with CoreBluetooth directly."
        )

    async def stop_gatt_server(self) -> None:
        """Stop the GATT server."""
        pass  # No-op since GATT server isn't supported

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
    """
    Get the default BLE provider for the current platform.
    
    On macOS, returns CoreBluetoothBLEProvider for GATT server support.
    On other platforms, returns BleakBLEProvider (client-only).
    """
    import sys
    
    if sys.platform == "darwin":
        try:
            from .macos import CoreBluetoothBLEProvider
            return CoreBluetoothBLEProvider()
        except ImportError:
            # pyobjc not installed, fall back to bleak
            pass
    
    return BleakBLEProvider()
