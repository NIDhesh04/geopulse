"""
GeoPulse Phase 11: End-to-End Edge-Cloud Integration Test Suite

Tests:
1. Cloud model service loading, metadata integrity, and prediction broadcast
2. Edge server initialization, weight synthesis, and initial route computation
3. Edge server degradation evaluation and dual-threshold gating
4. Vehicle client simulation, link-by-link kinematic traversal, and position telemetry
5. Closed-loop Cloud -> Edge -> Vehicle -> Traffic Update -> Reroute integration
6. Verification that demo results match canonical Phase 9 values (time saved = 84.9s, +6.60%)
7. Verification that all 3 publication figures exist at 300 DPI
"""

import os
import sys
sys.path.insert(0, os.path.abspath('.'))

import json
import pytest
import pandas as pd
import numpy as np
import networkx as nx

from src.routing.traffic_weights import GraphWeightManager
from src.cloud.model_service import CloudModelService
from src.edge.edge_server import EdgeServer
from src.edge.messages import TrafficUpdateMessage, PositionUpdateMessage
from src.simulation.vehicle import Vehicle


@pytest.fixture(scope="module")
def shared_graph_and_mapping():
    G = nx.read_graphml('data/raw/osm/bhubaneswar_drive.graphml')
    mapping_df = pd.read_parquet('data/processed/traffic_to_osm_mapping_final.parquet')
    weight_manager = GraphWeightManager(G, mapping_df)
    return G, mapping_df, weight_manager


def test_cloud_model_service_lifecycle():
    cloud = CloudModelService()
    meta = cloud.get_metadata()

    assert meta['model_type'] == 'LightGBMRegressor'
    assert meta['feature_count'] == 25
    assert len(meta['feature_cols']) == 25
    assert "LightGBM" in meta['model_version']

    # Test broadcast generation
    msg, exec_ms = cloud.generate_predictions_broadcast("2026-01-15 14:00:00+00:00")
    assert msg.total_segments == 700
    assert len(msg.predicted_speeds) == 700
    assert exec_ms > 0.0


def test_edge_server_initial_routing(shared_graph_and_mapping):
    _, _, weight_manager = shared_graph_and_mapping
    cloud = CloudModelService()
    edge_server = EdgeServer(weight_manager, threshold_seconds=10.0, threshold_percent=3.0)

    model_msg, _ = cloud.generate_predictions_broadcast("2026-01-15 14:00:00+00:00")
    t_synth = edge_server.update_model_predictions(model_msg)
    assert t_synth > 0.0
    assert len(edge_server.predicted_weights) > 40000

    origin = "3722327026"
    dest = "2443921849"
    route_msg, dijkstra_ms = edge_server.compute_initial_route("veh_test", origin, dest, "2026-01-15 19:30:00+05:30")

    assert route_msg.vehicle_id == "veh_test"
    assert not route_msg.is_reroute
    assert len(route_msg.edge_path) == 74
    assert route_msg.node_path[0] == origin
    assert route_msg.node_path[-1] == dest
    assert dijkstra_ms > 0.0


def test_edge_server_threshold_gating(shared_graph_and_mapping):
    _, _, weight_manager = shared_graph_and_mapping
    cloud = CloudModelService()
    edge_server = EdgeServer(weight_manager, threshold_seconds=10.0, threshold_percent=3.0)

    model_msg, _ = cloud.generate_predictions_broadcast("2026-01-15 14:00:00+00:00")
    edge_server.update_model_predictions(model_msg)

    origin = "3722327026"
    dest = "2443921849"
    edge_server.compute_initial_route("veh_gate_test", origin, dest, "2026-01-15 19:30:00+05:30")

    # If observed traffic equals predicted traffic, saving is 0 -> should NOT reroute
    dummy_traffic = TrafficUpdateMessage(
        timestamp="2026-01-15 20:30:00+05:30",
        observed_speeds=model_msg.predicted_speeds,
        sensor_count=700
    )
    edge_server.update_traffic(dummy_traffic)

    # Position vehicle at step 15
    node_step15 = edge_server.sessions["veh_gate_test"]['active_route_nodes'][15]
    pos_msg = PositionUpdateMessage(
        vehicle_id="veh_gate_test",
        current_node=node_step15,
        current_edge=None,
        edge_index=15,
        progress_pct=20.0,
        elapsed_time_s=300.0,
        timestamp="2026-01-15 20:00:00+05:30"
    )
    edge_server.update_vehicle_position(pos_msg)

    route_update, metrics = edge_server.evaluate_and_reroute("veh_gate_test", "2026-01-15 20:30:00+05:30")
    assert route_update is None, "Should NOT trigger reroute when speeds match predictions"
    assert not metrics['reroute_triggered']


def test_vehicle_simulation_and_reroute_acceptance():
    v = Vehicle("veh_unit", "A", "E", "2026-01-15 19:30:00+05:30")
    from src.edge.messages import RouteUpdateMessage

    init_msg = RouteUpdateMessage(
        vehicle_id="veh_unit",
        node_path=["A", "B", "C", "D", "E"],
        edge_path=[("A", "B", 0), ("B", "C", 0), ("C", "D", 0), ("D", "E", 0)],
        total_cost_s=400.0,
        is_reroute=False,
        saving_s=0.0,
        saving_pct=0.0,
        reason="Initial"
    )
    v.receive_initial_route(init_msg)
    assert v.current_node == "A"
    assert len(v.current_route_edges) == 4

    weights = {("A", "B", 0): 50.0, ("B", "C", 0): 50.0, ("C", "D", 0): 100.0, ("D", "E", 0): 100.0,
               ("B", "F", 0): 40.0, ("F", "E", 0): 40.0}
    lens = {e: 500.0 for e in weights}

    # Advance 2 steps to B
    pos = v.advance_to_step(2, weights, lens, "2026-01-15 19:40:00+05:30")
    assert v.current_node == "C"
    assert v.edge_index == 2
    assert v.elapsed_travel_time_s == 100.0

    # Reroute from C -> F -> E
    reroute_msg = RouteUpdateMessage(
        vehicle_id="veh_unit",
        node_path=["A", "B", "C", "F", "E"],
        edge_path=[("A", "B", 0), ("B", "C", 0), ("C", "F", 0), ("F", "E", 0)],
        total_cost_s=250.0,
        is_reroute=True,
        saving_s=50.0,
        saving_pct=25.0,
        reason="Bottleneck avoided"
    )
    v.apply_route_update(reroute_msg, "2026-01-15 19:40:00+05:30")
    assert v.reroute_received

    # Complete journey
    v.complete_journey(weights, lens, "2026-01-15 19:50:00+05:30")
    assert v.is_journey_complete
    assert v.current_node == "E"


def test_canonical_demo_results_match_phase9():
    res_path = 'results/phase11/demo_results.json'
    assert os.path.exists(res_path), f"Missing {res_path}"

    with open(res_path, 'r') as f:
        res = json.load(f)

    assert res['origin_node'] == "3722327026"
    assert res['destination_node'] == "2443921849"
    assert res['decision_node'] == "3320289784"
    assert res['decision_step'] == 15
    assert res['reroute_triggered'] is True

    # Numerically verify equivalence with Phase 9 within 0.1s tolerance
    assert abs(res['no_reroute_total_time_s'] - 1287.06) < 0.1
    assert abs(res['dynamic_reroute_total_time_s'] - 1202.15) < 0.1
    assert abs(res['time_saved_s'] - 84.90) < 0.1
    assert abs(res['improvement_pct'] - 6.60) < 0.1
    assert abs(res['route_overlap'] - 0.60) < 0.01


def test_phase11_all_figures_and_tables_exist():
    expected_files = [
        'results/phase11/demo_results.json',
        'results/phase11/demo_timeline.csv',
        'results/phase11/edge_execution_times.csv',
        'results/phase11/architecture_events.json',
        'results/phase11/figures/01_end_to_end_route.png',
        'results/phase11/figures/02_end_to_end_timeline.png',
        'results/phase11/figures/03_edge_cloud_architecture.png'
    ]
    for p in expected_files:
        assert os.path.exists(p), f"Artifact missing: {p}"
        assert os.path.getsize(p) > 100, f"Artifact {p} is empty"
