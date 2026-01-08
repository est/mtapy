"""
Abstract interfaces for platform-specific components.

Users can implement these interfaces to use different crypto libraries,
BLE stacks, or WiFi P2P implementations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List, AsyncIterator, Callable, Awaitable
import asyncio

from .models import DeviceInfo, P2pInfo


class SessionCipher(ABC):
    """Abstract cipher for encrypting/decrypting P2P credentials."""
    
    @abstractmethod
    def encrypt(self, data: str) -> str:
        """Encrypt a string, return base64-encoded ciphertext."""
        pass

    @abstractmethod
    def decrypt(self, encoded_data: str) -> str:
        """Decrypt base64-encoded ciphertext, return plaintext."""
        pass


class CryptoProvider(ABC):
    """
    Abstract crypto provider for ECDH key exchange and AES encryption.
    
    Default implementation uses the `cryptography` library.
    Users can provide their own implementation (e.g., using PyCryptodome).
    """

    @abstractmethod
    def get_public_key(self) -> str:
        """Get base64-encoded public key for key exchange."""
        pass

    @abstractmethod
    def derive_session_cipher(self, peer_public_key: str) -> SessionCipher:
        """
        Derive a session cipher from peer's public key using ECDH.
        
        Args:
            peer_public_key: Base64-encoded X.509 SubjectPublicKeyInfo
            
        Returns:
            A SessionCipher for encrypting/decrypting P2P credentials.
        """
        pass


@dataclass
class DiscoveredDevice:
    """A device discovered via BLE scanning."""
    address: str  # BLE MAC address
    name: str
    rssi: int
    brand: Optional[str] = None
    supports_5ghz: bool = True
    raw_data: Optional[bytes] = None


class BLEProvider(ABC):
    """
    Abstract BLE provider for device discovery and GATT operations.
    
    Default implementations provided for Windows/macOS/Linux using bleak.
    """

    @abstractmethod
    async def start_scan(
        self,
        on_device_found: Callable[[DiscoveredDevice], Awaitable[None]],
        timeout: float = 30.0,
    ) -> None:
        """
        Start scanning for MTA devices.
        
        Args:
            on_device_found: Async callback when device is discovered
            timeout: Scan timeout in seconds
        """
        pass

    @abstractmethod
    async def stop_scan(self) -> None:
        """Stop scanning for devices."""
        pass

    @abstractmethod
    async def connect(self, address: str) -> "BLEConnection":
        """
        Connect to a device by address.
        
        Args:
            address: BLE MAC address
            
        Returns:
            A BLEConnection for GATT operations.
        """
        pass


class BLEConnection(ABC):
    """Abstract BLE GATT connection."""

    @abstractmethod
    async def read_device_info(self) -> DeviceInfo:
        """Read DeviceInfo from CHAR_STATUS characteristic."""
        pass

    @abstractmethod
    async def write_p2p_info(self, p2p_info: P2pInfo) -> None:
        """Write P2pInfo to CHAR_P2P characteristic."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the device."""
        pass


class WiFiP2PProvider(ABC):
    """
    Abstract WiFi P2P (WiFi Direct) provider.
    
    Platform-specific implementations handle the actual P2P group
    creation and management.
    """

    @abstractmethod
    async def create_group(
        self,
        ssid: str,
        passphrase: str,
        band: str = "auto",  # "2.4ghz", "5ghz", "auto"
    ) -> "WiFiP2PGroup":
        """
        Create a WiFi P2P group as group owner.
        
        Args:
            ssid: Network name (e.g., "DIRECT-XXXXXXXX")
            passphrase: Network password
            band: Frequency band preference
            
        Returns:
            A WiFiP2PGroup representing the created group.
        """
        pass

    @abstractmethod
    async def connect_to_group(
        self,
        ssid: str,
        passphrase: str,
    ) -> "WiFiP2PGroup":
        """
        Connect to an existing WiFi P2P group.
        
        Args:
            ssid: Network name
            passphrase: Network password
            
        Returns:
            A WiFiP2PGroup representing the joined group.
        """
        pass

    @abstractmethod
    def get_mac_address(self) -> str:
        """Get the P2P interface MAC address."""
        pass


class WiFiP2PGroup(ABC):
    """Abstract WiFi P2P group."""

    @property
    @abstractmethod
    def group_owner_address(self) -> str:
        """Get the group owner's IP address."""
        pass

    @property
    @abstractmethod
    def is_group_owner(self) -> bool:
        """Check if we are the group owner."""
        pass

    @abstractmethod
    async def wait_for_client(self, timeout: float = 30.0) -> Optional[str]:
        """
        Wait for a client to connect (when group owner).
        
        Returns:
            Client's IP address, or None on timeout.
        """
        pass

    @abstractmethod
    async def remove(self) -> None:
        """Remove/leave the P2P group."""
        pass
