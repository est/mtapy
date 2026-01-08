"""
mtapy - Python3 MTA (Mutual Transmission Alliance) Protocol Library

A sans-io implementation of the MTA file transfer protocol used by
Xiaomi, OPPO, vivo, OnePlus, Realme, and other Android manufacturers.
"""

from .models import (
    DeviceInfo,
    P2pInfo,
    SendRequest,
    TransferStatus,
    generate_sender_id,
    generate_task_id,
)
from .protocol import WSMessage, make_status, make_version_negotiation, make_send_request
from .interfaces import (
    CryptoProvider,
    SessionCipher,
    BLEProvider,
    BLEConnection,
    DiscoveredDevice,
    WiFiP2PProvider,
    WiFiP2PGroup,
)
from .receiver import (
    ReceiverProtocol,
    ReceiverState,
    ReceiverEvent,
    VersionNegotiated,
    SendRequestReceived,
    TransferAccepted,
    TextReceived,
    StatusReceived,
    ProtocolError,
)
from .sender import (
    SenderProtocol,
    SenderState,
    SenderEvent,
    FileSpec,
    HandshakeStarted,
    VersionAcked,
    RequestSent,
    TransferStarted,
    TransferCompleted,
    TransferRejected,
    SenderProtocolError,
)
from .constants import (
    ADV_SERVICE_UUID,
    SERVICE_UUID,
    CHAR_STATUS_UUID,
    CHAR_P2P_UUID,
    PROTOCOL_VERSION,
    STATUS_OK,
    STATUS_ERROR,
    STATUS_USER_REFUSE,
)

__version__ = "0.1.0"

__all__ = [
    # Version
    "__version__",
    # Models
    "DeviceInfo",
    "P2pInfo",
    "SendRequest",
    "TransferStatus",
    "generate_sender_id",
    "generate_task_id",
    # Protocol
    "WSMessage",
    "make_status",
    "make_version_negotiation",
    "make_send_request",
    # Interfaces
    "CryptoProvider",
    "SessionCipher",
    "BLEProvider",
    "BLEConnection",
    "DiscoveredDevice",
    "WiFiP2PProvider",
    "WiFiP2PGroup",
    # Receiver
    "ReceiverProtocol",
    "ReceiverState",
    "ReceiverEvent",
    "VersionNegotiated",
    "SendRequestReceived",
    "TransferAccepted",
    "TextReceived",
    "StatusReceived",
    "ProtocolError",
    # Sender
    "SenderProtocol",
    "SenderState",
    "SenderEvent",
    "FileSpec",
    "HandshakeStarted",
    "VersionAcked",
    "RequestSent",
    "TransferStarted",
    "TransferCompleted",
    "TransferRejected",
    "SenderProtocolError",
    # Constants
    "ADV_SERVICE_UUID",
    "SERVICE_UUID",
    "CHAR_STATUS_UUID",
    "CHAR_P2P_UUID",
    "PROTOCOL_VERSION",
    "STATUS_OK",
    "STATUS_ERROR",
    "STATUS_USER_REFUSE",
]


def get_crypto_provider() -> CryptoProvider:
    """Get the default crypto provider (requires cryptography)."""
    from .crypto import get_default_crypto_provider
    return get_default_crypto_provider()


def get_ble_provider() -> BLEProvider:
    """Get the default BLE provider (requires bleak)."""
    from .ble import get_default_ble_provider
    return get_default_ble_provider()


def get_wifi_p2p_provider() -> WiFiP2PProvider:
    """Get the default WiFi P2P provider for the current platform."""
    from .wifi_p2p import get_default_wifi_p2p_provider
    return get_default_wifi_p2p_provider()
