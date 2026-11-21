"""Capped inspection of forced one-exit corridors for Two-Edge decisions."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Set, Tuple

Edge = Tuple[str, str, int]


@dataclass(frozen=True)
class ForcedCorridorAssessment:
    """Evidence gathered while following a candidate through forced exits."""

    candidate_edge: Edge
    status: str
    accumulated_time_s: float
    corridor_edge_count: int
    corridor_distance_m: float
    destination_progress_m: Optional[float]
    reaches_junction: bool
    returns_to_active_path: bool
    reaches_dead_end: bool
    incomplete_edge_cap: bool
    endpoint_node: str
    check_latency_ms: float

    @property
    def is_proven_trap(self) -> bool:
        return self.returns_to_active_path or self.reaches_dead_end

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


class ForcedCorridorEvaluator:
    """Follow only consecutive forced exits, stopping at a bounded endpoint.

    ``edge_cap`` counts the candidate edge as the first inspected edge. At an
    encountered node, successors already on the active or hypothetical corridor
    path are not valid forward continuations. If a fresh successor remains, it
    is followed only when it is the sole valid continuation. A node with two or
    more valid directed edges is a decision junction. A cap stop is always
    reported as incomplete, never as a proven dead end.
    """

    def __init__(
        self,
        adjacency: Dict[str, List[Tuple[str, int]]],
        edge_weights: Dict[Edge, float],
        edge_lengths: Dict[Edge, float],
        node_coords: Optional[Dict[str, Tuple[float, float]]] = None,
        edge_cap: int = 10,
    ):
        self.adjacency = adjacency
        self.edge_weights = edge_weights
        self.edge_lengths = edge_lengths
        self.node_coords = node_coords or {}
        self.edge_cap = max(1, int(edge_cap))

    def evaluate(
        self,
        candidate_edge: Edge,
        destination: str,
        active_path_nodes: Optional[Set[str]] = None,
    ) -> ForcedCorridorAssessment:
        started = time.perf_counter()
        edge = (str(candidate_edge[0]), str(candidate_edge[1]), int(candidate_edge[2]))
        u, v, _ = edge
        destination = str(destination)
        active = {str(node) for node in (active_path_nodes or set())}
        active.add(u)
        path_nodes = set(active)
        origin = u
        current = v
        edge_count = 1
        accumulated_time = float(self.edge_weights.get(edge, 10.0))
        corridor_distance = float(self.edge_lengths.get(edge, 25.0))

        def finish(status: str, endpoint: str) -> ForcedCorridorAssessment:
            progress = self._destination_progress(origin, endpoint, destination)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            return ForcedCorridorAssessment(
                candidate_edge=edge,
                status=status,
                accumulated_time_s=accumulated_time,
                corridor_edge_count=edge_count,
                corridor_distance_m=corridor_distance,
                destination_progress_m=progress,
                reaches_junction=status == "junction",
                returns_to_active_path=status == "active_path_return",
                reaches_dead_end=status == "dead_end",
                incomplete_edge_cap=status == "edge_cap",
                endpoint_node=str(endpoint),
                check_latency_ms=elapsed_ms,
            )

        if current == destination:
            return finish("destination", current)
        if current in path_nodes:
            return finish("active_path_return", current)
        path_nodes.add(current)

        while True:
            raw_edges = [
                (str(next_node), int(key))
                for next_node, key in self.adjacency.get(current, [])
            ]
            if not raw_edges:
                return finish("dead_end", current)

            valid_edges = [edge_item for edge_item in raw_edges if edge_item[0] not in path_nodes]
            if len(valid_edges) > 1:
                return finish("junction", current)
            if not valid_edges:
                if any(next_node in path_nodes for next_node, _ in raw_edges):
                    return finish("active_path_return", current)
                return finish("dead_end", current)

            if edge_count >= self.edge_cap:
                return finish("edge_cap", current)

            next_node, key = valid_edges[0]
            forced_edge = (current, next_node, key)
            accumulated_time += float(self.edge_weights.get(forced_edge, 10.0))
            corridor_distance += float(self.edge_lengths.get(forced_edge, 25.0))
            edge_count += 1
            if next_node == destination:
                return finish("destination", next_node)
            if next_node in path_nodes:
                return finish("active_path_return", next_node)
            path_nodes.add(next_node)
            current = next_node

    def _destination_progress(self, origin: str, endpoint: str, destination: str) -> Optional[float]:
        if not all(node in self.node_coords for node in (origin, endpoint, destination)):
            return None
        origin_to_destination = self._haversine(*self.node_coords[origin], *self.node_coords[destination])
        endpoint_to_destination = self._haversine(*self.node_coords[endpoint], *self.node_coords[destination])
        return origin_to_destination - endpoint_to_destination

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        from math import atan2, cos, radians, sin, sqrt

        radius_m = 6371000.0
        phi1, phi2 = radians(lat1), radians(lat2)
        delta_phi = radians(lat2 - lat1)
        delta_lon = radians(lon2 - lon1)
        a = sin(delta_phi / 2.0) ** 2 + cos(phi1) * cos(phi2) * sin(delta_lon / 2.0) ** 2
        return radius_m * 2.0 * atan2(sqrt(a), sqrt(1.0 - a))
