"""
GeoPulse Phase 10: Robustness Analysis Engine (Experiments D, E, F)

Evaluates system robustness across operational dimensions:
  Experiment D: Diurnal Time Periods (Morning Peak, Midday, Evening Peak, Off-Peak)
  Experiment E: Route Length Bins (Short <5 km, Medium 5-8 km, Long >8 km)
  Experiment F: Network Congestion Conditions (Quantile-based tertiles: Low, Medium, High)
"""

from typing import Dict, List, Tuple, Any, Optional
import numpy as np
import pandas as pd
from src.phase10.experiment_config import ROUTE_LENGTH_BINS, ROUTE_LENGTH_LABELS, CONGESTION_LABELS


def analyze_robustness_by_time_period(
    df_runs: pd.DataFrame,
    df_replay: Optional[pd.DataFrame] = None
) -> pd.DataFrame:
    """
    Experiment D: Evaluates routing and rerouting performance broken down by diurnal period.
    """
    rows = []
    periods = ['Morning Peak', 'Midday', 'Evening Peak', 'Off-Peak']

    # Diurnal stats from routing ablation (800 evaluations)
    for p in periods:
        sub = df_runs[df_runs['period'] == p]
        n = len(sub)
        if n == 0:
            continue

        mean_stat_t = sub['static_actual_time_s'].mean()
        mean_lgb_t = sub['lightgbm_actual_time_s'].mean()
        mean_hist_t = sub['historical_actual_time_s'].mean()
        mean_ora_t = sub['oracle_actual_time_s'].mean()

        mean_sav_s = (sub['static_actual_time_s'] - sub['lightgbm_actual_time_s']).mean()
        mean_imp_pct = ((sub['static_actual_time_s'] - sub['lightgbm_actual_time_s']) / sub['static_actual_time_s'] * 100.0).mean()

        win_rate = (sub['lightgbm_actual_time_s'] < sub['static_actual_time_s']).sum() / n * 100.0
        mean_regret_s = sub['lightgbm_oracle_regret_s'].mean()
        mean_gap_pct = sub['lightgbm_oracle_gap_pct'].mean()

        # Dynamic rerouting replay stats for this period if available
        if df_replay is not None and 'period' in df_replay.columns:
            sub_rep = df_replay[df_replay['period'] == p]
            rep_n = len(sub_rep)
            if rep_n > 0:
                rep_trig = sub_rep['reroute_triggered'].sum()
                rep_freq = (rep_trig / rep_n) * 100.0
                rep_sav = sub_rep['time_saved_s'].mean()
            else:
                rep_freq = 0.0
                rep_sav = 0.0
        else:
            rep_freq = np.nan
            rep_sav = np.nan

        rows.append({
            'period': p,
            'evaluation_count': n,
            'mean_static_time_s': round(mean_stat_t, 2),
            'mean_lightgbm_time_s': round(mean_lgb_t, 2),
            'mean_historical_time_s': round(mean_hist_t, 2),
            'mean_oracle_time_s': round(mean_ora_t, 2),
            'mean_saving_vs_static_s': round(mean_sav_s, 2),
            'mean_improvement_vs_static_pct': round(mean_imp_pct, 2),
            'win_rate_vs_static_pct': round(win_rate, 2),
            'mean_oracle_regret_s': round(mean_regret_s, 2),
            'mean_oracle_gap_pct': round(mean_gap_pct, 2),
            'replay_reroute_frequency_pct': round(rep_freq, 2) if not np.isnan(rep_freq) else np.nan,
            'replay_mean_saving_s': round(rep_sav, 2) if not np.isnan(rep_sav) else np.nan
        })

    return pd.DataFrame(rows)


def analyze_robustness_by_route_length(
    df_runs: pd.DataFrame,
    df_replay: Optional[pd.DataFrame] = None
) -> pd.DataFrame:
    """
    Experiment E: Evaluates performance categorized by route length:
      Short (<5 km), Medium (5-8 km), Long (>8 km).
    """
    df_runs_local = df_runs.copy()
    df_runs_local['length_bin'] = pd.cut(
        df_runs_local['static_distance_m'],
        bins=ROUTE_LENGTH_BINS,
        labels=ROUTE_LENGTH_LABELS
    )

    rows = []
    for bin_lbl in ROUTE_LENGTH_LABELS:
        sub = df_runs_local[df_runs_local['length_bin'] == bin_lbl]
        n = len(sub)
        if n == 0:
            continue

        mean_dist_m = sub['static_distance_m'].mean()
        mean_stat_t = sub['static_actual_time_s'].mean()
        mean_lgb_t = sub['lightgbm_actual_time_s'].mean()
        mean_ora_t = sub['oracle_actual_time_s'].mean()

        mean_sav_s = (sub['static_actual_time_s'] - sub['lightgbm_actual_time_s']).mean()
        mean_imp_pct = ((sub['static_actual_time_s'] - sub['lightgbm_actual_time_s']) / sub['static_actual_time_s'] * 100.0).mean()
        win_rate = (sub['lightgbm_actual_time_s'] < sub['static_actual_time_s']).sum() / n * 100.0
        mean_regret_s = sub['lightgbm_oracle_regret_s'].mean()
        mean_gap_pct = sub['lightgbm_oracle_gap_pct'].mean()

        rows.append({
            'route_length_bin': bin_lbl,
            'evaluation_count': n,
            'mean_distance_m': round(mean_dist_m, 2),
            'mean_static_time_s': round(mean_stat_t, 2),
            'mean_lightgbm_time_s': round(mean_lgb_t, 2),
            'mean_oracle_time_s': round(mean_ora_t, 2),
            'mean_saving_vs_static_s': round(mean_sav_s, 2),
            'mean_improvement_vs_static_pct': round(mean_imp_pct, 2),
            'win_rate_vs_static_pct': round(win_rate, 2),
            'mean_oracle_regret_s': round(mean_regret_s, 2),
            'mean_oracle_gap_pct': round(mean_gap_pct, 2)
        })

    return pd.DataFrame(rows)


def analyze_robustness_by_congestion_condition(
    df_runs: pd.DataFrame,
    pred_df: pd.DataFrame
) -> pd.DataFrame:
    """
    Experiment F: Evaluates performance across objective, quantile-based
    network congestion tertiles:
      - Low Congestion (Top 33% speed quantile across network)
      - Medium Congestion (Middle 33% speed quantile)
      - High Congestion (Bottom 33% speed quantile / severe bottlenecking)
    """
    # Compute mean network monitored speed for each timestamp
    p_df = pred_df.copy()
    if 'ts_round' not in p_df.columns:
        p_df['ts_round'] = pd.to_datetime(p_df['timestamp']).dt.round('h')
    else:
        p_df['ts_round'] = pd.to_datetime(p_df['ts_round'])

    ts_mean_speed = p_df.groupby('ts_round')['actual_speed'].mean().reset_index()
    ts_mean_speed.rename(columns={'actual_speed': 'network_mean_speed_kmh'}, inplace=True)

    # Merge into runs
    df_runs_local = df_runs.copy()
    df_runs_local['ts_round_dt'] = pd.to_datetime(df_runs_local['timestamp'])
    merged = pd.merge(df_runs_local, ts_mean_speed, left_on='ts_round_dt', right_on='ts_round', how='left')

    # Quantiles: Note that higher speed means LOWER congestion!
    # q33 and q66 of speed:
    q33 = merged['network_mean_speed_kmh'].quantile(0.33)
    q66 = merged['network_mean_speed_kmh'].quantile(0.66)

    def classify_congestion(spd):
        if spd <= q33:
            return 'High Congestion'
        elif spd <= q66:
            return 'Medium Congestion'
        else:
            return 'Low Congestion'

    merged['congestion_condition'] = merged['network_mean_speed_kmh'].apply(classify_congestion)

    rows = []
    for c_lbl in CONGESTION_LABELS:
        sub = merged[merged['congestion_condition'] == c_lbl]
        n = len(sub)
        if n == 0:
            continue

        mean_spd = sub['network_mean_speed_kmh'].mean()
        mean_stat_t = sub['static_actual_time_s'].mean()
        mean_lgb_t = sub['lightgbm_actual_time_s'].mean()
        mean_ora_t = sub['oracle_actual_time_s'].mean()

        mean_sav_s = (sub['static_actual_time_s'] - sub['lightgbm_actual_time_s']).mean()
        mean_imp_pct = ((sub['static_actual_time_s'] - sub['lightgbm_actual_time_s']) / sub['static_actual_time_s'] * 100.0).mean()
        win_rate = (sub['lightgbm_actual_time_s'] < sub['static_actual_time_s']).sum() / n * 100.0
        mean_regret_s = sub['lightgbm_oracle_regret_s'].mean()
        mean_gap_pct = sub['lightgbm_oracle_gap_pct'].mean()

        rows.append({
            'congestion_condition': c_lbl,
            'evaluation_count': n,
            'mean_network_speed_kmh': round(mean_spd, 2),
            'mean_static_time_s': round(mean_stat_t, 2),
            'mean_lightgbm_time_s': round(mean_lgb_t, 2),
            'mean_oracle_time_s': round(mean_ora_t, 2),
            'mean_saving_vs_static_s': round(mean_sav_s, 2),
            'mean_improvement_vs_static_pct': round(mean_imp_pct, 2),
            'win_rate_vs_static_pct': round(win_rate, 2),
            'mean_oracle_regret_s': round(mean_regret_s, 2),
            'mean_oracle_gap_pct': round(mean_gap_pct, 2)
        })

    return pd.DataFrame(rows)
