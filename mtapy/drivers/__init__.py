"""
Platform-specific BLE drivers.

This module provides platform-specific implementations of the BLEProvider interface.

Available drivers:
- bleak: Cross-platform BLE client using bleak (Windows/macOS/Linux)
- macos: macOS native using CoreBluetooth (GATT server support)

Usage:
    from mtapy.drivers import get_ble_provider
    ble = get_ble_provider()  # Auto-selects based on platform
"""

from ..interfaces import BLEProvider


def get_ble_provider() -> BLEProvider:
    """
    Get the best BLE provider for the current platform.
    
    On macOS with pyobjc installed: Returns CoreBluetoothBLEProvider (GATT server support)
    Otherwise: Returns BleakBLEProvider (client-only)
    """
    import sys
    
    if sys.platform == "darwin":
        try:
            from .macos import CoreBluetoothBLEProvider
            return CoreBluetoothBLEProvider()
        except ImportError:
            pass  # pyobjc not installed
    
    from .bleak_driver import BleakBLEProvider
    return BleakBLEProvider()


__all__ = ["get_ble_provider", "BLEProvider"]
