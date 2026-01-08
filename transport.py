"""
Asyncio transport layer for MTA protocol.

Provides full sender and receiver implementations using asyncio,
websockets for WebSocket connections, and urllib for HTTP downloads.
"""

import asyncio
import ssl
import json
import io
import zipfile
import urllib.request
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Callable, Awaitable, BinaryIO, AsyncIterator
import tempfile
import os

from .models import P2pInfo, DeviceInfo, SendRequest
from .protocol import WSMessage
from .receiver import (
    ReceiverProtocol, ReceiverState, 
    SendRequestReceived, TextReceived, TransferAccepted,
    VersionNegotiated, StatusReceived,
)
from .sender import SenderProtocol, SenderState, FileSpec
from .interfaces import CryptoProvider, BLEProvider, WiFiP2PProvider
from .crypto import get_default_crypto_provider


@dataclass
class ReceivedFile:
    """A file received from a transfer."""
    name: str
    path: Path
    size: int


def _create_insecure_ssl_context() -> ssl.SSLContext:
    """Create SSL context that accepts self-signed certificates."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


class MTAReceiver:
    """
    High-level asyncio-based receiver for MTA file transfers.
    
    Usage:
        receiver = MTAReceiver(
            output_dir=Path("./downloads"),
            on_request=my_accept_callback,
        )
        await receiver.receive_from(p2p_info)
    """

    def __init__(
        self,
        output_dir: Path,
        on_request: Optional[Callable[[SendRequest], Awaitable[bool]]] = None,
        on_text: Optional[Callable[[str], Awaitable[None]]] = None,
        auto_accept: bool = False,
        crypto_provider: Optional[CryptoProvider] = None,
    ):
        """
        Initialize receiver.
        
        Args:
            output_dir: Directory to save received files
            on_request: Async callback to accept/reject transfers (return True to accept)
            on_text: Async callback for text shares
            auto_accept: If True, automatically accept all transfers
            crypto_provider: Optional crypto provider for encryption
        """
        self.output_dir = output_dir
        self.on_request = on_request
        self.on_text = on_text
        self.auto_accept = auto_accept
        self.crypto = crypto_provider or get_default_crypto_provider()
        
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def receive_from(
        self,
        host: str,
        port: int,
        timeout: float = 60.0,
    ) -> List[ReceivedFile]:
        """
        Receive files from a sender.
        
        Args:
            host: Sender's IP address (group owner address from P2P)
            port: Sender's HTTPS server port
            timeout: Connection timeout in seconds
            
        Returns:
            List of received files.
        """
        import websockets
        
        ssl_context = _create_insecure_ssl_context()
        ws_url = f"wss://{host}:{port}/websocket"
        
        protocol = ReceiverProtocol(host, port)
        received_files: List[ReceivedFile] = []

        async with websockets.connect(
            ws_url,
            ssl=ssl_context,
            close_timeout=10,
            open_timeout=timeout,
        ) as ws:
            async for raw_msg in ws:
                if isinstance(raw_msg, bytes):
                    raw_msg = raw_msg.decode("utf-8")
                
                msg = WSMessage.parse(raw_msg)
                if msg is None:
                    continue
                
                for event, response in protocol.on_ws_message(msg):
                    # Send response if any
                    if response:
                        await ws.send(response.serialize())
                    
                    # Handle events
                    if isinstance(event, VersionNegotiated):
                        pass  # Version negotiated, waiting for send request
                    
                    elif isinstance(event, TextReceived):
                        # Text share - call callback and send OK
                        if self.on_text:
                            await self.on_text(event.text)
                        ok_msg = protocol.send_ok()
                        await ws.send(ok_msg.serialize())
                        return []  # No files for text share
                    
                    elif isinstance(event, SendRequestReceived):
                        # Ask user to accept
                        accepted = self.auto_accept
                        if not accepted and self.on_request:
                            accepted = await self.on_request(event.request)
                        
                        if accepted:
                            accept_event, _ = protocol.accept_transfer()
                            if accept_event:
                                # Download files
                                received_files = await self._download_files(
                                    accept_event.download_url,
                                    ssl_context,
                                )
                                # Send OK status
                                ok_msg = protocol.send_ok()
                                await ws.send(ok_msg.serialize())
                                await asyncio.sleep(1)  # Give time for ACK
                                return received_files
                        else:
                            # Reject
                            reject_msg = protocol.reject_transfer()
                            await ws.send(reject_msg.serialize())
                            return []
                    
                    elif isinstance(event, StatusReceived):
                        # Status from sender (e.g., cancel)
                        if event.status.type == 3:  # User refuse
                            return []

        return received_files

    async def _download_files(
        self,
        download_url: str,
        ssl_context: ssl.SSLContext,
    ) -> List[ReceivedFile]:
        """Download and extract files from ZIP stream."""
        # Use urllib for HTTPS download (simpler than adding aiohttp)
        loop = asyncio.get_event_loop()
        
        def do_download():
            req = urllib.request.Request(download_url)
            with urllib.request.urlopen(req, context=ssl_context) as resp:
                return resp.read()
        
        data = await loop.run_in_executor(None, do_download)
        return extract_zip_stream(data, self.output_dir)


class MTASender:
    """
    High-level asyncio-based sender for MTA file transfers.
    
    Usage:
        sender = MTASender(
            device_name="My Device",
            files=[("/path/to/file.txt", "file.txt")],
        )
        await sender.send_to(ble_device)
    """

    def __init__(
        self,
        device_name: str = "MTA Device",
        files: Optional[List[tuple]] = None,  # List of (path, display_name)
        crypto_provider: Optional[CryptoProvider] = None,
        ble_provider: Optional[BLEProvider] = None,
        wifi_p2p_provider: Optional[WiFiP2PProvider] = None,
    ):
        """
        Initialize sender.
        
        Args:
            device_name: Device name to display on receiver
            files: List of (path, display_name) tuples
            crypto_provider: Optional crypto provider
            ble_provider: Optional BLE provider
            wifi_p2p_provider: Optional WiFi P2P provider
        """
        self.device_name = device_name
        self.files = files or []
        self.crypto = crypto_provider or get_default_crypto_provider()
        self._ble = ble_provider
        self._wifi_p2p = wifi_p2p_provider

    def add_file(self, path: str, display_name: Optional[str] = None) -> None:
        """Add a file to send."""
        p = Path(path)
        name = display_name or p.name
        self.files.append((str(p), name))

    def add_text(self, text: str, name: str = "shared_text.txt") -> None:
        """Add text content to share."""
        # Store as special file-like object
        self.files.append(("__text__", name, text))

    async def send_to(self, device_address: str) -> bool:
        """
        Send files to a device.
        
        Args:
            device_address: BLE address of the receiver
            
        Returns:
            True if transfer completed successfully.
        """
        # This requires full implementation with:
        # 1. BLE connect and read DeviceInfo
        # 2. Create WiFi P2P group
        # 3. Write P2pInfo to BLE
        # 4. Start HTTPS server
        # 5. Handle WebSocket and file download
        
        raise NotImplementedError(
            "Full sender implementation requires platform-specific WiFi P2P. "
            "Use SenderProtocol for sans-io integration."
        )


async def create_zip_stream(
    files: List[tuple],
) -> AsyncIterator[bytes]:
    """
    Create a ZIP stream from files.
    
    Args:
        files: List of (path, display_name) or (path, display_name, text_content)
        
    Yields:
        Chunks of ZIP data.
    """
    buffer = io.BytesIO()
    
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as zf:
        for i, item in enumerate(files):
            if len(item) == 3 and item[0] == "__text__":
                # Text content
                _, name, content = item
                zf.writestr(f"{i}/{name}", content.encode("utf-8"))
            else:
                # Regular file
                path, name = item[:2]
                zf.write(path, f"{i}/{name}")
    
    buffer.seek(0)
    
    # Yield in chunks
    while True:
        chunk = buffer.read(1024 * 1024)  # 1MB chunks
        if not chunk:
            break
        yield chunk


def extract_zip_stream(
    data: bytes,
    output_dir: Path,
) -> List[ReceivedFile]:
    """
    Extract files from a ZIP stream.
    
    Args:
        data: ZIP file data
        output_dir: Directory to extract to
        
    Returns:
        List of extracted files.
    """
    received = []
    
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            
            # Get just the filename (strip directory prefix)
            name = Path(info.filename).name
            out_path = output_dir / name
            
            # Handle name conflicts
            counter = 1
            while out_path.exists():
                stem = out_path.stem
                suffix = out_path.suffix
                out_path = output_dir / f"{stem}_{counter}{suffix}"
                counter += 1
            
            with zf.open(info) as src, open(out_path, "wb") as dst:
                dst.write(src.read())
            
            received.append(ReceivedFile(
                name=name,
                path=out_path,
                size=info.file_size,
            ))
    
    return received
