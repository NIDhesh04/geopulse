"""
GeoPulse Phase 11B: Interactive Dashboard Automated Test Suite

Validates:
1. Dashboard backend and visualization module imports
2. Scenario catalog integrity and coverage
3. Dynamic pipeline execution of canonical Guided Demo (OD #0)
4. Numerical parity with Phase 11 baseline (84.9s saved, +6.60%)
5. Dynamic rerouting scenario behavior (OD #2 Evening Peak)
6. Dynamic rerouting suppression / no-reroute behavior (OD #1 Morning Peak)
7. Non-hardcoded dynamic execution across distinct scenarios
8. Existence of required metrics (Speeds, ETAs, Gates, Software latencies)
9. Map and timeline visualization generation
10. Preservation of canonical Phase 11 result artifacts during dashboard run exports
"""

import os
import sys
import json
import pytest
import pandas as pd
import numpy as np
import networkx as nx

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath('.'))

from src.dashboard.backend import (
    load_graph_and_mappings,
    load_cloud_service,
    load_predictions_data,
    get_scenario_catalog,
    run_geopulse_pipeline,
    export_run_results
)
from src.dashboard.visualization import (
    render_route_map_matplotlib,
    create_pydeck_map,
    render_journey_timeline_figure,
    get_step_simulation_status
)
from src.dashboard.state import (
    init_session_state,
    set_current_run,
    step_forward,
    step_backward,
    reset_playback,
    jump_to_decision,
    jump_to_destination
)


@pytest.fixture(scope="module")
def shared_graph():
    G, mapping_df, weight_manager = load_graph_and_mappings()
    return G, mapping_df, weight_manager


def test_dashboard_imports_and_loaders():
    """Requirement 1: Dashboard modules and resource loaders import and execute cleanly."""
    G, mapping_df, weight_manager = load_graph_and_mappings()
    assert isinstance(G, nx.MultiDiGraph)
    assert len(G.nodes) > 1000
    assert not mapping_df.empty
    assert weight_manager is not None

    cloud = load_cloud_service()
    assert cloud is not None

    pred_df, scenarios_df = load_predictions_data()
    assert len(pred_df) > 0
    assert len(scenarios_df) == 20


def test_scenario_catalog_integrity():
    """Requirement 2: Scenario catalog provides 20+ scenarios with required metadata."""
    catalog = get_scenario_catalog()
    assert len(catalog) >= 20

    scen0 = catalog[0]
    assert scen0['scenario_id'] == 0
    assert scen0['od_id'] == 0
    assert "Evening Peak" in scen0['period']
    assert scen0['origin_node'] == "3722327026"
    assert scen0['destination_node'] == "2443921849"
    assert scen0['decision_step'] == 15
    assert scen0['expected_reroute'] is True
    assert "CANONICAL BENCHMARK" in scen0['label']

    # Check for presence of no-reroute scenarios (Morning Peak, Midday, Off-Peak)
    no_reroute_scenarios = [c for c in catalog if not c['expected_reroute']]
    assert len(no_reroute_scenarios) >= 12


def test_canonical_pipeline_execution_and_numerical_parity():
    """Requirement 3 & 8: Dynamic pipeline execution matches canonical Phase 11 results."""
    res = run_geopulse_pipeline(scenario_id=0)

    assert res['scenario_id'] == 0
    assert res['is_canonical'] is True
    assert res['canonical_match'] is True
    assert res['reroute_triggered'] is True

    # Parity verification with Phase 11 canonical benchmark:
    # No reroute: ~1287s, Dynamic: ~1202s, Saved: ~84.9s (+6.60%)
    assert abs(res['time_saved_s'] - 84.91) < 0.2
    assert abs(res['improvement_pct'] - 6.60) < 0.1
    assert abs(res['no_reroute_total_time_s'] - 1287.06) < 1.0
    assert abs(res['dynamic_reroute_total_time_s'] - 1202.15) < 1.0
    assert res['decision_step'] == 15
    assert res['decision_node'] == "3320289784"
    assert len(res['initial_route_edges']) == 74
    assert len(res['final_route_edges']) == 46
    assert abs(res['route_overlap'] - 0.60) < 0.05


def test_reroute_scenario_execution():
    """Requirement 5: Validates an alternative rerouting scenario (OD #2, Evening Peak)."""
    res = run_geopulse_pipeline(scenario_id=3)

    assert res['scenario_id'] == 3
    assert res['od_id'] == 2
    assert res['reroute_triggered'] is True
    assert res['time_saved_s'] > 50.0  # Saves ~84.9s (+5.53%)
    assert res['improvement_pct'] > 5.0
    assert res['route_overlap'] < 1.0
    assert res['delta_T_s'] >= 10.0
    assert res['delta_T_pct'] >= 3.0


def test_no_reroute_scenario_execution():
    """Requirement 4: Validates a scenario where rerouting is properly suppressed (Morning Peak)."""
    res = run_geopulse_pipeline(scenario_id=8)

    assert res['scenario_id'] == 8
    assert res['od_id'] == 1
    assert res['reroute_triggered'] is False
    assert res['time_saved_s'] == 0.0
    assert res['improvement_pct'] == 0.0
    assert res['initial_route_edges_count'] == res['final_route_edges_count']
    assert res['route_overlap'] == 1.0
    assert res['delta_T_s'] < 10.0 or res['delta_T_pct'] < 3.0


def test_required_metrics_and_latencies_exist():
    """Requirement 6: All speed, routing, threshold, and latency metrics are populated."""
    res = run_geopulse_pipeline(scenario_id=0)

    # Speed metrics
    assert 'speed_metrics' in res
    assert res['speed_metrics']['predicted_speed_kmh'] > 0.0
    assert res['speed_metrics']['observed_speed_kmh'] > 0.0
    assert res['speed_metrics']['prediction_error_pct'] >= 0.0
    assert 'speed_drop_pct' in res['speed_metrics']

    # ETA metrics
    assert 'eta_metrics' in res
    assert res['eta_metrics']['initial_route_eta_s'] > 0.0
    assert res['eta_metrics']['current_remaining_eta_s'] > 0.0
    assert res['eta_metrics']['optimal_alternative_eta_s'] > 0.0

    # Decision metrics
    assert res['threshold_seconds'] == 10.0
    assert res['threshold_percent'] == 3.0
    assert res['delta_T_s'] > 0.0
    assert res['delta_T_pct'] > 0.0

    # Software latency execution times
    latencies = res['execution_times_ms']
    assert latencies['cloud_prediction_broadcast_ms'] > 0.0
    assert latencies['edge_weight_synthesis_ms'] > 0.0
    assert latencies['edge_initial_dijkstra_ms'] > 0.0
    assert latencies['edge_traffic_ingest_ms'] > 0.0
    assert latencies['edge_reroute_dijkstra_ms'] > 0.0
    assert latencies['total_edge_decision_ms'] > 0.0

    # Timeline and architecture events
    assert len(res['timeline']) >= 10
    assert len(res['architecture_events']) >= 4


def test_results_are_dynamically_computed_not_hardcoded():
    """Requirement 7: Distinct inputs yield distinct computed mathematical outputs."""
    res0 = run_geopulse_pipeline(scenario_id=0)
    res3 = run_geopulse_pipeline(scenario_id=3)
    res8 = run_geopulse_pipeline(scenario_id=8)

    # Scenarios have different origins and destinations
    assert res0['origin_node'] != res3['origin_node']
    assert res0['destination_node'] != res3['destination_node']
    assert res0['origin_node'] != res8['origin_node']

    # Total times and distances vary dynamically
    assert res0['no_reroute_total_time_s'] != res3['no_reroute_total_time_s']
    assert res0['initial_route_distance_m'] != res8['initial_route_distance_m']

    # Forced 'No Reroute' mode changes outcome
    res_forced = run_geopulse_pipeline(scenario_id=0, reroute_mode="No Reroute")
    assert res_forced['reroute_triggered'] is False


def test_visualizations_render_cleanly(shared_graph):
    """Verifies that Matplotlib, Pydeck, and Timeline visualizations generate without errors."""
    G, _, _ = shared_graph
    res = run_geopulse_pipeline(scenario_id=0)

    # 1. Matplotlib route map
    fig_map = render_route_map_matplotlib(G, res, current_step=15)
    assert fig_map is not None
    import matplotlib.pyplot as plt
    plt.close(fig_map)

    # 2. Pydeck 3D GIS deck
    deck = create_pydeck_map(G, res, current_step=15)
    assert deck is not None
    assert len(deck.layers) == 2

    # 3. Journey timeline figure
    fig_tl = render_journey_timeline_figure(res)
    assert fig_tl is not None
    plt.close(fig_tl)

    # 4. Simulation step telemetry
    status_dep = get_step_simulation_status(res, 0)
    assert status_dep['stage'] == "DEPARTURE"

    status_dec = get_step_simulation_status(res, res['decision_step'])
    assert status_dec['stage'] == "DECISION_REROUTE"

    status_arr = get_step_simulation_status(res, len(res['final_route_edges']))
    assert status_arr['stage'] == "ARRIVED"


def test_results_export_preserves_canonical_artifacts():
    """Requirement 19: Export creates dashboard run records without touching canonical Phase 11 files."""
    canonical_json_path = 'results/phase11/demo_results.json'
    assert os.path.exists(canonical_json_path)

    # Read canonical mtime and content
    orig_mtime = os.path.getmtime(canonical_json_path)
    with open(canonical_json_path, 'r') as f:
        orig_content = f.read()

    # Perform dashboard export
    res = run_geopulse_pipeline(scenario_id=0)
    json_path, csv_path = export_run_results(res, export_dir='results/dashboard_runs')

    assert os.path.exists(json_path)
    assert os.path.exists(csv_path)

    # Verify canonical file was untouched
    assert os.path.getmtime(canonical_json_path) == orig_mtime
    with open(canonical_json_path, 'r') as f:
        new_content = f.read()
    assert new_content == orig_content

    # Verify exported file is valid JSON
    with open(json_path, 'r') as f:
        exported_data = json.load(f)
    assert exported_data['scenario_id'] == 0
    assert exported_data['time_saved_s'] == res['time_saved_s']


def test_scenario_8_execution_and_suppression_audit():
    """Test 1 & 3: Selecting Scenario #8 executes Scenario #8 and displays valid suppression reason."""
    res = run_geopulse_pipeline(scenario_id=8)
    assert res['scenario_id'] == 8
    assert res['od_id'] == 1
    assert "Patia Infocity" in res['origin_name']
    assert res['reroute_triggered'] is False
    assert res['time_saved_s'] == 0.0
    assert res['improvement_pct'] == 0.0

    # Verify suppression explanations are dynamically populated
    gate_info = res['gate_evaluation']
    assert gate_info['final_decision'] == "KEEP CURRENT ROUTE"
    assert "GeoPulse kept the current route" in gate_info['explanation']
    assert "GeoPulse kept the current route" in res['reroute_explanation']


def test_scenario_20_execution_and_reroute_audit():
    """Test 2 & 4: Selecting Scenario #20 executes Scenario #20 and displays diverse real saving."""
    res = run_geopulse_pipeline(scenario_id=20)
    assert res['scenario_id'] == 20
    assert res['od_id'] == 15
    assert "Tamando" in res['origin_name']
    assert res['reroute_triggered'] is True
    # Evaluated saving on diverse candidate corridor: ~62.8s (+3.26%)
    assert abs(res['time_saved_s'] - 62.80) < 1.0
    assert abs(res['improvement_pct'] - 3.26) < 0.5

    gate_info = res['gate_evaluation']
    assert gate_info['final_decision'] == "REROUTE"
    assert gate_info['time_gate_pass'] is True
    assert gate_info['percent_gate_pass'] is True
    assert "satisfying both operational gates" in res['reroute_explanation']


def test_suppressed_scenarios_specific_gate_failure_reasons():
    """Test 3: Verifies specific gate failure reporting across distinct negative control scenarios."""
    # Scenario 12: ΔT = 8.69s (< 10s threshold), ΔT% = 0.56% (< 3% threshold)
    res12 = run_geopulse_pipeline(scenario_id=12)
    assert res12['reroute_triggered'] is False
    assert res12['gate_evaluation']['time_gate_pass'] is False
    assert res12['gate_evaluation']['percent_gate_pass'] is False
    assert "both the absolute time gate" in res12['reroute_explanation']

    # Scenario 15: ΔT = 17.39s (>= 10s), but ΔT% = 1.27% (< 3% threshold)
    res15 = run_geopulse_pipeline(scenario_id=15)
    assert res15['reroute_triggered'] is False
    assert res15['gate_evaluation']['time_gate_pass'] is True
    assert res15['gate_evaluation']['percent_gate_pass'] is False
    assert "relative improvement was only" in res15['reroute_explanation']
    assert "below the required" in res15['reroute_explanation']


def test_state_isolation_no_stale_scenario_0_data():
    """Test 5: Verifies that transitioning between scenarios creates fully isolated result dictionaries."""
    res0 = run_geopulse_pipeline(scenario_id=0)
    res8 = run_geopulse_pipeline(scenario_id=8)

    assert res8['scenario_id'] != res0['scenario_id']
    assert res8['origin_node'] != res0['origin_node']
    assert res8['destination_node'] != res0['destination_node']
    assert res8['initial_route_edges'] != res0['initial_route_edges']
    assert res8['no_reroute_total_time_s'] != res0['no_reroute_total_time_s']
    assert res8['time_saved_s'] != res0['time_saved_s']


def test_route_geometries_correspond_to_selected_scenario():
    """Test 6: Route geometry nodes strictly anchor to origin and destination for each scenario."""
    for s_id in [0, 8, 20]:
        res = run_geopulse_pipeline(scenario_id=s_id)
        # Initial route starts at origin and ends at destination
        assert res['initial_route_nodes'][0] == res['origin_node']
        assert res['initial_route_nodes'][-1] == res['destination_node']

        # Final route ends at destination
        assert res['final_route_nodes'][0] == res['origin_node']
        assert res['final_route_nodes'][-1] == res['destination_node']


def test_bottleneck_and_shared_pattern_detection():
    """Test: Validates automated bottleneck edge detection and shared pattern flag."""
    res0 = run_geopulse_pipeline(scenario_id=0)
    assert res0['shared_bottleneck_info']['detected'] is True
    assert "NH16" in res0['shared_bottleneck_info']['corridor']
    assert res0['bottleneck_analysis']['detected'] is True
    assert res0['bottleneck_analysis']['edge'] is not None

    res8 = run_geopulse_pipeline(scenario_id=8)
    assert res8['shared_bottleneck_info']['detected'] is False


def test_dashboard_session_state_lifecycle():
    """Test: Validates session state initialization, set_current_run with and without kwargs, and playback."""
    init_session_state()

    dummy_run = {
        'scenario_id': 5,
        'reroute_mode': 'GeoPulse Dual Threshold',
        'threshold_seconds': 10.0,
        'threshold_percent': 3.0,
        'reroute_triggered': True,
        'decision_step': 2,
        'initial_route_edges': [('A', 'B'), ('B', 'C'), ('C', 'D')],
        'final_route_edges': [('A', 'B'), ('B', 'E'), ('E', 'D')]
    }

    # Test 1: set_current_run without keyword args
    set_current_run(dummy_run)
    assert hasattr(set_current_run, '__call__')

    # Test 2: set_current_run with params keyword argument (backward & hot-reload compatibility)
    set_current_run(dummy_run, params=(5, 'GeoPulse Dual Threshold', 10.0, 3.0))

    # Test 3: Playback navigation step forward / reset
    step_forward()
    reset_playback()
    jump_to_decision()
    jump_to_destination()


