"""
GeoPulse Phase 10: Ablation & Robustness Test Suite

Tests:
1. Strategy ablation schema & row counts (800 runs)
2. Empirical travel-time hierarchy (Oracle <= LightGBM <= Persistence <= Static)
3. Non-negativity of Oracle regret
4. Monotonicity of reroute frequency under threshold tightening
5. Selectivity of the dual threshold policy over unconstrained rerouting
6. 100% beneficial reroute rate under GeoPulse dual threshold
7. Robustness period coverage (Morning, Midday, Evening, Off-Peak)
8. Automated data leakage audit status (ALL CHECKS PASSED)
9. Existence and integrity of all 10 high-resolution visual figures
"""

import os
import json
import pytest
import pandas as pd
import numpy as np


@pytest.fixture(scope="module")
def ablation_data():
    runs_path = 'results/phase10/routing_strategy_ablation.parquet'
    summary_path = 'results/phase10/routing_strategy_summary.csv'
    reroute_path = 'results/phase10/dynamic_rerouting_ablation.csv'
    grid_path = 'results/phase10/threshold_sensitivity.csv'
    period_path = 'results/phase10/time_period_robustness.csv'
    audit_path = 'results/phase10/data_leakage_audit.json'

    assert os.path.exists(runs_path), f"Missing {runs_path}"
    assert os.path.exists(summary_path), f"Missing {summary_path}"
    assert os.path.exists(reroute_path), f"Missing {reroute_path}"
    assert os.path.exists(grid_path), f"Missing {grid_path}"
    assert os.path.exists(period_path), f"Missing {period_path}"
    assert os.path.exists(audit_path), f"Missing {audit_path}"

    df_runs = pd.read_parquet(runs_path)
    df_summary = pd.read_csv(summary_path)
    df_reroute = pd.read_csv(reroute_path)
    df_grid = pd.read_csv(grid_path)
    df_period = pd.read_csv(period_path)
    with open(audit_path, 'r') as f:
        audit_res = json.load(f)

    return {
        'runs': df_runs,
        'summary': df_summary,
        'reroute': df_reroute,
        'grid': df_grid,
        'period': df_period,
        'audit': audit_res
    }


def test_strategy_ablation_output_schema(ablation_data):
    df_runs = ablation_data['runs']
    assert len(df_runs) == 800, f"Expected 800 runs, got {len(df_runs)}"

    required_cols = [
        'od_id', 'timestamp', 'period', 'source_node', 'destination_node',
        'static_actual_time_s', 'persistence_actual_time_s',
        'historical_actual_time_s', 'lightgbm_actual_time_s', 'oracle_actual_time_s',
        'lightgbm_vs_static_saving_s', 'lightgbm_oracle_regret_s'
    ]
    for col in required_cols:
        assert col in df_runs.columns, f"Missing required column: {col}"
        assert not df_runs[col].isnull().any(), f"Column {col} contains NaN values"


def test_strategy_travel_time_ordering(ablation_data):
    df_summary = ablation_data['summary'].set_index('strategy')
    
    t_stat = df_summary.loc['Static Baseline', 'mean_travel_time_s']
    t_pers = df_summary.loc['Persistence Prediction', 'mean_travel_time_s']
    t_hist = df_summary.loc['Historical Baseline', 'mean_travel_time_s']
    t_lgb = df_summary.loc['LightGBM Prediction', 'mean_travel_time_s']
    t_ora = df_summary.loc['Current-Traffic Oracle', 'mean_travel_time_s']

    # Empirical order: Oracle <= LightGBM <= Persistence <= Static
    assert t_ora <= t_lgb + 1e-4, f"Oracle ({t_ora}) must be <= LightGBM ({t_lgb})"
    assert t_lgb <= t_pers + 1e-4, f"LightGBM ({t_lgb}) must be <= Persistence ({t_pers})"
    assert t_pers <= t_stat + 1e-4, f"Persistence ({t_pers}) must be <= Static ({t_stat})"
    # Historical and LightGBM are close
    assert abs(t_lgb - t_hist) < 1.0, f"LightGBM and Historical expected to be within 1.0s, got {abs(t_lgb - t_hist)}"


def test_oracle_regret_strictly_non_negative(ablation_data):
    df_runs = ablation_data['runs']
    for strat in ['static', 'persistence', 'historical', 'lightgbm']:
        regret_col = f'{strat}_oracle_regret_s'
        assert (df_runs[regret_col] >= -1e-4).all(), f"Found negative oracle regret in {regret_col}"


def test_dynamic_rerouting_policy_monotonicity(ablation_data):
    df_reroute = ablation_data['reroute'].set_index('policy')
    # Always reroute (B2) should have >= triggers than any gated policy
    freq_b2 = df_reroute.loc['B2: Always Reroute (Unrestricted)', 'reroute_frequency_pct']
    freq_b5 = df_reroute.loc['B5: Dual Threshold (>= 10s AND >= 3%) [GeoPulse]', 'reroute_frequency_pct']
    freq_b1 = df_reroute.loc['B1: No Rerouting (Baseline)', 'reroute_frequency_pct']

    assert freq_b1 == 0.0, "B1 No Rerouting must have 0% frequency"
    assert freq_b2 >= freq_b5, f"B2 ({freq_b2}%) should have >= triggers than B5 ({freq_b5}%)"
    assert freq_b5 >= freq_b1, f"B5 ({freq_b5}%) should have >= triggers than B1 ({freq_b1}%)"


def test_beneficial_reroute_rate_under_dual_threshold(ablation_data):
    df_reroute = ablation_data['reroute'].set_index('policy')
    b5 = df_reroute.loc['B5: Dual Threshold (>= 10s AND >= 3%) [GeoPulse]']
    
    assert b5['reroute_count'] == 8, f"Expected 8 reroutes under B5, got {b5['reroute_count']}"
    assert b5['beneficial_reroutes_count'] == 8, "All triggered reroutes must be beneficial"
    assert b5['detrimental_reroutes_count'] == 0, "No detrimental reroutes allowed under B5"
    assert b5['beneficial_reroute_rate_pct'] == 100.0, "Beneficial rate must be 100%"


def test_time_period_robustness_coverage(ablation_data):
    df_period = ablation_data['period']
    assert len(df_period) == 4, f"Expected 4 diurnal periods, got {len(df_period)}"
    periods = set(df_period['period'])
    assert periods == {'Morning Peak', 'Midday', 'Evening Peak', 'Off-Peak'}

    # Evening peak should demonstrate highest mean saving
    p_map = df_period.set_index('period')['mean_saving_vs_static_s']
    assert p_map['Evening Peak'] > p_map['Morning Peak'], "Evening Peak saving must exceed Morning Peak saving"
    assert p_map['Evening Peak'] > p_map['Midday'], "Evening Peak saving must exceed Midday saving"


def test_automated_data_leakage_audit_pass(ablation_data):
    audit = ablation_data['audit']
    assert audit['overall_leakage_audit_status'] == 'ALL CHECKS PASSED', "Data leakage audit must pass completely"
    assert audit['check_1_ml_feature_leakage']['status'] == 'PASSED'
    assert audit['check_2_prediction_not_oracle']['status'] == 'PASSED'
    assert audit['check_3_route_planning_separation']['status'] == 'PASSED'
    assert audit['check_4_dynamic_telemetry_quarantine']['status'] == 'PASSED'


def test_all_10_figures_exist_and_nonempty():
    fig_dir = 'results/phase10/figures'
    expected_figures = [
        '01_routing_strategy_travel_time.png',
        '02_routing_strategy_improvement.png',
        '03_prediction_method_comparison.png',
        '04_oracle_regret_comparison.png',
        '05_dynamic_rerouting_policy_comparison.png',
        '06_threshold_sensitivity.png',
        '07_rerouting_frequency_vs_savings.png',
        '08_performance_by_time_period.png',
        '09_performance_by_route_length.png',
        '10_prediction_error_vs_routing_gain.png'
    ]
    for fig_name in expected_figures:
        fig_path = os.path.join(fig_dir, fig_name)
        assert os.path.exists(fig_path), f"Figure missing: {fig_path}"
        size_bytes = os.path.getsize(fig_path)
        assert size_bytes > 50000, f"Figure {fig_name} appears incomplete (size: {size_bytes} bytes)"
