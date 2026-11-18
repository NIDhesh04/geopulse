"""
GeoPulse Simulation Controller Module

Manages simulation state, step pacing, two-edge intersection evaluation,
kinematic movement progression, dynamic traffic events, and user controls.
"""

from enum import Enum
from typing import Dict, List, Tuple, Set, Optional, Any
import time

from src.routing.candidate_generator import CandidateGenerator, CandidateGenerationStrategy
from src.routing.decision_strategies import (
    BaseDecisionStrategy,
    GreedyDecisionStrategy,
    DestinationAwareDecisionStrategy,
    LimitedLookaheadDecisionStrategy,
    AdaptiveDecisionStrategy
)
from src.routing.lookahead import LimitedLookaheadEvaluator
from src.routing.two_edge_selector import TwoEdgeSelector, TwoEdgeDecisionStep
from src.pygame_simulation.scenario_manager import SimulationScenario


class SimState(str, Enum):
    IDLE = "idle"
    DECISION_PAUSE = "decision_pause"
    MOVING = "moving"
    REROUTE_ALERT = "reroute_alert"
    ARRIVED = "arrived"


class SimulationController:
    """Coordinates the live algorithmic execution and visualization state."""

    def __init__(
        self,
        scenario: SimulationScenario,
        strategy_type: str = "destination_aware",
        decision_pause_seconds: float = 1.0,
        move_speed_multiplier: float = 1.0
    ):
        self.scenario = scenario
        self.decision_pause_duration = float(decision_pause_seconds)
        self.speed_multiplier = float(move_speed_multiplier)
        self.strategy_type = strategy_type

        # Initialize routing components
        self._init_routing_engine(strategy_type)

        # Simulation runtime state
        self.state = SimState.IDLE
        self.is_paused = False
        self.step_mode = False

        # Reset simulation state variables
        self.reset()

    def _init_routing_engine(self, strategy_type: str):
        """Builds CandidateGenerator, Strategies, and TwoEdgeSelector."""
        self.generator = CandidateGenerator(
            adjacency=self.scenario.adjacency,
            edge_lengths=self.scenario.edge_lengths,
            node_coords=self.scenario.node_coords
        )

        if strategy_type == "greedy":
            self.strategy = GreedyDecisionStrategy()
        elif strategy_type == "lookahead_2":
            evaluator = LimitedLookaheadEvaluator(
                self.scenario.adjacency,
                self.scenario.initial_weights,
                self.generator.estimate_remaining_time,
                depth=2
            )
            self.strategy = LimitedLookaheadDecisionStrategy(evaluator)
        elif strategy_type == "lookahead_3":
            evaluator = LimitedLookaheadEvaluator(
                self.scenario.adjacency,
                self.scenario.initial_weights,
                self.generator.estimate_remaining_time,
                depth=3
            )
            self.strategy = LimitedLookaheadDecisionStrategy(evaluator)
        elif strategy_type == "adaptive":
            dest_aware = DestinationAwareDecisionStrategy()
            evaluator = LimitedLookaheadEvaluator(
                self.scenario.adjacency,
                self.scenario.initial_weights,
                self.generator.estimate_remaining_time,
                depth=2
            )
            lookahead = LimitedLookaheadDecisionStrategy(evaluator)
            self.strategy = AdaptiveDecisionStrategy(dest_aware, lookahead)
        else:
            # Default: destination_aware
            self.strategy = DestinationAwareDecisionStrategy()

        self.selector = TwoEdgeSelector(
            candidate_generator=self.generator,
            decision_strategy=self.strategy
        )

    def reset(self):
        """Resets simulation back to origin."""
        self.current_node = self.scenario.source_node
        self.previous_node: Optional[str] = None
        self.destination_node = self.scenario.destination_node

        self.active_weights = dict(self.scenario.initial_weights)
        self.active_speeds = dict(self.scenario.initial_speeds)

        self.visited_nodes: Set[str] = {self.current_node}
        self.traversed_edges: List[Tuple[str, str, int]] = []
        self.history_nodes: List[str] = [self.current_node]

        self.elapsed_travel_time_s = 0.0
        self.accumulated_distance_m = 0.0
        self.decisions_count = 0
        self.reroutes_count = 0
        self.step_index = 0

        # Current decision data
        self.current_decision: Optional[TwoEdgeDecisionStep] = None
        self.active_edge: Optional[Tuple[str, str, int]] = None
        self.active_edge_progress: float = 0.0
        self.state_timer: float = 0.0

        self.state = SimState.DECISION_PAUSE
        self._evaluate_current_intersection()

    def set_strategy(self, strategy_type: str):
        """Switches decision strategy on the fly."""
        self.strategy_type = strategy_type
        self._init_routing_engine(strategy_type)
        if self.state == SimState.DECISION_PAUSE:
            self._evaluate_current_intersection()

    def _evaluate_current_intersection(self):
        """Executes two-edge candidate selection at current_node."""
        if self.current_node == self.destination_node:
            self.state = SimState.ARRIVED
            return

        # Check dynamic traffic injection
        if (
            self.scenario.traffic_update_step is not None
            and self.decisions_count == self.scenario.traffic_update_step
            and self.scenario.updated_weights
        ):
            self.active_weights = dict(self.scenario.updated_weights)
            if self.scenario.updated_speeds:
                self.active_speeds = dict(self.scenario.updated_speeds)
            self.reroutes_count += 1
            self.state = SimState.REROUTE_ALERT

        decision = self.selector.decide_next_edge(
            step_index=self.step_index,
            current_node=self.current_node,
            destination=self.destination_node,
            edge_weights=self.active_weights,
            edge_speeds=self.active_speeds,
            previous_node=self.previous_node,
            visited_nodes=self.visited_nodes
        )

        self.current_decision = decision
        self.active_edge = decision.selected_edge
        self.active_edge_progress = 0.0
        self.state_timer = 0.0

    def update(self, dt: float):
        """
        Main simulation tick update.

        Parameters
        ----------
        dt : float
            Elapsed real wall-clock time in seconds since last frame.
        """
        if self.is_paused or self.state == SimState.ARRIVED:
            return

        scaled_dt = dt * self.speed_multiplier

        if self.state in (SimState.DECISION_PAUSE, SimState.REROUTE_ALERT):
            self.state_timer += scaled_dt
            if self.state_timer >= self.decision_pause_duration and not self.step_mode:
                if self.active_edge is not None:
                    self.state = SimState.MOVING
                    self.state_timer = 0.0
                else:
                    self.state = SimState.ARRIVED

        elif self.state == SimState.MOVING:
            if not self.active_edge or not self.current_decision:
                self.state = SimState.DECISION_PAUSE
                return

            edge_cost = self.current_decision.travel_time_s
            edge_dist = self.current_decision.length_m

            # Pacing: progress advances relative to simulated travel time
            # Visual speed: travel edge in approximately 1.5 seconds normalized
            norm_duration = max(0.8, min(edge_cost * 0.15, 2.5))
            self.active_edge_progress += scaled_dt / norm_duration

            if self.active_edge_progress >= 1.0:
                # Edge completed!
                self.active_edge_progress = 1.0
                self.elapsed_travel_time_s += edge_cost
                self.accumulated_distance_m += edge_dist
                self.traversed_edges.append(self.active_edge)

                self.previous_node = self.current_node
                self.current_node = self.current_decision.next_node or self.active_edge[1]
                self.history_nodes.append(self.current_node)
                self.visited_nodes.add(self.current_node)

                self.decisions_count += 1
                self.step_index += 1

                if self.current_node == self.destination_node:
                    self.state = SimState.ARRIVED
                else:
                    self.state = SimState.DECISION_PAUSE
                    self._evaluate_current_intersection()

                if self.step_mode:
                    self.is_paused = True
                    self.step_mode = False

    def trigger_step(self):
        """Manually advances 1 step when in paused mode."""
        if self.state == SimState.DECISION_PAUSE and self.active_edge:
            self.state = SimState.MOVING
            self.is_paused = False
            self.step_mode = True
        elif self.state == SimState.MOVING:
            self.active_edge_progress = 1.0

    def get_hud_state_dict(self) -> Dict[str, Any]:
        """Packages current state for UI rendering."""
        cand_a_dict = None
        cand_b_dict = None
        chosen = 'A'

        if self.current_decision:
            ca = self.current_decision.candidate_a
            cb = self.current_decision.candidate_b

            if ca:
                cand_a_dict = {
                    'edge': f"{ca.u}->{ca.v}",
                    'speed': ca.speed_kmh,
                    'cost': ca.travel_time_s,
                    'score': self.current_decision.score_a or ca.travel_time_s
                }
            if cb:
                cand_b_dict = {
                    'edge': f"{cb.u}->{cb.v}",
                    'speed': cb.speed_kmh,
                    'cost': cb.travel_time_s,
                    'score': self.current_decision.score_b or cb.travel_time_s
                }

            if self.current_decision.selected_edge and ca:
                if self.current_decision.selected_edge == ca.edge_tuple:
                    chosen = 'A'
                else:
                    chosen = 'B'

        return {
            'strategy_name': self.strategy.name,
            'network_type': self.scenario.network_type,
            'origin': self.scenario.source_node,
            'destination': self.scenario.destination_node,
            'current_node': self.current_node,
            'elapsed_time_s': self.elapsed_travel_time_s,
            'distance_m': self.accumulated_distance_m,
            'decisions_count': self.decisions_count,
            'reroutes_count': self.reroutes_count,
            'candidate_a': cand_a_dict,
            'candidate_b': cand_b_dict,
            'chosen_candidate': chosen,
            'decision_reason': self.current_decision.decision_reason if self.current_decision else "Initializing...",
            'is_paused': self.is_paused,
            'speed_multiplier': int(self.speed_multiplier)
        }
