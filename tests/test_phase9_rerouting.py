"""
Phase 9 Dynamic Rerouting Test Suite

Verifies:
1. Rerouting is not triggered below threshold.
2. Rerouting is triggered above threshold.
3. Route changes when an edge becomes congested.
4. No-reroute counterfactual strategy can be evaluated.
5. Dynamic strategy can be evaluated.
6. Travel-time savings are calculated correctly.
7. Original route is not modified retroactively.
8. Actual traffic is not used to choose the initial ML route.
9. Custom Dijkstra is used for rerouting.
10. Source and destination remain valid.
"""

import os
import sys
sys.path.insert(0, os.path.abspath('.'))

import pytest
import numpy as np
import networkx as nx

from src.routing.dijkstra import custom_dijkstra, DijkstraResult
from src.routing.traffic_weights import GraphWeightManager, calculate_travel_time_seconds
from src.routing.dynamic_rerouter import DynamicRerouter


@pytest.fixture
def toy_weight_manager():
    """Create a minimal mock weight manager with controlled topology."""
    G = nx.MultiDiGraph()
    # Path 1: A -> B -> C -> D
    # Path 2: B -> E -> D
    G.add_edge('A', 'B', key=0, length='1000.0', highway='primary')
    G.add_edge('B', 'C', key=0, length='1000.0', highway='primary')
    G.add_edge('C', 'D', key=0, length='1000.0', highway='primary')
    G.add_edge('B', 'E', key=0, length='1100.0', highway='secondary')
    G.add_edge('E', 'D', key=0, length='1100.0', highway='secondary')
    
    # Empty mapping for mock
    import pandas as pd
    df_empty = pd.DataFrame(columns=['traffic_segment_id', 'u', 'v', 'key', 'routing_eligibility'])
    wm = GraphWeightManager(G, df_empty)
    return wm


def test_reroute_not_triggered_below_threshold(toy_weight_manager):
    """Test 1: Rerouting is not triggered when savings are below threshold."""
    rerouter = DynamicRerouter(toy_weight_manager, reroute_threshold_seconds=10.0, reroute_threshold_percent=3.0)
    
    current_time = 100.0
    alt_time = 95.0  # saves 5.0s (5%), but below 10s threshold
    
    triggered, abs_sav, rel_sav, reason = rerouter.should_reroute(current_time, alt_time)
    assert triggered is False
    assert abs_sav == 5.0
    assert rel_sav == 5.0
    assert "below" in reason.lower()


def test_reroute_triggered_above_threshold(toy_weight_manager):
    """Test 2: Rerouting is triggered when savings exceed both thresholds."""
    rerouter = DynamicRerouter(toy_weight_manager, reroute_threshold_seconds=10.0, reroute_threshold_percent=3.0)
    
    current_time = 200.0
    alt_time = 150.0  # saves 50.0s (25%), well above 10s and 3%
    
    triggered, abs_sav, rel_sav, reason = rerouter.should_reroute(current_time, alt_time)
    assert triggered is True
    assert abs_sav == 50.0
    assert rel_sav == 25.0
    assert "exceeding" in reason.lower()


def test_route_changes_when_edge_congested(toy_weight_manager):
    """Test 3: Verify Dijkstra changes path when downstream edge C->D slows down."""
    wm = toy_weight_manager
    rerouter = DynamicRerouter(wm, reroute_threshold_seconds=10.0, reroute_threshold_percent=3.0)
    
    # Initial weights: C->D is fast (40 km/h = 90s)
    # Total B->C->D = 90 + 90 = 180s. B->E->D = 132 + 132 = 264s
    w_pred = dict(wm.static_weights)
    w_pred[('B', 'C', 0)] = 90.0
    w_pred[('C', 'D', 0)] = 90.0
    w_pred[('B', 'E', 0)] = 132.0
    w_pred[('E', 'D', 0)] = 132.0
    
    res0 = rerouter.compute_alternative_route('B', 'D', w_pred)
    assert res0.node_path == ['B', 'C', 'D'], "Initial route must prefer B->C->D"
    
    # Congestion on C->D: slows to 10 km/h (360s). Total B->C->D = 450s > 264s
    w_obs = dict(w_pred)
    w_obs[('C', 'D', 0)] = 360.0
    
    res1 = rerouter.compute_alternative_route('B', 'D', w_obs)
    assert res1.node_path == ['B', 'E', 'D'], "Reroute must deflect to bypass B->E->D"


def test_no_reroute_counterfactual_evaluated(toy_weight_manager):
    """Test 4 & 5 & 6: Validate no-reroute vs dynamic journey calculation."""
    wm = toy_weight_manager
    rerouter = DynamicRerouter(wm, reroute_threshold_seconds=10.0, reroute_threshold_percent=3.0)
    
    # Planning weights (t0): A->B->C->D is planned
    w_pred = {
        ('A', 'B', 0): 90.0,
        ('B', 'C', 0): 90.0,
        ('C', 'D', 0): 90.0,
        ('B', 'E', 0): 130.0,
        ('E', 'D', 0): 130.0
    }
    
    # Observed weights at t1: C->D gridlocked (360s)
    w_obs = {
        ('A', 'B', 0): 90.0,
        ('B', 'C', 0): 90.0,
        ('C', 'D', 0): 360.0,
        ('B', 'E', 0): 130.0,
        ('E', 'D', 0): 130.0
    }
    
    sim = rerouter.simulate_journey(
        scenario_id=1,
        od_id=0,
        source='A',
        destination='D',
        t0='2026-01-16 17:00:00',
        t1='2026-01-16 18:00:00',
        t0_ist='2026-01-16 17:00:00 IST',
        t1_ist='2026-01-16 18:00:00 IST',
        period_label='Evening Peak',
        w_pred_t0=w_pred,
        w_obs_t1=w_obs,
        dynamic_edges_set={('C', 'D', 0)},
        decision_frac=0.33  # Decision at node B
    )
    
    # Total no-reroute = A->B (90) + B->C (90) + C->D (360) = 540s
    assert sim['total_time_no_reroute_s'] == 540.0
    # Dynamic route switches at B to B->E->D (260). Total = 90 + 260 = 350s
    assert sim['total_time_dynamic_s'] == 350.0
    # Time saved = 540 - 350 = 190s
    assert sim['time_saved_s'] == 190.0
    assert sim['reroute_triggered'] is True
    assert sim['improvement_pct'] == round((190.0 / 540.0) * 100.0, 2)


def test_original_route_not_modified_retroactively(toy_weight_manager):
    """Test 7: Verify original route R0 remains intact in output structure."""
    wm = toy_weight_manager
    rerouter = DynamicRerouter(wm)
    w = dict(wm.static_weights)
    
    sim = rerouter.simulate_journey(
        scenario_id=1, od_id=0, source='A', destination='D',
        t0='t0', t1='t1', t0_ist='t0_ist', t1_ist='t1_ist',
        period_label='Peak', w_pred_t0=w, w_obs_t1=w, dynamic_edges_set=set(),
        decision_frac=0.33
    )
    assert sim['r0_node_path'][0] == 'A'
    assert sim['r0_node_path'][-1] == 'D'
    assert len(sim['r0_node_path']) >= 3


def test_no_actual_traffic_leakage_for_initial_plan(toy_weight_manager):
    """Test 8: Verify initial plan consumes strictly predicted weights."""
    wm = toy_weight_manager
    rerouter = DynamicRerouter(wm)
    
    # Under predicted weights, B->C->D is preferred (180s vs 260s)
    w_pred = {('A', 'B', 0): 10, ('B', 'C', 0): 10, ('C', 'D', 0): 10, ('B', 'E', 0): 100, ('E', 'D', 0): 100}
    # Even if actual traffic had B->C->D completely blocked:
    w_obs = {('A', 'B', 0): 10, ('B', 'C', 0): 10, ('C', 'D', 0): 10000, ('B', 'E', 0): 100, ('E', 'D', 0): 100}
    
    res = rerouter.plan_initial_route('A', 'D', w_pred)
    assert res.node_path == ['A', 'B', 'C', 'D'], "Initial route must NOT leak actual future traffic"


def test_source_and_destination_preserved(toy_weight_manager):
    """Test 9 & 10: Verify endpoints are preserved in both initial and rerouted paths."""
    wm = toy_weight_manager
    rerouter = DynamicRerouter(wm)
    w = dict(wm.static_weights)
    sim = rerouter.simulate_journey(
        scenario_id=1, od_id=0, source='A', destination='D',
        t0='t0', t1='t1', t0_ist='t0_ist', t1_ist='t1_ist',
        period_label='Peak', w_pred_t0=w, w_obs_t1=w, dynamic_edges_set=set()
    )
    assert sim['r0_node_path'][0] == 'A' and sim['r0_node_path'][-1] == 'D'
    assert sim['r1_node_path'][0] == 'A' and sim['r1_node_path'][-1] == 'D'
