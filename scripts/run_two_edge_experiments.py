"""
GeoPulse Master Two-Edge Experimental Suite & Benchmark Script

Executes all 8 formal research experiments and generates publication figures.
Usage:
    python scripts/run_two_edge_experiments.py
"""

import os
import sys
import time
import pandas as pd
import networkx as nx

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath('.'))

from src.routing.traffic_weights import GraphWeightManager
from src.experiments.benchmark_runner import ExperimentalBenchmark
from src.experiments.visualizations import generate_all_figures


def main():
    print("=" * 70)
    print("      GEOPULSE MASTER SEQUENTIAL ROUTING EXPERIMENTAL SUITE")
    print("=" * 70)

    # 1. Load Road Graph and Mapping
    print("\n[Step 1/5] Loading Bhubaneswar OSM Road Network...")
    graph_path = 'data/raw/osm/bhubaneswar_drive.graphml'
    mapping_path = 'data/processed/traffic_to_osm_mapping_final.parquet'

    G = nx.read_graphml(graph_path)
    mapping_df = pd.read_parquet(mapping_path)
    weight_manager = GraphWeightManager(G, mapping_df)
    print(f"Loaded road graph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} directed edges.")

    # 2. Load ML Predictions and Observed Speeds
    print("\n[Step 2/5] Loading LightGBM Predictions & Ground-Truth Telemetry...")
    pred_path = 'results/phase7_predictions.parquet'
    pred_df = pd.read_parquet(pred_path)
    pred_df['ts_round'] = pd.to_datetime(pred_df['timestamp']).dt.round('h')

    # Canonical evaluation timestamp (Evening Peak: 2026-01-15 19:30 IST / 14:00 UTC)
    canonical_ts = pd.to_datetime('2026-01-15 14:00:00+00:00')
    sub_pred = pred_df[pred_df['ts_round'] == canonical_ts]
    if len(sub_pred) == 0:
        sub_pred = pred_df.head(700)

    pred_speeds = dict(zip(sub_pred['traffic_segment_id'], sub_pred['predicted_speed']))
    obs_speeds = dict(zip(sub_pred['traffic_segment_id'], sub_pred['actual_speed']))

    # Synthesize scenario weights
    w_pred, _, _ = weight_manager.build_scenario_weights(pred_speeds)
    w_obs, _, _ = weight_manager.build_scenario_weights(obs_speeds)

    # 3. Select Representative OD Pairs
    print("\n[Step 3/5] Sampling Representative Origin-Destination Corridors...")
    od_path = 'results/phase8_od_pairs.csv'
    od_df = pd.read_csv(od_path)

    # Select canonical ODs spanning Short, Medium, Long distances
    selected_ods = [
        (str(int(od_df.iloc[0]['source_node'])), str(int(od_df.iloc[0]['destination_node']))),  # OD 0 (Canonical 10.9km)
        (str(int(od_df.iloc[1]['source_node'])), str(int(od_df.iloc[1]['destination_node']))),  # OD 1 (Short 3.4km)
        (str(int(od_df.iloc[6]['source_node'])), str(int(od_df.iloc[6]['destination_node']))),  # OD 6 (Medium 2.5km)
        (str(int(od_df.iloc[8]['source_node'])), str(int(od_df.iloc[8]['destination_node']))),  # OD 8 (Arterial 4.9km)
    ]
    print(f"Sampled {len(selected_ods)} evaluation corridors for multi-algorithm benchmarking.")

    # 4. Run Benchmark Suite
    print("\n[Step 4/5] Executing Controlled Experiments 1 through 8...")
    benchmark = ExperimentalBenchmark(weight_manager, output_dir="results/two_edge_experiments")

    t_start = time.perf_counter()
    df_exp1 = benchmark.run_experiment_1_candidate_generation(selected_ods, w_pred)
    df_exp2 = benchmark.run_experiment_2_decision_strategies(selected_ods, w_pred)
    df_exp3 = benchmark.run_experiment_3_lookahead_depth(selected_ods, w_pred)
    df_exp4 = benchmark.run_experiment_4_dynamic_traffic(selected_ods, w_pred)
    df_exp5 = benchmark.run_experiment_5_threshold_sensitivity(selected_ods, w_pred)
    df_master = benchmark.run_master_algorithm_comparison(selected_ods, w_pred, w_obs)
    t_total = time.perf_counter() - t_start
    print(f"All experiments completed in {t_total:.2f} seconds.")

    # 5. Generate Visual Analytics Figures
    print("\n[Step 5/5] Generating Publication-Ready Figures...")
    generate_all_figures(output_dir="results/two_edge_experiments")

    # Summary Report Table
    print("\n" + "=" * 70)
    print("                    MASTER ALGORITHM SUMMARY RESULTS")
    print("=" * 70)
    summary_table = df_master.groupby('algorithm').agg({
        'actual_travel_time_s': 'mean',
        'distance_m': 'mean',
        'computation_time_ms': 'mean',
        'avg_decision_latency_ms': 'mean',
        'recovery_events': 'sum',
        'reroutes_count': 'sum'
    }).reset_index()

    print(summary_table.to_string(index=False))
    print("\nArtifacts and figures saved in results/two_edge_experiments/")


if __name__ == "__main__":
    main()
