"""
Sans-io receiver protocol for MTA file transfers.

This module contains the protocol logic without any I/O operations.
Users can integrate this with their preferred async framework.
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, List, Generator, Tuple, Any, Dict
import json

from .models import SendRequest, TransferStatus
from .protocol import (
    WSMessage,
    make_version_negotiation,
    make_status,
)
from .constants import (
    WS_TYPE_ACTION,
    WS_TYPE_ACK,
    WS_ACTION_VERSION_NEGOTIATION,
    WS_ACTION_SEND_REQUEST,
    WS_ACTION_STATUS,
    STATUS_OK,
    STATUS_USER_REFUSE,
    PROTOCOL_VERSION,
)


class ReceiverState(Enum):
    """Receiver protocol state."""
    WAITING_VERSION = auto()
    WAITING_SEND_REQUEST = auto()
    WAITING_USER_ACCEPT = auto()
    TRANSFERRING = auto()
    COMPLETED = auto()
    FAILED = auto()


@dataclass
class ReceiverEvent:
    """Base class for receiver events."""
    pass


@dataclass
class VersionNegotiated(ReceiverEvent):
    """Version negotiation completed."""
    version: int
    thread_limit: int = 5


@dataclass
class SendRequestReceived(ReceiverEvent):
    """Send request received, waiting for user acceptance."""
    request: SendRequest
    thumbnail_path: Optional[str] = None


@dataclass
class TransferAccepted(ReceiverEvent):
    """User accepted the transfer, ready to download."""
    task_id: str
    download_url: str


@dataclass
class TextReceived(ReceiverEvent):
    """Text content received (clipboard share)."""
    text: str
    task_id: str


@dataclass
class StatusReceived(ReceiverEvent):
    """Status message received from sender."""
    status: TransferStatus


@dataclass
class ProtocolError(ReceiverEvent):
    """Protocol error occurred."""
    message: str


class ReceiverProtocol:
    """
    Sans-io receiver protocol state machine.
    
    Usage:
        protocol = ReceiverProtocol(server_host, server_port)
        
        for msg in websocket_messages:
            parsed = WSMessage.parse(msg)
            for event, response in protocol.on_ws_message(parsed):
                if response:
                    websocket.send(response.serialize())
                handle_event(event)
    """

    def __init__(self, server_host: str, server_port: int):
        """
        Initialize receiver protocol.
        
        Args:
            server_host: Sender's HTTP server host
            server_port: Sender's HTTP server port
        """
        self.server_host = server_host
        self.server_port = server_port
        self.state = ReceiverState.WAITING_VERSION
        self.version = PROTOCOL_VERSION
        self.thread_limit = 5
        self._send_request: Optional[SendRequest] = None
        self._msg_id_counter = 99

    def _next_msg_id(self) -> int:
        """Get next message ID for outgoing messages."""
        self._msg_id_counter += 1
        return self._msg_id_counter

    def on_ws_message(
        self, msg: WSMessage
    ) -> Generator[Tuple[Optional[ReceiverEvent], Optional[WSMessage]], None, None]:
        """
        Process incoming WebSocket message.
        
        Args:
            msg: Parsed WebSocket message
            
        Yields:
            Tuple of (event, response_message)
            - event may be None if no event to emit
            - response_message may be None if no response needed
        """
        if msg.type != WS_TYPE_ACTION:
            # We only care about action messages
            return

        name_lower = msg.name.lower()
        
        if name_lower == WS_ACTION_VERSION_NEGOTIATION.lower():
            # Version negotiation
            in_version = msg.payload.get("version", 1) if msg.payload else 1
            self.version = min(in_version, PROTOCOL_VERSION)
            
            response_payload = {
                "version": self.version,
                "threadLimit": self.thread_limit,
            }
            
            self.state = ReceiverState.WAITING_SEND_REQUEST
            yield (
                VersionNegotiated(version=self.version, thread_limit=self.thread_limit),
                msg.make_ack(response_payload),
            )

        elif name_lower == WS_ACTION_SEND_REQUEST.lower():
            # Send request
            if msg.payload is None:
                yield (ProtocolError("sendRequest has no payload"), msg.make_ack())
                return

            self._send_request = SendRequest.from_dict(msg.payload)
            self.state = ReceiverState.WAITING_USER_ACCEPT
            
            thumbnail_path = self._send_request.thumbnail
            
            # Check if this is a text share
            if self._send_request.text_content is not None:
                yield (
                    TextReceived(
                        text=self._send_request.text_content,
                        task_id=self._send_request.task_id,
                    ),
                    msg.make_ack(),
                )
            else:
                yield (
                    SendRequestReceived(
                        request=self._send_request,
                        thumbnail_path=thumbnail_path,
                    ),
                    msg.make_ack(),
                )

        elif name_lower == WS_ACTION_STATUS.lower():
            # Status message
            if msg.payload is None:
                yield (ProtocolError("status has no payload"), msg.make_ack())
                return

            status = TransferStatus.from_dict(msg.payload)
            
            if status.type == STATUS_USER_REFUSE and status.reason == "user refuse":
                self.state = ReceiverState.FAILED
            
            yield (StatusReceived(status=status), msg.make_ack())

        else:
            # Unknown action, just ack
            yield (None, msg.make_ack())

    def accept_transfer(self) -> Tuple[Optional[TransferAccepted], Optional[WSMessage]]:
        """
        Accept the transfer request.
        
        Returns:
            Tuple of (event, status_message_to_send)
        """
        if self._send_request is None:
            return (None, None)

        self.state = ReceiverState.TRANSFERRING
        download_url = f"https://{self.server_host}:{self.server_port}/download?taskId={self._send_request.task_id}"
        
        return (
            TransferAccepted(
                task_id=self._send_request.task_id,
                download_url=download_url,
            ),
            None,  # No immediate message needed
        )

    def reject_transfer(self) -> WSMessage:
        """
        Reject the transfer request.
        
        Returns:
            Status message to send to reject the transfer.
        """
        task_id = self._send_request.task_id if self._send_request else ""
        self.state = ReceiverState.FAILED
        return make_status(self._next_msg_id(), task_id, STATUS_USER_REFUSE, "user refuse")

    def send_ok(self) -> WSMessage:
        """
        Send OK status after successful transfer.
        
        Returns:
            Status message to send.
        """
        task_id = self._send_request.task_id if self._send_request else ""
        self.state = ReceiverState.COMPLETED
        return make_status(self._next_msg_id(), task_id, STATUS_OK, "ok")

    def get_thumbnail_url(self) -> Optional[str]:
        """Get the full thumbnail URL if available."""
        if self._send_request and self._send_request.thumbnail:
            return f"https://{self.server_host}:{self.server_port}{self._send_request.thumbnail}"
        return None
