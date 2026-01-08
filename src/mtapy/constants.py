"""
Protocol constants for MTA.
"""

import uuid

# BLE Service and Characteristic UUIDs
ADV_SERVICE_UUID = uuid.UUID("00003331-0000-1000-8000-008123456789")
SERVICE_UUID = uuid.UUID("00009955-0000-1000-8000-00805f9b34fb")
CHAR_STATUS_UUID = uuid.UUID("00009954-0000-1000-8000-00805f9b34fb")
CHAR_P2P_UUID = uuid.UUID("00009953-0000-1000-8000-00805f9b34fb")

# Crypto constants
AES_IV = b"0102030405060708"

# WebSocket message types
WS_TYPE_ACTION = "action"
WS_TYPE_ACK = "ack"

# WebSocket action names
WS_ACTION_VERSION_NEGOTIATION = "versionNegotiation"
WS_ACTION_SEND_REQUEST = "sendRequest"
WS_ACTION_STATUS = "status"

# Status types
STATUS_OK = 1
STATUS_ERROR = 2
STATUS_USER_REFUSE = 3

# Protocol version
PROTOCOL_VERSION = 1
