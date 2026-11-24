"""Fair temporal comparison of fixed, dynamic, and sequential two-edge routing.

Predicted speeds are used only to choose routes.  The vehicle traverses each
edge using the observed speed stream from the replay frames, integrating across
hour boundaries.  Traffic information becomes available for routing at the next
intersection reached after its target-valid time.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import asdict, dataclass, field
from time import perf_counter
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

import numpy as np
import pandas as pd
import heapq

from src.routing.dijkstra import DijkstraResult, custom_dijkstra
from src.simulation.vehicle import Vehicle
from src.traffic.replay import TrafficReplayFrame


Edge = Tuple[str, str, int]
STRATEGIES = ("static_dijkstra", "dynamic_dijkstra", "geopulse_two_edge")


@dataclass
class RouteTraceCounter:
    """Measure revisits, route retracing, and closed loops as separate events.

    A backtracking event is a traversal of an edge in the reverse direction of
    any previously traversed edge (edge keys are ignored for parallel OSM links).
    A repeated-node visit is any arrival at a node seen earlier. A loop trap is
    a repeated-node arrival that closes a cycle of at least three edges. Thus an
    immediate reversal is a backtrack and repeat, but not a loop trap; a triangle
    closure is a repeat and loop trap, but not a backtrack.
    """

    origin: str
    node_path: List[str] = field(init=False)
    traversed_edges: List[Edge] = field(default_factory=list)
    backtracking_events: int = 0
    repeated_node_visits: int = 0
    loop_traps: int = 0

    def __post_init__(self) -> None:
        self.origin = str(self.origin)
        self.node_path = [self.origin]

    def record(self, edge: Edge) -> Dict[str, bool]:
        source, target = str(edge[0]), str(edge[1])
        if source != self.node_path[-1]:
            raise ValueError(f"Route trace edge {edge!r} does not leave {self.node_path[-1]!r}")
        repeated = target in self.node_path
        backtracking = any(
            str(previous[0]) == target and str(previous[1]) == source
            for previous in self.traversed_edges
        )
        loop_trap = False
        if repeated:
            self.repeated_node_visits += 1
            prior_index = max(index for index, node in enumerate(self.node_path) if node == target)
            cycle_edge_count = len(self.traversed_edges) - prior_index + 1
            loop_trap = cycle_edge_count >= 3
            if loop_trap:
                self.loop_traps += 1
        if backtracking:
            self.backtracking_events += 1
        self.traversed_edges.append((source, target, edge[2]))
        self.node_path.append(target)
        return {
            "backtracking_event": backtracking,
            "repeated_node_visit": repeated,
            "loop_trap": loop_trap,
        }


@dataclass
class TemporalJourneyResult:
    strategy: str
    origin: str
    destination: str
    departure_timestamp: str
    success: bool
    failure_reason: str
    travel_time_s: float
    distance_m: float
    two_edge_only_success: Optional[bool]
    traversed_edges: int
    intersection_decisions: int
    two_edge_alternative_selections: int
    prediction_updates_applied: int
    dijkstra_reroutes: int
    dijkstra_fallback_steps: int
    backtracking_events: int
    repeated_node_visits: int
    loop_traps: int
    mean_decision_latency_ms: Optional[float]
    p95_decision_latency_ms: Optional[float]
    mean_two_edge_decision_latency_ms: Optional[float]
    p95_two_edge_decision_latency_ms: Optional[float]
    execution_time_s: float
    traversed_edge_path: List[Edge] = field(default_factory=list)
    decision_trace: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        row = asdict(self)
        # Compatibility for earlier Phase 4 CSV consumers.
        row["backtracking_steps"] = row["backtracking_events"]
        row.pop("traversed_edge_path", None)
        row.pop("decision_trace", None)
        return row


class TemporalJourneyEngine:
    """Run the three routing policies against one replay and one realized stream."""

    HOUR = pd.Timedelta(hours=1)

    def __init__(self, weight_manager: Any, replay_frames: Sequence[TrafficReplayFrame]):
        if not replay_frames:
            raise ValueError("At least one historical replay frame is required")
        frames = sorted(replay_frames, key=lambda frame: frame.target_valid_timestamp)
        valid_times = [pd.Timestamp(frame.target_valid_timestamp) for frame in frames]
        if len(set(valid_times)) != len(valid_times):
            raise ValueError("Replay frames contain duplicate target-valid timestamps")
        for earlier, later in zip(valid_times, valid_times[1:]):
            if later - earlier != pd.Timedelta(hours=1):
                raise ValueError("Temporal journey replay requires contiguous hourly frames")
        if any(not frame.has_realized_observations for frame in frames):
            raise ValueError("Temporal execution requires saved actual_speed observations")
        self.weight_manager = weight_manager
        self.frames = list(frames)
        self.valid_times = valid_times
        # Frames apply on [target_valid_timestamp, next hour). The final
        # observation is held constant for that same one-hour interval only.
        self.final_valid_until = valid_times[-1] + self.HOUR
        self._predicted_weights: Dict[int, Dict[Edge, float]] = {}
        self._realized_speeds: Dict[int, Dict[Edge, float]] = {}
        self._tail_route_cache: Dict[
            Tuple[int, str], Tuple[Dict[str, float], Dict[str, Tuple[str, int]]]
        ] = {}
        reverse: Dict[str, List[Tuple[str, int]]] = {}
        for u, transitions in weight_manager.adjacency.items():
            for v, key in transitions:
                reverse.setdefault(v, []).append((u, key))
        self._reverse_adjacency = reverse

    @staticmethod
    def _timestamp(value: Any) -> pd.Timestamp:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize("UTC")
        else:
            timestamp = timestamp.tz_convert("UTC")
        return timestamp

    def _frame_index_at(self, timestamp: pd.Timestamp) -> int:
        if timestamp >= self.final_valid_until:
            raise ValueError(
                "Observed traffic timeline ended at "
                f"{self.final_valid_until.isoformat()} (exclusive)"
            )
        index = bisect_right(self.valid_times, timestamp) - 1
        if index < 0:
            raise ValueError(
                f"No target-valid prediction/observation frame at {timestamp.isoformat()}"
            )
        return index

    def _prediction_weights(self, index: int) -> Dict[Edge, float]:
        if index not in self._predicted_weights:
            weights, _, _ = self.weight_manager.build_scenario_weights(
                self.frames[index].predicted_speeds
            )
            self._predicted_weights[index] = weights
        return self._predicted_weights[index]

    def _realized_speeds_for(self, index: int) -> Dict[Edge, float]:
        if index not in self._realized_speeds:
            _, speeds, _ = self.weight_manager.build_scenario_weights(
                self.frames[index].realized_speeds
            )
            self._realized_speeds[index] = speeds
        return self._realized_speeds[index]

    def _adjacency_avoiding(self, blocked_nodes: Iterable[str]) -> Dict[str, List[Tuple[str, int]]]:
        blocked = {str(node) for node in blocked_nodes}
        return {
            u: [(v, key) for v, key in transitions if v not in blocked]
            for u, transitions in self.weight_manager.adjacency.items()
            if u not in blocked
        }

    def _route(
        self,
        source: str,
        destination: str,
        weights: Mapping[Edge, float],
        blocked_nodes: Iterable[str] = (),
    ) -> DijkstraResult:
        blocked = {str(node) for node in blocked_nodes} - {str(source)}
        return custom_dijkstra(
            self._adjacency_avoiding(blocked),
            dict(weights),
            str(source),
            str(destination),
        )

    def _remaining_route_tree(
        self,
        destination: str,
        weights: Mapping[Edge, float],
    ) -> Tuple[Dict[str, float], Dict[str, Tuple[str, int]]]:
        """Return a cached reverse Dijkstra tree for exact destination-tail costs."""
        target = str(destination)
        cache_key = (id(weights), target)
        if cache_key in self._tail_route_cache:
            return self._tail_route_cache[cache_key]

        distances: Dict[str, float] = {target: 0.0}
        next_hop: Dict[str, Tuple[str, int]] = {}
        queue: List[Tuple[float, str]] = [(0.0, target)]
        while queue:
            cost, node = heapq.heappop(queue)
            if cost != distances.get(node):
                continue
            for predecessor, key in self._reverse_adjacency.get(node, []):
                edge_cost = weights.get((predecessor, node, key))
                if edge_cost is None:
                    continue
                total = cost + edge_cost
                if total < distances.get(predecessor, float("inf")):
                    distances[predecessor] = total
                    next_hop[predecessor] = (node, key)
                    heapq.heappush(queue, (total, predecessor))

        tree = (distances, next_hop)
        self._tail_route_cache[cache_key] = tree
        return tree

    @staticmethod
    def _tail_from_tree(
        source: str,
        destination: str,
        tree: Tuple[Dict[str, float], Dict[str, Tuple[str, int]]],
    ) -> Optional[Tuple[float, List[Edge]]]:
        distances, next_hop = tree
        source, target = str(source), str(destination)
        if source not in distances:
            return None
        path: List[Edge] = []
        node = source
        seen = {source}
        while node != target:
            step = next_hop.get(node)
            if step is None or step[0] in seen:
                return None
            following, key = step
            path.append((node, following, key))
            node = following
            seen.add(node)
        return float(distances[source]), path

    @staticmethod
    def _nodes_for_edges(start: str, edges: Sequence[Edge]) -> List[str]:
        nodes = [str(start)]
        for edge in edges:
            if str(edge[0]) != nodes[-1]:
                raise ValueError(f"Non-contiguous temporal route at edge {edge!r}")
            nodes.append(str(edge[1]))
        return nodes

    def _two_edge_choice(
        self,
        current: str,
        destination: str,
        planned_edges: Sequence[Edge],
        weights: Mapping[Edge, float],
        visited: Set[str],
    ) -> Tuple[Optional[Edge], List[Edge], Dict[str, Any], bool, bool]:
        """Compare the planned next edge with its best reachable alternative."""
        blocked = set(visited) | {str(current)}
        tail_tree = self._remaining_route_tree(destination, weights)
        tail_cache: Dict[str, Optional[Tuple[float, List[Edge]]]] = {}

        def cached_tail(node: str) -> Optional[Tuple[float, List[Edge]]]:
            node = str(node)
            if node not in tail_cache:
                tail_cache[node] = self._tail_from_tree(node, destination, tail_tree)
            return tail_cache[node]

        planned = planned_edges[0] if planned_edges and planned_edges[0][0] == current else None
        lower_bounds: Dict[Edge, float] = {}
        for neighbor, key in self.weight_manager.adjacency.get(current, []):
            edge = (current, neighbor, key)
            if neighbor in visited or edge not in weights:
                continue
            tail = cached_tail(neighbor)
            if tail is None:
                continue
            lower_bounds[edge] = float(weights[edge]) + tail[0]

        if not lower_bounds:
            return None, [], {"reason": "no_reachable_candidate"}, False, False

        exact_options: Dict[Edge, Tuple[float, List[Edge]]] = {}

        def exact_candidate(edge: Edge) -> Optional[Tuple[float, List[Edge]]]:
            if edge in exact_options:
                return exact_options[edge]
            tail = cached_tail(edge[1])
            if tail is None:
                return None
            if any(path_edge[1] in blocked for path_edge in tail[1]):
                # The global shortest tail would revisit the active path. Use a
                # constrained Dijkstra only for this candidate, and only when
                # its lower bound could still win the two-edge comparison.
                constrained = self._route(edge[1], destination, weights, blocked)
                if not constrained.is_reached:
                    return None
                tail_cost = float(constrained.total_cost)
                tail_path = list(constrained.edge_path)
            else:
                tail_cost = tail[0]
                tail_path = list(tail[1])
            exact_options[edge] = (float(weights[edge]) + tail_cost, tail_path)
            return exact_options[edge]

        candidate_a = planned if planned in lower_bounds else None
        if candidate_a is None:
            # A stale planned edge can be repaired through a new Dijkstra suffix;
            # this remains a route-plan repair, not a selected fallback step.
            refreshed = self._route(current, destination, weights, visited)
            if refreshed.is_reached and refreshed.edge_path:
                candidate_a = refreshed.edge_path[0]
                if candidate_a not in lower_bounds:
                    candidate_a = None

        if candidate_a is None:
            candidate_a = min(
                lower_bounds,
                key=lambda edge: (lower_bounds[edge], edge[1], str(edge[2])),
            )
        score_a = exact_candidate(candidate_a)
        if score_a is None:
            lower_bounds.pop(candidate_a, None)
            if not lower_bounds:
                return None, [], {"reason": "no_reachable_candidate"}, False, False
            candidate_a = min(
                lower_bounds,
                key=lambda edge: (lower_bounds[edge], edge[1], str(edge[2])),
            )
            score_a = exact_candidate(candidate_a)
            if score_a is None:
                return None, [], {"reason": "no_reachable_candidate"}, False, False

        alternative_edges = sorted(
            (edge for edge in lower_bounds if edge != candidate_a),
            key=lambda edge: (lower_bounds[edge], edge[1], str(edge[2])),
        )
        candidate_b: Optional[Edge] = None
        score_b: Optional[Tuple[float, List[Edge]]] = None
        for edge in alternative_edges:
            if score_b is not None and lower_bounds[edge] >= score_b[0]:
                break
            candidate_score = exact_candidate(edge)
            if candidate_score is not None and (
                score_b is None or candidate_score[0] < score_b[0]
            ):
                candidate_b = edge
                score_b = candidate_score

        if candidate_b is None:
            selected = candidate_a
            forced = True
        else:
            selected = candidate_a if score_a[0] <= score_b[0] else candidate_b
            forced = False

        selected_tail = exact_options[selected][1]
        if selected == candidate_a and planned == candidate_a and len(planned_edges) > 1:
            planned_tail = list(planned_edges[1:])
            try:
                planned_tail_nodes = self._nodes_for_edges(selected[1], planned_tail)[1:]
            except ValueError:
                planned_tail_nodes = []
            if (
                planned_tail
                and planned_tail[-1][1] == destination
                and not (set(planned_tail_nodes) & visited)
            ):
                # Preserve the departure/last-selected plan through forced
                # corridors. New traffic changes affect the next actual choice
                # junction instead of silently replacing a one-edge choice.
                selected_tail = planned_tail
        next_plan = [selected, *selected_tail]
        trace = {
            "candidate_a": candidate_a,
            "score_a": score_a[0],
            "candidate_b": candidate_b,
            "score_b": score_b[0] if score_b else None,
            "selected_edge": selected,
            "decision_reason": "lower_predicted_edge_plus_dijkstra_tail_cost",
        }
        return selected, next_plan, trace, forced, candidate_b is not None

    def _traverse_realized(
        self,
        edge: Edge,
        current_time: pd.Timestamp,
    ) -> Tuple[float, pd.Timestamp]:
        length_m = float(self.weight_manager.edge_lengths[edge])
        remaining_m = length_m
        elapsed_s = 0.0
        now = current_time
        while remaining_m > 1e-7:
            frame_index = self._frame_index_at(now)
            speed_kmh = float(self._realized_speeds_for(frame_index)[edge])
            speed_mps = speed_kmh / 3.6
            if not np.isfinite(speed_mps) or speed_mps <= 0:
                raise RuntimeError(f"No valid realized speed for edge {edge!r}")
            if frame_index + 1 < len(self.valid_times):
                boundary = self.valid_times[frame_index + 1]
            else:
                boundary = self.final_valid_until
            if boundary <= now:
                raise ValueError(
                    f"Observed traffic replay ended before edge {edge!r} was traversed"
                )
            available_s = (boundary - now).total_seconds()
            possible_m = speed_mps * available_s
            if remaining_m <= possible_m:
                chunk_s = remaining_m / speed_mps
                elapsed_s += chunk_s
                now += pd.to_timedelta(chunk_s, unit="s")
                remaining_m = 0.0
            else:
                elapsed_s += available_s
                remaining_m -= possible_m
                now = boundary
                if now >= self.final_valid_until and remaining_m > 1e-7:
                    raise ValueError(
                        "Observed traffic replay ended at "
                        f"{self.final_valid_until.isoformat()} while traversing edge {edge!r}"
                    )
        return elapsed_s, now

    def run(
        self,
        origin: Any,
        destination: Any,
        departure_timestamp: Any,
        strategy: str,
        max_steps: Optional[int] = None,
    ) -> TemporalJourneyResult:
        if strategy not in STRATEGIES:
            raise ValueError(f"Unknown temporal routing strategy {strategy!r}")
        origin, destination = str(origin), str(destination)
        departure = self._timestamp(departure_timestamp)
        start_clock = perf_counter()
        trace: List[Dict[str, Any]] = []
        route_trace = RouteTraceCounter(origin)
        latency_samples: List[float] = []
        two_edge_latency_samples: List[float] = []
        counts = {
            "intersection_decisions": 0,
            "two_edge_alternative_selections": 0,
            "prediction_updates_applied": 0,
            "dijkstra_reroutes": 0,
            "dijkstra_fallback_steps": 0,
        }
        failure = ""
        success = False
        visited = {origin}
        current_time = departure
        current = origin
        route_result: Optional[DijkstraResult] = None
        planned_edges: List[Edge] = []
        route_cursor = 0
        last_prediction_index: Optional[int] = None

        try:
            frame_index = self._frame_index_at(departure)
            weights = self._prediction_weights(frame_index)
            route_result = self._route(origin, destination, weights)
            if not route_result.is_reached:
                failure = "destination_unreachable_at_departure"
            elif origin == destination:
                vehicle = Vehicle("phase4", origin, destination, departure.isoformat())
                vehicle.begin_temporal_journey([origin], [], departure.isoformat())
                vehicle.finish_temporal_journey(departure.isoformat())
                success = True
            else:
                vehicle = Vehicle("phase4", origin, destination, departure.isoformat())
                vehicle.begin_temporal_journey(
                    list(route_result.node_path), list(route_result.edge_path), departure.isoformat()
                )
                planned_edges = list(route_result.edge_path)
                last_prediction_index = frame_index
                if max_steps is None:
                    max_steps = max(100, len(self.weight_manager.adjacency) * 2)

                for step in range(max_steps):
                    current = str(vehicle.current_node)
                    if current == destination:
                        vehicle.finish_temporal_journey(current_time.isoformat())
                        success = True
                        break
                    frame_index = self._frame_index_at(current_time)
                    weights = self._prediction_weights(frame_index)
                    started = perf_counter()
                    selected_edge: Optional[Edge] = None
                    fallback_step = False
                    event: Dict[str, Any] = {
                        "strategy": strategy,
                        "step": step,
                        "timestamp": current_time.isoformat(),
                        "prediction_target_valid_timestamp": self.valid_times[frame_index].isoformat(),
                        "current_node": current,
                    }

                    if strategy == "static_dijkstra":
                        if route_cursor >= len(route_result.edge_path):
                            failure = "fixed_route_exhausted_before_destination"
                            break
                        selected_edge = route_result.edge_path[route_cursor]
                        route_cursor += 1
                        event.update(event="fixed_route_step", selected_edge=selected_edge)
                    elif strategy == "dynamic_dijkstra":
                        if frame_index != last_prediction_index:
                            reroute = self._route(current, destination, weights, visited)
                            counts["prediction_updates_applied"] += 1
                            old_edges = list(planned_edges)
                            if not reroute.is_reached:
                                reroute = self._route(current, destination, weights)
                            if not reroute.is_reached or not reroute.edge_path:
                                failure = "destination_unreachable_after_traffic_update"
                                event.update(event="reroute_failed", selected_edge=None)
                                trace.append(event)
                                break
                            planned_edges = list(reroute.edge_path)
                            last_prediction_index = frame_index
                            if planned_edges != old_edges:
                                counts["dijkstra_reroutes"] += 1
                            route_nodes = self._nodes_for_edges(current, planned_edges)
                            vehicle.set_temporal_plan(
                                route_nodes, planned_edges, current_time.isoformat(),
                                "Dynamic Dijkstra recomputed at the first intersection after a prediction update",
                            )
                            event.update(
                                event="dynamic_dijkstra_reroute",
                                route_changed=(planned_edges != old_edges),
                                selected_edge=planned_edges[0],
                            )
                        if not planned_edges:
                            failure = "dynamic_route_exhausted_before_destination"
                            break
                        selected_edge = planned_edges.pop(0)
                        event.setdefault("event", "dynamic_route_step")
                        event["selected_edge"] = selected_edge
                    else:
                        if frame_index != last_prediction_index:
                            counts["prediction_updates_applied"] += 1
                            last_prediction_index = frame_index
                            event["traffic_update_applied_at_intersection"] = True
                        selected_edge, new_plan, choice, forced, is_decision = self._two_edge_choice(
                            current, destination, planned_edges, weights, visited
                        )
                        if selected_edge is None:
                            fallback = self._route(current, destination, weights, visited)
                            if not fallback.is_reached or not fallback.edge_path:
                                fallback = self._route(current, destination, weights)
                            if not fallback.is_reached or not fallback.edge_path:
                                failure = "no_reachable_two_edge_candidate_or_fallback"
                                event.update(event="two_edge_dead_end", selected_edge=None)
                                trace.append(event)
                                break
                            selected_edge = fallback.edge_path[0]
                            new_plan = list(fallback.edge_path)
                            fallback_step = True
                            event.update(event="dijkstra_safety_fallback", selected_edge=selected_edge)
                        else:
                            event.update(
                                event=(
                                    "two_edge_decision"
                                    if is_decision else "two_edge_forced_continuation"
                                ),
                                **choice,
                            )
                            if is_decision:
                                counts["intersection_decisions"] += 1
                                two_edge_latency_samples.append(
                                    (perf_counter() - started) * 1000.0
                                )
                                if selected_edge == choice.get("candidate_b"):
                                    counts["two_edge_alternative_selections"] += 1
                            if forced:
                                event["forced_continuation"] = True
                        planned_edges = list(new_plan)
                        route_nodes = self._nodes_for_edges(current, planned_edges)
                        vehicle.set_temporal_plan(
                            route_nodes, planned_edges, current_time.isoformat(),
                            "Sequential Two-Edge decision updated the remaining Dijkstra-costed plan",
                        )

                    if selected_edge is None:
                        failure = failure or "no_next_edge"
                        break
                    if str(selected_edge[0]) != current:
                        failure = f"non_contiguous_selected_edge:{selected_edge!r}"
                        break
                    latency_ms = (perf_counter() - started) * 1000.0
                    if strategy != "static_dijkstra":
                        latency_samples.append(latency_ms)
                    try:
                        edge_time_s, arrival_time = self._traverse_realized(selected_edge, current_time)
                    except (RuntimeError, ValueError) as exc:
                        failure = f"realized_traffic_unavailable:{exc}"
                        event["selected_edge"] = selected_edge
                        event["decision_latency_ms"] = latency_ms
                        trace.append(event)
                        break
                    edge_length = float(self.weight_manager.edge_lengths[selected_edge])
                    vehicle.record_realized_edge_traversal(
                        selected_edge,
                        edge_time_s,
                        edge_length,
                        arrival_time.isoformat(),
                    )
                    next_node = str(selected_edge[1])
                    route_events = route_trace.record(selected_edge)
                    visited.add(next_node)
                    current_time = arrival_time
                    current = next_node
                    if (
                        strategy == "geopulse_two_edge"
                        and planned_edges
                        and planned_edges[0] == selected_edge
                    ):
                        # The next intersection must compare the next edge of
                        # the maintained plan, not the edge just traversed.
                        planned_edges.pop(0)
                    event.update(
                        realized_travel_time_s=edge_time_s,
                        distance_m=edge_length,
                        arrival_timestamp=arrival_time.isoformat(),
                        decision_latency_ms=latency_ms,
                        dijkstra_fallback_step=fallback_step,
                        **route_events,
                    )
                    if fallback_step:
                        counts["dijkstra_fallback_steps"] += 1
                    trace.append(event)
                else:
                    failure = "maximum_edge_steps_exceeded"

                if current == destination and not success:
                    vehicle.finish_temporal_journey(current_time.isoformat())
                    success = True
        except (ValueError, KeyError, RuntimeError) as exc:
            failure = failure or f"simulation_error:{exc}"
            vehicle = locals().get("vehicle")

        elapsed = perf_counter() - start_clock
        if "vehicle" in locals():
            travel_time_s = float(vehicle.elapsed_travel_time_s)
            distance_m = float(vehicle.accumulated_distance_m)
            traversed_edges = len(vehicle.temporal_traversed_edges)
            traversed_path = list(vehicle.temporal_traversed_edges)
        else:
            travel_time_s = 0.0
            distance_m = 0.0
            traversed_edges = 0
            traversed_path = []
        if not success and not failure:
            failure = "journey_not_completed"
        return TemporalJourneyResult(
            strategy=strategy,
            origin=origin,
            destination=destination,
            departure_timestamp=departure.isoformat(),
            success=success,
            failure_reason=failure,
            travel_time_s=travel_time_s,
            distance_m=distance_m,
            two_edge_only_success=(
                success
                and counts["dijkstra_fallback_steps"] == 0
                and route_trace.backtracking_events == 0
                if strategy == "geopulse_two_edge" else None
            ),
            traversed_edges=traversed_edges,
            intersection_decisions=counts["intersection_decisions"],
            two_edge_alternative_selections=counts["two_edge_alternative_selections"],
            prediction_updates_applied=counts["prediction_updates_applied"],
            dijkstra_reroutes=counts["dijkstra_reroutes"],
            dijkstra_fallback_steps=counts["dijkstra_fallback_steps"],
            backtracking_events=route_trace.backtracking_events,
            repeated_node_visits=route_trace.repeated_node_visits,
            loop_traps=route_trace.loop_traps,
            mean_decision_latency_ms=float(np.mean(latency_samples)) if latency_samples else None,
            p95_decision_latency_ms=float(np.percentile(latency_samples, 95)) if latency_samples else None,
            mean_two_edge_decision_latency_ms=(
                float(np.mean(two_edge_latency_samples)) if two_edge_latency_samples else None
            ),
            p95_two_edge_decision_latency_ms=(
                float(np.percentile(two_edge_latency_samples, 95))
                if two_edge_latency_samples else None
            ),
            execution_time_s=elapsed,
            traversed_edge_path=traversed_path,
            decision_trace=trace,
        )
