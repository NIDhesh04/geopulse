"""
GeoPulse Phase 10: Prediction Error vs Routing Performance Analysis (Experiment G)

Quantifies the empirical relationship between model prediction error and routing
decision quality:
  1. Route travel-time error vs Oracle regret
  2. Network-level speed MAE vs Route improvement
  3. Prediction deviation at update epoch vs Rerouting travel-time savings
"""

from typing import Dict, List, Tuple, Any, Optional
import numpy as np
import pandas as pd
from scipy import stats


def analyze_prediction_error_vs_routing(
    df_runs: pd.DataFrame,
    pred_df: pd.DataFrame,
    df_replay: Optional[pd.DataFrame] = None
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Computes statistical correlations and relationships between prediction error
    and downstream routing outcomes.

    Returns
    -------
    df_analysis : pd.DataFrame
        Enriched evaluation dataframe with prediction errors, regrets, and gains.
    df_corr : pd.DataFrame
        Summary table of Pearson and Spearman correlations with p-values.
    """
    df_local = df_runs.copy()

    # Network-level speed MAE for each timestamp
    p_df = pred_df.copy()
    if 'ts_round' not in p_df.columns:
        p_df['ts_round'] = pd.to_datetime(p_df['timestamp']).dt.round('h')
    else:
        p_df['ts_round'] = pd.to_datetime(p_df['ts_round'])

    p_df['abs_speed_err_kmh'] = (p_df['actual_speed'] - p_df['predicted_speed']).abs()
    ts_speed_mae = p_df.groupby('ts_round')['abs_speed_err_kmh'].mean().reset_index()
    ts_speed_mae.rename(columns={'abs_speed_err_kmh': 'network_speed_mae_kmh'}, inplace=True)

    df_local['ts_round_dt'] = pd.to_datetime(df_local['timestamp'])
    merged = pd.merge(df_local, ts_speed_mae, left_on='ts_round_dt', right_on='ts_round', how='left')

    # Read phase 8 predicted times if present in p8 parquet, or approximate
    if 'ml_predicted_time_s' in merged.columns:
        merged['route_pred_error_s'] = (merged['ml_predicted_time_s'] - merged['lightgbm_actual_time_s']).abs()
        merged['route_pred_error_pct'] = (merged['route_pred_error_s'] / merged['lightgbm_actual_time_s']) * 100.0
    else:
        # Load from phase 8 eval parquet
        try:
            p8_eval = pd.read_parquet('results/phase8_route_evaluation.parquet')
            merged['ml_predicted_time_s'] = p8_eval['ml_predicted_time_s']
            merged['route_pred_error_s'] = (merged['ml_predicted_time_s'] - merged['lightgbm_actual_time_s']).abs()
            merged['route_pred_error_pct'] = (merged['route_pred_error_s'] / merged['lightgbm_actual_time_s']) * 100.0
        except Exception:
            merged['route_pred_error_s'] = 0.0
            merged['route_pred_error_pct'] = 0.0

    # Variables of interest
    v_speed_mae = merged['network_speed_mae_kmh'].fillna(0.0)
    v_route_err = merged['route_pred_error_s'].fillna(0.0)
    v_regret = merged['lightgbm_oracle_regret_s']
    v_gap_pct = merged['lightgbm_oracle_gap_pct']
    v_saving = merged['lightgbm_vs_static_saving_s']
    v_imp_pct = merged['lightgbm_vs_static_imp_pct']

    corr_pairs = [
        ('Route Travel-Time Error (s)', 'Oracle Regret (s)', v_route_err, v_regret),
        ('Route Travel-Time Error (s)', 'Improvement vs Static (s)', v_route_err, v_saving),
        ('Network Speed MAE (km/h)', 'Oracle Regret (s)', v_speed_mae, v_regret),
        ('Network Speed MAE (km/h)', 'Oracle Gap (%)', v_speed_mae, v_gap_pct),
        ('Network Speed MAE (km/h)', 'Improvement vs Static (%)', v_speed_mae, v_imp_pct)
    ]

    corr_records = []
    for var1, var2, s1, s2 in corr_pairs:
        # Pearson
        r_val, r_p = stats.pearsonr(s1, s2)
        # Spearman
        rho_val, rho_p = stats.spearmanr(s1, s2)

        corr_records.append({
            'variable_x': var1,
            'variable_y': var2,
            'pearson_r': round(r_val, 4),
            'pearson_p_value': float(f"{r_p:.4e}") if r_p < 1e-4 else round(float(r_p), 4),
            'spearman_rho': round(rho_val, 4),
            'spearman_p_value': float(f"{rho_p:.4e}") if rho_p < 1e-4 else round(float(rho_p), 4),
            'sample_size': len(s1),
            'statistical_interpretation': (
                f"{'Statistically significant' if r_p < 0.05 else 'Not significant'} "
                f"({ 'positive' if r_val > 0 else 'negative'} correlation)"
            )
        })

    df_corr = pd.DataFrame(corr_records)
    return merged, df_corr
