"""
GeoPulse Phase 11: Vehicle / Client Simulator Component

Simulates vehicular client operations:
  - Receiving and executing route directives from Edge Server
  - Advancing discrete link progress according to kinematic edge costs
  - Emitting periodic POSITION_UPDATE telemetry to Edge Server
  - Ingesting and switching to dynamic reroute directives mid-journey
"""

from typing import Dict, List, Tuple, Any, Optional
from src.edge.messages import PositionUpdateMessage, RouteUpdateMessage


class Vehicle:
    """
    Lightweight vehicular client navigating physical network links.
    """

    def __init__(
        self,
        vehicle_id: str,
        origin: str,
        destination: str,
        departure_time: str
    ):
        self.vehicle_id = vehicle_id
        self.origin = origin
        self.destination = destination
        self.departure_time = departure_time

        # Position state
        self.current_node = origin
        self.current_edge: Optional[Tuple[str, str, int]] = None
        self.edge_index = 0
        self.progress_pct = 0.0

        # Route state
        self.current_route_nodes: List[str] = [origin]
        self.current_route_edges: List[Tuple[str, str, int]] = []
        self.initial_route_nodes: List[str] = []
        self.initial_route_edges: List[Tuple[str, str, int]] = []

        # Kinematics
        self.elapsed_travel_time_s = 0.0
        self.accumulated_distance_m = 0.0
        self.is_journey_complete = False
        self.reroute_received = False

        # Timeline history log
        self.timeline: List[Dict[str, Any]] = []

        # Temporal experiments keep the executed path separate from the mutable
        # route guidance maintained by the existing edge/server simulation.
        self.temporal_traversed_edges: List[Tuple[str, str, int]] = []

    def receive_initial_route(self, route_msg: RouteUpdateMessage):
        """Initializes vehicle path guidance from Edge Server."""
        self.current_route_nodes = list(route_msg.node_path)
        self.current_route_edges = list(route_msg.edge_path)
        self.initial_route_nodes = list(route_msg.node_path)
        self.initial_route_edges = list(route_msg.edge_path)
        self.current_node = self.current_route_nodes[0]
        self.edge_index = 0
        self.progress_pct = 0.0

        self.timeline.append({
            'timestamp': self.departure_time,
            'event': 'DEPARTURE',
            'current_node': self.current_node,
            'edge_index': 0,
            'progress_pct': 0.0,
            'elapsed_time_s': 0.0,
            'accumulated_dist_m': 0.0,
            'description': f"Departed origin {self.origin} on initial route R0 ({len(self.current_route_edges)} links)"
        })

    def begin_temporal_journey(
        self,
        node_path: List[str],
        edge_path: List[Tuple[str, str, int]],
        timestamp: str,
    ) -> None:
        """Initialize temporal simulation with a predicted-cost route plan."""
        if not node_path or node_path[0] != self.origin:
            raise ValueError("Initial temporal route must start at the vehicle origin")
        if len(node_path) != len(edge_path) + 1:
            raise ValueError("Temporal route node and edge paths are inconsistent")
        self.current_node = self.origin
        self.current_route_nodes = list(node_path)
        self.current_route_edges = list(edge_path)
        self.initial_route_nodes = list(node_path)
        self.initial_route_edges = list(edge_path)
        self.edge_index = 0
        self.progress_pct = 0.0
        self.timeline.append({
            "timestamp": timestamp,
            "event": "DEPARTURE",
            "current_node": self.current_node,
            "edge_index": 0,
            "progress_pct": 0.0,
            "elapsed_time_s": 0.0,
            "accumulated_dist_m": 0.0,
            "description": f"Temporal journey started from {self.origin}",
        })

    def set_temporal_plan(
        self,
        node_path: List[str],
        edge_path: List[Tuple[str, str, int]],
        timestamp: str,
        reason: str,
    ) -> None:
        """Replace future guidance at the current intersection, preserving motion."""
        if not node_path or node_path[0] != self.current_node:
            raise ValueError("Updated temporal route must start at the current node")
        if len(node_path) != len(edge_path) + 1:
            raise ValueError("Temporal route node and edge paths are inconsistent")
        self.current_route_nodes = list(node_path)
        self.current_route_edges = list(edge_path)
        self.timeline.append({
            "timestamp": timestamp,
            "event": "ROUTE_DECISION",
            "current_node": self.current_node,
            "edge_index": self.edge_index,
            "progress_pct": round(self.progress_pct, 2),
            "elapsed_time_s": round(self.elapsed_travel_time_s, 2),
            "accumulated_dist_m": round(self.accumulated_distance_m, 2),
            "description": reason,
        })

    def record_realized_edge_traversal(
        self,
        edge: Tuple[str, str, int],
        travel_time_s: float,
        distance_m: float,
        arrival_timestamp: str,
    ) -> None:
        """Advance one edge using realized motion costs, never route predictions."""
        import math

        try:
            duration = float(travel_time_s)
            distance = float(distance_m)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Realized edge time and distance must be numeric") from exc
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("Realized edge time must be finite and positive")
        if not math.isfinite(distance) or distance <= 0:
            raise ValueError("Realized edge distance must be finite and positive")
        if str(edge[0]) != str(self.current_node):
            raise ValueError(
                f"Temporal edge {edge!r} does not leave current node {self.current_node!r}"
            )

        normalized_edge = (str(edge[0]), str(edge[1]), edge[2])
        self.current_edge = normalized_edge
        self.current_node = normalized_edge[1]
        self.edge_index += 1
        self.temporal_traversed_edges.append(normalized_edge)
        self.elapsed_travel_time_s += duration
        self.accumulated_distance_m += distance
        self.progress_pct = (
            min(100.0, 100.0 * self.edge_index / len(self.initial_route_edges))
            if self.initial_route_edges else 100.0
        )
        self.timeline.append({
            "timestamp": arrival_timestamp,
            "event": "REALIZED_LINK_TRAVERSAL",
            "current_node": self.current_node,
            "edge_index": self.edge_index,
            "progress_pct": round(self.progress_pct, 2),
            "elapsed_time_s": round(self.elapsed_travel_time_s, 2),
            "accumulated_dist_m": round(self.accumulated_distance_m, 2),
            "description": (
                f"Traversed edge {normalized_edge[0]} -> {normalized_edge[1]} "
                f"in {duration:.1f}s using realized speed ({distance:.1f}m)"
            ),
        })

    def finish_temporal_journey(self, arrival_timestamp: str) -> None:
        """Mark a temporal journey complete at its requested destination."""
        if str(self.current_node) != str(self.destination):
            raise ValueError("Cannot complete a temporal journey before reaching its destination")
        self.is_journey_complete = True
        self.progress_pct = 100.0
        self.timeline.append({
            "timestamp": arrival_timestamp,
            "event": "ARRIVAL",
            "current_node": self.current_node,
            "edge_index": self.edge_index,
            "progress_pct": 100.0,
            "elapsed_time_s": round(self.elapsed_travel_time_s, 2),
            "accumulated_dist_m": round(self.accumulated_distance_m, 2),
            "description": (
                f"Arrived at destination {self.destination} in "
                f"{self.elapsed_travel_time_s:.1f}s"
            ),
        })

    def advance_to_step(
        self,
        target_step: int,
        weights: Dict[Tuple[str, str, int], float],
        edge_lengths: Dict[Tuple[str, str, int], float],
        current_timestamp: str
    ) -> PositionUpdateMessage:
        """
        Advances the vehicle along its current route from its current edge_index
        up to target_step, accumulating travel time and distance.

        Returns
        -------
        PositionUpdateMessage : Telemetry message to dispatch to Edge Server
        """
        target_step = min(target_step, len(self.current_route_edges))

        while self.edge_index < target_step:
            edge = self.current_route_edges[self.edge_index]
            dt = weights.get(edge, 10.0)
            dist = edge_lengths.get(edge, 100.0)

            self.elapsed_travel_time_s += dt
            self.accumulated_distance_m += dist
            self.current_edge = edge
            self.edge_index += 1
            self.current_node = self.current_route_nodes[self.edge_index]

            total_links = len(self.current_route_edges)
            self.progress_pct = (self.edge_index / total_links) * 100.0 if total_links > 0 else 100.0

            self.timeline.append({
                'timestamp': current_timestamp,
                'event': 'LINK_TRAVERSAL',
                'current_node': self.current_node,
                'edge_index': self.edge_index,
                'progress_pct': round(self.progress_pct, 2),
                'elapsed_time_s': round(self.elapsed_travel_time_s, 2),
                'accumulated_dist_m': round(self.accumulated_distance_m, 2),
                'description': f"Traversed edge {edge[0]} -> {edge[1]} in {dt:.1f}s ({dist:.1f}m)"
            })

        pos_msg = PositionUpdateMessage(
            vehicle_id=self.vehicle_id,
            current_node=self.current_node,
            current_edge=self.current_edge,
            edge_index=self.edge_index,
            progress_pct=round(self.progress_pct, 2),
            elapsed_time_s=round(self.elapsed_travel_time_s, 2),
            timestamp=current_timestamp
        )
        return pos_msg

    def apply_route_update(self, route_msg: RouteUpdateMessage, timestamp: str):
        """
        Seamlessly updates vehicle path guidance with dynamic detour directive.
        """
        if route_msg.is_reroute:
            self.current_route_nodes = list(route_msg.node_path)
            self.current_route_edges = list(route_msg.edge_path)
            self.reroute_received = True

            self.timeline.append({
                'timestamp': timestamp,
                'event': 'REROUTE_SWITCH',
                'current_node': self.current_node,
                'edge_index': self.edge_index,
                'progress_pct': round(self.progress_pct, 2),
                'elapsed_time_s': round(self.elapsed_travel_time_s, 2),
                'accumulated_dist_m': round(self.accumulated_distance_m, 2),
                'description': f"Switched to dynamic bypass R1 at Node {self.current_node} ({route_msg.reason})"
            })

    def complete_journey(
        self,
        weights: Dict[Tuple[str, str, int], float],
        edge_lengths: Dict[Tuple[str, str, int], float],
        arrival_timestamp: str
    ):
        """
        Advances the vehicle through all remaining links to reach the destination.
        """
        total_links = len(self.current_route_edges)
        while self.edge_index < total_links:
            edge = self.current_route_edges[self.edge_index]
            dt = weights.get(edge, 10.0)
            dist = edge_lengths.get(edge, 100.0)

            self.elapsed_travel_time_s += dt
            self.accumulated_distance_m += dist
            self.current_edge = edge
            self.edge_index += 1
            self.current_node = self.current_route_nodes[self.edge_index]

            self.progress_pct = (self.edge_index / total_links) * 100.0

            self.timeline.append({
                'timestamp': arrival_timestamp,
                'event': 'LINK_TRAVERSAL',
                'current_node': self.current_node,
                'edge_index': self.edge_index,
                'progress_pct': round(self.progress_pct, 2),
                'elapsed_time_s': round(self.elapsed_travel_time_s, 2),
                'accumulated_dist_m': round(self.accumulated_distance_m, 2),
                'description': f"Traversed edge {edge[0]} -> {edge[1]} in {dt:.1f}s ({dist:.1f}m)"
            })

        self.is_journey_complete = True
        self.timeline.append({
            'timestamp': arrival_timestamp,
            'event': 'ARRIVAL',
            'current_node': self.current_node,
            'edge_index': self.edge_index,
            'progress_pct': 100.0,
            'elapsed_time_s': round(self.elapsed_travel_time_s, 2),
            'accumulated_dist_m': round(self.accumulated_distance_m, 2),
            'description': f"Arrived at destination {self.destination} in {self.elapsed_travel_time_s:.1f}s ({self.accumulated_distance_m:.1f}m)"
        })
