"""
WebSocket message protocol for MTA.

Message format: type:id:name?payload
- type: "action" or "ack"
- id: message ID (integer)
- name: action name
- payload: optional JSON object
"""

import re
import json
from dataclasses import dataclass
from typing import Optional, Dict, Any

from .constants import (
    WS_TYPE_ACTION,
    WS_TYPE_ACK,
    WS_ACTION_STATUS,
)


# Pattern: type:id:name?json_payload
MESSAGE_PATTERN = re.compile(r"^(\w+):(\d+):(\w+)(\?(.*))?$")


@dataclass
class WSMessage:
    """WebSocket message in MTA protocol."""
    type: str  # "action" or "ack"
    id: int
    name: str
    payload: Optional[Dict[str, Any]] = None

    def serialize(self, new_id: Optional[int] = None) -> str:
        """
        Serialize message to wire format.
        
        Args:
            new_id: Optional new message ID to use instead of self.id
            
        Returns:
            Message string in format "type:id:name?json"
        """
        msg_id = new_id if new_id is not None else self.id
        result = f"{self.type}:{msg_id}:{self.name}"
        if self.payload is not None:
            result += "?" + json.dumps(self.payload, separators=(",", ":"))
        return result

    @classmethod
    def parse(cls, text: str) -> Optional["WSMessage"]:
        """
        Parse message from wire format.
        
        Args:
            text: Message string in format "type:id:name?json"
            
        Returns:
            WSMessage if parsing successful, None otherwise.
        """
        match = MESSAGE_PATTERN.match(text)
        if not match:
            return None

        json_text = match.group(5)
        payload = None
        if json_text:
            try:
                payload = json.loads(json_text)
            except json.JSONDecodeError:
                return None

        return cls(
            type=match.group(1),
            id=int(match.group(2)),
            name=match.group(3),
            payload=payload,
        )

    def make_ack(self, response_payload: Optional[Dict[str, Any]] = None) -> "WSMessage":
        """
        Create an ACK message in response to this message.
        
        Args:
            response_payload: Optional payload to include in ACK
            
        Returns:
            ACK message with same id and name.
        """
        return WSMessage(
            type=WS_TYPE_ACK,
            id=self.id,
            name=self.name,
            payload=response_payload,
        )


def make_version_negotiation(msg_id: int = 0, version: int = 1) -> WSMessage:
    """Create a version negotiation action message."""
    return WSMessage(
        type=WS_TYPE_ACTION,
        id=msg_id,
        name="versionNegotiation",
        payload={
            "version": version,
            "versions": [version],
        },
    )


def make_send_request(msg_id: int, request_dict: Dict[str, Any]) -> WSMessage:
    """Create a send request action message."""
    return WSMessage(
        type=WS_TYPE_ACTION,
        id=msg_id,
        name="sendRequest",
        payload=request_dict,
    )


def make_status(
    msg_id: int,
    task_id: str,
    status_type: int,
    reason: str,
) -> WSMessage:
    """
    Create a status action message.
    
    Args:
        msg_id: Message ID
        task_id: Transfer task ID
        status_type: 1=ok, 2=error, 3=user_refuse
        reason: Status reason string
        
    Returns:
        Status action message.
    """
    return WSMessage(
        type=WS_TYPE_ACTION,
        id=msg_id,
        name=WS_ACTION_STATUS,
        payload={
            "taskId": task_id,
            "id": task_id,
            "type": status_type,
            "reason": reason,
        },
    )
