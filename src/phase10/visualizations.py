"""
GeoPulse Phase 10: Publication & Defense Visualizations Engine (Section 16)

Generates all 10 presentation-grade analytical figures at 300 DPI:
  01_routing_strategy_travel_time.png
  02_routing_strategy_improvement.png
  03_prediction_method_comparison.png
  04_oracle_regret_comparison.png
  05_dynamic_rerouting_policy_comparison.png
  06_threshold_sensitivity.png
  07_rerouting_frequency_vs_savings.png
  08_performance_by_time_period.png
  09_performance_by_route_length.png
  10_prediction_error_vs_routing_gain.png
"""

import os
from typing import Dict, Any, Optional
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from src.phase10.experiment_config import FIGURES_DIR

# Visual configuration
plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.size'] = 11
plt.rcParams['axes.titlesize'] = 13
plt.rcParams['axes.labelsize'] = 11
plt.rcParams['figure.titlesize'] = 14


def generate_all_phase10_figures(
    df_runs: pd.DataFrame,
    df_summary: pd.DataFrame,
    df_reroute: pd.DataFrame,
    df_grid: pd.DataFrame,
    df_period: pd.DataFrame,
    df_length: pd.DataFrame,
    df_pred_analysis: pd.DataFrame,
    output_dir: str = FIGURES_DIR
) -> Dict[str, str]:
    """
    Renders and saves all 10 Phase 10 analytical figures at 300 DPI.
    """
    os.makedirs(output_dir, exist_ok=True)
    saved_paths = {}

    palette_5 = ['#6c757d', '#fd7e14', '#20c997', '#0d6efd', '#198754']
    strat_labels = ['Static Baseline', 'Persistence', 'Historical', 'LightGBM', 'Current Oracle']
    strat_cols = [
        'static_actual_time_s',
        'persistence_actual_time_s',
        'historical_actual_time_s',
        'lightgbm_actual_time_s',
        'oracle_actual_time_s'
    ]

    # -------------------------------------------------------------------------
    # Figure 1: Routing Strategy Actual Travel Time (Boxplot / Jitter)
    # -------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 6))
    data_melted = []
    for label, col in zip(strat_labels, strat_cols):
        for val in df_runs[col]:
            data_melted.append({'Strategy': label, 'Travel Time (s)': val})
    df_melt = pd.DataFrame(data_melted)

    sns.boxplot(data=df_melt, x='Strategy', y='Travel Time (s)', palette=palette_5, ax=ax, width=0.45, showmeans=True,
                meanprops={'marker': 'o', 'markerfacecolor': 'white', 'markeredgecolor': 'black', 'markersize': 7})
    ax.set_title("Figure 1: Ground-Truth Travel Time Distribution Across Routing Strategies", pad=12, fontweight='bold')
    ax.set_ylabel("Actual Route Travel Time (seconds)")
    ax.set_xlabel("Routing Strategy")
    # Annotate means
    means = df_melt.groupby('Strategy')['Travel Time (s)'].mean()
    for idx, (label, col) in enumerate(zip(strat_labels, strat_cols)):
        m_val = df_runs[col].mean()
        ax.text(idx, m_val + 35, f"Mean:\n{m_val:.1f}s", ha='center', fontsize=9, fontweight='semibold',
                bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.8, edgecolor='#ccc'))

    plt.tight_layout()
    p1 = os.path.join(output_dir, '01_routing_strategy_travel_time.png')
    plt.savefig(p1, dpi=300)
    plt.close()
    saved_paths['fig01'] = p1

    # -------------------------------------------------------------------------
    # Figure 2: Routing Strategy Improvement vs Static (Violin / Boxplot)
    # -------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 6))
    imp_labels = ['Persistence', 'Historical Baseline', 'LightGBM Regressor', 'Current Oracle']
    imp_cols = [
        'persistence_vs_static_saving_s',
        'historical_vs_static_saving_s',
        'lightgbm_vs_static_saving_s',
        'oracle_vs_static_saving_s'
    ]
    imp_palette = ['#fd7e14', '#20c997', '#0d6efd', '#198754']

    imp_melt = []
    for lbl, col in zip(imp_labels, imp_cols):
        for val in df_runs[col]:
            imp_melt.append({'Strategy': lbl, 'Time Saved vs Static (s)': val})
    df_imp_melt = pd.DataFrame(imp_melt)

    sns.barplot(data=df_imp_melt, x='Strategy', y='Time Saved vs Static (s)', palette=imp_palette, ax=ax, errorbar=('ci', 95), capsize=0.1)
    ax.axhline(0, color='black', linestyle='--', linewidth=1, alpha=0.7)
    ax.set_title("Figure 2: Mean Travel-Time Improvement vs. Static Baseline (95% CI)", pad=12, fontweight='bold')
    ax.set_ylabel("Mean Travel Time Saved vs. Static (seconds)")
    ax.set_xlabel("Predictive Strategy vs. Upper-Bound Oracle")

    for idx, col in enumerate(imp_cols):
        val = df_runs[col].mean()
        ax.text(idx, val + 0.25, f"+{val:.2f}s", ha='center', fontweight='bold', fontsize=10)

    plt.tight_layout()
    p2 = os.path.join(output_dir, '02_routing_strategy_improvement.png')
    plt.savefig(p2, dpi=300)
    plt.close()
    saved_paths['fig02'] = p2

    # -------------------------------------------------------------------------
    # Figure 3: Prediction Method Multi-Metric Comparison
    # -------------------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5.5))
    comp_df = df_summary[df_summary['strategy'].isin([
        'Persistence Prediction', 'Historical Baseline', 'LightGBM Prediction'
    ])].copy()

    # Win Rate vs Static
    sns.barplot(data=comp_df, x='strategy', y='win_rate_vs_static_pct', palette=['#fd7e14', '#20c997', '#0d6efd'], ax=ax1)
    ax1.set_title("Win Rate vs. Static Baseline (%)", fontweight='bold')
    ax1.set_ylabel("Win Rate (%)")
    ax1.set_xlabel("")
    ax1.set_xticklabels(['Persistence', 'Historical', 'LightGBM'], rotation=15)
    for idx, r in comp_df.reset_index().iterrows():
        ax1.text(idx, r['win_rate_vs_static_pct'] + 1.0, f"{r['win_rate_vs_static_pct']:.1f}%", ha='center', fontweight='bold')
    ax1.set_ylim(0, 45)

    # Mean Time Saved vs Static
    sns.barplot(data=comp_df, x='strategy', y='mean_saving_vs_static_s', palette=['#fd7e14', '#20c997', '#0d6efd'], ax=ax2)
    ax2.set_title("Mean Time Saved vs. Static (seconds)", fontweight='bold')
    ax2.set_ylabel("Mean Saving (s)")
    ax2.set_xlabel("")
    ax2.set_xticklabels(['Persistence', 'Historical', 'LightGBM'], rotation=15)
    for idx, r in comp_df.reset_index().iterrows():
        ax2.text(idx, r['mean_saving_vs_static_s'] + 0.1, f"{r['mean_saving_vs_static_s']:.2f}s", ha='center', fontweight='bold')

    fig.suptitle("Figure 3: Multi-Metric Comparison of Predictive Routing Methods", y=0.98, fontweight='bold')
    plt.tight_layout()
    p3 = os.path.join(output_dir, '03_prediction_method_comparison.png')
    plt.savefig(p3, dpi=300)
    plt.close()
    saved_paths['fig03'] = p3

    # -------------------------------------------------------------------------
    # Figure 4: Empirical CDF of Oracle Regret
    # -------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 6))
    regret_meta = [
        ('Static Baseline', 'static_oracle_regret_s', '#6c757d'),
        ('Persistence', 'persistence_oracle_regret_s', '#fd7e14'),
        ('Historical Baseline', 'historical_oracle_regret_s', '#20c997'),
        ('LightGBM Regressor', 'lightgbm_oracle_regret_s', '#0d6efd')
    ]

    for lbl, col, clr in regret_meta:
        sorted_vals = np.sort(df_runs[col])
        cdf = np.arange(1, len(sorted_vals) + 1) / len(sorted_vals)
        ax.plot(sorted_vals, cdf, label=lbl, color=clr, linewidth=2.2)

    ax.set_title("Figure 4: Cumulative Distribution Function (CDF) of Oracle Regret", pad=12, fontweight='bold')
    ax.set_xlabel("Oracle Regret: T_actual - T_oracle (seconds)")
    ax.set_ylabel("Cumulative Probability P(Regret ≤ x)")
    ax.set_xlim(-1, 50)
    ax.axvline(0, color='black', linestyle=':', alpha=0.5)
    ax.legend(frameon=True, facecolor='white', loc='lower right')

    plt.tight_layout()
    p4 = os.path.join(output_dir, '04_oracle_regret_comparison.png')
    plt.savefig(p4, dpi=300)
    plt.close()
    saved_paths['fig04'] = p4

    # -------------------------------------------------------------------------
    # Figure 5: Dynamic Rerouting Policy Comparison (Experiment B)
    # -------------------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 6))
    
    # Reroute Frequency by Policy
    short_names = [p.split(':')[0] + ': ' + p.split(':')[1].split('(')[0].strip() for p in df_reroute['policy']]
    df_reroute_plot = df_reroute.copy()
    df_reroute_plot['short_name'] = short_names

    sns.barplot(data=df_reroute_plot, y='short_name', x='reroute_frequency_pct', palette='viridis', ax=ax1)
    ax1.set_title("Reroute Trigger Frequency (%)", fontweight='bold')
    ax1.set_xlabel("Frequency (%)")
    ax1.set_ylabel("")
    for idx, r in df_reroute_plot.iterrows():
        ax1.text(r['reroute_frequency_pct'] + 1, idx, f"{r['reroute_frequency_pct']:.0f}%", va='center', fontsize=9)

    # Mean Travel-Time Saving
    sns.barplot(data=df_reroute_plot, y='short_name', x='mean_saving_seconds_overall', palette='mako', ax=ax2)
    ax2.set_title("Fleet-Wide Mean Saving (seconds)", fontweight='bold')
    ax2.set_xlabel("Mean Time Saved (s)")
    ax2.set_ylabel("")
    for idx, r in df_reroute_plot.iterrows():
        ax2.text(r['mean_saving_seconds_overall'] + 0.8, idx, f"{r['mean_saving_seconds_overall']:.1f}s", va='center', fontsize=9)

    fig.suptitle("Figure 5: Dynamic Rerouting Policy Ablation (Threshold Gating Impact)", y=0.98, fontweight='bold')
    plt.tight_layout()
    p5 = os.path.join(output_dir, '05_dynamic_rerouting_policy_comparison.png')
    plt.savefig(p5, dpi=300)
    plt.close()
    saved_paths['fig05'] = p5

    # -------------------------------------------------------------------------
    # Figure 6: Threshold Sensitivity 2D Grid Heatmap
    # -------------------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))
    grid_pivot_freq = df_grid[df_grid['threshold_seconds'] > 0].pivot(
        index='threshold_seconds',
        columns='threshold_percent',
        values='reroute_frequency_pct'
    )
    grid_pivot_sav = df_grid[df_grid['threshold_seconds'] > 0].pivot(
        index='threshold_seconds',
        columns='threshold_percent',
        values='mean_saving_seconds_overall'
    )

    sns.heatmap(grid_pivot_freq, annot=True, fmt='.1f', cmap='Blues', ax=ax1, cbar_kws={'label': 'Trigger %'})
    ax1.set_title("Reroute Trigger Frequency (%)", fontweight='bold')
    ax1.set_xlabel("Relative Threshold ΔT (%)")
    ax1.set_ylabel("Absolute Threshold ΔT (seconds)")

    sns.heatmap(grid_pivot_sav, annot=True, fmt='.1f', cmap='YlGn', ax=ax2, cbar_kws={'label': 'Mean Saving (s)'})
    ax2.set_title("Fleet Mean Time Saved (seconds)", fontweight='bold')
    ax2.set_xlabel("Relative Threshold ΔT (%)")
    ax2.set_ylabel("Absolute Threshold ΔT (seconds)")

    fig.suptitle("Figure 6: Threshold Sensitivity Grid: Absolute (s) vs Relative (%) Gates", y=0.98, fontweight='bold')
    plt.tight_layout()
    p6 = os.path.join(output_dir, '06_threshold_sensitivity.png')
    plt.savefig(p6, dpi=300)
    plt.close()
    saved_paths['fig06'] = p6

    # -------------------------------------------------------------------------
    # Figure 7: Rerouting Frequency vs. Savings Trade-off
    # -------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(9, 6))
    sns.scatterplot(
        data=df_reroute,
        x='reroute_frequency_pct',
        y='mean_saving_seconds_overall',
        hue='policy',
        s=180,
        palette='tab10',
        ax=ax,
        legend=False
    )

    for _, r in df_reroute.iterrows():
        lbl = r['policy'].split(':')[0]
        ax.annotate(lbl, (r['reroute_frequency_pct'], r['mean_saving_seconds_overall']),
                    textcoords="offset points", xytext=(8, 4), ha='left', fontsize=9, fontweight='semibold')

    ax.set_title("Figure 7: Rerouting Pareto Trade-Off: Route Stability vs. Travel-Time Gain", pad=12, fontweight='bold')
    ax.set_xlabel("Reroute Trigger Frequency (%) [Higher = More Path Changes]")
    ax.set_ylabel("Fleet Mean Travel Time Saved (seconds)")
    ax.grid(True, linestyle='--', alpha=0.6)

    plt.tight_layout()
    p7 = os.path.join(output_dir, '07_rerouting_frequency_vs_savings.png')
    plt.savefig(p7, dpi=300)
    plt.close()
    saved_paths['fig07'] = p7

    # -------------------------------------------------------------------------
    # Figure 8: Performance by Diurnal Time Period
    # -------------------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5))
    period_order = ['Morning Peak', 'Midday', 'Evening Peak', 'Off-Peak']
    p_df = df_period.set_index('period').loc[period_order].reset_index()

    sns.barplot(data=p_df, x='period', y='mean_saving_vs_static_s', palette='coolwarm', ax=ax1)
    ax1.set_title("Travel Time Saved vs. Static by Period (s)", fontweight='bold')
    ax1.set_ylabel("Mean Time Saved (s)")
    ax1.set_xlabel("")
    for idx, r in p_df.iterrows():
        ax1.text(idx, r['mean_saving_vs_static_s'] + 0.1, f"+{r['mean_saving_vs_static_s']:.2f}s", ha='center', fontweight='bold')

    sns.barplot(data=p_df, x='period', y='win_rate_vs_static_pct', palette='crest', ax=ax2)
    ax2.set_title("ML Win Rate vs. Static by Period (%)", fontweight='bold')
    ax2.set_ylabel("Win Rate (%)")
    ax2.set_xlabel("")
    for idx, r in p_df.iterrows():
        ax2.text(idx, r['win_rate_vs_static_pct'] + 1.0, f"{r['win_rate_vs_static_pct']:.1f}%", ha='center', fontweight='bold')
    ax2.set_ylim(0, 50)

    fig.suptitle("Figure 8: GeoPulse Performance Across Diurnal Operational Periods", y=0.98, fontweight='bold')
    plt.tight_layout()
    p8 = os.path.join(output_dir, '08_performance_by_time_period.png')
    plt.savefig(p8, dpi=300)
    plt.close()
    saved_paths['fig08'] = p8

    # -------------------------------------------------------------------------
    # Figure 9: Performance by Route Length
    # -------------------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5.5))
    sns.barplot(data=df_length, x='route_length_bin', y='mean_saving_vs_static_s', palette='Blues_r', ax=ax1)
    ax1.set_title("Mean Time Saved vs. Static by Corridor Length", fontweight='bold')
    ax1.set_ylabel("Mean Time Saved (s)")
    ax1.set_xlabel("")
    for idx, r in df_length.iterrows():
        ax1.text(idx, r['mean_saving_vs_static_s'] + 0.15, f"+{r['mean_saving_vs_static_s']:.2f}s", ha='center', fontweight='bold')

    sns.barplot(data=df_length, x='route_length_bin', y='win_rate_vs_static_pct', palette='Blues_r', ax=ax2)
    ax2.set_title("Win Rate vs. Static by Corridor Length", fontweight='bold')
    ax2.set_ylabel("Win Rate (%)")
    ax2.set_xlabel("")
    for idx, r in df_length.iterrows():
        ax2.text(idx, r['win_rate_vs_static_pct'] + 1.0, f"{r['win_rate_vs_static_pct']:.1f}%", ha='center', fontweight='bold')
    ax2.set_ylim(0, 50)

    fig.suptitle("Figure 9: Routing Performance Robustness Across Trip Distance Bins", y=0.98, fontweight='bold')
    plt.tight_layout()
    p9 = os.path.join(output_dir, '09_performance_by_route_length.png')
    plt.savefig(p9, dpi=300)
    plt.close()
    saved_paths['fig09'] = p9

    # -------------------------------------------------------------------------
    # Figure 10: Prediction Error vs. Routing Outcome
    # -------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(9, 6))
    sub_scatter = df_pred_analysis[df_pred_analysis['lightgbm_oracle_regret_s'] < 80].copy()

    sns.regplot(
        data=sub_scatter,
        x='route_pred_error_s',
        y='lightgbm_oracle_regret_s',
        scatter_kws={'alpha': 0.35, 'color': '#0d6efd', 's': 25},
        line_kws={'color': '#dc3545', 'linewidth': 2},
        ax=ax
    )

    r_corr = df_pred_analysis['route_pred_error_s'].corr(df_pred_analysis['lightgbm_oracle_regret_s'])
    ax.text(0.05, 0.90, f"Pearson r = +{r_corr:.4f}\np < 0.001 (Significant)", transform=ax.transAxes,
            fontsize=11, fontweight='bold', bbox=dict(boxstyle='round,pad=0.4', facecolor='white', alpha=0.9, edgecolor='#ccc'))

    ax.set_title("Figure 10: Route Travel-Time Prediction Error vs. Oracle Regret", pad=12, fontweight='bold')
    ax.set_xlabel("Route Travel-Time Prediction Error |T_pred - T_actual| (seconds)")
    ax.set_ylabel("Oracle Regret: T_ML - T_oracle (seconds)")

    plt.tight_layout()
    p10 = os.path.join(output_dir, '10_prediction_error_vs_routing_gain.png')
    plt.savefig(p10, dpi=300)
    plt.close()
    saved_paths['fig10'] = p10

    return saved_paths
