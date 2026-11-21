"""
GeoPulse Candidate Edge Generator Module

Responsible for identifying, filtering, and selecting eligible outgoing edges
at any intersection node during sequential routing.

Supports:
- Out-degree handling (=0 dead ends, =1 forced continuations, =2 natural pairs, >2 branching).
- Reversal avoidance (prevents immediate u -> v -> u oscillation unless cul-de-sac).
- Visited loop penalties.
- Configurable candidate generation strategies:
    1. RANDOM: Uniformly sampled pairs.
    2. LOWEST_IMMEDIATE_COST: Two lowest immediate travel-time edges.
    3. DESTINATION_AWARE: Two edges minimizing immediate cost + remaining heuristic.
    4. LOOKAHEAD: Two edges minimizing limited lookahead cost.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Tuple, Set, Optional, Any, Callable
import math
import random
import networkx as nx


class CandidateGenerationStrategy(str, Enum):
    RANDOM = "random"
    LOWEST_IMMEDIATE_COST = "lowest_immediate_cost"
    DESTINATION_AWARE = "destination_aware"
    LOOKAHEAD = "lookahead"
    FASTEST_PLUS_PROGRESS = "fastest_plus_progress"
    DESTINATION_PLUS_LOOKAHEAD = "destination_plus_lookahead"
    ADAPTIVE_DIVERSE = "adaptive_diverse"


@dataclass
class CandidateEdge:
    """Encapsulates a candidate outgoing edge from current node."""
    u: str
    v: str
    key: int
    length_m: float
    speed_kmh: float
    travel_time_s: float
    heuristic_remaining_s: float = 0.0
    total_estimated_s: float = 0.0
    is_forced: bool = False
    attributes: Dict[str, Any] = field(default_factory=dict)

    @property
    def edge_tuple(self) -> Tuple[str, str, int]:
        return (self.u, self.v, self.key)


@dataclass
class CandidateGenerationResult:
    """Encapsulates the candidates identified at an intersection."""
    current_node: str
    candidates: List[CandidateEdge]
    total_outgoing_count: int
    eligible_count: int
    is_dead_end: bool = False
    is_forced: bool = False
    status_message: str = ""


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in meters."""
    R = 6371000.0  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


class CandidateGenerator:
    """
    Identifies and filters candidate outgoing edges for sequential two-edge decision making.
    """

    def __init__(
        self,
        adjacency: Dict[str, List[Tuple[str, int]]],
        edge_lengths: Dict[Tuple[str, str, int], float],
        node_coords: Optional[Dict[str, Tuple[float, float]]] = None,
        default_free_flow_speed_kmh: float = 25.0,
        random_seed: Optional[int] = 42
    ):
        """
        Parameters
        ----------
        adjacency : Dict[str, List[Tuple[str, int]]]
            Adjacency dictionary mapping node u -> list of (v, key).
        edge_lengths : Dict[Tuple[str, str, int], float]
            Mapping of directed edge (u, v, key) -> metric length in meters.
        node_coords : Optional[Dict[str, Tuple[float, float]]]
            Mapping of node -> (lat, lon) or (y, x) for heuristic estimation.
        default_free_flow_speed_kmh : float
            Speed used in the straight-line Haversine travel-time estimate.
            The default 25 km/h matches the existing research configuration but is
            not an admissible lower bound when any edge can be faster than 25 km/h.
        random_seed : Optional[int]
            Random seed for reproducibility in stochastic selection.
        """
        self.adjacency = adjacency
        self.edge_lengths = edge_lengths
        self.node_coords = node_coords or {}
        self.default_free_flow_speed_kmh = float(default_free_flow_speed_kmh)
        self.free_flow_speed_ms = max(self.default_free_flow_speed_kmh / 3.6, 1.0)
        self.rng = random.Random(random_seed)

    def estimate_remaining_time(self, from_node: str, to_node: str) -> float:
        """
        Straight-line remaining-time estimate. It is a lower bound only when the
        configured speed is at least the maximum speed allowed on every graph edge.
        """
        if from_node == to_node:
            return 0.0

        if from_node in self.node_coords and to_node in self.node_coords:
            lat1, lon1 = self.node_coords[from_node]
            lat2, lon2 = self.node_coords[to_node]
            dist_m = haversine_distance_m(lat1, lon1, lat2, lon2)
            return dist_m / self.free_flow_speed_ms

        # Fallback if coordinates missing: nominal cost 0.0 (still admissible)
        return 0.0

    def generate_candidates(
        self,
        current_node: str,
        destination: str,
        edge_weights: Dict[Tuple[str, str, int], float],
        edge_speeds: Optional[Dict[Tuple[str, str, int], float]] = None,
        previous_node: Optional[str] = None,
        visited_nodes: Optional[Set[str]] = None,
        strategy: CandidateGenerationStrategy = CandidateGenerationStrategy.DESTINATION_AWARE,
        lookahead_evaluator: Optional[Callable[[Tuple[str, str, int]], float]] = None,
        avoid_visited_successors: bool = False,
        excluded_edges: Optional[Set[Tuple[str, str, int]]] = None,
        corridor_assessor: Optional[Callable[[Tuple[str, str, int]], Any]] = None,
        corridor_policy: Optional[str] = None,
    ) -> CandidateGenerationResult:
        """
        Generates candidate outgoing edges from current_node.

        Parameters
        ----------
        current_node : str
            Current intersection node.
        destination : str
            Target destination node.
        edge_weights : Dict[Tuple[str, str, int], float]
            Active travel times in seconds for edges.
        edge_speeds : Optional[Dict[Tuple[str, str, int], float]]
            Active speeds in km/h for edges.
        previous_node : Optional[str]
            Node from which vehicle entered current_node (used for reversal pruning).
        visited_nodes : Optional[Set[str]]
            Nodes on the active journey path.
        strategy : CandidateGenerationStrategy
            Strategy used to reduce >2 eligible edges down to exactly 2 candidates.
        lookahead_evaluator : Optional[Callable]
            Evaluation function for lookahead candidate ranking.
        avoid_visited_successors : bool
            When true, do not select an edge back into the active path while any
            successor remains unvisited. If every successor is on the active path,
            return a loop trap so the controller can backtrack and retry a branch.
        excluded_edges : Optional[Set[Tuple[str, str, int]]]
            Directed edges already explored and rejected during local backtracking.
        corridor_assessor : Optional[Callable]
            Bounded forced-corridor inspection for one outgoing edge.
        corridor_policy : Optional[str]
            ``ranking`` ranks proven safe corridors ahead of incomplete paths and
            proven traps. ``conservative_rejection`` filters proven traps only
            when another candidate remains; cap-incomplete paths are retained.

        Returns
        -------
        CandidateGenerationResult
            Result containing selected candidates (0 for dead-end, 1 for forced, 2 for choice).
        """
        visited = visited_nodes or set()
        excluded = excluded_edges or set()
        self.last_corridor_checks = []
        raw_out = self.adjacency.get(str(current_node), [])
        total_out_count = len(raw_out)

        # 1. Dead end: no outgoing edges
        if total_out_count == 0:
            return CandidateGenerationResult(
                current_node=str(current_node),
                candidates=[],
                total_outgoing_count=0,
                eligible_count=0,
                is_dead_end=True,
                status_message=f"Dead end: node {current_node} has 0 outgoing edges."
            )

        # 2. Build CandidateEdge structures
        all_candidates: List[CandidateEdge] = []
        for v_raw, key in raw_out:
            v_str = str(v_raw)
            edge_tuple = (str(current_node), v_str, int(key))
            if edge_tuple in excluded:
                continue
            length_m = self.edge_lengths.get(edge_tuple, 25.0)
            cost_s = edge_weights.get(edge_tuple, 10.0)
            speed_kmh = (
                edge_speeds.get(edge_tuple, (length_m / cost_s * 3.6) if cost_s > 0 else 30.0)
                if edge_speeds
                else (length_m / cost_s * 3.6 if cost_s > 0 else 30.0)
            )
            h_s = self.estimate_remaining_time(v_str, str(destination))

            all_candidates.append(
                CandidateEdge(
                    u=str(current_node),
                    v=v_str,
                    key=int(key),
                    length_m=length_m,
                    speed_kmh=speed_kmh,
                    travel_time_s=cost_s,
                    heuristic_remaining_s=h_s,
                    total_estimated_s=cost_s + h_s
                )
            )

        if not all_candidates:
            return CandidateGenerationResult(
                current_node=str(current_node),
                candidates=[],
                total_outgoing_count=total_out_count,
                eligible_count=0,
                is_dead_end=True,
                status_message=f"Loop trap at {current_node}: no untried outgoing edge remains.",
            )

        # 3. Prefer non-reversal exits, while retaining lane-specific edge records.
        filtered_candidates = all_candidates
        if previous_node is not None and len(all_candidates) > 1:
            non_reversal = [c for c in all_candidates if c.v != str(previous_node)]
            if non_reversal:
                filtered_candidates = non_reversal

        # A fixed finite loop penalty can be smaller than destination/lookahead
        # score differences. In local-backtracking mode, never choose a successor
        # already on the active path when any unvisited successor is available.
        if avoid_visited_successors and visited:
            unvisited_candidates = [c for c in filtered_candidates if c.v not in visited]
            if unvisited_candidates:
                filtered_candidates = unvisited_candidates
            else:
                return CandidateGenerationResult(
                    current_node=str(current_node),
                    candidates=[],
                    total_outgoing_count=total_out_count,
                    eligible_count=0,
                    is_dead_end=True,
                    status_message=f"Loop trap at {current_node}: no untried eligible successor remains.",
                )

        if corridor_assessor is not None:
            for candidate in filtered_candidates:
                assessment = corridor_assessor(candidate.edge_tuple)
                candidate.attributes["forced_corridor"] = assessment
                details = assessment.to_dict() if hasattr(assessment, "to_dict") else dict(assessment)
                self.last_corridor_checks.append(details)

            if corridor_policy == "conservative_rejection":
                alternatives = [
                    candidate
                    for candidate in filtered_candidates
                    if not self._is_proven_corridor_trap(candidate)
                ]
                # Never discard every choice. An incomplete corridor is not a
                # proven trap and is therefore always retained here.
                if alternatives:
                    filtered_candidates = alternatives

        eligible_count = len(filtered_candidates)

        # 4. Out-degree == 1: Forced continuation
        if eligible_count == 1:
            forced_candidate = filtered_candidates[0]
            forced_candidate.is_forced = True
            return CandidateGenerationResult(
                current_node=str(current_node),
                candidates=[forced_candidate],
                total_outgoing_count=total_out_count,
                eligible_count=1,
                is_forced=True,
                status_message=f"Forced continuation: exactly 1 eligible outgoing edge from {current_node}."
            )

        # 5. Out-degree == 2: Natural pair
        if eligible_count == 2:
            return CandidateGenerationResult(
                current_node=str(current_node),
                candidates=filtered_candidates,
                total_outgoing_count=total_out_count,
                eligible_count=2,
                status_message=f"Natural pair: exactly 2 eligible outgoing edges from {current_node}."
            )

        # 6. Out-degree > 2: Apply selection strategy to select exactly 2 candidates
        selected_pair = self._select_two(
            filtered_candidates,
            strategy,
            visited,
            lookahead_evaluator,
            corridor_policy,
        )

        return CandidateGenerationResult(
            current_node=str(current_node),
            candidates=selected_pair,
            total_outgoing_count=total_out_count,
            eligible_count=eligible_count,
            status_message=f"Selected 2 candidates from {eligible_count} eligible edges using strategy {strategy.value}."
        )

    def _select_two(
        self,
        candidates: List[CandidateEdge],
        strategy: CandidateGenerationStrategy,
        visited: Set[str],
        lookahead_evaluator: Optional[Callable[[Tuple[str, str, int]], float]],
        corridor_policy: Optional[str] = None,
    ) -> List[CandidateEdge]:
        """Reduces >2 candidates down to exactly 2 candidates according to strategy."""
        # Loop avoidance ranking penalty: unvisited nodes preferred
        def loop_penalty(c: CandidateEdge) -> float:
            return 1000.0 if c.v in visited else 0.0

        def corridor_rank(c: CandidateEdge) -> int:
            if corridor_policy != "ranking":
                return 0
            assessment = c.attributes.get("forced_corridor")
            if assessment is None:
                return 1
            status = assessment.status if hasattr(assessment, "status") else assessment.get("status")
            return {
                "destination": 0,
                "junction": 0,
                "edge_cap": 1,
                "dead_end": 2,
                "active_path_return": 2,
            }.get(status, 1)

        if strategy == CandidateGenerationStrategy.RANDOM:
            # Deterministic pseudo-random selection
            sampled = self.rng.sample(candidates, 2)
            return sampled

        elif strategy == CandidateGenerationStrategy.LOWEST_IMMEDIATE_COST:
            sorted_candidates = sorted(
                candidates,
                key=lambda c: (loop_penalty(c), corridor_rank(c), c.travel_time_s)
            )
            return sorted_candidates[:2]

        elif strategy == CandidateGenerationStrategy.DESTINATION_AWARE:
            sorted_candidates = sorted(
                candidates,
                key=lambda c: (loop_penalty(c), corridor_rank(c), c.total_estimated_s)
            )
            return sorted_candidates[:2]

        elif strategy == CandidateGenerationStrategy.LOOKAHEAD:
            if lookahead_evaluator is not None:
                sorted_candidates = sorted(
                    candidates,
                    key=lambda c: (loop_penalty(c), corridor_rank(c), lookahead_evaluator(c.edge_tuple))
                )
                return sorted_candidates[:2]
            # Fallback to destination-aware when no bounded evaluator exists.
            sorted_candidates = sorted(
                candidates,
                key=lambda c: (loop_penalty(c), c.total_estimated_s)
            )
            return sorted_candidates[:2]

        elif strategy == CandidateGenerationStrategy.FASTEST_PLUS_PROGRESS:
            # Preserve two-edge comparison while ensuring the pair contains a
            # locally cheap option and the successor closest to the destination.
            fastest = min(
                candidates,
                key=lambda c: (loop_penalty(c), c.travel_time_s, c.total_estimated_s),
            )
            progress = min(
                (c for c in candidates if c.edge_tuple != fastest.edge_tuple),
                key=lambda c: (loop_penalty(c), c.heuristic_remaining_s, c.travel_time_s),
                default=None,
            )
            return [fastest, progress] if progress is not None else [fastest]

        elif strategy in (
            CandidateGenerationStrategy.DESTINATION_PLUS_LOOKAHEAD,
            CandidateGenerationStrategy.ADAPTIVE_DIVERSE,
        ):
            # The old Adaptive selector inherited DESTINATION_AWARE candidate
            # ranking, so its Lookahead branch could never compare an omitted
            # lookahead-favored successor. Build a two-edge pair that includes
            # the best candidate under each signal, then let the decision
            # strategy compare only those two edges.
            by_destination = sorted(
                candidates,
                key=lambda c: (loop_penalty(c), c.total_estimated_s, c.travel_time_s),
            )
            first = by_destination[0]
            if lookahead_evaluator is None:
                return by_destination[:2]
            by_lookahead = sorted(
                candidates,
                key=lambda c: (
                    loop_penalty(c),
                    lookahead_evaluator(c.edge_tuple),
                    c.total_estimated_s,
                ),
            )
            second = next(
                (candidate for candidate in by_lookahead if candidate.edge_tuple != first.edge_tuple),
                None,
            )
            return [first, second] if second is not None else [first]

        # Default fallback
        return candidates[:2]

    @staticmethod
    def _is_proven_corridor_trap(candidate: CandidateEdge) -> bool:
        assessment = candidate.attributes.get("forced_corridor")
        if assessment is None:
            return False
        if hasattr(assessment, "is_proven_trap"):
            return bool(assessment.is_proven_trap)
        return bool(assessment.get("returns_to_active_path") or assessment.get("reaches_dead_end"))
