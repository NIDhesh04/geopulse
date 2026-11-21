"""Sequential journey controller for GeoPulse's two-edge routing strategy."""

from dataclasses import dataclass, field
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from src.routing.dijkstra import DijkstraResult, custom_dijkstra
from src.routing.two_edge_selector import TwoEdgeDecisionStep, TwoEdgeSelector


Edge = Tuple[str, str, int]


@dataclass
class SequentialJourneyResult:
    """Metrics and path produced by one sequential routing journey."""

    source_node: str
    destination_node: str
    strategy_name: str
    candidate_strategy: str
    is_success: bool
    total_travel_time_s: float
    total_distance_m: float
    node_path: List[str]
    edge_path: List[Edge]
    decision_steps: List[TwoEdgeDecisionStep]
    total_decisions: int
    forced_decisions: int
    recovery_events: int
    reroute_events: int
    traffic_updates_accepted: int
    average_decision_latency_ms: float
    total_computation_time_ms: float
    termination_reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class RouteController:
    """Execute a sequential journey, applying bounded recovery and traffic updates."""

    def __init__(
        self,
        adjacency: Dict[str, List[Tuple[str, int]]],
        edge_lengths: Dict[Edge, float],
        two_edge_selector: TwoEdgeSelector,
        max_hops_multiplier: float = 3.0,
        max_node_visits: int = 2,
        local_backtracking: bool = False,
        strict_loop_avoidance: bool = True,
        reroute_threshold_seconds: float = 10.0,
        reroute_threshold_percent: float = 3.0,
    ):
        self.adjacency = adjacency
        self.edge_lengths = edge_lengths
        self.selector = two_edge_selector
        self.max_hops_multiplier = float(max_hops_multiplier)
        self.max_node_visits = int(max_node_visits)
        self.local_backtracking = bool(local_backtracking)
        self.strict_loop_avoidance = bool(strict_loop_avoidance)
        self.selector.avoid_visited_successors = self.strict_loop_avoidance
        self.reroute_threshold_s = float(reroute_threshold_seconds)
        self.reroute_threshold_pct = float(reroute_threshold_percent)

    @staticmethod
    def _path_cost(path: List[Edge], weights: Dict[Edge, float]) -> float:
        return sum(float(weights.get(edge, 10.0)) for edge in path)

    def _recovery_decision(
        self,
        step: int,
        current_node: str,
        next_node: str,
        edge: Edge,
        weights: Dict[Edge, float],
        speeds: Dict[Edge, float],
        reason_tag: str,
        reason: str,
        evaluation_time_ms: float = 0.0,
        length_m_override: Optional[float] = None,
    ) -> TwoEdgeDecisionStep:
        length_m = float(
            length_m_override
            if length_m_override is not None
            else self.edge_lengths.get(edge, 50.0)
        )
        travel_time_s = float(weights.get(edge, 10.0))
        speed_kmh = float(
            speeds.get(
                edge,
                (length_m / travel_time_s * 3.6) if travel_time_s > 0 else 30.0,
            )
        )
        return TwoEdgeDecisionStep(
            step_index=step,
            current_node=current_node,
            next_node=next_node,
            selected_edge=edge,
            candidate_a=None,
            candidate_b=None,
            score_a=None,
            score_b=None,
            travel_time_s=travel_time_s,
            length_m=length_m,
            speed_kmh=speed_kmh,
            strategy_name=f"{self.selector.decision_strategy.name} [{reason_tag}]",
            decision_reason=reason,
            is_forced=True,
            is_dead_end=False,
            evaluation_time_ms=evaluation_time_ms,
        )

    def _make_local_backtrack_decision(
        self,
        step: int,
        current_node: str,
        parent_node: str,
        incoming_edge: Edge,
        weights: Dict[Edge, float],
        speeds: Dict[Edge, float],
        reason_tag: str,
        reason: str,
    ) -> TwoEdgeDecisionStep:
        """Build a physical one-edge backtrack without consulting Dijkstra."""
        reverse_edges = [
            edge
            for edge in self.edge_lengths
            if edge[0] == current_node and edge[1] == parent_node
        ]
        if reverse_edges:
            reverse_edge = min(
                reverse_edges,
                key=lambda edge: (float(weights.get(edge, 10.0)), edge[2]),
            )
            reverse_length = float(self.edge_lengths[reverse_edge])
        else:
            reverse_edge = (current_node, parent_node, incoming_edge[2])
            reverse_length = float(self.edge_lengths.get(incoming_edge, 50.0))
            weights.setdefault(reverse_edge, float(weights.get(incoming_edge, 10.0)))
            if incoming_edge in speeds:
                speeds.setdefault(reverse_edge, speeds[incoming_edge])

        return self._recovery_decision(
            step,
            current_node,
            parent_node,
            reverse_edge,
            weights,
            speeds,
            reason_tag,
            reason,
            length_m_override=reverse_length,
        )

    def execute_journey(
        self,
        source: str,
        destination: str,
        initial_weights: Dict[Edge, float],
        initial_speeds: Optional[Dict[Edge, float]] = None,
        traffic_update_step: Optional[int] = None,
        updated_weights: Optional[Dict[Edge, float]] = None,
        updated_speeds: Optional[Dict[Edge, float]] = None,
        max_hops: Optional[int] = None,
        reference_dijkstra: Optional[DijkstraResult] = None,
    ) -> SequentialJourneyResult:
        """Route one vehicle, making a two-edge decision at each intersection.

        A traffic update is retained only when the best updated route improves on
        the previously planned route evaluated under the updated costs by both
        configured thresholds. ``reroute_events`` counts accepted changes to the
        shortest route; ``traffic_updates_accepted`` records accepted updates.
        """
        started = time.perf_counter()
        source_node, destination_node = str(source), str(destination)
        strategy_name = self.selector.decision_strategy.name
        candidate_strategy = self.selector.candidate_strategy.value

        if source_node == destination_node:
            return SequentialJourneyResult(
                source_node=source_node,
                destination_node=destination_node,
                strategy_name=strategy_name,
                candidate_strategy=candidate_strategy,
                is_success=True,
                total_travel_time_s=0.0,
                total_distance_m=0.0,
                node_path=[source_node],
                edge_path=[],
                decision_steps=[],
                total_decisions=0,
                forced_decisions=0,
                recovery_events=0,
                reroute_events=0,
                traffic_updates_accepted=0,
                average_decision_latency_ms=0.0,
                total_computation_time_ms=0.0,
                termination_reason="Source equals destination.",
            )

        if max_hops is None:
            if reference_dijkstra and reference_dijkstra.is_reached and reference_dijkstra.node_path:
                hop_limit = max(
                    50,
                    int(len(reference_dijkstra.node_path) * self.max_hops_multiplier),
                )
            else:
                hop_limit = 200
        else:
            hop_limit = max(10, int(max_hops))

        current_weights = dict(initial_weights)
        current_speeds = dict(initial_speeds or {})
        current_node = source_node
        previous_node: Optional[str] = None
        node_path = [current_node]
        edge_path: List[Edge] = []
        active_path_nodes = [current_node]
        active_path_edges: List[Edge] = []
        decisions: List[TwoEdgeDecisionStep] = []
        decision_latencies: List[float] = []
        visit_counts: Dict[str, int] = {current_node: 1}
        visited_nodes: Set[str] = {current_node}
        total_time_s = 0.0
        total_distance_m = 0.0
        recovery_events = 0
        reroute_events = 0
        traffic_updates_accepted = 0
        failed_edges: Dict[str, Set[Edge]] = {}
        traffic_update_processed = False
        recovery_path_edges: List[Edge] = []
        success = False
        termination_reason = ""
        step = 0

        def perform_local_backtrack(reason_tag: str, reason: str) -> bool:
            nonlocal current_node, previous_node, step, total_time_s, total_distance_m
            if not self.local_backtracking or len(active_path_nodes) <= 1:
                return False

            departing_node = current_node
            parent_node = active_path_nodes[-2]
            incoming_edge = active_path_edges[-1]
            backtrack = self._make_local_backtrack_decision(
                step=step,
                current_node=departing_node,
                parent_node=parent_node,
                incoming_edge=incoming_edge,
                weights=current_weights,
                speeds=current_speeds,
                reason_tag=reason_tag,
                reason=reason,
            )
            edge_path.append(backtrack.selected_edge)
            node_path.append(parent_node)
            decisions.append(backtrack)
            total_time_s += backtrack.travel_time_s
            total_distance_m += backtrack.length_m

            failed_edges.setdefault(parent_node, set()).update(
                edge for edge in self.edge_lengths
                if edge[0] == parent_node and edge[1] == departing_node
            )
            failed_edges.pop(departing_node, None)
            active_path_edges.pop()
            removed_node = active_path_nodes.pop()
            visit_counts[removed_node] -= 1
            if visit_counts[removed_node] <= 0:
                visit_counts.pop(removed_node, None)
                visited_nodes.discard(removed_node)

            previous_node, current_node = departing_node, parent_node
            step += 1
            return True

        while step < hop_limit:
            if current_node == destination_node:
                success = True
                termination_reason = "Destination reached successfully."
                break

            if (
                not traffic_update_processed
                and traffic_update_step is not None
                and step == traffic_update_step
                and updated_weights is not None
            ):
                traffic_update_processed = True
                old_weights = current_weights
                proposed_weights = dict(updated_weights)
                old_route = custom_dijkstra(
                    self.adjacency, old_weights, current_node, destination_node
                )
                proposed_route = custom_dijkstra(
                    self.adjacency, proposed_weights, current_node, destination_node
                )

                if proposed_route.is_reached:
                    proposed_cost = self._path_cost(proposed_route.edge_path, proposed_weights)
                    if old_route.is_reached:
                        old_plan_cost = self._path_cost(old_route.edge_path, proposed_weights)
                        saving_s = old_plan_cost - proposed_cost
                        saving_pct = (
                            saving_s / old_plan_cost * 100.0 if old_plan_cost > 0 else 0.0
                        )
                    else:
                        saving_s = float("inf")
                        saving_pct = 100.0
                else:
                    saving_s = float("-inf")
                    saving_pct = float("-inf")

                accepts_update = (
                    saving_s >= self.reroute_threshold_s
                    and saving_pct >= self.reroute_threshold_pct
                )
                if accepts_update:
                    current_weights = proposed_weights
                    current_speeds = dict(updated_speeds or {})
                    recovery_path_edges.clear()
                    failed_edges.clear()
                    traffic_updates_accepted += 1
                    if old_route.edge_path != proposed_route.edge_path:
                        reroute_events += 1

            following_recovery_path = False
            if recovery_path_edges and recovery_path_edges[0][0] != current_node:
                recovery_path_edges.clear()

            if recovery_path_edges:
                recovery_edge = recovery_path_edges.pop(0)
                decision_latency_ms = 0.0
                decision = self._recovery_decision(
                    step,
                    current_node,
                    recovery_edge[1],
                    recovery_edge,
                    current_weights,
                    current_speeds,
                    "RECOVERY_SHORTEST_PATH",
                    f"Continue shortest-path recovery along {recovery_edge[0]}->{recovery_edge[1]}.",
                )
                following_recovery_path = True
            else:
                decision_started = time.perf_counter()
                decision = self.selector.decide_next_edge(
                    step_index=step,
                    current_node=current_node,
                    destination=destination_node,
                    edge_weights=current_weights,
                    edge_speeds=current_speeds,
                    previous_node=previous_node,
                    visited_nodes=visited_nodes,
                    excluded_edges=failed_edges.get(current_node, set()),
                )
                decision_latency_ms = (time.perf_counter() - decision_started) * 1000.0
                decision_latencies.append(decision_latency_ms)

            if decision.is_dead_end or decision.selected_edge is None or decision.next_node is None:
                recovery_events += 1
                if perform_local_backtrack(
                    "RECOVERY_LOOP_BACKTRACK"
                    if "Loop trap" in decision.decision_reason
                    else "RECOVERY_BACKTRACK",
                    (
                        f"Local loop avoidance at {current_node}; backtrack and retry the "
                        "previous Two-Edge choice."
                        if "Loop trap" in decision.decision_reason
                        else f"Local dead-end recovery at {current_node}; backtrack and retry."
                    ),
                ):
                    continue

                fallback = custom_dijkstra(
                    self.adjacency, current_weights, current_node, destination_node
                )
                if fallback.is_reached and fallback.edge_path:
                    edge = fallback.edge_path[0]
                    next_node = fallback.node_path[1]
                    recovery_path_edges = list(fallback.edge_path[1:])
                    decision = self._recovery_decision(
                        step,
                        current_node,
                        next_node,
                        edge,
                        current_weights,
                        current_speeds,
                        "RECOVERY_FORWARD",
                        f"Forward recovery from {current_node} along {edge[0]}->{edge[1]}.",
                        decision_latency_ms,
                    )
                elif previous_node is not None and edge_path:
                    # Prefer a real directed reverse edge, including nonzero lane keys.
                    reverse_edges = {
                        edge
                        for edge in self.edge_lengths
                        if edge[0] == current_node and edge[1] == previous_node
                    }
                    reverse_edges.update(
                        (current_node, str(target), int(key))
                        for target, key in self.adjacency.get(current_node, [])
                        if str(target) == previous_node
                    )
                    if reverse_edges:
                        reverse_edge = min(
                            sorted(reverse_edges),
                            key=lambda edge: current_weights.get(edge, 10.0),
                        )
                        reverse_length = self.edge_lengths.get(reverse_edge)
                        if reverse_length is None:
                            reverse_length = self.edge_lengths.get(edge_path[-1], 50.0)
                    else:
                        # A vehicle can physically reverse on the road it just used,
                        # even when the directed routing graph has no reverse arc.
                        incoming_edge = edge_path[-1]
                        reverse_edge = (
                            current_node,
                            previous_node,
                            incoming_edge[2],
                        )
                        reverse_length = float(self.edge_lengths.get(incoming_edge, 50.0))
                        current_weights.setdefault(
                            reverse_edge,
                            float(current_weights.get(incoming_edge, 10.0)),
                        )
                        if incoming_edge in current_speeds:
                            current_speeds.setdefault(
                                reverse_edge, current_speeds[incoming_edge]
                            )
                    decision = self._recovery_decision(
                        step,
                        current_node,
                        previous_node,
                        reverse_edge,
                        current_weights,
                        current_speeds,
                        "RECOVERY_BACKTRACK",
                        f"Backtrack from dead end {current_node} to {previous_node}.",
                        decision_latency_ms,
                        length_m_override=reverse_length,
                    )
                else:
                    termination_reason = (
                        f"Unrecoverable dead end at {current_node}; no route or previous edge."
                    )
                    break

            next_node = str(decision.next_node)
            selected_edge = decision.selected_edge
            if selected_edge is None:
                termination_reason = f"No edge selected at {current_node}."
                break

            intentional_backtrack = "[RECOVERY_BACKTRACK]" in decision.strategy_name
            if (
                not intentional_backtrack
                and not following_recovery_path
                and visit_counts.get(next_node, 0) >= self.max_node_visits
            ):
                if perform_local_backtrack(
                    "RECOVERY_CYCLE_BACKTRACK",
                    f"Active-path cycle detected at {next_node}; backtrack and retry locally.",
                ):
                    recovery_events += 1
                    continue

                fallback = custom_dijkstra(
                    self.adjacency, current_weights, current_node, destination_node
                )
                if fallback.is_reached and fallback.edge_path:
                    recovery_events += 1
                    recovery_edge = fallback.edge_path[0]
                    recovery_next = fallback.node_path[1]
                    recovery_path_edges = list(fallback.edge_path[1:])
                    decision = self._recovery_decision(
                        step,
                        current_node,
                        recovery_next,
                        recovery_edge,
                        current_weights,
                        current_speeds,
                        "RECOVERY_CYCLE_BREAKER",
                        f"Cycle recovery at {next_node}; follow shortest-path edge {recovery_edge[0]}->{recovery_edge[1]}.",
                        decision_latency_ms,
                    )
                    next_node = recovery_next
                    selected_edge = recovery_edge
                else:
                    termination_reason = (
                        f"Cycle detected at {next_node}; no route to {destination_node}."
                    )
                    break

            edge_path.append(selected_edge)
            node_path.append(next_node)
            decisions.append(decision)
            total_time_s += decision.travel_time_s
            total_distance_m += decision.length_m
            previous_node, current_node = current_node, next_node
            visit_counts[current_node] = visit_counts.get(current_node, 0) + 1
            visited_nodes.add(current_node)
            active_path_edges.append(selected_edge)
            active_path_nodes.append(current_node)
            if self.local_backtracking:
                visited_nodes = set(active_path_nodes)
            step += 1

        if current_node == destination_node:
            success = True
            termination_reason = "Destination reached successfully."
        elif not termination_reason and step >= hop_limit:
            termination_reason = f"Maximum hops exceeded ({hop_limit} hops)."

        total_computation_ms = (time.perf_counter() - started) * 1000.0
        average_latency_ms = (
            sum(decision_latencies) / len(decision_latencies) if decision_latencies else 0.0
        )
        return SequentialJourneyResult(
            source_node=source_node,
            destination_node=destination_node,
            strategy_name=strategy_name,
            candidate_strategy=candidate_strategy,
            is_success=success,
            total_travel_time_s=round(total_time_s, 2),
            total_distance_m=round(total_distance_m, 2),
            node_path=node_path,
            edge_path=edge_path,
            decision_steps=decisions,
            total_decisions=len(decisions),
            forced_decisions=sum(1 for item in decisions if item.is_forced),
            recovery_events=recovery_events,
            reroute_events=reroute_events,
            traffic_updates_accepted=traffic_updates_accepted,
            average_decision_latency_ms=round(average_latency_ms, 3),
            total_computation_time_ms=round(total_computation_ms, 3),
            termination_reason=termination_reason,
        )
