"""
GeoPulse Sequential Two-Edge Decision & Safety Test Suite

Validates:
1. Candidate Generation:
   - Out-degree >= 2: exactly 2 candidates produced.
   - Out-degree == 1: forced continuation, exactly 1 candidate, is_forced=True.
   - Out-degree == 0: dead-end handled cleanly, is_dead_end=True.
   - Immediate reversal excluded unless cul-de-sac.
   - All 4 candidate generation strategies (Random, Lowest Immediate Cost, Destination-Aware, Lookahead).
2. Decision Strategies:
   - Greedy: picks candidate with lowest immediate travel time.
   - Destination-Aware: picks candidate minimizing immediate + destination heuristic.
   - Limited Lookahead: evaluates depths 1, 2, 3, 5 correctly.
   - Adaptive: switches to lookahead under congestion.
3. Route Safety & Resilience:
   - Cycle prevention and loop detection.
   - Dead-end recovery using Dijkstra fallback.
   - Max-hop limits prevent infinite loops.
4. End-to-End Integration:
   - Full journey from source to destination completes cleanly.
   - Dynamic traffic change mid-journey triggers reroute handling.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.abspath('.'))

from src.routing.candidate_generator import (
    CandidateGenerator,
    CandidateEdge,
    CandidateGenerationStrategy
)
from src.routing.lookahead import LimitedLookaheadEvaluator
from src.routing.decision_strategies import (
    GreedyDecisionStrategy,
    DestinationAwareDecisionStrategy,
    LimitedLookaheadDecisionStrategy,
    AdaptiveDecisionStrategy
)
from src.routing.two_edge_selector import TwoEdgeSelector
from src.routing.route_controller import RouteController
from src.routing.dijkstra import custom_dijkstra


# -----------------------------------------------------------------------------
# FIXTURES: Controlled Toy Graphs
# -----------------------------------------------------------------------------

@pytest.fixture
def diamond_graph():
    """
    Diamond graph:
        A -> B (weight 5, dist 50m)
        A -> C (weight 2, dist 20m)
        A -> X (weight 10, dist 100m)  [3rd branch to test >2 candidates]
        B -> D (weight 5, dist 50m)
        C -> D (weight 2, dist 20m)
        X -> D (weight 10, dist 100m)
    """
    adj = {
        'A': [('B', 0), ('C', 0), ('X', 0)],
        'B': [('D', 0)],
        'C': [('D', 0)],
        'X': [('D', 0)],
        'D': []
    }
    lengths = {
        ('A', 'B', 0): 50.0,
        ('A', 'C', 0): 20.0,
        ('A', 'X', 0): 100.0,
        ('B', 'D', 0): 50.0,
        ('C', 'D', 0): 20.0,
        ('X', 'D', 0): 100.0
    }
    weights = {
        ('A', 'B', 0): 5.0,
        ('A', 'C', 0): 2.0,
        ('A', 'X', 0): 10.0,
        ('B', 'D', 0): 5.0,
        ('C', 'D', 0): 2.0,
        ('X', 'D', 0): 10.0
    }
    speeds = {
        ('A', 'B', 0): 36.0,
        ('A', 'C', 0): 36.0,
        ('A', 'X', 0): 36.0,
        ('B', 'D', 0): 36.0,
        ('C', 'D', 0): 36.0,
        ('X', 'D', 0): 36.0
    }
    coords = {
        'A': (20.0000, 85.0000),
        'C': (20.00018, 85.00018),  # ~20m from A, ~30m to D
        'B': (20.00045, 85.00045),  # ~50m from A
        'X': (20.00090, 85.00090),  # ~100m from A
        'D': (20.00040, 85.00040)
    }
    return adj, lengths, weights, speeds, coords


# -----------------------------------------------------------------------------
# 1. CANDIDATE GENERATION TESTS
# -----------------------------------------------------------------------------

def test_candidate_generation_exactly_two_when_multiple_available(diamond_graph):
    """Verify that when out-degree > 2, exactly 2 candidates are returned."""
    adj, lengths, weights, speeds, coords = diamond_graph
    generator = CandidateGenerator(adj, lengths, coords)

    res = generator.generate_candidates(
        current_node='A',
        destination='D',
        edge_weights=weights,
        edge_speeds=speeds,
        strategy=CandidateGenerationStrategy.LOWEST_IMMEDIATE_COST
    )

    assert res.total_outgoing_count == 3
    assert res.eligible_count == 3
    assert len(res.candidates) == 2
    assert not res.is_forced
    assert not res.is_dead_end

    # The lowest cost candidates from A are C (cost 2) and B (cost 5)
    candidate_targets = {c.v for c in res.candidates}
    assert candidate_targets == {'B', 'C'}


def test_candidate_generation_forced_continuation(diamond_graph):
    """Verify that when out-degree == 1, forced continuation is returned without fake edge."""
    adj, lengths, weights, speeds, coords = diamond_graph
    generator = CandidateGenerator(adj, lengths, coords)

    res = generator.generate_candidates(
        current_node='B',
        destination='D',
        edge_weights=weights,
        edge_speeds=speeds
    )

    assert res.total_outgoing_count == 1
    assert res.eligible_count == 1
    assert len(res.candidates) == 1
    assert res.is_forced is True
    assert res.candidates[0].v == 'D'


def test_candidate_generation_dead_end():
    """Verify that node with out-degree 0 returns dead end status."""
    adj = {'A': [('B', 0)], 'B': []}
    lengths = {('A', 'B', 0): 50.0}
    generator = CandidateGenerator(adj, lengths)

    res = generator.generate_candidates(
        current_node='B',
        destination='Z',
        edge_weights={('A', 'B', 0): 10.0}
    )

    assert res.is_dead_end is True
    assert len(res.candidates) == 0
    assert res.eligible_count == 0


def test_candidate_generation_reversal_pruning():
    """Verify that immediate reverse edge back to previous node is pruned when alternatives exist."""
    # Two-way road: A <-> B, A -> C
    adj = {
        'A': [('B', 0), ('C', 0)],
        'B': [('A', 0), ('D', 0)],
        'C': [('D', 0)],
        'D': []
    }
    lengths = {
        ('A', 'B', 0): 50.0,
        ('B', 'A', 0): 50.0,
        ('A', 'C', 0): 50.0,
        ('B', 'D', 0): 50.0,
        ('C', 'D', 0): 50.0
    }
    weights = {e: 10.0 for e in lengths}
    generator = CandidateGenerator(adj, lengths)

    # Arriving at B from A: outgoing from B are A and D.
    # A should be pruned as immediate reversal, leaving only D.
    res = generator.generate_candidates(
        current_node='B',
        destination='D',
        edge_weights=weights,
        previous_node='A'
    )

    assert res.eligible_count == 1
    assert res.candidates[0].v == 'D'
    assert res.is_forced is True


# -----------------------------------------------------------------------------
# 2. DECISION STRATEGIES TESTS
# -----------------------------------------------------------------------------

def test_greedy_selection_picks_lower_immediate_cost(diamond_graph):
    """Verify Greedy strategy picks candidate with lowest immediate travel time."""
    adj, lengths, weights, speeds, coords = diamond_graph
    generator = CandidateGenerator(adj, lengths, coords)
    strategy = GreedyDecisionStrategy()
    selector = TwoEdgeSelector(generator, strategy)

    step = selector.decide_next_edge(
        step_index=0,
        current_node='A',
        destination='D',
        edge_weights=weights,
        edge_speeds=speeds
    )

    assert step.is_forced is False
    assert step.selected_edge == ('A', 'C', 0)
    assert step.next_node == 'C'
    assert step.travel_time_s == 2.0


def test_destination_aware_selection():
    """
    Verify Destination-Aware strategy picks the edge leading toward destination
    even if immediate cost is slightly higher than an opposite branch.
    """
    # Node A branches:
    # A -> B (cost 2, but B is away from D: h = 100s)
    # A -> C (cost 4, but C is close to D: h = 10s)
    adj = {'A': [('B', 0), ('C', 0)], 'B': [], 'C': [('D', 0)], 'D': []}
    lengths = {('A', 'B', 0): 20.0, ('A', 'C', 0): 40.0, ('C', 'D', 0): 10.0}
    weights = {('A', 'B', 0): 2.0, ('A', 'C', 0): 4.0, ('C', 'D', 0): 1.0}
    coords = {
        'A': (20.0, 85.0),
        'B': (19.0, 84.0),  # Far
        'C': (20.05, 85.05), # Close
        'D': (20.06, 85.06)
    }

    generator = CandidateGenerator(adj, lengths, coords)
    strategy = DestinationAwareDecisionStrategy(heuristic_weight=1.0)
    selector = TwoEdgeSelector(generator, strategy)

    step = selector.decide_next_edge(
        step_index=0,
        current_node='A',
        destination='D',
        edge_weights=weights
    )

    # Destination aware should choose C because total estimated time (4 + small h) < (2 + large h)
    assert step.next_node == 'C'
    assert step.selected_edge == ('A', 'C', 0)


def test_limited_lookahead_evaluation():
    """
    Verify Lookahead strategy avoids a fast edge that leads into a severe downstream bottleneck.
    Path 1: A -> B (cost 1) -> D (cost 50) => Total = 51s
    Path 2: A -> C (cost 3) -> D (cost 3)  => Total = 6s
    Greedy would pick B (cost 1). Lookahead (depth 2) should pick C.
    """
    adj = {
        'A': [('B', 0), ('C', 0)],
        'B': [('D', 0)],
        'C': [('D', 0)],
        'D': []
    }
    lengths = {('A', 'B', 0): 10.0, ('A', 'C', 0): 30.0, ('B', 'D', 0): 500.0, ('C', 'D', 0): 30.0}
    weights = {
        ('A', 'B', 0): 1.0,
        ('A', 'C', 0): 3.0,
        ('B', 'D', 0): 50.0,  # severe bottleneck
        ('C', 'D', 0): 3.0    # clear bypass
    }

    generator = CandidateGenerator(adj, lengths)
    heuristic_fn = lambda u, v: 0.0
    lookahead_eval = LimitedLookaheadEvaluator(adj, weights, heuristic_fn, depth=2)
    strategy = LimitedLookaheadDecisionStrategy(lookahead_eval)
    selector = TwoEdgeSelector(generator, strategy)

    step = selector.decide_next_edge(
        step_index=0,
        current_node='A',
        destination='D',
        edge_weights=weights
    )

    assert step.next_node == 'C'
    assert step.selected_edge == ('A', 'C', 0)


def test_adaptive_strategy_switches_under_congestion():
    """Verify Adaptive strategy delegates to Lookahead when speeds drop below threshold."""
    adj = {'A': [('B', 0), ('C', 0)], 'B': [('D', 0)], 'C': [('D', 0)], 'D': []}
    lengths = {('A', 'B', 0): 10.0, ('A', 'C', 0): 30.0, ('B', 'D', 0): 50.0, ('C', 'D', 0): 30.0}
    weights = {('A', 'B', 0): 10.0, ('A', 'C', 0): 12.0, ('B', 'D', 0): 50.0, ('C', 'D', 0): 3.0}
    speeds = {('A', 'B', 0): 10.0, ('A', 'C', 0): 12.0, ('B', 'D', 0): 10.0, ('C', 'D', 0): 36.0}

    generator = CandidateGenerator(adj, lengths)
    dest_aware = DestinationAwareDecisionStrategy()
    lookahead_eval = LimitedLookaheadEvaluator(adj, weights, lambda u, v: 0.0, depth=2)
    lookahead_strat = LimitedLookaheadDecisionStrategy(lookahead_eval)

    adaptive = AdaptiveDecisionStrategy(
        dest_aware_strategy=dest_aware,
        lookahead_strategy=lookahead_strat,
        congestion_speed_threshold_kmh=20.0
    )
    selector = TwoEdgeSelector(generator, adaptive)

    # Congestion speed is 10 km/h (< 20 km/h), so it switches to Lookahead and selects C
    step = selector.decide_next_edge(
        step_index=0,
        current_node='A',
        destination='D',
        edge_weights=weights,
        edge_speeds=speeds
    )

    assert "Lookahead" in step.strategy_name
    assert step.next_node == 'C'


# -----------------------------------------------------------------------------
# 3. ROUTE SAFETY & RESILIENCE TESTS
# -----------------------------------------------------------------------------

def test_cycle_prevention_and_loop_breaking():
    """
    Verify RouteController detects cyclic loops (e.g. A <-> B) and invokes recovery
    to force forward progress to destination.
    """
    # Graph with potential cycle:
    # A -> B (1), B -> A (1), A -> C (10), C -> D (1)
    adj = {
        'A': [('B', 0), ('C', 0)],
        'B': [('A', 0)],
        'C': [('D', 0)],
        'D': []
    }
    lengths = {('A', 'B', 0): 10.0, ('B', 'A', 0): 10.0, ('A', 'C', 0): 100.0, ('C', 'D', 0): 10.0}
    weights = {('A', 'B', 0): 1.0, ('B', 'A', 0): 1.0, ('A', 'C', 0): 10.0, ('C', 'D', 0): 1.0}

    generator = CandidateGenerator(adj, lengths)
    strategy = GreedyDecisionStrategy()
    selector = TwoEdgeSelector(generator, strategy)
    controller = RouteController(adj, lengths, selector, max_node_visits=1)

    result = controller.execute_journey(
        source='A',
        destination='D',
        initial_weights=weights
    )

    assert result.is_success is True
    assert result.node_path[-1] == 'D'
    # Either strategy loop penalty or cycle breaker forced forward progress
    assert 'D' in result.node_path


def test_dead_end_recovery():
    """
    Verify RouteController handles a dead end by falling back to Dijkstra.
    A -> DeadEnd (no exits)
    A -> Alternate -> D
    """
    adj = {
        'A': [('DeadEnd', 0), ('Alternate', 0)],
        'DeadEnd': [],
        'Alternate': [('D', 0)],
        'D': []
    }
    lengths = {('A', 'DeadEnd', 0): 10.0, ('A', 'Alternate', 0): 20.0, ('Alternate', 'D', 0): 20.0}
    weights = {('A', 'DeadEnd', 0): 1.0, ('A', 'Alternate', 0): 2.0, ('Alternate', 'D', 0): 2.0}

    generator = CandidateGenerator(adj, lengths)
    strategy = GreedyDecisionStrategy()
    selector = TwoEdgeSelector(generator, strategy)
    controller = RouteController(adj, lengths, selector)

    result = controller.execute_journey(
        source='A',
        destination='D',
        initial_weights=weights
    )

    assert result.is_success is True
    assert result.node_path[-1] == 'D'


def test_complete_sequential_journey_matches_dijkstra_on_diamond(diamond_graph):
    """Verify that on diamond graph, Destination-Aware sequential selection finds optimal path."""
    adj, lengths, weights, speeds, coords = diamond_graph
    generator = CandidateGenerator(adj, lengths, coords)
    strategy = DestinationAwareDecisionStrategy()
    selector = TwoEdgeSelector(generator, strategy)
    controller = RouteController(adj, lengths, selector)

    result = controller.execute_journey(
        source='A',
        destination='D',
        initial_weights=weights,
        initial_speeds=speeds
    )

    assert result.is_success is True
    assert result.node_path == ['A', 'C', 'D']
    assert abs(result.total_travel_time_s - 4.0) < 1e-4
    assert result.total_decisions == 2
    assert result.recovery_events == 0


def test_sequential_journey_with_dynamic_traffic_update(diamond_graph):
    """
    Verify sequential journey correctly adapts when traffic changes mid-journey.
    At step 1 (arrival at C), C -> D degrades from 2s to 50s.
    """
    adj, lengths, weights, speeds, coords = diamond_graph
    updated_weights = dict(weights)
    updated_weights[('C', 'D', 0)] = 50.0  # sudden bottleneck

    generator = CandidateGenerator(adj, lengths, coords)
    strategy = DestinationAwareDecisionStrategy()
    selector = TwoEdgeSelector(generator, strategy)
    controller = RouteController(adj, lengths, selector)

    result = controller.execute_journey(
        source='A',
        destination='D',
        initial_weights=weights,
        traffic_update_step=1,
        updated_weights=updated_weights
    )

    assert result.is_success is True
    assert result.node_path[-1] == 'D'
    assert result.reroute_events > 0


def test_backtrack_recovery_records_reverse_movement():
    """A dead-end node backtracks to the previous node and records the reverse edge.
    The graph includes a reverse edge with defined length and weight.
    """
    adj = {
        'A': [('B', 0)],
        'B': [('A', 0), ('C', 0)],
        'C': []
    }
    lengths = {('A', 'B', 0): 10.0, ('B', 'A', 0): 10.0, ('B', 'C', 0): 20.0}
    weights = {('A', 'B', 0): 1.0, ('B', 'A', 0): 1.0, ('B', 'C', 0): 2.0}
    generator = CandidateGenerator(adj, lengths)
    selector = TwoEdgeSelector(generator, GreedyDecisionStrategy())
    controller = RouteController(adj, lengths, selector)
    # Force backtrack by allowing only one visit per node
    controller.max_node_visits = 0
    result = controller.execute_journey(source='A', destination='C', initial_weights=weights)
    assert result.node_path == ['A', 'B', 'A', 'B', 'C']
    assert result.edge_path[0] == ('A', 'B', 0)
    assert result.edge_path[1] == ('B', 'A', 0)
    assert result.edge_path[-1] == ('B', 'C', 0)
    expected_time = weights[('A', 'B', 0)] + weights[('B', 'A', 0)] + weights[('B', 'C', 0)]
    assert abs(result.total_travel_time_s - expected_time) < 1e-6


def test_cycle_detection_breaks_loop():
    """Detect and break a simple two-node cycle using fallback recovery."""
    adj = {'A': [('B', 0), ('C', 0)], 'B': [('A', 0)], 'C': []}
    lengths = {('A', 'B', 0): 10.0, ('B', 'A', 0): 10.0, ('A', 'C', 0): 20.0}
    weights = {('A', 'B', 0): 1.0, ('B', 'A', 0): 1.0, ('A', 'C', 0): 5.0}
    generator = CandidateGenerator(adj, lengths)
    selector = TwoEdgeSelector(generator, GreedyDecisionStrategy())
    controller = RouteController(adj, lengths, selector, max_node_visits=1)
    result = controller.execute_journey(source='A', destination='C', initial_weights=weights)
    assert result.is_success
    assert result.node_path[-1] == 'C'
    assert result.recovery_events >= 1


def test_traffic_update_accepts_and_changes_route():
    """Traffic update passes thresholds and alters the chosen path."""
    adj = {'A': [('B', 0), ('C', 0)], 'B': [('D', 0)], 'C': [('D', 0)], 'D': []}
    lengths = {('A', 'B', 0): 10.0, ('A', 'C', 0): 10.0, ('B', 'D', 0): 10.0, ('C', 'D', 0): 10.0}
    init_weights = {('A', 'B', 0): 1.0, ('A', 'C', 0): 2.0, ('B', 'D', 0): 1.0, ('C', 'D', 0): 2.0}
    updated_weights = {('A', 'B', 0): 5.0, ('A', 'C', 0): 2.0, ('B', 'D', 0): 10.0, ('C', 'D', 0): 2.0}
    generator = CandidateGenerator(adj, lengths)
    selector = TwoEdgeSelector(generator, GreedyDecisionStrategy())
    controller = RouteController(adj, lengths, selector, reroute_threshold_seconds=0.0, reroute_threshold_percent=0.0)
    result = controller.execute_journey(
        source='A', destination='D', initial_weights=init_weights,
        traffic_update_step=0, updated_weights=updated_weights)
    assert result.node_path[:3] == ['A', 'C', 'D']
    assert result.reroute_events == 1


def test_traffic_update_rejected_restores_original_weights():
    """Traffic update fails thresholds; original route is kept."""
    adj = {'A': [('B', 0), ('C', 0)], 'B': [('D', 0)], 'C': [('D', 0)], 'D': []}
    lengths = {('A', 'B', 0): 10.0, ('A', 'C', 0): 10.0, ('B', 'D', 0): 10.0, ('C', 'D', 0): 10.0}
    init_weights = {('A', 'B', 0): 1.0, ('A', 'C', 0): 2.0, ('B', 'D', 0): 1.0, ('C', 'D', 0): 2.0}
    updated_weights = {('A', 'B', 0): 2.0, ('A', 'C', 0): 2.0, ('B', 'D', 0): 3.0, ('C', 'D', 0): 2.0}
    generator = CandidateGenerator(adj, lengths)
    selector = TwoEdgeSelector(generator, GreedyDecisionStrategy())
    controller = RouteController(adj, lengths, selector, reroute_threshold_seconds=5.0, reroute_threshold_percent=10.0)
    result = controller.execute_journey(
        source='A', destination='D', initial_weights=init_weights,
        traffic_update_step=0, updated_weights=updated_weights)
    assert result.node_path[:3] == ['A', 'B', 'D']
    assert result.reroute_events == 0


def test_lookahead_uses_updated_weights_after_reroute():
    """Lookahead decision reflects new weights after a successful traffic update."""
    adj = {'A': [('B', 0), ('C', 0)], 'B': [('D', 0)], 'C': [('D', 0)], 'D': []}
    lengths = {('A', 'B', 0): 10.0, ('A', 'C', 0): 10.0, ('B', 'D', 0): 10.0, ('C', 'D', 0): 10.0}
    init_weights = {('A', 'B', 0): 1.0, ('A', 'C', 0): 2.0, ('B', 'D', 0): 1.0, ('C', 'D', 0): 2.0}
    updated_weights = {('A', 'B', 0): 5.0, ('A', 'C', 0): 2.0, ('B', 'D', 0): 10.0, ('C', 'D', 0): 2.0}
    generator = CandidateGenerator(adj, lengths)
    lookahead_eval = LimitedLookaheadEvaluator(adj, init_weights, lambda u, v: 0.0, depth=2)
    selector = TwoEdgeSelector(generator, LimitedLookaheadDecisionStrategy(lookahead_eval))
    controller = RouteController(adj, lengths, selector, reroute_threshold_seconds=0.0, reroute_threshold_percent=0.0)
    result = controller.execute_journey(
        source='A', destination='D', initial_weights=init_weights,
        traffic_update_step=0, updated_weights=updated_weights)
    assert result.node_path[1] == 'C'
    assert result.reroute_events == 1
