"""
GeoPulse Experimental Visualizations Module

Generates publication-ready figures for experimental validation:
1. 01_algorithm_travel_time_comparison.png
2. 02_candidate_generation_comparison.png
3. 03_lookahead_depth_latency_tradeoff.png
4. 04_dynamic_traffic_performance.png
5. 05_rerouting_threshold_surface.png
6. 06_robustness_and_recovery_summary.png
7. 07_optimality_gap_distribution.png
8. 08_master_experimental_summary.png
"""

import os
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np

# Set standard academic style
plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.size'] = 10
plt.rcParams['axes.titlesize'] = 12
plt.rcParams['axes.labelsize'] = 10


def generate_all_figures(output_dir: str = "results/two_edge_experiments"):
    """Generates all 8 formal research evaluation figures."""
    fig_dir = os.path.join(output_dir, "figures")
    os.makedirs(fig_dir, exist_ok=True)

    master_csv = os.path.join(output_dir, "master_algorithm_comparison.csv")
    exp1_csv = os.path.join(output_dir, "exp1_candidate_generation.csv")
    exp2_csv = os.path.join(output_dir, "exp2_decision_strategies.csv")
    exp3_csv = os.path.join(output_dir, "exp3_lookahead_depth.csv")
    exp4_csv = os.path.join(output_dir, "exp4_dynamic_traffic.csv")
    exp5_csv = os.path.join(output_dir, "exp5_threshold_sensitivity.csv")

    # -------------------------------------------------------------
    # Figure 1: 8-Algorithm Travel Time Comparison
    # -------------------------------------------------------------
    if os.path.exists(master_csv):
        df_master = pd.read_csv(master_csv)
        plt.figure(figsize=(10, 5))
        avg_tt = df_master.groupby('algorithm')['actual_travel_time_s'].mean().reset_index()
        avg_tt = avg_tt.sort_values('actual_travel_time_s')

        colors = ['#10b981' if 'Sequential' in a else '#6366f1' if 'Dijkstra' in a else '#f59e0b' for a in avg_tt['algorithm']]
        bars = plt.barh(avg_tt['algorithm'], avg_tt['actual_travel_time_s'], color=colors, edgecolor='none', height=0.6)
        plt.xlabel("Mean Actual Travel Time (seconds)")
        plt.title("Algorithm Comparison: Travel Time Performance Across Corridors", fontweight='bold')

        for bar in bars:
            w = bar.get_width()
            plt.text(w + 5, bar.get_y() + bar.get_height() / 2, f"{w:.1f}s", va='center', fontsize=9, fontweight='bold')

        plt.xlim(0, max(avg_tt['actual_travel_time_s']) * 1.15)
        plt.tight_layout()
        plt.savefig(os.path.join(fig_dir, "01_algorithm_travel_time_comparison.png"), dpi=300)
        plt.close()

    # -------------------------------------------------------------
    # Figure 2: Candidate Generation Strategies
    # -------------------------------------------------------------
    if os.path.exists(exp1_csv):
        df1 = pd.read_csv(exp1_csv)
        plt.figure(figsize=(8, 4.5))
        cand_summary = df1.groupby('candidate_strategy')['optimality_gap_pct'].mean().reset_index()

        palette = ['#ef4444', '#f59e0b', '#10b981', '#06b6d4']
        bars = plt.bar(cand_summary['candidate_strategy'], cand_summary['optimality_gap_pct'], color=palette, edgecolor='none', width=0.5)
        plt.ylabel("Mean Optimality Gap vs Dijkstra (%)")
        plt.xlabel("Candidate Generation Strategy")
        plt.title("Experiment 1: Candidate Generation Quality (Optimality Gap)", fontweight='bold')

        for bar in bars:
            h = bar.get_height()
            plt.text(bar.get_x() + bar.get_width() / 2, h + 0.05, f"{h:.2f}%", ha='center', fontsize=9, fontweight='bold')

        plt.ylim(0, max(cand_summary['optimality_gap_pct']) * 1.25)
        plt.tight_layout()
        plt.savefig(os.path.join(fig_dir, "02_candidate_generation_comparison.png"), dpi=300)
        plt.close()

    # -------------------------------------------------------------
    # Figure 3: Lookahead Depth Latency Trade-Off
    # -------------------------------------------------------------
    if os.path.exists(exp3_csv):
        df3 = pd.read_csv(exp3_csv)
        fig, ax1 = plt.subplots(figsize=(8, 4.5))

        depth_summary = df3.groupby('lookahead_depth').agg({
            'optimality_gap_s': 'mean',
            'avg_latency_ms': 'mean'
        }).reset_index()

        ax1.plot(depth_summary['lookahead_depth'], depth_summary['optimality_gap_s'], marker='o', color='#10b981', linewidth=2, label="Optimality Gap (s)")
        ax1.set_xlabel("Lookahead Depth (k)")
        ax1.set_ylabel("Optimality Gap vs Reference (seconds)", color='#10b981')
        ax1.tick_params(axis='y', labelcolor='#10b981')

        ax2 = ax1.twinx()
        ax2.bar(depth_summary['lookahead_depth'] + 0.1, depth_summary['avg_latency_ms'], width=0.2, alpha=0.3, color='#6366f1', label="Decision Latency (ms)")
        ax2.set_ylabel("Per-Decision Latency (ms)", color='#6366f1')
        ax2.tick_params(axis='y', labelcolor='#6366f1')

        plt.title("Experiment 3: Lookahead Depth vs. Decision Latency & Optimality Gap", fontweight='bold')
        fig.tight_layout()
        plt.savefig(os.path.join(fig_dir, "03_lookahead_depth_latency_tradeoff.png"), dpi=300)
        plt.close()

    # -------------------------------------------------------------
    # Figure 4: Dynamic Traffic Performance
    # -------------------------------------------------------------
    if os.path.exists(exp4_csv):
        df4 = pd.read_csv(exp4_csv)
        plt.figure(figsize=(8, 4.5))
        traf_summary = df4.groupby('traffic_scenario')['travel_time_s'].mean().reset_index()
        traf_summary = traf_summary.sort_values('travel_time_s')

        bars = plt.bar(traf_summary['traffic_scenario'], traf_summary['travel_time_s'], color=['#10b981', '#f59e0b', '#ef4444', '#8b5cf6'], width=0.5)
        plt.ylabel("Journey Travel Time (seconds)")
        plt.title("Experiment 4: Sequential Routing Under Congestion Conditions", fontweight='bold')

        for bar in bars:
            h = bar.get_height()
            plt.text(bar.get_x() + bar.get_width() / 2, h + 5, f"{h:.1f}s", ha='center', fontsize=9, fontweight='bold')

        plt.ylim(0, max(traf_summary['travel_time_s']) * 1.2)
        plt.tight_layout()
        plt.savefig(os.path.join(fig_dir, "04_dynamic_traffic_performance.png"), dpi=300)
        plt.close()

    # -------------------------------------------------------------
    # Figure 5: Rerouting Threshold Sensitivity
    # -------------------------------------------------------------
    if os.path.exists(exp5_csv):
        df5 = pd.read_csv(exp5_csv)
        plt.figure(figsize=(7, 5))
        pivot_table = df5.pivot_table(index='delta_T_threshold_s', columns='delta_pct_threshold', values='reroute_events', aggfunc='mean')
        sns.heatmap(pivot_table, annot=True, fmt=".1f", cmap="Blues", cbar_kws={'label': 'Reroute Frequency'})
        plt.xlabel("Percentage Threshold (%)")
        plt.ylabel("Absolute Threshold (seconds)")
        plt.title("Experiment 5: Rerouting Trigger Sensitivity Surface", fontweight='bold')
        plt.tight_layout()
        plt.savefig(os.path.join(fig_dir, "05_rerouting_threshold_surface.png"), dpi=300)
        plt.close()

    # -------------------------------------------------------------
    # Figure 6: Robustness & Recovery Summary
    # -------------------------------------------------------------
    if os.path.exists(master_csv):
        df_master = pd.read_csv(master_csv)
        plt.figure(figsize=(8, 4))
        rec_summary = df_master.groupby('algorithm')['recovery_events'].sum().reset_index()

        bars = plt.barh(rec_summary['algorithm'], rec_summary['recovery_events'], color='#3b82f6', height=0.5)
        plt.xlabel("Total Emergency Recovery Events")
        plt.title("Experiment 8: Algorithmic Robustness & Recovery Invocations", fontweight='bold')
        plt.tight_layout()
        plt.savefig(os.path.join(fig_dir, "06_robustness_and_recovery_summary.png"), dpi=300)
        plt.close()

    # -------------------------------------------------------------
    # Figure 7: Optimality Gap Distribution
    # -------------------------------------------------------------
    if os.path.exists(exp2_csv):
        df2 = pd.read_csv(exp2_csv)
        plt.figure(figsize=(8, 4.5))
        sns.barplot(data=df2, x='decision_strategy', y='optimality_gap_pct', palette='viridis', errorbar=None)
        plt.ylabel("Optimality Gap vs Dijkstra (%)")
        plt.xlabel("Decision Strategy")
        plt.title("Decision Strategies: Optimality Gap Comparison", fontweight='bold')
        plt.tight_layout()
        plt.savefig(os.path.join(fig_dir, "07_optimality_gap_distribution.png"), dpi=300)
        plt.close()

    # -------------------------------------------------------------
    # Figure 8: Master Experimental Summary
    # -------------------------------------------------------------
    if os.path.exists(master_csv):
        df_master = pd.read_csv(master_csv)
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))

        # Subplot 1: Travel Time
        avg_tt = df_master.groupby('algorithm')['actual_travel_time_s'].mean()
        axes[0].barh([a.split('.')[1].strip() if '.' in a else a for a in avg_tt.index], avg_tt.values, color='#0284c7', height=0.6)
        axes[0].set_xlabel("Mean Travel Time (s)")
        axes[0].set_title("Travel Time (Lower is Better)")

        # Subplot 2: Computation Latency
        avg_lat = df_master.groupby('algorithm')['avg_decision_latency_ms'].mean()
        axes[1].barh([a.split('.')[1].strip() if '.' in a else a for a in avg_lat.index], avg_lat.values, color='#8b5cf6', height=0.6)
        axes[1].set_xlabel("Per-Decision Latency (ms)")
        axes[1].set_title("Decision Latency (Lower is Better)")

        plt.suptitle("GeoPulse Master Experimental Synthesis", fontweight='bold', fontsize=14)
        plt.tight_layout()
        plt.savefig(os.path.join(fig_dir, "08_master_experimental_summary.png"), dpi=300)
        plt.close()

    print(f"[Visualizations] All 8 publication figures saved to {fig_dir}")
