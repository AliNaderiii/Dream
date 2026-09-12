"""Consistent Hash Ring and Capability-Based Routing for Federation Mesh."""

from __future__ import annotations

import hashlib

from dream.federation.types import PeerHealth, PeerNode


class MeshRouter:
    """Routes tasks and messages to optimal peers using capability matching and hash ring."""

    def __init__(self, replicas: int = 3) -> None:
        self.replicas = replicas
        self._ring: dict[int, str] = {}  # hash_value -> node_id
        self._sorted_keys: list[int] = []

    def build_ring(self, nodes: dict[str, PeerNode]) -> None:
        """Construct consistent hashing ring from active healthy nodes."""
        self._ring.clear()
        for node_id, node in nodes.items():
            if node.health in (PeerHealth.HEALTHY, PeerHealth.SUSPECT):
                for r in range(self.replicas):
                    key_str = f"{node_id}:{r}"
                    h = int(hashlib.md5(key_str.encode("utf-8")).hexdigest(), 16)
                    self._ring[h] = node_id

        self._sorted_keys = sorted(self._ring.keys())

    def route_by_key(self, routing_key: str) -> str | None:
        """Route arbitrary string key to the nearest peer on the consistent hash ring."""
        if not self._ring:
            return None

        h = int(hashlib.md5(routing_key.encode("utf-8")).hexdigest(), 16)
        for ring_key in self._sorted_keys:
            if h <= ring_key:
                return self._ring[ring_key]

        return self._ring[self._sorted_keys[0]]

    def find_best_node_for_capability(
        self,
        nodes: dict[str, PeerNode],
        required_capability: str,
    ) -> PeerNode | None:
        """Select healthy node possessing required capability with minimum workload."""
        exact_matches = [
            node
            for node in nodes.values()
            if node.health == PeerHealth.HEALTHY and required_capability in node.capabilities
        ]
        if exact_matches:
            exact_matches.sort(key=lambda n: n.workload_score)
            return exact_matches[0]

        # Fallback to general capability nodes
        general_candidates = [
            node
            for node in nodes.values()
            if node.health == PeerHealth.HEALTHY
            and ("general" in node.capabilities or not required_capability)
        ]
        if general_candidates:
            general_candidates.sort(key=lambda n: n.workload_score)
            return general_candidates[0]

        return None

    def get_routing_table(self, nodes: dict[str, PeerNode]) -> dict[str, list[str]]:
        """Compute inverted capability index mapping capabilities to node IDs."""
        cap_map: dict[str, list[str]] = {}
        for n_id, node in nodes.items():
            for cap in node.capabilities:
                cap_map.setdefault(cap, []).append(n_id)
        return cap_map
