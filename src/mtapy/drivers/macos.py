"""
macOS BLE implementation using CoreBluetooth via pyobjc.

This module provides a GATT server implementation for macOS,
enabling the device to act as a BLE peripheral.

Requires:
    pip install pyobjc-framework-CoreBluetooth
"""

import asyncio
from typing import Callable, Awaitable, Optional
import sys
import objc

if sys.platform != "darwin":
    raise ImportError("This module is only for macOS")

# CoreBluetooth imports via pyobjc
try:
    from Foundation import NSData, NSObject, NSUUID
    from CoreBluetooth import (
        CBUUID,
        CBPeripheralManager,
        CBPeripheralManagerStateUnknown,
        CBPeripheralManagerStatePoweredOn,
        CBPeripheralManagerStatePoweredOff,
        CBMutableService,
        CBMutableCharacteristic,
        CBCharacteristicPropertyRead,
        CBCharacteristicPropertyWrite,
        CBCharacteristicPropertyWriteWithoutResponse,
        CBAttributePermissionsReadable,
        CBAttributePermissionsWriteable,
        CBAdvertisementDataLocalNameKey,
        CBAdvertisementDataServiceUUIDsKey,
        CBATTErrorSuccess,
    )
except ImportError as e:
    raise ImportError(
        "pyobjc-framework-CoreBluetooth is required for macOS BLE support.\n"
        "Install it with: pip install pyobjc-framework-CoreBluetooth"
    ) from e

from ..interfaces import BLEProvider, BLEConnection, DiscoveredDevice


class _PeripheralManagerDelegate(NSObject):
    """
    Objective-C delegate for CBPeripheralManager.
    
    Bridges CoreBluetooth callbacks to asyncio events.
    """

    def initWithLoop_onRead_onWrite_(self, loop, on_read, on_write):
        self = objc.super(_PeripheralManagerDelegate, self).init()
        if self is None:
            return None
        self._loop = loop
        self._on_read = on_read
        self._on_write = on_write
        self._state_event = asyncio.Event()
        self._powered_on = False
        self._characteristics = {}  # uuid_str -> CBMutableCharacteristic
        return self

    # Called when CBPeripheralManager state changes
    def peripheralManagerDidUpdateState_(self, peripheral):
        state = peripheral.state()
        print(f"DEBUG: Peripheral manager state changed: {state}")
        if state == CBPeripheralManagerStatePoweredOn:
            self._powered_on = True
            print("DEBUG: Bluetooth is POWERED ON")
        else:
            self._powered_on = False
            print(f"DEBUG: Bluetooth is NOT powered on (state: {state})")
        self._loop.call_soon_threadsafe(self._state_event.set)

    # Called when a central requests to read a characteristic
    def peripheralManager_didReceiveReadRequest_(self, peripheral, request):
        char = request.characteristic()
        uuid_str = str(char.UUID().UUIDString()).lower()
        
        if self._on_read:
            async def handle_read():
                try:
                    data = await self._on_read(uuid_str)
                    request.setValue_(NSData.dataWithBytes_length_(data, len(data)))
                    peripheral.respondToRequest_withResult_(request, CBATTErrorSuccess)
                except Exception as e:
                    print(f"GATT read error: {e}")
                    peripheral.respondToRequest_withResult_(request, 1)  # Error
            
            asyncio.run_coroutine_threadsafe(handle_read(), self._loop)
        else:
            peripheral.respondToRequest_withResult_(request, 1)

    # Called when a central writes to a characteristic
    def peripheralManager_didReceiveWriteRequests_(self, peripheral, requests):
        for request in requests:
            char = request.characteristic()
            uuid_str = str(char.UUID().UUIDString()).lower()
            value = request.value()
            data = bytes(value) if value else b""
            
            if self._on_write:
                async def handle_write(uid=uuid_str, d=data, req=request):
                    try:
                        await self._on_write(uid, d)
                        peripheral.respondToRequest_withResult_(req, CBATTErrorSuccess)
                    except Exception as e:
                        print(f"GATT write error: {e}")
                        peripheral.respondToRequest_withResult_(req, 1)
                
                asyncio.run_coroutine_threadsafe(handle_write(), self._loop)
            else:
                peripheral.respondToRequest_withResult_(request, CBATTErrorSuccess)

    # Called when service was added
    def peripheralManager_didAddService_error_(self, peripheral, service, error):
        if error:
            print(f"DEBUG: Failed to add service: {error}")
        else:
            print(f"DEBUG: Service added successfully: {service.UUID().UUIDString()}")

    # Called when advertising started
    def peripheralManagerDidStartAdvertising_error_(self, peripheral, error):
        if error:
            print(f"DEBUG: Failed to start advertising: {error}")
        else:
            print("DEBUG: Started advertising successfully")


class CoreBluetoothBLEProvider(BLEProvider):
    """
    macOS BLE provider using CoreBluetooth.
    
    Supports both scanning (via bleak) and GATT server (via CoreBluetooth).
    """

    def __init__(self):
        self._peripheral_manager: Optional[CBPeripheralManager] = None
        self._delegate: Optional[_PeripheralManagerDelegate] = None
        self._advertising = False
        self._on_read_callback: Optional[Callable[[str], Awaitable[bytes]]] = None
        self._on_write_callback: Optional[Callable[[str, bytes], Awaitable[None]]] = None

    async def start_scan(
        self,
        on_device_found: Callable[[DiscoveredDevice], Awaitable[None]],
        timeout: float = 30.0,
    ) -> None:
        """
        Start scanning for MTA devices.
        
        Uses bleak for scanning since CoreBluetooth central is complex.
        """
        # Import bleak directly to avoid circular import with BleakBLEProvider
        from bleak import BleakScanner
        from bleak.backends.device import BLEDevice
        from bleak.backends.scanner import AdvertisementData
        
        from ..constants import ADV_SERVICE_UUID
        
        seen_devices: set[str] = set()
        
        def detection_callback(device: BLEDevice, adv_data: AdvertisementData):
            service_uuid_str = str(ADV_SERVICE_UUID)
            if service_uuid_str not in adv_data.service_uuids:
                return
            
            if device.address in seen_devices:
                return
            seen_devices.add(device.address)
            
            discovered = DiscoveredDevice(
                address=device.address,
                name=device.name or "Unknown",
                rssi=adv_data.rssi or -100,
                supports_5ghz=True,
            )
            
            import asyncio
            asyncio.create_task(on_device_found(discovered))
        
        scanner = BleakScanner(detection_callback=detection_callback)
        await scanner.start()
        await asyncio.sleep(timeout)
        await scanner.stop()

    async def stop_scan(self) -> None:
        """Stop scanning for devices."""
        pass  # Scanner is stopped automatically after timeout

    async def start_advertising(
        self,
        name: str,
        service_uuid: str,
        service_data: Optional[dict[str, bytes]] = None,
    ) -> None:
        """Start advertising as an MTA device."""
        if self._peripheral_manager is None:
            raise RuntimeError("Call setup_gatt_server before start_advertising")
        
        # Build advertisement data
        from ..constants import ADV_SERVICE_UUID
        adv_svc_cbuuid = CBUUID.UUIDWithString_(str(ADV_SERVICE_UUID))
        
        # MTA specifically wants these service data segments for discovery
        # segment 1: 000001ff... -> 6 bytes (random)
        # segment 2: 0000ffff... -> 27 bytes (name and flags)
        
        # Generate some random bytes for the discovery segments
        import os
        random_bytes = os.urandom(2)
        
        # Svc data 1 (000001ff...)
        svc_data_1_uuid_str = "000001ff-0000-1000-8000-00805f9b34fb"
        svc_data_1_value = NSData.dataWithBytes_length_(random_bytes + b"\x00"*4, 6)
        
        # Svc data 2 (0000ffff...) - contains the name
        svc_data_2_uuid_str = "0000ffff-0000-1000-8000-00805f9b34fb"
        name_bytes = name.encode("utf-8")[:16].ljust(16, b"\x00")
        # Format: 8 bytes zero, 2 bytes random, 16 bytes name, 1 byte flag
        svc_data_2_raw = b"\x00"*8 + random_bytes + name_bytes + b"\x01"
        svc_data_2_value = NSData.dataWithBytes_length_(svc_data_2_raw, 27)

        ad_data = {
            CBAdvertisementDataLocalNameKey: name,
            CBAdvertisementDataServiceUUIDsKey: [adv_svc_cbuuid],
            # Note: PyObjC requires the keys of kCBAdvDataServiceData to be strings, NOT CBUUIDs.
            "kCBAdvDataServiceData": {
                svc_data_1_uuid_str: svc_data_1_value,
                svc_data_2_uuid_str: svc_data_2_value,
            }
        }
        
        print(f"DEBUG: Starting advertising with name='{name}' and MTA service data")
        self._peripheral_manager.startAdvertising_(ad_data)
        self._advertising = True

    async def stop_advertising(self) -> None:
        """Stop BLE advertising."""
        if self._peripheral_manager and self._advertising:
            self._peripheral_manager.stopAdvertising()
            self._advertising = False

    async def setup_gatt_server(
        self,
        service_uuid: str,
        characteristics: dict[str, tuple[bool, bool]],
        on_read: Callable[[str], Awaitable[bytes]],
        on_write: Callable[[str, bytes], Awaitable[None]],
    ) -> None:
        """
        Setup GATT server with specified characteristics.
        
        Args:
            service_uuid: Service UUID to host
            characteristics: Dict mapping characteristic UUIDs to (readable, writable)
            on_read: Async callback for read requests
            on_write: Async callback for write requests
        """
        loop = asyncio.get_running_loop()
        
        self._on_read_callback = on_read
        self._on_write_callback = on_write
        
        # Create delegate
        self._delegate = _PeripheralManagerDelegate.alloc().initWithLoop_onRead_onWrite_(
            loop, on_read, on_write
        )
        
        # Create peripheral manager
        print("DEBUG: Initializing CBPeripheralManager...")
        
        # Try to get a background queue to avoid blocking the main thread
        # Note: On macOS with asyncio, avoiding the main thread hang requires
        # either a background queue (hard to create via PyObjC) or running
        # the asyncio loop in a background thread (implemented in demo.py).
        # We fallback to None (Main Queue) here.
        queue = None
        print("DEBUG: Using main dispatch queue (requires RunLoop in main thread)")

        self._peripheral_manager = CBPeripheralManager.alloc().initWithDelegate_queue_(
            self._delegate, queue
        )
        
        # Wait for Bluetooth to power on
        print("DEBUG: Waiting for Bluetooth to power on...")
        await self._delegate._state_event.wait()
        if not self._delegate._powered_on:
            raise RuntimeError("Bluetooth is not powered on")
        
        # Create service
        service_cbuuid = CBUUID.UUIDWithString_(service_uuid)
        service = CBMutableService.alloc().initWithType_primary_(service_cbuuid, True)
        
        # Create characteristics
        chars = []
        for char_uuid, (readable, writable) in characteristics.items():
            char_cbuuid = CBUUID.UUIDWithString_(char_uuid)
            
            properties = 0
            permissions = 0
            
            if readable:
                properties |= CBCharacteristicPropertyRead
                permissions |= CBAttributePermissionsReadable
            if writable:
                properties |= CBCharacteristicPropertyWrite
                properties |= CBCharacteristicPropertyWriteWithoutResponse
                permissions |= CBAttributePermissionsWriteable
            
            char = CBMutableCharacteristic.alloc().initWithType_properties_value_permissions_(
                char_cbuuid, properties, None, permissions
            )
            chars.append(char)
            self._delegate._characteristics[char_uuid.lower()] = char
        
        service.setCharacteristics_(chars)
        
        # Add service to peripheral manager
        self._peripheral_manager.addService_(service)
        
        # Small delay to allow service registration
        await asyncio.sleep(0.5)

    async def stop_gatt_server(self) -> None:
        """Stop the GATT server."""
        if self._peripheral_manager:
            self._peripheral_manager.stopAdvertising()
            self._peripheral_manager.removeAllServices()
            self._peripheral_manager = None
            self._delegate = None

    async def connect(self, address: str) -> BLEConnection:
        """
        Connect to a device by address.
        
        Uses bleak for client connections.
        """
        from .bleak_driver import BleakBLEProvider
        provider = BleakBLEProvider()
        return await provider.connect(address)


def get_macos_ble_provider() -> BLEProvider:
    """Get the macOS-specific BLE provider with GATT server support."""
    return CoreBluetoothBLEProvider()
