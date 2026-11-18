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
from src.routing.lookahead import LimitedLookaheadEvaluator


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
    Destination-aware decision strategy: evaluates immediate travel time + admissible heuristic distance to destination.
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
