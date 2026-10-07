"""
GeoPulse Phase 11: Edge Server Component

Simulates the regional Edge Server responsible for latency-sensitive operations:
  - Dynamic weight construction from incoming traffic streams
  - Real-time vehicle telemetry session management
  - Scratch-built Dijkstra shortest path route computation
  - Route degradation detection and dual-threshold rerouting gating
  - Dispatching ROUTE_UPDATE messages to connected vehicles
"""

import time
from typing import Dict, List, Tuple, Any, Optional

from src.routing.dijkstra import custom_dijkstra, DijkstraResult
from src.routing.traffic_weights import GraphWeightManager
from src.edge.messages import (
    ModelUpdateMessage,
    PositionUpdateMessage,
    TrafficUpdateMessage,
    RouteUpdateMessage,
    ArchitectureEvent
)


class EdgeServer:
    """
    Logical Edge Server handling dynamic graph weights, vehicle routing,
    and threshold-gated rerouting.
    """

    def __init__(
        self,
        weight_manager: GraphWeightManager,
        threshold_seconds: float = 10.0,
        threshold_percent: float = 3.0
    ):
        self.weight_manager = weight_manager
        self.threshold_seconds = float(threshold_seconds)
        self.threshold_percent = float(threshold_percent)

        # Active edge weights
        self.static_weights = self.weight_manager.static_weights
        self.predicted_weights: Dict[Tuple[str, str, int], float] = self.static_weights.copy()
        self.observed_weights: Dict[Tuple[str, str, int], float] = self.static_weights.copy()
        self.dynamic_edges: set = set()

        # Connected vehicle sessions: vehicle_id -> session_dict
        self.sessions: Dict[str, Dict[str, Any]] = {}

        # Architecture event log
        self.event_log: List[ArchitectureEvent] = []
        self._event_counter = 0

    def _log_event(
        self,
        timestamp: str,
        source: str,
        target: str,
        msg_type: str,
        summary: str,
        exec_ms: float
    ) -> ArchitectureEvent:
        self._event_counter += 1
        ev = ArchitectureEvent(
            event_id=self._event_counter,
            timestamp=timestamp,
            source_component=source,
            target_component=target,
            message_type=msg_type,
            summary=summary,
            execution_time_ms=round(exec_ms, 3)
        )
        self.event_log.append(ev)
        return ev

    def update_model_predictions(self, message: ModelUpdateMessage) -> float:
        """
        Ingests MODEL_UPDATE broadcast from Cloud and constructs predicted edge weights.

        Returns
        -------
        execution_time_ms : float (Prototype software execution time in ms)
        """
        t0 = time.perf_counter()
        weights, _, dyn_set = self.weight_manager.build_scenario_weights(message.predicted_speeds)
        self.predicted_weights = weights
        self.dynamic_edges = dyn_set
        exec_ms = (time.perf_counter() - t0) * 1000.0

        self._log_event(
            timestamp=message.prediction_timestamp,
            source="Cloud",
            target="EdgeServer",
            msg_type="MODEL_UPDATE",
            summary=f"Synthesized predicted weights ({len(weights):,} edges, {len(dyn_set)} dynamic) from {message.model_version}",
            exec_ms=exec_ms
        )
        return exec_ms

    def update_traffic(self, message: TrafficUpdateMessage) -> float:
        """
        Ingests TRAFFIC_UPDATE observation from sensor stream and constructs observed edge weights.

        Returns
        -------
        execution_time_ms : float (Prototype software execution time in ms)
        """
        t0 = time.perf_counter()
        weights, _, dyn_set = self.weight_manager.build_scenario_weights(message.observed_speeds)
        self.observed_weights = weights
        self.dynamic_edges = dyn_set
        exec_ms = (time.perf_counter() - t0) * 1000.0

        self._log_event(
            timestamp=message.timestamp,
            source="TrafficSensorStream",
            target="EdgeServer",
            msg_type="TRAFFIC_UPDATE",
            summary=f"Updated real-time observed traffic weights across {message.sensor_count} sensors",
            exec_ms=exec_ms
        )
        return exec_ms

    def update_vehicle_position(self, message: PositionUpdateMessage) -> float:
        """
        Ingests POSITION_UPDATE telemetry from a vehicle and records its current position in session.

        Returns
        -------
        execution_time_ms : float
        """
        t0 = time.perf_counter()
        v_id = message.vehicle_id
        if v_id in self.sessions:
            self.sessions[v_id]['current_node'] = message.current_node
            self.sessions[v_id]['current_edge'] = message.current_edge
            self.sessions[v_id]['edge_index'] = message.edge_index
            self.sessions[v_id]['progress_pct'] = message.progress_pct
            self.sessions[v_id]['elapsed_time_s'] = message.elapsed_time_s
            self.sessions[v_id]['last_telemetry_timestamp'] = message.timestamp

        exec_ms = (time.perf_counter() - t0) * 1000.0
        self._log_event(
            timestamp=message.timestamp,
            source=f"Vehicle[{v_id}]",
            target="EdgeServer",
            msg_type="POSITION_UPDATE",
            summary=f"Vehicle progress: {message.progress_pct:.1f}% at Node {message.current_node} (Edge #{message.edge_index})",
            exec_ms=exec_ms
        )
        return exec_ms

    def compute_initial_route(
        self,
        vehicle_id: str,
        source: str,
        destination: str,
        departure_timestamp: str
    ) -> Tuple[RouteUpdateMessage, float]:
        """
        Computes the initial planned route using custom Dijkstra and active predicted weights.

        Returns
        -------
        route_msg : RouteUpdateMessage
        dijkstra_exec_ms : float
        """
        t0 = time.perf_counter()
        res: DijkstraResult = custom_dijkstra(
            self.weight_manager.adjacency,
            self.predicted_weights,
            source,
            destination
        )
        dijkstra_exec_ms = (time.perf_counter() - t0) * 1000.0

        if not res.is_reached:
            raise ValueError(f"Destination {destination} unreachable from {source}")

        # Register session
        self.sessions[vehicle_id] = {
            'vehicle_id': vehicle_id,
            'source': source,
            'destination': destination,
            'departure_timestamp': departure_timestamp,
            'current_node': source,
            'current_edge': None,
            'edge_index': 0,
            'progress_pct': 0.0,
            'elapsed_time_s': 0.0,
            'initial_route_nodes': res.node_path,
            'initial_route_edges': res.edge_path,
            'initial_expected_time_s': res.total_cost,
            'active_route_nodes': res.node_path,
            'active_route_edges': res.edge_path,
            'reroute_occurred': False,
            'last_telemetry_timestamp': departure_timestamp
        }

        route_msg = RouteUpdateMessage(
            vehicle_id=vehicle_id,
            node_path=res.node_path,
            edge_path=res.edge_path,
            total_cost_s=res.total_cost,
            is_reroute=False,
            saving_s=0.0,
            saving_pct=0.0,
            reason=f"Initial predictive route planned via LightGBM weights ({len(res.edge_path)} segments, {res.total_cost:.1f}s expected)"
        )

        self._log_event(
            timestamp=departure_timestamp,
            source="EdgeServer",
            target=f"Vehicle[{vehicle_id}]",
            msg_type="ROUTE_UPDATE",
            summary=f"Dispatched initial route R0 ({len(res.edge_path)} links, {res.total_cost:.1f}s ETA)",
            exec_ms=dijkstra_exec_ms
        )

        return route_msg, dijkstra_exec_ms

    def evaluate_and_reroute(
        self,
        vehicle_id: str,
        timestamp: str
    ) -> Tuple[Optional[RouteUpdateMessage], Dict[str, Any]]:
        """
        State 2 & 3: Evaluates route degradation for vehicle_id under current observed traffic.
        If degradation exceeds dual thresholds, executes custom Dijkstra from current position
        and issues a ROUTE_UPDATE message.

        Returns
        -------
        route_msg : Optional[RouteUpdateMessage] (None if reroute not triggered)
        metrics : Dict[str, Any] (Degradation and timing metrics)
        """
        if vehicle_id not in self.sessions:
            raise KeyError(f"No active session for vehicle {vehicle_id}")

        sess = self.sessions[vehicle_id]
        curr_node = sess['current_node']
        dest = sess['destination']
        edge_idx = sess['edge_index']
        active_edges = sess['active_route_edges']

        t0_total = time.perf_counter()

        # Remaining edges of current route
        rem_edges = active_edges[edge_idx:]
        t_remain_curr = sum(self.observed_weights.get(e, 0.0) for e in rem_edges)

        # Compute optimal alternative from curr_node to destination under observed traffic
        t0_dijkstra = time.perf_counter()
        res_alt: DijkstraResult = custom_dijkstra(
            self.weight_manager.adjacency,
            self.observed_weights,
            curr_node,
            dest
        )
        dijkstra_exec_ms = (time.perf_counter() - t0_dijkstra) * 1000.0
        t_remain_alt = res_alt.total_cost

        # Calculate potential degradation & savings
        t0_decision = time.perf_counter()
        abs_saving = t_remain_curr - t_remain_alt
        if t_remain_curr > 0:
            rel_saving = (abs_saving / t_remain_curr) * 100.0
        else:
            rel_saving = 0.0

        # Evaluate dual threshold condition
        triggered = (abs_saving >= self.threshold_seconds) and (rel_saving >= self.threshold_percent)
        decision_exec_ms = (time.perf_counter() - t0_decision) * 1000.0

        total_exec_ms = (time.perf_counter() - t0_total) * 1000.0

        metrics = {
            'vehicle_id': vehicle_id,
            'decision_node': curr_node,
            'decision_step': edge_idx,
            'remaining_current_time_s': round(t_remain_curr, 2),
            'remaining_optimal_time_s': round(t_remain_alt, 2),
            'absolute_saving_s': round(abs_saving, 2),
            'relative_saving_pct': round(rel_saving, 2),
            'threshold_seconds': self.threshold_seconds,
            'threshold_percent': self.threshold_percent,
            'reroute_triggered': bool(triggered),
            'dijkstra_time_ms': round(dijkstra_exec_ms, 3),
            'decision_time_ms': round(decision_exec_ms, 3),
            'total_edge_decision_time_ms': round(total_exec_ms, 3)
        }

        if triggered:
            # Update session with new route
            traversed_nodes = sess['active_route_nodes'][:edge_idx]
            traversed_edges = sess['active_route_edges'][:edge_idx]

            new_full_nodes = traversed_nodes + res_alt.node_path
            new_full_edges = traversed_edges + res_alt.edge_path

            sess['active_route_nodes'] = new_full_nodes
            sess['active_route_edges'] = new_full_edges
            sess['reroute_occurred'] = True

            reason = (
                f"Degradation detected: Alternative saves {abs_saving:.1f}s ({rel_saving:.1f}%), "
                f"exceeding gates ({self.threshold_seconds}s / {self.threshold_percent}%)."
            )

            route_msg = RouteUpdateMessage(
                vehicle_id=vehicle_id,
                node_path=new_full_nodes,
                edge_path=new_full_edges,
                total_cost_s=sess['elapsed_time_s'] + t_remain_alt,
                is_reroute=True,
                saving_s=round(abs_saving, 2),
                saving_pct=round(rel_saving, 2),
                reason=reason
            )

            self._log_event(
                timestamp=timestamp,
                source="EdgeServer",
                target=f"Vehicle[{vehicle_id}]",
                msg_type="ROUTE_UPDATE (REROUTE)",
                summary=f"Reroute triggered: Saves {abs_saving:.1f}s ({rel_saving:.1f}%). New route: {len(new_full_edges)} links.",
                exec_ms=total_exec_ms
            )
            return route_msg, metrics
        else:
            self._log_event(
                timestamp=timestamp,
                source="EdgeServer",
                target=f"Vehicle[{vehicle_id}]",
                msg_type="ROUTE_CONFIRMED",
                summary=f"No reroute triggered: Potential saving {max(abs_saving, 0.0):.1f}s below threshold.",
                exec_ms=total_exec_ms
            )
            return None, metrics

    def get_session(self, vehicle_id: str) -> Optional[Dict[str, Any]]:
        """Returns the internal state of a vehicle session."""
        return self.sessions.get(vehicle_id)
