"""
GeoPulse Routing Engine Package

Includes:
- Pure Python custom Dijkstra solver
- Dynamic traffic weights & graph management
- Candidate edge generation
- Two-edge selection & decision strategies
- Limited lookahead evaluation
- Sequential route controller
- Dynamic rerouting engine
"""

from src.routing.dijkstra import custom_dijkstra, DijkstraResult
from src.routing.astar import custom_astar, AStarResult
from src.routing.traffic_weights import (
    GraphWeightManager,
    TrafficCoverageDiagnostics,
    TrafficEdgeCostUpdate,
    TrafficEdgeCostUpdater,
    calculate_travel_time_seconds,
    get_static_speed_kmh
)
from src.routing.candidate_generator import (
    CandidateGenerator,
    CandidateEdge,
    CandidateGenerationResult,
    CandidateGenerationStrategy
)
from src.routing.lookahead import LimitedLookaheadEvaluator
from src.routing.decision_strategies import (
    BaseDecisionStrategy,
    GreedyDecisionStrategy,
    DestinationAwareDecisionStrategy,
    LimitedLookaheadDecisionStrategy,
    AdaptiveDecisionStrategy,
    DecisionEvaluationResult,
    StrategyType
)
from src.routing.two_edge_selector import (
    TwoEdgeSelector,
    TwoEdgeDecisionStep
)
from src.routing.route_controller import (
    RouteController,
    SequentialJourneyResult
)
from src.routing.dynamic_rerouter import DynamicRerouter
from src.routing.route_evaluator import compute_edge_jaccard_overlap

__all__ = [
    "custom_dijkstra",
    "DijkstraResult",
    "GraphWeightManager",
    "TrafficCoverageDiagnostics",
    "TrafficEdgeCostUpdate",
    "TrafficEdgeCostUpdater",
    "calculate_travel_time_seconds",
    "get_static_speed_kmh",
    "CandidateGenerator",
    "CandidateEdge",
    "CandidateGenerationResult",
    "CandidateGenerationStrategy",
    "LimitedLookaheadEvaluator",
    "BaseDecisionStrategy",
    "GreedyDecisionStrategy",
    "DestinationAwareDecisionStrategy",
    "LimitedLookaheadDecisionStrategy",
    "AdaptiveDecisionStrategy",
    "DecisionEvaluationResult",
    "StrategyType",
    "TwoEdgeSelector",
    "TwoEdgeDecisionStep",
    "RouteController",
    "SequentialJourneyResult",
    "DynamicRerouter",
    "compute_edge_jaccard_overlap"
]
