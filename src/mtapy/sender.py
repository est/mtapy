"""
Sans-io sender protocol for MTA file transfers.

This module contains the protocol logic without any I/O operations.
Users can integrate this with their preferred async framework.
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, List, Generator, Tuple, Any, Dict
import json

from .models import SendRequest, TransferStatus, generate_sender_id, generate_task_id
from .protocol import (
    WSMessage,
    make_version_negotiation,
    make_send_request,
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


class SenderState(Enum):
    """Sender protocol state."""
    INITIAL = auto()
    SENT_VERSION = auto()
    SENT_REQUEST = auto()
    WAITING_DOWNLOAD = auto()
    TRANSFERRING = auto()
    COMPLETED = auto()
    REJECTED = auto()
    FAILED = auto()


@dataclass
class SenderEvent:
    """Base class for sender events."""
    pass


@dataclass
class HandshakeStarted(SenderEvent):
    """Handshake started, version negotiation sent."""
    pass


@dataclass
class VersionAcked(SenderEvent):
    """Version negotiation acknowledged."""
    version: int


@dataclass
class RequestSent(SenderEvent):
    """Send request sent, waiting for acceptance."""
    task_id: str


@dataclass
class TransferStarted(SenderEvent):
    """Transfer started (download request received)."""
    task_id: str


@dataclass
class TransferCompleted(SenderEvent):
    """Transfer completed successfully."""
    task_id: str


@dataclass
class TransferRejected(SenderEvent):
    """Transfer rejected by receiver."""
    reason: str


@dataclass
class SenderProtocolError(SenderEvent):
    """Protocol error occurred."""
    message: str


@dataclass 
class FileSpec:
    """Specification for a file to send."""
    name: str
    size: int
    mime_type: str = "application/octet-stream"
    text_content: Optional[str] = None


class SenderProtocol:
    """
    Sans-io sender protocol state machine.
    
    Usage:
        protocol = SenderProtocol(device_name="My Device")
        protocol.set_files([FileSpec("file.txt", 1234)])
        
        # Get initial messages to send
        messages = protocol.start_handshake()
        for msg in messages:
            websocket.send(msg.serialize())
        
        # Process incoming messages
        for msg in websocket_messages:
            parsed = WSMessage.parse(msg)
            for event, response in protocol.on_ws_message(parsed):
                if response:
                    websocket.send(response.serialize())
                handle_event(event)
    """

    def __init__(
        self,
        device_name: str = "MTA Device",
        sender_id: Optional[str] = None,
    ):
        """
        Initialize sender protocol.
        
        Args:
            device_name: Name to display on receiver
            sender_id: Optional sender ID (random if not provided)
        """
        self.device_name = device_name
        self.sender_id = sender_id or generate_sender_id()
        self.task_id = generate_task_id()
        self.state = SenderState.INITIAL
        self.version = PROTOCOL_VERSION
        self._files: List[FileSpec] = []
        self._msg_id = 0
        self._version_ack_received = False
        self._request_ack_received = False

    def set_files(self, files: List[FileSpec]) -> None:
        """Set the files to send."""
        self._files = files

    def _next_msg_id(self) -> int:
        """Get next message ID."""
        msg_id = self._msg_id
        self._msg_id += 1
        return msg_id

    def _build_send_request(self) -> SendRequest:
        """Build SendRequest from configured files."""
        total_size = sum(f.size for f in self._files)
        file_count = len(self._files)
        
        # Determine mime type
        if file_count == 1:
            mime_type = self._files[0].mime_type
        else:
            mime_types = set(f.mime_type for f in self._files)
            mime_type = "*/*" if len(mime_types) > 1 else next(iter(mime_types))
        
        # Check for text content (single file text share)
        text_content = None
        if file_count == 1 and self._files[0].text_content is not None:
            text_content = self._files[0].text_content
        
        return SendRequest(
            task_id=self.task_id,
            sender_id=self.sender_id,
            sender_name=self.device_name,
            file_name=self._files[0].name if self._files else "",
            mime_type=mime_type,
            file_count=file_count,
            total_size=total_size,
            text_content=text_content,
        )

    def start_handshake(self) -> List[WSMessage]:
        """
        Start the handshake by sending version negotiation.
        
        Returns:
            List of messages to send (just version negotiation).
        """
        self.state = SenderState.SENT_VERSION
        return [make_version_negotiation(self._next_msg_id(), self.version)]

    def on_ws_message(
        self, msg: WSMessage
    ) -> Generator[Tuple[Optional[SenderEvent], Optional[WSMessage]], None, None]:
        """
        Process incoming WebSocket message.
        
        Args:
            msg: Parsed WebSocket message
            
        Yields:
            Tuple of (event, response_message)
        """
        if msg.type == WS_TYPE_ACK:
            # Handle ACK messages
            name_lower = msg.name.lower()
            
            if name_lower == WS_ACTION_VERSION_NEGOTIATION.lower():
                # Version negotiation ACK
                self._version_ack_received = True
                acked_version = msg.payload.get("version", 1) if msg.payload else 1
                self.version = min(acked_version, self.version)
                
                # Now send the actual request
                request = self._build_send_request()
                request_msg = make_send_request(self._next_msg_id(), request.to_dict())
                self.state = SenderState.SENT_REQUEST
                
                yield (VersionAcked(version=self.version), request_msg)

            elif name_lower == WS_ACTION_SEND_REQUEST.lower():
                # Request ACK - waiting for download
                self._request_ack_received = True
                self.state = SenderState.WAITING_DOWNLOAD
                yield (RequestSent(task_id=self.task_id), None)

            elif name_lower == WS_ACTION_STATUS.lower():
                # Status ACK - just acknowledge
                yield (None, None)

        elif msg.type == WS_TYPE_ACTION:
            # Handle action messages
            name_lower = msg.name.lower()
            
            if name_lower == WS_ACTION_STATUS.lower():
                # Status from receiver
                if msg.payload is None:
                    yield (SenderProtocolError("status has no payload"), msg.make_ack())
                    return

                status = TransferStatus.from_dict(msg.payload)
                
                if status.type == STATUS_USER_REFUSE:
                    self.state = SenderState.REJECTED
                    yield (TransferRejected(reason=status.reason), msg.make_ack())
                elif status.type == STATUS_OK:
                    self.state = SenderState.COMPLETED
                    yield (TransferCompleted(task_id=self.task_id), msg.make_ack())
                else:
                    yield (None, msg.make_ack())

            else:
                # Unknown action, just ACK
                yield (None, msg.make_ack())

    def on_download_started(self) -> TransferStarted:
        """
        Call when HTTP download request is received.
        
        Returns:
            TransferStarted event.
        """
        self.state = SenderState.TRANSFERRING
        return TransferStarted(task_id=self.task_id)

    def check_task_id(self, request_task_id: str) -> bool:
        """Check if the task ID matches the current transfer."""
        return request_task_id == self.task_id
