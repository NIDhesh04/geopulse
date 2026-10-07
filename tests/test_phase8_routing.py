"""
Phase 8 Routing Validation Test Suite

Validates:
1. Custom Dijkstra on toy graphs (known shortest path, parallel edges, unreachable, source == dest).
2. Physical weight calculation kinematics (1000m at 36 km/h = 100 seconds).
3. Dynamic edge preference when travel time improves.
4. Dynamic rerouting deflection when traffic congestion changes edge speed.
5. Zero data leakage: ML route selection does not consume actual future traffic.
"""

import os
import sys
sys.path.insert(0, os.path.abspath('.'))

import pytest
import numpy as np
from src.routing.dijkstra import custom_dijkstra, DijkstraResult
from src.routing.traffic_weights import calculate_travel_time_seconds, get_static_speed_kmh


# -----------------------------------------------------------------------------
# 1. DIJKSTRA TESTS ON CONTROLLED TOY GRAPHS
# -----------------------------------------------------------------------------

def test_dijkstra_known_shortest_path():
    """Verify Dijkstra finds the exact known minimum path on a diamond graph."""
    # Graph: A -> B (5), A -> C (2), C -> D (2), B -> D (5)
    # Expected path: A -> C -> D, cost = 4.0
    adj = {
        'A': [('B', 0), ('C', 0)],
        'B': [('D', 0)],
        'C': [('D', 0)],
        'D': []
    }
    weights = {
        ('A', 'B', 0): 5.0,
        ('A', 'C', 0): 2.0,
        ('C', 'D', 0): 2.0,
        ('B', 'D', 0): 5.0
    }

    res = custom_dijkstra(adj, weights, 'A', 'D')
    assert res.is_reached is True
    assert res.node_path == ['A', 'C', 'D']
    assert res.edge_path == [('A', 'C', 0), ('C', 'D', 0)]
    assert abs(res.total_cost - 4.0) < 1e-6


def test_dijkstra_source_equals_destination():
    """Verify source == target returns 0 cost, single-node path, and reached=True."""
    adj = {'A': [('B', 0)], 'B': []}
    weights = {('A', 'B', 0): 10.0}

    res = custom_dijkstra(adj, weights, 'A', 'A')
    assert res.is_reached is True
    assert res.node_path == ['A']
    assert res.edge_path == []
    assert res.total_cost == 0.0
    assert res.visited_nodes_count == 1


def test_dijkstra_unreachable_target():
    """Verify unreachable target returns empty path and infinite cost."""
    adj = {
        'A': [('B', 0)],
        'B': [],
        'C': [('D', 0)],
        'D': []
    }
    weights = {
        ('A', 'B', 0): 5.0,
        ('C', 'D', 0): 5.0
    }

    res = custom_dijkstra(adj, weights, 'A', 'D')
    assert res.is_reached is False
    assert res.node_path == []
    assert res.edge_path == []
    assert np.isinf(res.total_cost)


def test_dijkstra_parallel_edges():
    """Verify Dijkstra correctly selects the minimum-weight key among parallel edges."""
    # Two edges between A and B: key 0 (cost 10) and key 1 (cost 3)
    adj = {
        'A': [('B', 0), ('B', 1)],
        'B': []
    }
    weights = {
        ('A', 'B', 0): 10.0,
        ('A', 'B', 1): 3.0
    }

    res = custom_dijkstra(adj, weights, 'A', 'B')
    assert res.is_reached is True
    assert res.node_path == ['A', 'B']
    assert res.edge_path == [('A', 'B', 1)]
    assert abs(res.total_cost - 3.0) < 1e-6


# -----------------------------------------------------------------------------
# 2. PHYSICAL WEIGHT KINEMATICS TESTS
# -----------------------------------------------------------------------------

def test_kinematic_travel_time():
    """
    Verify fundamental requirement:
    1000m at 36 km/h must equal exactly 100.0 seconds (36 km/h = 10 m/s).
    """
    length_m = 1000.0
    speed_kmh = 36.0
    expected_seconds = 100.0

    calc_time = calculate_travel_time_seconds(length_m, speed_kmh)
    assert abs(calc_time - expected_seconds) < 1e-6, f"Expected 100.0s, got {calc_time}"


def test_speed_guardrail_clamping():
    """Verify speed cannot drop below minimum crawl speed of 3.0 km/h."""
    length_m = 300.0
    zero_speed = 0.0
    negative_speed = -10.0

    # 300m at 3.0 km/h = 300 / (3.0 / 3.6) = 300 / 0.833333 = 360 seconds
    t_zero = calculate_travel_time_seconds(length_m, zero_speed)
    t_neg = calculate_travel_time_seconds(length_m, negative_speed)

    assert abs(t_zero - 360.0) < 1e-4
    assert abs(t_neg - 360.0) < 1e-4


# -----------------------------------------------------------------------------
# 3. DYNAMIC ROUTING & REROUTING LOGIC
# -----------------------------------------------------------------------------

def test_dynamic_edge_preference_and_rerouting():
    """
    Verify routing behavior when traffic speeds change:
    Two alternative routes:
    Route 1: A -> B -> D (length 1000m each)
    Route 2: A -> C -> D (length 1200m each)
    At free-flow (both 40 km/h), Route 1 is shorter and preferred.
    When Route 1 experiences congestion (slows to 10 km/h),
    Dijkstra must dynamically deflect/reroute to Route 2.
    """
    adj = {
        'A': [('B', 0), ('C', 0)],
        'B': [('D', 0)],
        'C': [('D', 0)],
        'D': []
    }

    # Case 1: Free flow (both at 40 km/h)
    t_AB = calculate_travel_time_seconds(1000, 40)  # 90.0s
    t_BD = calculate_travel_time_seconds(1000, 40)  # 90.0s -> Route 1 total = 180s
    t_AC = calculate_travel_time_seconds(1200, 40)  # 108.0s
    t_CD = calculate_travel_time_seconds(1200, 40)  # 108.0s -> Route 2 total = 216s

    weights_free = {
        ('A', 'B', 0): t_AB,
        ('B', 'D', 0): t_BD,
        ('A', 'C', 0): t_AC,
        ('C', 'D', 0): t_CD,
    }

    res_free = custom_dijkstra(adj, weights_free, 'A', 'D')
    assert res_free.node_path == ['A', 'B', 'D'], "Free flow should take shorter Route 1"

    # Case 2: Route 1 becomes heavily congested (slows to 10 km/h)
    t_AB_congested = calculate_travel_time_seconds(1000, 10)  # 360.0s
    t_BD_congested = calculate_travel_time_seconds(1000, 10)  # 360.0s -> Route 1 total = 720s

    weights_congested = {
        ('A', 'B', 0): t_AB_congested,
        ('B', 'D', 0): t_BD_congested,
        ('A', 'C', 0): t_AC,
        ('C', 'D', 0): t_CD,
    }

    res_congested = custom_dijkstra(adj, weights_congested, 'A', 'D')
    assert res_congested.node_path == ['A', 'C', 'D'], "Congestion should trigger dynamic reroute to Route 2"
    assert res_congested.total_cost < weights_congested[('A', 'B', 0)] + weights_congested[('B', 'D', 0)]


# -----------------------------------------------------------------------------
# 4. ZERO DATA LEAKAGE TEST
# -----------------------------------------------------------------------------

def test_zero_leakage_in_ml_route_selection():
    """
    Verify that ML route selection consumes strictly predicted weights,
    not future observed weights.
    """
    adj = {
        'A': [('B', 0), ('C', 0)],
        'B': [('D', 0)],
        'C': [('D', 0)],
        'D': []
    }

    # Model predicted weights: believes Route 1 is faster
    pred_weights = {
        ('A', 'B', 0): 50.0,
        ('B', 'D', 0): 50.0,
        ('A', 'C', 0): 100.0,
        ('C', 'D', 0): 100.0
    }

    # Actual observed weights at time t+1: Route 1 suffered sudden incident
    actual_weights = {
        ('A', 'B', 0): 500.0,
        ('B', 'D', 0): 500.0,
        ('A', 'C', 0): 100.0,
        ('C', 'D', 0): 100.0
    }

    # Route decision must be made strictly with predicted weights
    ml_route = custom_dijkstra(adj, pred_weights, 'A', 'D')
    assert ml_route.node_path == ['A', 'B', 'D'], "ML pathfinder must strictly use predicted weights"

    # Evaluated actual travel time must be evaluated on actual weights
    ml_actual_time = sum(actual_weights[e] for e in ml_route.edge_path)
    assert ml_actual_time == 1000.0, "Actual cost evaluation must accurately reflect ground truth"
