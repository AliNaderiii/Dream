"""Epidemic Gossip Protocol Engine for Decentralized State Synchronization."""

from __future__ import annotations

import random
import time
import uuid
from typing import Any

from dream.federation.types import GossipMessage, GossipMessageType, PeerNode


class GossipEngine:
    """Manages epidemic peer-to-peer gossip dissemination and message deduplication."""

    def __init__(self, fanout: int = 3, message_ttl: int = 4) -> None:
        self.fanout = fanout
        self.message_ttl = message_ttl
        self._seen_messages: set[str] = set()
        self._message_log: list[GossipMessage] = []

    def create_message(
        self,
        msg_type: GossipMessageType,
        sender_id: str,
        payload: dict[str, Any],
        target_node_id: str | None = None,
    ) -> GossipMessage:
        """Create a new standardized gossip envelope."""
        msg_id = f"gsp-{uuid.uuid4().hex[:8]}"
        msg = GossipMessage(
            message_id=msg_id,
            msg_type=msg_type,
            sender_id=sender_id,
            payload=payload,
            timestamp=time.time(),
            ttl_hops=self.message_ttl,
            vector_clock=1,
            target_node_id=target_node_id,
        )
        self._seen_messages.add(msg_id)
        self._message_log.append(msg)
        return msg

    def process_incoming_message(
        self,
        msg: GossipMessage,
        current_node_id: str,
    ) -> tuple[bool, list[str]]:
        """Process an incoming gossip packet, check deduplication, and return next hop peer IDs.

        Returns:
            (is_new, target_peer_ids_to_forward)
        """
        if msg.message_id in self._seen_messages:
            return False, []

        self._seen_messages.add(msg.message_id)
        self._message_log.append(msg)

        if msg.ttl_hops <= 1:
            return True, []  # Reached hop limit

        # Decrement TTL for forwarding
        msg.ttl_hops -= 1
        msg.vector_clock += 1

        return True, []

    def select_gossip_targets(
        self,
        active_nodes: list[PeerNode],
        exclude_node_id: str,
    ) -> list[str]:
        """Randomly select `fanout` peer nodes to forward gossip packets to."""
        eligible = [n.node_id for n in active_nodes if n.node_id != exclude_node_id]
        if not eligible:
            return []
        k = min(self.fanout, len(eligible))
        return random.sample(eligible, k)

    def get_message_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Retrieve recent gossip message log."""
        return [m.to_dict() for m in self._message_log[-limit:]]

    def clear(self) -> None:
        """Reset gossip history and deduplication caches."""
        self._seen_messages.clear()
        self._message_log.clear()
