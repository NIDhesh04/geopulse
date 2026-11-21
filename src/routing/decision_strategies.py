"""
GeoPulse Sequential Decision Strategies Module

Defines decision strategies for evaluating two candidate outgoing edges at an intersection:
1. GREEDY: Selects the candidate with the lowest immediate edge traversal cost.
2. DESTINATION_AWARE: Balances immediate edge traversal cost with remaining heuristic distance to target.
3. LIMITED_LOOKAHEAD: Evaluates forward consequences up to depth k (k in {1, 2, 3, 5}).
4. ADAPTIVE: Dynamically switches strategies based on traffic conditions and proximity to destination.

All strategies inherit from BaseDecisionStrategy to ensure interchangeable evaluation.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Tuple, Set, Optional, Any
import time

from src.routing.candidate_generator import CandidateEdge
from src.routing.lookahead import BoundedReachabilityEvaluator, LimitedLookaheadEvaluator


class StrategyType(str, Enum):
    GREEDY = "greedy"
    DESTINATION_AWARE = "destination_aware"
    LOOKAHEAD = "lookahead"
    ADAPTIVE = "adaptive"


@dataclass
class DecisionEvaluationResult:
    """Encapsulates the comparative evaluation of two candidate edges."""
    candidate_a: CandidateEdge
    candidate_b: Optional[CandidateEdge]
    selected_candidate: CandidateEdge
    score_a: float
    score_b: Optional[float]
    strategy_used: str
    decision_reason: str
    is_forced: bool = False
    evaluation_time_ms: float = 0.0


class BaseDecisionStrategy(ABC):
    """Abstract base class for two-edge decision strategies."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def evaluate_candidates(
        self,
        candidate_a: CandidateEdge,
        candidate_b: Optional[CandidateEdge],
        current_node: str,
        destination: str,
        visited_nodes: Optional[Set[str]] = None
    ) -> DecisionEvaluationResult:
        """
        Evaluates Candidates A and B, returning the selection decision.
        If Candidate B is None (e.g. forced continuation), Candidate A is chosen.
        """
        pass


class CorridorRankingDecisionStrategy(BaseDecisionStrategy):
    """Add bounded-corridor evidence as the primary pair-ranking signal."""

    def __init__(self, delegate: BaseDecisionStrategy):
        super().__init__(name=f"Corridor Ranking ({delegate.name})")
        self.delegate = delegate

    @staticmethod
    def _rank(candidate: CandidateEdge) -> int:
        assessment = candidate.attributes.get("forced_corridor")
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

    def evaluate_candidates(
        self,
        candidate_a: CandidateEdge,
        candidate_b: Optional[CandidateEdge],
        current_node: str,
        destination: str,
        visited_nodes: Optional[Set[str]] = None,
    ) -> DecisionEvaluationResult:
        result = self.delegate.evaluate_candidates(
            candidate_a,
            candidate_b,
            current_node,
            destination,
            visited_nodes,
        )
        if candidate_b is not None:
            rank_a, rank_b = self._rank(candidate_a), self._rank(candidate_b)
            if rank_a != rank_b:
                result.selected_candidate = candidate_a if rank_a < rank_b else candidate_b
                result.decision_reason = (
                    f"Corridor evidence ranked {result.selected_candidate.v} ahead "
                    f"(status rank {min(rank_a, rank_b)} vs {max(rank_a, rank_b)}); "
                    f"delegate: {result.decision_reason}"
                )
            else:
                result.decision_reason = f"Corridor evidence tied; delegate: {result.decision_reason}"
        result.strategy_used = f"Corridor Ranking -> {result.strategy_used}"
        return result


class GreedyDecisionStrategy(BaseDecisionStrategy):
    """
    Greedy decision strategy: selects candidate edge with lowest immediate travel time.
    """

    def __init__(self):
        super().__init__(name="Greedy (Immediate Cost)")

    def evaluate_candidates(
        self,
        candidate_a: CandidateEdge,
        candidate_b: Optional[CandidateEdge],
        current_node: str,
        destination: str,
        visited_nodes: Optional[Set[str]] = None
    ) -> DecisionEvaluationResult:
        t0 = time.perf_counter()

        # Forced continuation when only 1 candidate exists
        if candidate_b is None:
            exec_ms = (time.perf_counter() - t0) * 1000.0
            return DecisionEvaluationResult(
                candidate_a=candidate_a,
                candidate_b=None,
                selected_candidate=candidate_a,
                score_a=candidate_a.travel_time_s,
                score_b=None,
                strategy_used=self.name,
                decision_reason=f"Forced continuation on edge {candidate_a.u}->{candidate_a.v}.",
                is_forced=True,
                evaluation_time_ms=exec_ms
            )

        # Loop penalty
        visited = visited_nodes or set()
        penalty_a = 1000.0 if candidate_a.v in visited else 0.0
        penalty_b = 1000.0 if candidate_b.v in visited else 0.0

        score_a = candidate_a.travel_time_s + penalty_a
        score_b = candidate_b.travel_time_s + penalty_b

        if score_a <= score_b:
            selected = candidate_a
            reason = f"Candidate A ({candidate_a.u}->{candidate_a.v}) has lower immediate travel time ({candidate_a.travel_time_s:.1f}s vs {candidate_b.travel_time_s:.1f}s)."
        else:
            selected = candidate_b
            reason = f"Candidate B ({candidate_b.u}->{candidate_b.v}) has lower immediate travel time ({candidate_b.travel_time_s:.1f}s vs {candidate_a.travel_time_s:.1f}s)."

        exec_ms = (time.perf_counter() - t0) * 1000.0
        return DecisionEvaluationResult(
            candidate_a=candidate_a,
            candidate_b=candidate_b,
            selected_candidate=selected,
            score_a=score_a,
            score_b=score_b,
            strategy_used=self.name,
            decision_reason=reason,
            is_forced=False,
            evaluation_time_ms=exec_ms
        )


class DestinationAwareDecisionStrategy(BaseDecisionStrategy):
    """
    Destination-aware strategy: immediate travel time plus the configured
    straight-line remaining-time estimate. That estimate is admissible only
    when its speed bound is at least the maximum speed allowed on graph edges.
    """

    def __init__(self, heuristic_weight: float = 1.0):
        super().__init__(name="Destination-Aware")
        self.alpha = float(heuristic_weight)

    def evaluate_candidates(
        self,
        candidate_a: CandidateEdge,
        candidate_b: Optional[CandidateEdge],
        current_node: str,
        destination: str,
        visited_nodes: Optional[Set[str]] = None
    ) -> DecisionEvaluationResult:
        t0 = time.perf_counter()

        if candidate_b is None:
            exec_ms = (time.perf_counter() - t0) * 1000.0
            return DecisionEvaluationResult(
                candidate_a=candidate_a,
                candidate_b=None,
                selected_candidate=candidate_a,
                score_a=candidate_a.total_estimated_s,
                score_b=None,
                strategy_used=self.name,
                decision_reason=f"Forced continuation on edge {candidate_a.u}->{candidate_a.v}.",
                is_forced=True,
                evaluation_time_ms=exec_ms
            )

        visited = visited_nodes or set()
        penalty_a = 1000.0 if candidate_a.v in visited else 0.0
        penalty_b = 1000.0 if candidate_b.v in visited else 0.0

        score_a = candidate_a.travel_time_s + self.alpha * candidate_a.heuristic_remaining_s + penalty_a
        score_b = candidate_b.travel_time_s + self.alpha * candidate_b.heuristic_remaining_s + penalty_b

        if score_a <= score_b:
            selected = candidate_a
            reason = (
                f"Candidate A ({candidate_a.u}->{candidate_a.v}) preferred: estimated total "
                f"{score_a:.1f}s (edge {candidate_a.travel_time_s:.1f}s + rem {candidate_a.heuristic_remaining_s:.1f}s) "
                f"vs Candidate B {score_b:.1f}s."
            )
        else:
            selected = candidate_b
            reason = (
                f"Candidate B ({candidate_b.u}->{candidate_b.v}) preferred: estimated total "
                f"{score_b:.1f}s (edge {candidate_b.travel_time_s:.1f}s + rem {candidate_b.heuristic_remaining_s:.1f}s) "
                f"vs Candidate A {score_a:.1f}s."
            )

        exec_ms = (time.perf_counter() - t0) * 1000.0
        return DecisionEvaluationResult(
            candidate_a=candidate_a,
            candidate_b=candidate_b,
            selected_candidate=selected,
            score_a=score_a,
            score_b=score_b,
            strategy_used=self.name,
            decision_reason=reason,
            is_forced=False,
            evaluation_time_ms=exec_ms
        )


class LimitedLookaheadDecisionStrategy(BaseDecisionStrategy):
    """
    Limited-lookahead decision strategy: evaluates consequences to depth k in {1, 2, 3, 5}.
    """

    def __init__(self, lookahead_evaluator: LimitedLookaheadEvaluator):
        depth = lookahead_evaluator.depth
        super().__init__(name=f"Limited Lookahead (Depth {depth})")
        self.evaluator = lookahead_evaluator

    def evaluate_candidates(
        self,
        candidate_a: CandidateEdge,
        candidate_b: Optional[CandidateEdge],
        current_node: str,
        destination: str,
        visited_nodes: Optional[Set[str]] = None
    ) -> DecisionEvaluationResult:
        t0 = time.perf_counter()

        if candidate_b is None:
            exec_ms = (time.perf_counter() - t0) * 1000.0
            return DecisionEvaluationResult(
                candidate_a=candidate_a,
                candidate_b=None,
                selected_candidate=candidate_a,
                score_a=candidate_a.total_estimated_s,
                score_b=None,
                strategy_used=self.name,
                decision_reason=f"Forced continuation on edge {candidate_a.u}->{candidate_a.v}.",
                is_forced=True,
                evaluation_time_ms=exec_ms
            )

        visited = visited_nodes or set()
        penalty_a = 1000.0 if candidate_a.v in visited else 0.0
        penalty_b = 1000.0 if candidate_b.v in visited else 0.0

        lookahead_a = self.evaluator.evaluate_edge(candidate_a.edge_tuple, destination, visited)
        lookahead_b = self.evaluator.evaluate_edge(candidate_b.edge_tuple, destination, visited)

        score_a = lookahead_a + penalty_a
        score_b = lookahead_b + penalty_b

        if score_a <= score_b:
            selected = candidate_a
            reason = (
                f"Candidate A ({candidate_a.u}->{candidate_a.v}) has lower lookahead cost "
                f"({score_a:.1f}s vs {score_b:.1f}s at depth {self.evaluator.depth})."
            )
        else:
            selected = candidate_b
            reason = (
                f"Candidate B ({candidate_b.u}->{candidate_b.v}) has lower lookahead cost "
                f"({score_b:.1f}s vs {score_a:.1f}s at depth {self.evaluator.depth})."
            )

        exec_ms = (time.perf_counter() - t0) * 1000.0
        return DecisionEvaluationResult(
            candidate_a=candidate_a,
            candidate_b=candidate_b,
            selected_candidate=selected,
            score_a=score_a,
            score_b=score_b,
            strategy_used=self.name,
            decision_reason=reason,
            is_forced=False,
            evaluation_time_ms=exec_ms
        )


class BoundedReachabilityDecisionStrategy(BaseDecisionStrategy):
    """Compare two edges using bounded onward viability before travel time."""

    def __init__(self, evaluator: BoundedReachabilityEvaluator):
        super().__init__(name=f"Bounded Reachability (Depth {evaluator.depth})")
        self.evaluator = evaluator

    def evaluate_candidates(
        self,
        candidate_a: CandidateEdge,
        candidate_b: Optional[CandidateEdge],
        current_node: str,
        destination: str,
        visited_nodes: Optional[Set[str]] = None,
    ) -> DecisionEvaluationResult:
        t0 = time.perf_counter()
        visited = visited_nodes or set()

        def estimate(candidate: CandidateEdge):
            detail = self.evaluator.evaluate_edge_details(
                candidate.edge_tuple, destination, visited
            )
            # When a forced edge has no bounded viable continuation, or both
            # pair members are locally trapped, retain a finite fallback score
            # so sequential movement can continue and the controller can report
            # the later loop trap through its normal safety path.
            fallback = candidate.travel_time_s + candidate.heuristic_remaining_s
            if candidate.v in visited:
                fallback += 1000.0
            return detail, detail.estimated_cost_s if detail.viable else fallback

        detail_a, score_a = estimate(candidate_a)
        if candidate_b is None:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return DecisionEvaluationResult(
                candidate_a=candidate_a,
                candidate_b=None,
                selected_candidate=candidate_a,
                score_a=score_a,
                score_b=None,
                strategy_used=self.name,
                decision_reason=(
                    "Forced continuation; bounded continuation is "
                    f"{'viable' if detail_a.viable else 'unresolved/trapped'} "
                    f"after {detail_a.expanded_edges} local edge expansions."
                ),
                is_forced=True,
                evaluation_time_ms=elapsed_ms,
            )

        detail_b, score_b = estimate(candidate_b)
        if detail_a.viable != detail_b.viable:
            selected = candidate_a if detail_a.viable else candidate_b
        elif detail_a.viable:
            key_a = (score_a, -detail_a.viable_frontiers, candidate_a.travel_time_s)
            key_b = (score_b, -detail_b.viable_frontiers, candidate_b.travel_time_s)
            selected = candidate_a if key_a <= key_b else candidate_b
        else:
            selected = candidate_a if score_a <= score_b else candidate_b

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        selected_detail = detail_a if selected is candidate_a else detail_b
        decision_reason = (
            f"Selected {selected.u}->{selected.v}; bounded viability="
            f"{selected_detail.viable}, estimated continuation="
            f"{selected_detail.estimated_cost_s:.1f}s, "
            f"expanded={selected_detail.expanded_edges}."
        )
        return DecisionEvaluationResult(
            candidate_a=candidate_a,
            candidate_b=candidate_b,
            selected_candidate=selected,
            score_a=score_a,
            score_b=score_b,
            strategy_used=self.name,
            decision_reason=decision_reason,
            is_forced=False,
            evaluation_time_ms=elapsed_ms,
        )


class AdaptiveDecisionStrategy(BaseDecisionStrategy):
    """
    Adaptive decision strategy: selects between Destination-Aware and Lookahead
    based on local congestion level and remaining distance.
    """

    def __init__(
        self,
        dest_aware_strategy: DestinationAwareDecisionStrategy,
        lookahead_strategy: LimitedLookaheadDecisionStrategy,
        congestion_speed_threshold_kmh: float = 25.0
    ):
        super().__init__(name="Adaptive (Congestion-Responsive)")
        self.dest_aware = dest_aware_strategy
        self.lookahead = lookahead_strategy
        self.congestion_threshold = congestion_speed_threshold_kmh

    def evaluate_candidates(
        self,
        candidate_a: CandidateEdge,
        candidate_b: Optional[CandidateEdge],
        current_node: str,
        destination: str,
        visited_nodes: Optional[Set[str]] = None
    ) -> DecisionEvaluationResult:
        if candidate_b is None:
            return self.dest_aware.evaluate_candidates(
                candidate_a, None, current_node, destination, visited_nodes
            )

        # Detect if candidate corridor is congested
        min_speed = min(candidate_a.speed_kmh, candidate_b.speed_kmh)
        is_congested = min_speed < self.congestion_threshold

        if is_congested:
            res = self.lookahead.evaluate_candidates(
                candidate_a, candidate_b, current_node, destination, visited_nodes
            )
            res.strategy_used = f"{self.name} -> Lookahead (Congestion {min_speed:.1f} km/h)"
            return res
        else:
            res = self.dest_aware.evaluate_candidates(
                candidate_a, candidate_b, current_node, destination, visited_nodes
            )
            res.strategy_used = f"{self.name} -> Destination-Aware (Free-Flow {min_speed:.1f} km/h)"
            return res
