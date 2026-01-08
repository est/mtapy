"""Tests for WebSocket message protocol."""

import pytest
from mtapy.protocol import WSMessage, make_status, make_version_negotiation


def test_parse_action_message_with_payload():
    """Test parsing action message with JSON payload."""
    text = 'action:0:versionNegotiation?{"version":1,"versions":[1]}'
    msg = WSMessage.parse(text)
    
    assert msg is not None
    assert msg.type == "action"
    assert msg.id == 0
    assert msg.name == "versionNegotiation"
    assert msg.payload == {"version": 1, "versions": [1]}


def test_parse_action_message_without_payload():
    """Test parsing action message without payload."""
    text = "action:5:status"
    msg = WSMessage.parse(text)
    
    assert msg is not None
    assert msg.type == "action"
    assert msg.id == 5
    assert msg.name == "status"
    assert msg.payload is None


def test_parse_ack_message():
    """Test parsing ACK message."""
    text = 'ack:1:sendRequest?{"accepted":true}'
    msg = WSMessage.parse(text)
    
    assert msg is not None
    assert msg.type == "ack"
    assert msg.id == 1
    assert msg.name == "sendRequest"
    assert msg.payload == {"accepted": True}


def test_parse_invalid_message():
    """Test parsing invalid message returns None."""
    assert WSMessage.parse("invalid") is None
    assert WSMessage.parse("") is None
    assert WSMessage.parse("action:abc:test") is None  # Invalid ID


def test_serialize_message_with_payload():
    """Test serializing message with payload."""
    msg = WSMessage(
        type="action",
        id=0,
        name="test",
        payload={"key": "value"},
    )
    
    result = msg.serialize()
    assert result == 'action:0:test?{"key":"value"}'


def test_serialize_message_without_payload():
    """Test serializing message without payload."""
    msg = WSMessage(type="ack", id=1, name="test")
    
    result = msg.serialize()
    assert result == "ack:1:test"


def test_serialize_with_new_id():
    """Test serializing with overridden ID."""
    msg = WSMessage(type="action", id=0, name="test")
    
    result = msg.serialize(new_id=99)
    assert result == "action:99:test"


def test_roundtrip():
    """Test parse -> serialize roundtrip."""
    original = 'action:5:sendRequest?{"taskId":"123"}'
    msg = WSMessage.parse(original)
    assert msg is not None
    
    # Note: JSON serialization may differ in whitespace
    reparsed = WSMessage.parse(msg.serialize())
    assert reparsed is not None
    assert reparsed.type == msg.type
    assert reparsed.id == msg.id
    assert reparsed.name == msg.name
    assert reparsed.payload == msg.payload


def test_make_ack():
    """Test creating ACK from action message."""
    action = WSMessage(
        type="action",
        id=5,
        name="versionNegotiation",
        payload={"version": 1},
    )
    
    ack = action.make_ack({"version": 1, "threadLimit": 5})
    
    assert ack.type == "ack"
    assert ack.id == 5
    assert ack.name == "versionNegotiation"
    assert ack.payload == {"version": 1, "threadLimit": 5}


def test_make_version_negotiation():
    """Test version negotiation helper."""
    msg = make_version_negotiation(0, 1)
    
    assert msg.type == "action"
    assert msg.id == 0
    assert msg.name == "versionNegotiation"
    assert msg.payload["version"] == 1
    assert msg.payload["versions"] == [1]


def test_make_status():
    """Test status message helper."""
    msg = make_status(99, "task123", 1, "ok")
    
    assert msg.type == "action"
    assert msg.id == 99
    assert msg.name == "status"
    assert msg.payload["taskId"] == "task123"
    assert msg.payload["type"] == 1
    assert msg.payload["reason"] == "ok"
