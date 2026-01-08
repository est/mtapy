"""Tests for data models."""

import pytest
from mtapy.models import DeviceInfo, P2pInfo, SendRequest, TransferStatus


def test_device_info_to_json():
    """Test DeviceInfo JSON serialization."""
    info = DeviceInfo(state=0, mac="aa:bb:cc:dd:ee:ff", key="abc123", catshare=1)
    json_str = info.to_json()
    
    assert '"state":0' in json_str or '"state": 0' in json_str
    assert '"mac":"aa:bb:cc:dd:ee:ff"' in json_str or '"mac": "aa:bb:cc:dd:ee:ff"' in json_str


def test_device_info_from_json():
    """Test DeviceInfo JSON parsing."""
    json_str = '{"state": 0, "mac": "aa:bb:cc:dd:ee:ff", "key": "xyz", "catShare": 2}'
    info = DeviceInfo.from_json(json_str)
    
    assert info.state == 0
    assert info.mac == "aa:bb:cc:dd:ee:ff"
    assert info.key == "xyz"
    assert info.catshare == 2


def test_p2p_info_roundtrip():
    """Test P2pInfo JSON roundtrip."""
    original = P2pInfo(
        ssid="DIRECT-TEST",
        psk="password123",
        mac="11:22:33:44:55:66",
        port=8443,
        id="1234",
    )
    
    json_str = original.to_json()
    parsed = P2pInfo.from_json(json_str)
    
    assert parsed.ssid == original.ssid
    assert parsed.psk == original.psk
    assert parsed.mac == original.mac
    assert parsed.port == original.port
    assert parsed.id == original.id


def test_send_request_to_dict():
    """Test SendRequest dictionary serialization."""
    request = SendRequest(
        task_id="123456",
        sender_id="abcd",
        sender_name="Test Device",
        file_name="photo.jpg",
        file_count=1,
        total_size=1024,
        mime_type="image/jpeg",
    )
    
    d = request.to_dict()
    
    assert d["taskId"] == "123456"
    assert d["id"] == "123456"  # Both taskId and id
    assert d["senderId"] == "abcd"
    assert d["senderName"] == "Test Device"
    assert d["fileName"] == "photo.jpg"
    assert d["fileCount"] == 1
    assert d["totalSize"] == 1024
    assert "catShareText" not in d  # No text content


def test_send_request_with_text():
    """Test SendRequest with text content."""
    request = SendRequest(
        task_id="789",
        sender_id="efgh",
        sender_name="Text Sender",
        file_name="text.txt",
        file_count=1,
        total_size=100,
        text_content="Hello, world!",
    )
    
    d = request.to_dict()
    assert d["catShareText"] == "Hello, world!"


def test_send_request_from_dict():
    """Test SendRequest parsing from dictionary."""
    d = {
        "taskId": "111",
        "senderId": "xyz",
        "senderName": "Sender",
        "fileName": "doc.pdf",
        "mimeType": "application/pdf",
        "fileCount": 3,
        "totalSize": 5000,
    }
    
    request = SendRequest.from_dict(d)
    
    assert request.task_id == "111"
    assert request.sender_id == "xyz"
    assert request.file_count == 3
    assert request.total_size == 5000


def test_transfer_status_roundtrip():
    """Test TransferStatus dictionary roundtrip."""
    original = TransferStatus(type=1, reason="ok", task_id="task999")
    
    d = original.to_dict()
    parsed = TransferStatus.from_dict(d)
    
    assert parsed.type == original.type
    assert parsed.reason == original.reason
    assert parsed.task_id == original.task_id
