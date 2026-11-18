"""
GeoPulse Two-Edge Selector Engine

At any intersection, coordinates candidate generation, comparative evaluation,
and winner selection between Candidate A and Candidate B.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple, Set, Optional, Any

from src.routing.candidate_generator import (
    CandidateGenerator,
    CandidateEdge,
    CandidateGenerationResult,
    CandidateGenerationStrategy
)
from src.routing.decision_strategies import (
    BaseDecisionStrategy,
    DecisionEvaluationResult,
    LimitedLookaheadDecisionStrategy
)



@dataclass
class TwoEdgeDecisionStep:
    """Encapsulates the complete decision event at an intersection."""
    step_index: int
    current_node: str
    next_node: Optional[str]
    selected_edge: Optional[Tuple[str, str, int]]
    candidate_a: Optional[CandidateEdge]
    candidate_b: Optional[CandidateEdge]
    score_a: Optional[float]
    score_b: Optional[float]
    travel_time_s: float
    length_m: float
    speed_kmh: float
    strategy_name: str
    decision_reason: str
    is_forced: bool = False
    is_dead_end: bool = False
    evaluation_time_ms: float = 0.0


class TwoEdgeSelector:
    """
    Coordinates candidate generation and decision strategy execution at intersections.
    """

    def __init__(
        self,
        candidate_generator: CandidateGenerator,
        decision_strategy: BaseDecisionStrategy,
        candidate_strategy: Optional[CandidateGenerationStrategy] = None
    ):
        self.candidate_generator = candidate_generator
        self.decision_strategy = decision_strategy
        if candidate_strategy is not None:
            self.candidate_strategy = candidate_strategy
        else:
            # Align candidate generation with decision strategy
            strat_name = getattr(decision_strategy, 'name', '').lower()
            if 'greedy' in strat_name:
                self.candidate_strategy = CandidateGenerationStrategy.LOWEST_IMMEDIATE_COST
            elif 'lookahead' in strat_name:
                self.candidate_strategy = CandidateGenerationStrategy.LOOKAHEAD
            else:
                self.candidate_strategy = CandidateGenerationStrategy.DESTINATION_AWARE

    def decide_next_edge(
        self,
        step_index: int,
        current_node: str,
        destination: str,
        edge_weights: Dict[Tuple[str, str, int], float],
        edge_speeds: Optional[Dict[Tuple[str, str, int], float]] = None,
        previous_node: Optional[str] = None,
        visited_nodes: Optional[Set[str]] = None
    ) -> TwoEdgeDecisionStep:
        """
        Executes a single two-edge decision step at current_node.
        """
        # 1. Generate candidates
        # Determine if a lookahead evaluator should be supplied (for LOOKAHEAD strategy)
        lookahead_evaluator = None
        if isinstance(self.decision_strategy, LimitedLookaheadDecisionStrategy):
            # Create a fresh LimitedLookaheadEvaluator using the current edge_weights to avoid stale data
            eval_instance = LimitedLookaheadEvaluator(
                self.candidate_generator.adjacency,
                edge_weights,
                self.candidate_generator.estimate_remaining_time,
                depth=self.decision_strategy.evaluator.depth,
                max_expansions_per_node=self.decision_strategy.evaluator.max_expansions
            )
            lookahead_evaluator = eval_instance.evaluate_edge

        gen_result: CandidateGenerationResult = self.candidate_generator.generate_candidates(
            current_node=current_node,
            destination=destination,
            edge_weights=edge_weights,
            edge_speeds=edge_speeds,
            previous_node=previous_node,
            visited_nodes=visited_nodes,
            strategy=self.candidate_strategy,
            lookahead_evaluator=lookahead_evaluator
        )

        # 2. Dead-end check
        if gen_result.is_dead_end or not gen_result.candidates:
            return TwoEdgeDecisionStep(
                step_index=step_index,
                current_node=str(current_node),
                next_node=None,
                selected_edge=None,
                candidate_a=None,
                candidate_b=None,
                score_a=None,
                score_b=None,
                travel_time_s=0.0,
                length_m=0.0,
                speed_kmh=0.0,
                strategy_name=self.decision_strategy.name,
                decision_reason=f"Dead end: No outgoing eligible edges from node {current_node}.",
                is_forced=False,
                is_dead_end=True,
                evaluation_time_ms=0.0
            )

        # 3. Forced continuation (1 candidate)
        if len(gen_result.candidates) == 1:
            cand_a = gen_result.candidates[0]
            eval_res: DecisionEvaluationResult = self.decision_strategy.evaluate_candidates(
                candidate_a=cand_a,
                candidate_b=None,
                current_node=current_node,
                destination=destination,
                visited_nodes=visited_nodes
            )
            return TwoEdgeDecisionStep(
                step_index=step_index,
                current_node=str(current_node),
                next_node=cand_a.v,
                selected_edge=cand_a.edge_tuple,
                candidate_a=cand_a,
                candidate_b=None,
                score_a=eval_res.score_a,
                score_b=None,
                travel_time_s=cand_a.travel_time_s,
                length_m=cand_a.length_m,
                speed_kmh=cand_a.speed_kmh,
                strategy_name=eval_res.strategy_used,
                decision_reason=eval_res.decision_reason,
                is_forced=True,
                is_dead_end=False,
                evaluation_time_ms=eval_res.evaluation_time_ms
            )

        # 4. Natural or selected pair (2 candidates: A vs B)
        cand_a = gen_result.candidates[0]
        cand_b = gen_result.candidates[1]

        eval_res = self.decision_strategy.evaluate_candidates(
            candidate_a=cand_a,
            candidate_b=cand_b,
            current_node=current_node,
            destination=destination,
            visited_nodes=visited_nodes
        )

        chosen = eval_res.selected_candidate

        return TwoEdgeDecisionStep(
            step_index=step_index,
            current_node=str(current_node),
            next_node=chosen.v,
            selected_edge=chosen.edge_tuple,
            candidate_a=cand_a,
            candidate_b=cand_b,
            score_a=eval_res.score_a,
            score_b=eval_res.score_b,
            travel_time_s=chosen.travel_time_s,
            length_m=chosen.length_m,
            speed_kmh=chosen.speed_kmh,
            strategy_name=eval_res.strategy_used,
            decision_reason=eval_res.decision_reason,
            is_forced=False,
            is_dead_end=False,
            evaluation_time_ms=eval_res.evaluation_time_ms
        )
