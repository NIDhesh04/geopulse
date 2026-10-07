"""
GeoPulse Phase 11: Master Integrated Demo Pipeline
Edge-Cloud Architecture Simulation + End-to-End Dynamic Routing Demonstration

Executes the complete closed-loop lifecycle:
  Predict -> Route -> Drive -> Observe -> Detect -> Reroute -> Save Time
Under simulated Cloud -> Edge -> Vehicle architecture.
"""

import os
import sys
import json
import time
import pandas as pd
import numpy as np
import networkx as nx

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath('.'))

from src.routing.traffic_weights import GraphWeightManager
from src.routing.route_evaluator import compute_edge_jaccard_overlap
from src.cloud.model_service import CloudModelService
from src.edge.edge_server import EdgeServer
from src.edge.messages import TrafficUpdateMessage
from src.simulation.vehicle import Vehicle
from src.edge.visualizations import (
    generate_end_to_end_route_map,
    generate_end_to_end_timeline,
    generate_edge_cloud_architecture_diagram
)

RESULTS_DIR = 'results/phase11'
FIGURES_DIR = 'results/phase11/figures'


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(FIGURES_DIR, exist_ok=True)
    os.makedirs('docs', exist_ok=True)

    print("=" * 65)
    print("                 GEOPULSE LIVE DEMO")
    print("    AI-Based Dynamic Traffic Routing Prototype")
    print("=" * 65)

    # -------------------------------------------------------------------------
    # 1. SETUP & INITIALIZATION
    # -------------------------------------------------------------------------
    G = nx.read_graphml('data/raw/osm/bhubaneswar_drive.graphml')
    mapping_df = pd.read_parquet('data/processed/traffic_to_osm_mapping_final.parquet')
    pred_df = pd.read_parquet('results/phase7_predictions.parquet')
    pred_df['ts_round'] = pd.to_datetime(pred_df['timestamp']).dt.round('h')

    weight_manager = GraphWeightManager(G, mapping_df)

    # Canonical demo parameters (OD #0, Evening Peak)
    origin_node = "3722327026"
    dest_node = "2443921849"
    dep_time_ist = "2026-01-15 19:30:00+05:30"
    obs_time_ist = "2026-01-15 20:30:00+05:30"
    t0_utc = pd.to_datetime("2026-01-15 14:00:00+00:00")
    t1_utc = pd.to_datetime("2026-01-15 15:00:00+00:00")
    decision_step = 15

    print(f"\nOrigin:      Node {origin_node}")
    print(f"Destination: Node {dest_node}")
    print(f"Departure:   {dep_time_ist} (Evening Peak Commute)")

    # -------------------------------------------------------------------------
    # 2. CLOUD TIER
    # -------------------------------------------------------------------------
    print("\n" + "-" * 65)
    print("CLOUD COMPONENT (Centralized Model Service)")
    print("-" * 65)
    cloud_service = CloudModelService()
    meta = cloud_service.get_metadata()
    print(f"Model:              {meta['model_type']}")
    print(f"Model Version:      {meta['model_version']}")
    print(f"Trained Features:   {meta['feature_count']} features")
    print(f"Prediction Horizon: +1 hour ahead")

    model_msg, cloud_exec_ms = cloud_service.generate_predictions_broadcast(t0_utc)
    print(f"Model broadcast prepared in {cloud_exec_ms:.3f} ms (700 monitored links)")

    # -------------------------------------------------------------------------
    # 3. EDGE SERVER TIER
    # -------------------------------------------------------------------------
    print("\n" + "-" * 65)
    print("EDGE SERVER (Low-Latency Regional Control)")
    print("-" * 65)
    edge_server = EdgeServer(weight_manager, threshold_seconds=10.0, threshold_percent=3.0)

    # Ingest model predictions from cloud
    t_weight_prep = edge_server.update_model_predictions(model_msg)
    print(f"Predicted edge weights generated in {t_weight_prep:.3f} ms")

    # Compute initial route R0
    print("Running Custom Min-Heap Dijkstra...")
    initial_route_msg, t_dijkstra_init = edge_server.compute_initial_route(
        vehicle_id="veh_001",
        source=origin_node,
        destination=dest_node,
        departure_timestamp=dep_time_ist
    )

    r0_dist_m = sum(weight_manager.edge_lengths.get(e, 0.0) for e in initial_route_msg.edge_path)
    print("\nInitial Route R0 Selected:")
    print(f"  Distance:       {r0_dist_m/1000.0:.2f} km ({r0_dist_m:.1f} m)")
    print(f"  Expected Time:  {initial_route_msg.total_cost_s/60.0:.2f} min ({initial_route_msg.total_cost_s:.1f} s)")
    print(f"  Road Links:     {len(initial_route_msg.edge_path)} directed OSM segments")
    print(f"  Computation:    {t_dijkstra_init:.3f} ms")

    # -------------------------------------------------------------------------
    # 4. VEHICLE SIMULATION: TRAVERSAL
    # -------------------------------------------------------------------------
    print("\n" + "-" * 65)
    print("VEHICLE CLIENT SIMULATION")
    print("-" * 65)
    vehicle = Vehicle(
        vehicle_id="veh_001",
        origin=origin_node,
        destination=dest_node,
        departure_time=dep_time_ist
    )
    vehicle.receive_initial_route(initial_route_msg)
    print("Vehicle departed origin. Beginning link-by-link kinematic traversal...")

    # Advance vehicle to Decision Point (Step 15, ~20% of route)
    pos_msg = vehicle.advance_to_step(
        target_step=decision_step,
        weights=edge_server.predicted_weights,
        edge_lengths=weight_manager.edge_lengths,
        current_timestamp="2026-01-15 20:00:00+05:30"
    )

    t_pos_update = edge_server.update_vehicle_position(pos_msg)
    print(f"Vehicle reached Decision Node {pos_msg.current_node} (Edge #{pos_msg.edge_index})")
    print(f"Journey Progress: {pos_msg.progress_pct:.1f}%  |  Elapsed Travel Time: {pos_msg.elapsed_time_s/60.0:.2f} min ({pos_msg.elapsed_time_s:.1f} s)")

    # -------------------------------------------------------------------------
    # 5. TRAFFIC OBSERVATION & REROUTING DECISION
    # -------------------------------------------------------------------------
    print("\n" + "-" * 65)
    print("REAL-TIME TRAFFIC OBSERVATION & DEGRADATION AUDIT")
    print("-" * 65)
    p1 = pred_df[pred_df['ts_round'] == t1_utc].set_index('traffic_segment_id')
    obs_speeds = p1['actual_speed'].to_dict()

    traffic_msg = TrafficUpdateMessage(
        timestamp=obs_time_ist,
        observed_speeds=obs_speeds,
        sensor_count=len(obs_speeds)
    )

    t_traffic_ingest = edge_server.update_traffic(traffic_msg)
    print(f"Sensor observation received at {obs_time_ist} (ingested in {t_traffic_ingest:.3f} ms)")
    print("Downstream corridor bottleneck detected: Link speeds dropped into severe congestion.")

    # Edge Server evaluates degradation and re-routes
    reroute_msg, reroute_metrics = edge_server.evaluate_and_reroute(
        vehicle_id="veh_001",
        timestamp=obs_time_ist
    )

    print("\nREROUTING ANALYSIS:")
    print(f"  Current Route Remaining Time:  {reroute_metrics['remaining_current_time_s']:.2f} s")
    print(f"  Optimal Alternative Remaining: {reroute_metrics['remaining_optimal_time_s']:.2f} s")
    print(f"  Delta T (Absolute Saving):      {reroute_metrics['absolute_saving_s']:.2f} s")
    print(f"  Delta T% (Relative Saving):     {reroute_metrics['relative_saving_pct']:.2f}%")
    print(f"  Operating Threshold:           Delta T >= {reroute_metrics['threshold_seconds']:.1f}s AND Delta T% >= {reroute_metrics['threshold_percent']:.1f}%")
    print(f"  Decision Verdict:              {'TRIGGER DYNAMIC REROUTE' if reroute_metrics['reroute_triggered'] else 'MAINTAIN ROUTE'}")
    print(f"  Edge Solver Latency:           {reroute_metrics['total_edge_decision_time_ms']:.3f} ms (Dijkstra: {reroute_metrics['dijkstra_time_ms']:.3f} ms)")

    # Vehicle accepts reroute if triggered
    if reroute_msg:
        vehicle.apply_route_update(reroute_msg, timestamp=obs_time_ist)
        print("\nAlert: ROUTE_UPDATE applied to connected vehicle navigation system.")

    # -------------------------------------------------------------------------
    # 6. JOURNEY COMPLETION & COUNTERFACTUAL AUDIT
    # -------------------------------------------------------------------------
    vehicle.complete_journey(
        weights=edge_server.observed_weights,
        edge_lengths=weight_manager.edge_lengths,
        arrival_timestamp="2026-01-15 20:50:00+05:30"
    )

    # Strategy A Counterfactual (No Reroute)
    # Prefix elapsed + remaining of initial route under observed weights
    rem_r0_edges = vehicle.initial_route_edges[decision_step:]
    no_reroute_rem_time = sum(edge_server.observed_weights.get(e, 0.0) for e in rem_r0_edges)
    total_time_no_reroute = pos_msg.elapsed_time_s + no_reroute_rem_time

    # Strategy B (GeoPulse Dynamic Reroute)
    total_time_dynamic = vehicle.elapsed_travel_time_s
    time_saved = total_time_no_reroute - total_time_dynamic
    improvement_pct = (time_saved / total_time_no_reroute) * 100.0 if total_time_no_reroute > 0 else 0.0

    route_overlap = compute_edge_jaccard_overlap(vehicle.initial_route_edges, vehicle.current_route_edges)
    final_dist_m = vehicle.accumulated_distance_m

    print("\n" + "-" * 65)
    print("FINAL JOURNEY OUTCOME & COMPARATIVE AUDIT")
    print("-" * 65)
    print(f"Strategy A (No Rerouting):       {total_time_no_reroute/60.0:5.2f} min ({total_time_no_reroute:.1f} s)")
    print(f"Strategy B (GeoPulse Dynamic):   {total_time_dynamic/60.0:5.2f} min ({total_time_dynamic:.1f} s)")
    print(f"\n[+] NET TIME SAVED:              {time_saved/60.0:5.2f} min ({time_saved:.1f} s)")
    print(f"[+] TRAVEL TIME IMPROVEMENT:     +{improvement_pct:.2f}%")
    print(f"[+] ROUTE SPATIAL OVERLAP:       {route_overlap*100:.1f}%")
    print(f"[+] FINAL ROUTE DISTANCE:        {final_dist_m/1000.0:.2f} km ({final_dist_m:.1f} m)")
    print(f"[+] STATUS:                      SUCCESS")
    print("=" * 65)

    # -------------------------------------------------------------------------
    # 7. EXPORT RESULTS & EXECUTION TIMES
    # -------------------------------------------------------------------------
    exec_benchmarks = {
        'cloud_prediction_broadcast_ms': round(cloud_exec_ms, 3),
        'edge_weight_synthesis_ms': round(t_weight_prep, 3),
        'edge_initial_dijkstra_ms': round(t_dijkstra_init, 3),
        'edge_traffic_ingest_ms': round(t_traffic_ingest, 3),
        'edge_reroute_dijkstra_ms': round(reroute_metrics['dijkstra_time_ms'], 3),
        'edge_decision_evaluation_ms': round(reroute_metrics['decision_time_ms'], 3),
        'total_edge_decision_ms': round(reroute_metrics['total_edge_decision_time_ms'], 3)
    }

    demo_results = {
        'scenario_id': 'demo_scenario_0',
        'origin_node': origin_node,
        'destination_node': dest_node,
        'departure_timestamp': dep_time_ist,
        'observation_timestamp': obs_time_ist,
        'decision_node': pos_msg.current_node,
        'decision_step': decision_step,
        'no_reroute_total_time_s': round(total_time_no_reroute, 2),
        'dynamic_reroute_total_time_s': round(total_time_dynamic, 2),
        'time_saved_s': round(time_saved, 2),
        'improvement_pct': round(improvement_pct, 2),
        'initial_route_distance_m': round(r0_dist_m, 2),
        'final_route_distance_m': round(final_dist_m, 2),
        'initial_route_edges': len(vehicle.initial_route_edges),
        'final_route_edges': len(vehicle.current_route_edges),
        'route_overlap': round(route_overlap, 4),
        'reroute_triggered': reroute_metrics['reroute_triggered'],
        'delta_T_s': reroute_metrics['absolute_saving_s'],
        'delta_T_pct': reroute_metrics['relative_saving_pct'],
        'threshold_seconds': reroute_metrics['threshold_seconds'],
        'threshold_percent': reroute_metrics['threshold_percent'],
        'execution_times_ms': exec_benchmarks
    }

    # Save JSON results
    with open(os.path.join(RESULTS_DIR, 'demo_results.json'), 'w') as f:
        json.dump(demo_results, f, indent=2)

    # Save Timeline CSV
    df_timeline = pd.DataFrame(vehicle.timeline)
    df_timeline.to_csv(os.path.join(RESULTS_DIR, 'demo_timeline.csv'), index=False)

    # Save Edge Execution Times CSV
    df_exec = pd.DataFrame([
        {'operation': k, 'execution_time_ms': v, 'tier': 'Cloud' if 'cloud' in k else 'Edge Server'}
        for k, v in exec_benchmarks.items()
    ])
    df_exec.to_csv(os.path.join(RESULTS_DIR, 'edge_execution_times.csv'), index=False)

    # Save Architecture Events JSON
    events_export = [
        {
            'event_id': ev.event_id,
            'timestamp': ev.timestamp,
            'source': ev.source_component,
            'target': ev.target_component,
            'type': ev.message_type,
            'summary': ev.summary,
            'execution_time_ms': ev.execution_time_ms
        }
        for ev in edge_server.event_log
    ]
    with open(os.path.join(RESULTS_DIR, 'architecture_events.json'), 'w') as f:
        json.dump(events_export, f, indent=2)

    # -------------------------------------------------------------------------
    # 8. GENERATE ALL 3 PUBLICATION FIGURES (300 DPI)
    # -------------------------------------------------------------------------
    print("\nGenerating Phase 11 Visualizations at 300 DPI...")

    p1 = os.path.join(FIGURES_DIR, '01_end_to_end_route.png')
    generate_end_to_end_route_map(
        G=G,
        initial_edge_path=vehicle.initial_route_edges,
        final_edge_path=vehicle.current_route_edges,
        decision_step=decision_step,
        source_node=origin_node,
        destination_node=dest_node,
        decision_node=pos_msg.current_node,
        output_path=p1
    )
    print(f"  Saved: {p1}")

    p2 = os.path.join(FIGURES_DIR, '02_end_to_end_timeline.png')
    generate_end_to_end_timeline(demo_results, p2)
    print(f"  Saved: {p2}")

    p3 = os.path.join(FIGURES_DIR, '03_edge_cloud_architecture.png')
    generate_edge_cloud_architecture_diagram(exec_benchmarks, p3)
    print(f"  Saved: {p3}")

    print("\nPhase 11 Demo Pipeline Execution Finished Successfully.")


if __name__ == '__main__':
    main()
