"""
Default BLE implementation using the `bleak` library.

Provides device discovery and GATT operations for Windows/macOS/Linux.

For platform-specific implementations (e.g., macOS GATT server),
see the mtapy.drivers module.
"""

# Re-export everything from drivers for backwards compatibility
from .drivers.bleak_driver import (
    BleakBLEProvider,
    BleakBLEConnection,
    parse_scan_response,
)
from .drivers import get_ble_provider as get_default_ble_provider

__all__ = [
    "BleakBLEProvider",
    "BleakBLEConnection",
    "parse_scan_response",
    "get_default_ble_provider",
]
