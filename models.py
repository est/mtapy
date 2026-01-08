"""
Data models for MTA protocol.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional
import json
import random


@dataclass
class DeviceInfo:
    """Device information advertised via BLE GATT."""
    state: int
    mac: str
    key: Optional[str] = None
    catshare: Optional[int] = None

    def to_json(self) -> str:
        """Serialize to JSON string."""
        d = {"state": self.state, "mac": self.mac}
        if self.key is not None:
            d["key"] = self.key
        if self.catshare is not None:
            d["catShare"] = self.catshare
        return json.dumps(d)

    @classmethod
    def from_json(cls, data: str) -> "DeviceInfo":
        """Parse from JSON string."""
        d = json.loads(data)
        return cls(
            state=d.get("state", 0),
            mac=d["mac"],
            key=d.get("key"),
            catshare=d.get("catShare"),
        )


@dataclass
class P2pInfo:
    """P2P connection info exchanged via BLE GATT."""
    ssid: str
    psk: str
    mac: str
    port: int
    id: Optional[str] = None
    key: Optional[str] = None
    catshare: Optional[int] = None

    def to_json(self) -> str:
        """Serialize to JSON string."""
        d = {
            "ssid": self.ssid,
            "psk": self.psk,
            "mac": self.mac,
            "port": self.port,
        }
        if self.id is not None:
            d["id"] = self.id
        if self.key is not None:
            d["key"] = self.key
        if self.catshare is not None:
            d["catShare"] = self.catshare
        return json.dumps(d)

    @classmethod
    def from_json(cls, data: str) -> "P2pInfo":
        """Parse from JSON string."""
        d = json.loads(data)
        return cls(
            ssid=d["ssid"],
            psk=d["psk"],
            mac=d["mac"],
            port=d["port"],
            id=d.get("id"),
            key=d.get("key"),
            catshare=d.get("catShare"),
        )


@dataclass
class SendRequest:
    """File transfer request sent via WebSocket."""
    task_id: str
    sender_id: str
    sender_name: str
    file_name: str
    file_count: int
    total_size: int
    mime_type: str = "*/*"
    text_content: Optional[str] = None
    thumbnail: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        d = {
            "taskId": self.task_id,
            "id": self.task_id,
            "senderId": self.sender_id,
            "senderName": self.sender_name,
            "fileName": self.file_name,
            "mimeType": self.mime_type,
            "fileCount": self.file_count,
            "totalSize": self.total_size,
        }
        if self.text_content is not None:
            d["catShareText"] = self.text_content
        if self.thumbnail is not None:
            d["thumbnail"] = self.thumbnail
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "SendRequest":
        """Parse from dictionary."""
        task_id = d.get("taskId") or d.get("id", "")
        return cls(
            task_id=task_id,
            sender_id=d.get("senderId", ""),
            sender_name=d.get("senderName", "Unknown"),
            file_name=d.get("fileName", ""),
            mime_type=d.get("mimeType", "*/*"),
            file_count=d.get("fileCount", 1),
            total_size=d.get("totalSize", 0),
            text_content=d.get("catShareText"),
            thumbnail=d.get("thumbnail"),
        )


@dataclass
class TransferStatus:
    """Transfer status message."""
    type: int
    reason: str
    task_id: str

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "taskId": self.task_id,
            "id": self.task_id,
            "type": self.type,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TransferStatus":
        """Parse from dictionary."""
        task_id = d.get("taskId") or d.get("id", "")
        return cls(
            type=d.get("type", 0),
            reason=d.get("reason", ""),
            task_id=task_id,
        )


def generate_sender_id() -> str:
    """Generate a random 4-character hex sender ID."""
    return f"{random.randint(0, 0xFFFF):04x}"


def generate_task_id() -> str:
    """Generate a random task ID."""
    return str(random.randint(100000, 999999))
