"""
GeoPulse Phase 10: Master Ablation & Robustness Evaluation Pipeline

Executes the complete experimental suite:
  - Experiment A: Routing Strategy Ablation (Static vs Persistence vs Historical vs LightGBM vs Current Oracle)
  - Experiment B: Dynamic Rerouting Policy Ablation (Threshold gating policies)
  - Experiment C: 2D Threshold Sensitivity Grid Analysis
  - Experiment D: Robustness by Diurnal Time Period
  - Experiment E: Robustness by Route Distance Bins
  - Experiment F: Robustness by Network Congestion Tertiles
  - Experiment G: Prediction Error vs Routing Outcome Correlation
  - Statistical Hypothesis Testing (Paired t-tests, Wilcoxon signed-rank tests, 95% CIs)
  - Automated Data Leakage & Lookahead Audit
  - 10 Publication-Grade Visualizations (300 DPI)
"""

import os
import sys
import time
import json
import pandas as pd
import numpy as np
import networkx as nx

# Ensure root in import path
sys.path.insert(0, os.path.abspath('.'))

from src.routing.traffic_weights import GraphWeightManager
from src.phase10.experiment_config import (
    RESULTS_DIR, FIGURES_DIR, GRAPH_PATH, MAPPING_PARQUET,
    PHASE7_PREDICTIONS_PARQUET, PHASE8_OD_PAIRS_CSV,
    PHASE8_TIMESTAMPS_CSV, PHASE9_REPLAY_PARQUET
)
from src.phase10.routing_ablation import run_routing_strategy_ablation
from src.phase10.rerouting_ablation import run_dynamic_rerouting_ablation
from src.phase10.threshold_sensitivity import run_threshold_sensitivity_grid
from src.phase10.robustness import (
    analyze_robustness_by_time_period,
    analyze_robustness_by_route_length,
    analyze_robustness_by_congestion_condition
)
from src.phase10.prediction_error_analysis import analyze_prediction_error_vs_routing
from src.phase10.statistical_analysis import run_all_statistical_tests
from src.phase10.leakage_check import perform_data_leakage_audit
from src.phase10.visualizations import generate_all_phase10_figures


def main():
    print("=" * 75)
    print("GeoPulse Phase 10: Ablation & Robustness Evaluation Pipeline")
    print("=" * 75)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(FIGURES_DIR, exist_ok=True)
    os.makedirs('docs', exist_ok=True)

    # -------------------------------------------------------------------------
    # 1. LOAD ARTIFACTS
    # -------------------------------------------------------------------------
    print("\n[Step 1/9] Loading road graph, mapping, and historical test telemetry...")
    t0_load = time.time()
    G = nx.read_graphml(GRAPH_PATH)
    mapping_df = pd.read_parquet(MAPPING_PARQUET)
    pred_df = pd.read_parquet(PHASE7_PREDICTIONS_PARQUET)
    od_df = pd.read_csv(PHASE8_OD_PAIRS_CSV)
    eval_ts_df = pd.read_csv(PHASE8_TIMESTAMPS_CSV)
    replay_df = pd.read_parquet(PHASE9_REPLAY_PARQUET)

    weight_manager = GraphWeightManager(G, mapping_df)
    print(f"Loaded road network ({G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges) in {time.time()-t0_load:.2f}s")
    print(f"Evaluation set: {len(od_df)} OD pairs x {len(eval_ts_df)} timestamps = {len(od_df)*len(eval_ts_df)} runs")

    # -------------------------------------------------------------------------
    # 2. EXPERIMENT A: ROUTING STRATEGY ABLATION
    # -------------------------------------------------------------------------
    print("\n[Step 2/9] Executing Experiment A: Routing Strategy Ablation (5 Strategies x 800 Runs)...")
    t0_exp_a = time.time()
    ablation_pq_path = os.path.join(RESULTS_DIR, 'routing_strategy_ablation.parquet')
    summary_csv_path = os.path.join(RESULTS_DIR, 'routing_strategy_summary.csv')
    if os.path.exists(ablation_pq_path) and os.path.exists(summary_csv_path) and ('--force-recompute' not in sys.argv):
        print("  [Cache Hit] Loading precomputed Experiment A evaluation runs (800 rows)...")
        df_runs = pd.read_parquet(ablation_pq_path)
        df_summary = pd.read_csv(summary_csv_path)
    else:
        df_runs, df_summary = run_routing_strategy_ablation(weight_manager, pred_df, od_df, eval_ts_df)
        df_runs.to_parquet(ablation_pq_path, index=False)
        df_runs.to_csv(os.path.join(RESULTS_DIR, 'routing_strategy_ablation.csv'), index=False)
        df_summary.to_csv(summary_csv_path, index=False)
        with open(os.path.join(RESULTS_DIR, 'routing_strategy_summary.json'), 'w') as f:
            json.dump(df_summary.to_dict(orient='records'), f, indent=2)

    print(f"Experiment A completed in {time.time()-t0_exp_a:.2f}s.")
    print("Strategy Summary:")
    for _, r in df_summary.iterrows():
        print(f"  {r['strategy']:24s} | Mean Time: {r['mean_travel_time_s']:7.2f}s | Sav vs Stat: +{r['mean_saving_vs_static_s']:5.2f}s | Win%: {r['win_rate_vs_static_pct']:5.1f}% | Regret: {r['mean_oracle_regret_s']:5.2f}s")

    # -------------------------------------------------------------------------
    # 3. EXPERIMENT B: DYNAMIC REROUTING ABLATION
    # -------------------------------------------------------------------------
    print("\n[Step 3/9] Executing Experiment B: Dynamic Rerouting Policy Ablation...")
    t0_exp_b = time.time()
    df_reroute = run_dynamic_rerouting_ablation(replay_df)

    df_reroute.to_parquet(os.path.join(RESULTS_DIR, 'dynamic_rerouting_ablation.parquet'), index=False)
    df_reroute.to_csv(os.path.join(RESULTS_DIR, 'dynamic_rerouting_ablation.csv'), index=False)

    print(f"Experiment B completed in {time.time()-t0_exp_b:.2f}s.")
    for _, r in df_reroute.iterrows():
        print(f"  {r['policy']:36s} | Trig%: {r['reroute_frequency_pct']:5.1f}% | Sav: {r['mean_saving_seconds_overall']:5.2f}s | BenRate: {r['beneficial_reroute_rate_pct']:5.1f}%")

    # -------------------------------------------------------------------------
    # 4. EXPERIMENT C: THRESHOLD SENSITIVITY GRID
    # -------------------------------------------------------------------------
    print("\n[Step 4/9] Executing Experiment C: 2D Threshold Sensitivity Grid Analysis...")
    t0_exp_c = time.time()
    df_grid = run_threshold_sensitivity_grid(replay_df)
    df_grid.to_csv(os.path.join(RESULTS_DIR, 'threshold_sensitivity.csv'), index=False)
    print(f"Experiment C completed ({len(df_grid)} parameter combinations evaluated) in {time.time()-t0_exp_c:.2f}s.")

    # -------------------------------------------------------------------------
    # 5. EXPERIMENTS D, E, F: ROBUSTNESS EVALUATION
    # -------------------------------------------------------------------------
    print("\n[Step 5/9] Executing Experiments D, E, F: Diurnal Periods, Route Lengths, Congestion Tertiles...")
    t0_exp_d = time.time()
    df_period = analyze_robustness_by_time_period(df_runs, replay_df)
    df_length = analyze_robustness_by_route_length(df_runs, replay_df)
    df_congestion = analyze_robustness_by_congestion_condition(df_runs, pred_df)

    df_period.to_csv(os.path.join(RESULTS_DIR, 'time_period_robustness.csv'), index=False)
    df_length.to_csv(os.path.join(RESULTS_DIR, 'route_length_robustness.csv'), index=False)
    df_congestion.to_csv(os.path.join(RESULTS_DIR, 'congestion_condition_robustness.csv'), index=False)

    print(f"Robustness evaluations completed in {time.time()-t0_exp_d:.2f}s.")
    print("Period Breakdown:")
    for _, r in df_period.iterrows():
        print(f"  {r['period']:14s} | Runs: {r['evaluation_count']:3d} | Sav: +{r['mean_saving_vs_static_s']:5.2f}s | Win%: {r['win_rate_vs_static_pct']:5.1f}% | Regret: {r['mean_oracle_regret_s']:5.2f}s")

    # -------------------------------------------------------------------------
    # 6. EXPERIMENT G: PREDICTION ERROR VS ROUTING GAIN
    # -------------------------------------------------------------------------
    print("\n[Step 6/9] Executing Experiment G: Prediction Error vs Routing Performance Analysis...")
    t0_exp_g = time.time()
    df_pred_analysis, df_corr = analyze_prediction_error_vs_routing(df_runs, pred_df, replay_df)

    df_pred_analysis.to_csv(os.path.join(RESULTS_DIR, 'prediction_error_routing_analysis.csv'), index=False)
    df_corr.to_csv(os.path.join(RESULTS_DIR, 'prediction_error_correlations.csv'), index=False)

    print(f"Experiment G completed in {time.time()-t0_exp_g:.2f}s.")
    print("Key Statistical Correlations:")
    for _, r in df_corr.iterrows():
        print(f"  {r['variable_x']:28s} vs {r['variable_y']:28s} | Pearson r = {r['pearson_r']:+6.4f} (p={r['pearson_p_value']}) | Spearman rho = {r['spearman_rho']:+6.4f}")

    # -------------------------------------------------------------------------
    # 7. STATISTICAL HYPOTHESIS TESTING
    # -------------------------------------------------------------------------
    print("\n[Step 7/9] Running Statistical Hypothesis Testing Battery (Section 13)...")
    t0_exp_stat = time.time()
    df_stats = run_all_statistical_tests(df_runs, replay_df)
    df_stats.to_csv(os.path.join(RESULTS_DIR, 'statistical_tests.csv'), index=False)

    print(f"Statistical battery completed in {time.time()-t0_exp_stat:.2f}s.")
    for _, r in df_stats.iterrows():
        print(f"  {r['comparison']:34s} | Diff: +{r['mean_difference_s']:5.2f}s | t={r['paired_t_statistic']:6.2f} (p={r['paired_t_p_value']}) | W={r['wilcoxon_w_statistic']} (p={r['wilcoxon_p_value']}) | {r['significance_verdict']}")

    # -------------------------------------------------------------------------
    # 8. AUTOMATED DATA LEAKAGE AUDIT
    # -------------------------------------------------------------------------
    print("\n[Step 8/9] Executing Automated Data Leakage & Lookahead Audit (Section 14)...")
    leak_results = perform_data_leakage_audit()
    with open(os.path.join(RESULTS_DIR, 'data_leakage_audit.json'), 'w') as f:
        json.dump(leak_results, f, indent=2)

    print(f"Data Leakage Audit Status: {leak_results['overall_leakage_audit_status']}")
    for k, v in leak_results.items():
        if isinstance(v, dict):
            print(f"  {k:35s}: [{v['status']}] {v['details']}")

    # -------------------------------------------------------------------------
    # 9. GENERATE ALL 10 FIGURES
    # -------------------------------------------------------------------------
    print("\n[Step 9/9] Generating All 10 Publication-Grade Figures at 300 DPI (Section 16)...")
    t0_viz = time.time()
    fig_paths = generate_all_phase10_figures(
        df_runs=df_runs,
        df_summary=df_summary,
        df_reroute=df_reroute,
        df_grid=df_grid,
        df_period=df_period,
        df_length=df_length,
        df_pred_analysis=df_pred_analysis,
        output_dir=FIGURES_DIR
    )
    print(f"Generated {len(fig_paths)} presentation figures in {time.time()-t0_viz:.2f}s.")
    for k, p in fig_paths.items():
        print(f"  {k}: {p}")

    print("\n" + "=" * 75)
    print("PHASE 10 PIPELINE EXECUTION COMPLETED SUCCESSFULLY!")
    print("=" * 75)


if __name__ == '__main__':
    main()
