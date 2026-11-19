"""
GeoPulse Sequential Route Controller Module

Orchestrates sequential two-edge decision journeys from origin to destination.
Features:
- Step-by-step intersection progression.
- Route safety:
    * Cycle detection & loop breaking (tracks node visit frequencies).
    * Maximum hop limit protection.
    * Dead-end recovery (fallback Dijkstra subpath solver).
    * Reversal prevention.
- Dynamic rerouting integration:
    * Traffic condition change detection.
    * Dual-threshold hysteresis gating.
    * Seamless continuation from active vehicle position without teleportation.
- Comprehensive metrics recording:
    * Total accumulated travel time (seconds).
    * Total accumulated distance (meters).
    * Number of decision steps, forced continuations, recovery events, reroutes.
    * Per-decision evaluation latencies.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Set, Optional, Any
import time

from src.routing.dijkstra import custom_dijkstra, DijkstraResult
from src.routing.two_edge_selector import TwoEdgeSelector, TwoEdgeDecisionStep
from src.routing.traffic_weights import calculate_travel_time_seconds


@dataclass
@dataclass
class SequentialJourneyResult:
    """Encapsulates the complete outcome of a sequential two-edge routing journey."""
    source_node: str
    destination_node: str
    strategy_name: str
    candidate_strategy: str
    is_success: bool
    total_travel_time_s: float
    total_distance_m: float
    node_path: List[str]
    edge_path: List[Tuple[str, str, int]]
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
    """Encapsulates the complete outcome of a sequential two-edge routing journey."""
    source_node: str
    destination_node: str
    strategy_name: str
    candidate_strategy: str
    is_success: bool
    total_travel_time_s: float
    total_distance_m: float
    node_path: List[str]
    edge_path: List[Tuple[str, str, int]]
    decision_steps: List[TwoEdgeDecisionStep]
    total_decisions: int
    forced_decisions: int
    recovery_events: int
    reroute_events: int
    average_decision_latency_ms: float
    total_computation_time_ms: float
    termination_reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class RouteController:
    """Executes sequential routing journeys, managing state, safety, and dynamic rerouting."""

    def __init__(
        self,
        adjacency: Dict[str, List[Tuple[str, int]]],
        edge_lengths: Dict[Tuple[str, str, int], float],
        two_edge_selector: TwoEdgeSelector,
        max_hops_multiplier: float = 3.0,
        max_node_visits: int = 2,
        reroute_threshold_seconds: float = 10.0,
        reroute_threshold_percent: float = 3.0,
    ):
        self.adjacency = adjacency
        self.edge_lengths = edge_lengths
        self.selector = two_edge_selector
        self.max_hops_multiplier = float(max_hops_multiplier)
        self.max_node_visits = int(max_node_visits)
        self.reroute_threshold_s = float(reroute_threshold_seconds)
        self.reroute_threshold_pct = float(reroute_threshold_percent)

    def execute_journey(
        self,
        source: str,
        destination: str,
        initial_weights: Dict[Tuple[str, str, int], float],
        initial_speeds: Optional[Dict[Tuple[str, str, int], float]] = None,
        traffic_update_step: Optional[int] = None,
        updated_weights: Optional[Dict[Tuple[str, str, int], float]] = None,
        updated_speeds: Optional[Dict[Tuple[str, str, int], float]] = None,
        max_hops: Optional[int] = None,
        reference_dijkstra: Optional[DijkstraResult] = None,
    ) -> SequentialJourneyResult:
        """Executes a complete sequential journey from source to destination.

        Parameters
        ----------
        source : str
            Origin node.
        destination : str
            Target destination node.
        initial_weights : Dict[Tuple[str, str, int], float]
            Starting edge traversal weights in seconds.
        initial_speeds : Optional[Dict[Tuple[str, str, int], float]]
            Starting edge speeds in km/h.
        traffic_update_step : Optional[int]
            Step index at which traffic update arrives.
        updated_weights : Optional[Dict[Tuple[str, str, int], float]]
            New edge weights post-update.
        updated_speeds : Optional[Dict[Tuple[str, str, int], float]]
            New edge speeds post-update.
        max_hops : Optional[int]
            Hard limit on maximum edge traversals.
        reference_dijkstra : Optional[DijkstraResult]
            Precomputed reference path for baseline comparison.
        """
        start_time_perf = time.perf_counter()
        source_str = str(source)
        dest_str = str(destination)

        if source_str == dest_str:
            return SequentialJourneyResult(
                source_node=source_str,
                destination_node=dest_str,
                strategy_name=self.selector.decision_strategy.name,
                candidate_strategy=self.selector.candidate_strategy.value,
                is_success=True,
                total_travel_time_s=0.0,
                total_distance_m=0.0,
                node_path=[source_str],
                edge_path=[],
                decision_steps=[],
                total_decisions=0,
                forced_decisions=0,
                recovery_events=0,
                reroute_events=0,
                average_decision_latency_ms=0.0,
                total_computation_time_ms=0.0,
                termination_reason="Source equals destination.",
            )

        # Determine hop bound
        if max_hops is None:
            if reference_dijkstra and reference_dijkstra.is_reached and reference_dijkstra.node_path:
                computed_max_hops = max(50, int(len(reference_dijkstra.node_path) * self.max_hops_multiplier))
            else:
                computed_max_hops = 200
        else:
            computed_max_hops = max(10, int(max_hops))

        # Runtime tracking
        current_weights = dict(initial_weights)
        current_speeds = dict(initial_speeds) if initial_speeds else {}
        curr_node = source_str
        prev_node: Optional[str] = None
        node_path: List[str] = [curr_node]
        edge_path: List[Tuple[str, str, int]] = []
        decision_steps: List[TwoEdgeDecisionStep] = []
        visited_node_counts: Dict[str, int] = {curr_node: 1}
        visited_nodes_set: Set[str] = {curr_node}
        total_travel_time = 0.0
        total_distance = 0.0
        recovery_count = 0
        reroute_count = 0  # placeholder will be removed
        is_success = False
        termination_reason = ""
        decision_latencies: List[float] = []
        step = 0
        # New counters
        traffic_updates_accepted = 0
        actual_reroute_events = 0
        accepted_update_flag = False
        old_weights_snapshot = None
        old_speeds_snapshot = None

        while step < computed_max_hops:
            # Destination reached?
            if curr_node == dest_str:
                is_success = True
                termination_reason = "Destination reached successfully."
                break

                        # Dynamic traffic update handling (once)
            if (
                traffic_update_step is not None
                and step == traffic_update_step
                and updated_weights
            ):
                old_weights_snapshot = dict(current_weights)
                old_speeds_snapshot = dict(current_speeds)
                current_weights = dict(updated_weights)
                if updated_speeds:
                    current_speeds = dict(updated_speeds)
                # Compute remaining travel times
                remaining_old = custom_dijkstra(self.adjacency, old_weights_snapshot, curr_node, dest_str)
                remaining_old_time = (
                    sum(old_weights_snapshot.get(e, 10.0) for e in remaining_old.edge_path)
                    if remaining_old.is_reached
                    else float("inf")
                )
                remaining_new = custom_dijkstra(self.adjacency, current_weights, curr_node, dest_str)
                remaining_new_time = (
                    sum(current_weights.get(e, 10.0) for e in remaining_new.edge_path)
                    if remaining_new.is_reached
                    else float("inf")
                )
                absolute_saving = remaining_old_time - remaining_new_time
                relative_saving = (
                    (absolute_saving / remaining_old_time) * 100.0
                    if remaining_old_time > 0
                    else 0.0
                )
                if (
                    absolute_saving >= self.reroute_threshold_s
                    and relative_saving >= self.reroute_threshold_pct
                ):
                    # Accept update
                    reroute_count += 1
                    accepted_update_flag = True
                    traffic_updates_accepted += 1
                else:
                    # revert to previous state
                    current_weights = old_weights_snapshot
                    current_speeds = old_speeds_snapshot
                    accepted_update_flag = False
                # store snapshots for later comparison
                old_weights = old_weights_snapshot
                old_speeds = old_speeds_snapshot
            else:
                old_weights = None
                old_speeds = None
                accepted_update_flag = False

            if (
                traffic_update_step is not None
                and step == traffic_update_step
                and updated_weights
            ):
                old_weights = dict(current_weights)
                old_speeds = dict(current_speeds)
                current_weights = dict(updated_weights)
                if updated_speeds:
                    current_speeds = dict(updated_speeds)
                # Compute remaining travel times
                remaining_old = custom_dijkstra(self.adjacency, old_weights, curr_node, dest_str)
                remaining_old_time = (
                    sum(old_weights.get(e, 10.0) for e in remaining_old.edge_path)
                    if remaining_old.is_reached
                    else float("inf")
                )
                remaining_new = custom_dijkstra(self.adjacency, current_weights, curr_node, dest_str)
                remaining_new_time = (
                    sum(current_weights.get(e, 10.0) for e in remaining_new.edge_path)
                    if remaining_new.is_reached
                    else float("inf")
                )
                absolute_saving = remaining_old_time - remaining_new_time
                relative_saving = (
                    (absolute_saving / remaining_old_time) * 100.0
                    if remaining_old_time > 0
                    else 0.0
                )
                if (
                    absolute_saving >= self.reroute_threshold_s
                    and relative_saving >= self.reroute_threshold_pct
                ):
                    reroute_count += 1  # keep updated weights
                else:
                    # revert to previous state
                    current_weights = old_weights
                    current_speeds = old_speeds

            # Two‑edge selection
            t_step_start = time.perf_counter()
            decision: TwoEdgeDecisionStep = self.selector.decide_next_edge(
                step_index=step,
                current_node=curr_node,
                destination=dest_str,
                edge_weights=current_weights,
                edge_speeds=current_speeds,
                previous_node=prev_node,
                visited_nodes=visited_nodes_set,
            )
            step_lat_ms = (time.perf_counter() - t_step_start) * 1000.0
            decision_latencies.append(step_lat_ms)

            # Dead‑end or missing decision handling
            if decision.is_dead_end or decision.selected_edge is None or decision.next_node is None:
                recovery_count += 1
                fallback_res = custom_dijkstra(self.adjacency, current_weights, curr_node, dest_str)
                if fallback_res.is_reached and fallback_res.edge_path:
                    # Simple forward recovery from current node
                    rec_edge = fallback_res.edge_path[0]
                    rec_next = fallback_res.node_path[1]
                    rec_len = self.edge_lengths.get(rec_edge, 50.0)
                    rec_cost = current_weights.get(rec_edge, 10.0)
                    rec_speed = current_speeds.get(
                        rec_edge,
                        (rec_len / rec_cost * 3.6) if rec_cost > 0 else 30.0,
                    )
                    decision = TwoEdgeDecisionStep(
                        step_index=step,
                        current_node=curr_node,
                        next_node=rec_next,
                        selected_edge=rec_edge,
                        candidate_a=None,
                        candidate_b=None,
                        score_a=None,
                        score_b=None,
                        travel_time_s=rec_cost,
                        length_m=rec_len,
                        speed_kmh=rec_speed,
                        strategy_name=f"{self.selector.decision_strategy.name} [RECOVERY_DEAD_END]",
                        decision_reason=f"Dead‑end recovery invoked at node {curr_node}; routed along {rec_edge[0]}->{rec_edge[1]}.",
                        is_forced=True,
                        is_dead_end=False,
                        evaluation_time_ms=step_lat_ms,
                    )
                # Backtrack recovery – record a reverse traversal if edge exists
                # Find all reverse edges (any lane id) between current and previous node
                reverse_candidates = []
                for e in self.edge_lengths:
                    if e[0] == curr_node and e[1] == prev_node:
                        reverse_candidates.append(e)
                if reverse_candidates:
                    # Choose the one with the lowest current travel‑time weight
                    reverse_edge = min(
                        reverse_candidates,
                        key=lambda e: current_weights.get(e, 10.0)
                    )
                else:
                    reverse_edge = None
                if reverse_edge is not None:
                    rev_len = self.edge_lengths[reverse_edge]
                    rev_cost = current_weights.get(reverse_edge, 10.0)
                    rev_speed = current_speeds.get(
                        reverse_edge,
                        (rev_len / rev_cost * 3.6) if rev_cost > 0 else 30.0,
                    )
                    decision = TwoEdgeDecisionStep(
                        step_index=step,
                        current_node=curr_node,
                        next_node=prev_node,
                        selected_edge=reverse_edge,
                        candidate_a=None,
                        candidate_b=None,
                        score_a=None,
                        score_b=None,
                        travel_time_s=rev_cost,
                        length_m=rev_len,
                        speed_kmh=rev_speed,
                        strategy_name=f"{self.selector.decision_strategy.name} [RECOVERY_BACKTRACK]",
                        decision_reason=f"Backtrack from dead‑end {curr_node} to {prev_node}.",
                        is_forced=True,
                        is_dead_end=False,
                        evaluation_time_ms=step_lat_ms,
                    )
                    # Update current position for movement below
                    next_node = prev_node
                    selected_edge = reverse_edge
                else:
                    termination_reason = f"Unrecoverable dead-end at {curr_node}; no reverse edge."
                    break

                    # Backtrack recovery – record a reverse traversal if edge exists
                # Find all reverse edges (any lane id) between current and previous node
                reverse_candidates = []
                for e in self.edge_lengths:
                    if e[0] == curr_node and e[1] == prev_node:
                        reverse_candidates.append(e)
                if reverse_candidates:
                    # Choose the one with the lowest current travel‑time weight
                    reverse_edge = min(
                        reverse_candidates,
                        key=lambda e: current_weights.get(e, 10.0)
                    )
                else:
                    reverse_edge = None
                    # Find any reverse edge regardless of lane id
                    reverse_edge = None
                    for e in self.edge_lengths:
                        if e[0] == curr_node and e[1] == prev_node:
                            reverse_edge = e
                            break
                    if reverse_edge is not None:
                    if reverse_edge in self.edge_lengths:
                        rev_len = self.edge_lengths[reverse_edge]
                        rev_cost = current_weights.get(reverse_edge, 10.0)
                        rev_speed = current_speeds.get(
                            reverse_edge,
                            (rev_len / rev_cost * 3.6) if rev_cost > 0 else 30.0,
                        )
                        decision = TwoEdgeDecisionStep(
                            step_index=step,
                            current_node=curr_node,
                            next_node=prev_node,
                            selected_edge=reverse_edge,
                            candidate_a=None,
                            candidate_b=None,
                            score_a=None,
                            score_b=None,
                            travel_time_s=rev_cost,
                            length_m=rev_len,
                            speed_kmh=rev_speed,
                            strategy_name=f"{self.selector.decision_strategy.name} [RECOVERY_BACKTRACK]",
                            decision_reason=f"Backtrack from dead‑end {curr_node} to {prev_node}.",
                            is_forced=True,
                            is_dead_end=False,
                            evaluation_time_ms=step_lat_ms,
                        )
                        # Update current position for movement below
                        next_node = prev_node
                        selected_edge = reverse_edge
                    else:
                        termination_reason = f"Unrecoverable dead-end at {curr_node}; no reverse edge."
                        break
                else:
                    termination_reason = f"Unrecoverable dead‑end at {curr_node}."
                    break

            # If we have a fresh decision (not overwritten by recovery), extract next info
            next_node = decision.next_node
            selected_edge = decision.selected_edge

            # Cycle detection
            node_visits = visited_node_counts.get(next_node, 0)
            if node_visits >= self.max_node_visits:
                # Detected a cycle; attempt recovery without reusing the edge that caused the cycle
                recovery_count += 1
                fallback_res = custom_dijkstra(self.adjacency, current_weights, curr_node, dest_str)
                if fallback_res.is_reached and fallback_res.edge_path:
                    # Find an alternative edge that starts from the current node and is not the offending edge
                    alternative_edge = None
                    for alt in fallback_res.edge_path:
                        if alt != selected_edge and alt[0] == curr_node:
                            alternative_edge = alt
                            break
                    if alternative_edge is None:
                        # No valid alternative first edge; abort safely
                        termination_reason = f"Cycle detected at {next_node} with no alternative first edge; terminating."
                        break
                    rec_edge = alternative_edge
                    # The destination node of the chosen edge is the next node
                    rec_next = rec_edge[1]
                    rec_len = self.edge_lengths.get(rec_edge, 50.0)
                    rec_cost = current_weights.get(rec_edge, 10.0)
                    rec_speed = current_speeds.get(
                        rec_edge,
                        (rec_len / rec_cost * 3.6) if rec_cost > 0 else 30.0,
                    )
                    decision = TwoEdgeDecisionStep(
                        step_index=step,
                        current_node=curr_node,
                        next_node=rec_next,
                        selected_edge=rec_edge,
                        candidate_a=None,
                        candidate_b=None,
                        score_a=None,
                        score_b=None,
                        travel_time_s=rec_cost,
                        length_m=rec_len,
                        speed_kmh=rec_speed,
                        strategy_name=f"{self.selector.decision_strategy.name} [RECOVERY_CYCLE_BREAKER]",
                        decision_reason=f"Cycle break at {next_node} (visited {node_visits} times) using alternative edge.",
                        is_forced=True,
                        is_dead_end=False,
                        evaluation_time_ms=step_lat_ms,
                    )
                    next_node = rec_next
                    selected_edge = rec_edge
                else:
                    termination_reason = f"Cycle detected at {next_node} but no fallback path found."
                    break
                node_visits = visited_node_counts.get(next_node, 0)
                if node_visits >= self.max_node_visits:
                    # Detected a cycle; attempt recovery without reusing the edge that caused the cycle
                    recovery_count += 1
                    fallback_res = custom_dijkstra(self.adjacency, current_weights, curr_node, dest_str)
                    if fallback_res.is_reached and fallback_res.edge_path:
                        # Prefer an alternative edge different from the one that just caused the cycle
                        alternative_edge = None
                        for alt in fallback_res.edge_path:
                            if alt != selected_edge:
                                alternative_edge = alt
                                break
                        if alternative_edge is None:
                            # No alternative edge available; abort safely
                            termination_reason = f"Cycle detected at {next_node} with no alternative edge; terminating."
                            break
                        rec_edge = alternative_edge
                        rec_next = fallback_res.node_path[1]
                        rec_len = self.edge_lengths.get(rec_edge, 50.0)
                        rec_cost = current_weights.get(rec_edge, 10.0)
                        rec_speed = current_speeds.get(
                            rec_edge,
                            (rec_len / rec_cost * 3.6) if rec_cost > 0 else 30.0,
                        )
                        decision = TwoEdgeDecisionStep(
                            step_index=step,
                            current_node=curr_node,
                            next_node=rec_next,
                            selected_edge=rec_edge,
                            candidate_a=None,
                            candidate_b=None,
                            score_a=None,
                            score_b=None,
                            travel_time_s=rec_cost,
                            length_m=rec_len,
                            speed_kmh=rec_speed,
                            strategy_name=f"{self.selector.decision_strategy.name} [RECOVERY_CYCLE_BREAKER]",
                            decision_reason=f"Cycle break at {next_node} (visited {node_visits} times) using alternative edge.",
                            is_forced=True,
                            is_dead_end=False,
                            evaluation_time_ms=step_lat_ms,
                        )
                        next_node = rec_next
                        selected_edge = rec_edge
                    else:
                        termination_reason = f"Cycle detected at {next_node} but no fallback path found."
                        break

            node_visits = visited_node_counts.get(next_node, 0)
            if node_visits >= self.max_node_visits:
                recovery_count += 1
                fallback_res = custom_dijkstra(self.adjacency, current_weights, curr_node, dest_str)
                if fallback_res.is_reached and fallback_res.edge_path:
                    rec_edge = fallback_res.edge_path[0]
                    rec_next = fallback_res.node_path[1]
                    rec_len = self.edge_lengths.get(rec_edge, 50.0)
                    rec_cost = current_weights.get(rec_edge, 10.0)
                    rec_speed = current_speeds.get(
                        rec_edge,
                        (rec_len / rec_cost * 3.6) if rec_cost > 0 else 30.0,
                    )
                    decision = TwoEdgeDecisionStep(
                        step_index=step,
                        current_node=curr_node,
                        next_node=rec_next,
                        selected_edge=rec_edge,
                        candidate_a=None,
                        candidate_b=None,
                        score_a=None,
                        score_b=None,
                        travel_time_s=rec_cost,
                        length_m=rec_len,
                        speed_kmh=rec_speed,
                        strategy_name=f"{self.selector.decision_strategy.name} [RECOVERY_CYCLE_BREAKER]",
                        decision_reason=f"Cycle break at {next_node} (visited {node_visits} times).",
                        is_forced=True,
                        is_dead_end=False,
                        evaluation_time_ms=step_lat_ms,
                    )
                    next_node = rec_next
                    selected_edge = rec_edge

            # Record movement
            edge_path.append(selected_edge)
            node_path.append(next_node)
            decision_steps.append(decision)
            total_travel_time += decision.travel_time_s
            total_distance += decision.length_m
            prev_node = curr_node
            curr_node = next_node
            visited_node_counts[curr_node] = visited_node_counts.get(curr_node, 0) + 1
            visited_nodes_set.add(curr_node)
            step += 1

        # Post‑loop termination handling
        if not is_success and step >= computed_max_hops:
            termination_reason = f"Maximum hops exceeded ({computed_max_hops} hops)."

        total_comp_ms = (time.perf_counter() - start_time_perf) * 1000.0
        avg_lat_ms = (sum(decision_latencies) / len(decision_latencies)) if decision_latencies else 0.0
        forced_count = sum(1 for d in decision_steps if d.is_forced)

        return SequentialJourneyResult(
            source_node=source_str,
            destination_node=dest_str,
            strategy_name=self.selector.decision_strategy.name,
            candidate_strategy=self.selector.candidate_strategy.value,
            is_success=is_success,
            total_travel_time_s=round(total_travel_time, 2),
            total_distance_m=round(total_distance, 2),
            node_path=node_path,
            edge_path=edge_path,
            decision_steps=decision_steps,
            total_decisions=len(decision_steps),
            forced_decisions=forced_count,
            recovery_events=recovery_count,
            reroute_events=reroute_count,
            average_decision_latency_ms=round(avg_lat_ms, 3),
            total_computation_time_ms=round(total_comp_ms, 3),
            termination_reason=termination_reason,
        )
