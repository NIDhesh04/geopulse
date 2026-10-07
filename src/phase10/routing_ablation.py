"""
GeoPulse Phase 10: Routing Strategy Ablation Engine (Experiment A)

Evaluates 5 routing strategies under fair, controlled conditions over the 800
OD-timestamp evaluation instances from Phase 8:
  A1: Static Baseline (OSM speed hierarchy)
  A2: Persistence Prediction (speed(t+1) = speed(t))
  A3: Historical Same-Hour Baseline
  A4: LightGBM Prediction (Phase 7 trained model)
  A5: Current-Traffic Oracle (Upper-bound theoretical benchmark)
"""

from typing import Dict, List, Tuple, Any, Optional
import time
import numpy as np
import pandas as pd
import networkx as nx

from src.routing.dijkstra import custom_dijkstra, DijkstraResult
from src.routing.traffic_weights import GraphWeightManager
from src.routing.route_evaluator import compute_edge_jaccard_overlap


def run_routing_strategy_ablation(
    weight_manager: GraphWeightManager,
    pred_df: pd.DataFrame,
    od_df: pd.DataFrame,
    eval_ts_df: pd.DataFrame
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Executes the 5 routing strategies over all OD pairs and timestamps.

    Returns
    -------
    df_runs : pd.DataFrame
        Detailed evaluation table (800 rows) with side-by-side performance for all 5 strategies.
    df_summary : pd.DataFrame
        Summary comparison table aggregating primary and secondary metrics.
    """
    records = []
    w_static = weight_manager.static_weights
    edge_lengths = weight_manager.edge_lengths

    # Ensure timestamp parsing
    pred_df_local = pred_df.copy()
    if 'ts_round' not in pred_df_local.columns:
        pred_df_local['ts_round'] = pd.to_datetime(pred_df_local['timestamp']).dt.round('h')
    else:
        pred_df_local['ts_round'] = pd.to_datetime(pred_df_local['ts_round'])

    eval_ts_df_local = eval_ts_df.copy()
    eval_ts_df_local['ts_round_dt'] = pd.to_datetime(eval_ts_df_local['ts_round'])

    for _, ts_row in eval_ts_df_local.iterrows():
        ts_val = ts_row['ts_round_dt']
        ist_val = str(ts_row.get('ts_ist', ''))
        period_val = str(ts_row.get('period', ''))
        is_peak_val = int(ts_row.get('is_peak', 0))

        p_t = pred_df_local[pred_df_local['ts_round'] == ts_val].set_index('traffic_segment_id')
        if len(p_t) == 0:
            raise ValueError(f"No traffic predictions found for timestamp {ts_val}")

        # Construct scenario edge weights
        w_curr, _, dyn_edges = weight_manager.build_scenario_weights(p_t['actual_speed'].to_dict())
        w_pers, _, _ = weight_manager.build_scenario_weights(p_t['persistence_prediction'].to_dict())
        w_hist, _, _ = weight_manager.build_scenario_weights(p_t['historical_prediction'].to_dict())
        w_lgb, _, _ = weight_manager.build_scenario_weights(p_t['predicted_speed'].to_dict())

        weights_map = {
            'static': w_static,
            'persistence': w_pers,
            'historical': w_hist,
            'lightgbm': w_lgb,
            'oracle': w_curr
        }

        for _, od_row in od_df.iterrows():
            od_id = int(od_row['od_id'])
            s = str(int(float(od_row['source_node'])))
            t = str(int(float(od_row['destination_node'])))

            # Solve paths using custom Dijkstra
            res = {}
            for strat_key, strat_w in weights_map.items():
                r = custom_dijkstra(weight_manager.adjacency, strat_w, s, t)
                if not r.is_reached:
                    raise ValueError(f"Target unreachable: strategy {strat_key}, OD #{od_id}")
                res[strat_key] = r

            # Ground truth actual travel times under w_curr
            t_act = {}
            dist = {}
            edge_counts = {}
            for strat_key in weights_map.keys():
                t_act[strat_key] = sum(w_curr.get(e, 0.0) for e in res[strat_key].edge_path)
                dist[strat_key] = sum(edge_lengths.get(e, 0.0) for e in res[strat_key].edge_path)
                edge_counts[strat_key] = len(res[strat_key].edge_path)

            t_static = t_act['static']
            t_oracle = t_act['oracle']

            rec = {
                'od_id': od_id,
                'timestamp': str(ts_val),
                'ist_timestamp': ist_val,
                'period': period_val,
                'is_peak': is_peak_val,
                'source_node': s,
                'destination_node': t,

                # Actual travel times (s)
                'static_actual_time_s': round(t_act['static'], 2),
                'persistence_actual_time_s': round(t_act['persistence'], 2),
                'historical_actual_time_s': round(t_act['historical'], 2),
                'lightgbm_actual_time_s': round(t_act['lightgbm'], 2),
                'oracle_actual_time_s': round(t_act['oracle'], 2),

                # Distances (m)
                'static_distance_m': round(dist['static'], 2),
                'persistence_distance_m': round(dist['persistence'], 2),
                'historical_distance_m': round(dist['historical'], 2),
                'lightgbm_distance_m': round(dist['lightgbm'], 2),
                'oracle_distance_m': round(dist['oracle'], 2),

                # Edge counts
                'static_edge_count': edge_counts['static'],
                'persistence_edge_count': edge_counts['persistence'],
                'historical_edge_count': edge_counts['historical'],
                'lightgbm_edge_count': edge_counts['lightgbm'],
                'oracle_edge_count': edge_counts['oracle'],

                # Savings vs Static (s)
                'persistence_vs_static_saving_s': round(t_static - t_act['persistence'], 2),
                'historical_vs_static_saving_s': round(t_static - t_act['historical'], 2),
                'lightgbm_vs_static_saving_s': round(t_static - t_act['lightgbm'], 2),
                'oracle_vs_static_saving_s': round(t_static - t_act['oracle'], 2),

                # Improvement vs Static (%)
                'persistence_vs_static_imp_pct': round(((t_static - t_act['persistence']) / t_static) * 100.0, 4) if t_static > 0 else 0.0,
                'historical_vs_static_imp_pct': round(((t_static - t_act['historical']) / t_static) * 100.0, 4) if t_static > 0 else 0.0,
                'lightgbm_vs_static_imp_pct': round(((t_static - t_act['lightgbm']) / t_static) * 100.0, 4) if t_static > 0 else 0.0,
                'oracle_vs_static_imp_pct': round(((t_static - t_act['oracle']) / t_static) * 100.0, 4) if t_static > 0 else 0.0,

                # Oracle Regret (s)
                'static_oracle_regret_s': round(max(t_static - t_oracle, 0.0), 2),
                'persistence_oracle_regret_s': round(max(t_act['persistence'] - t_oracle, 0.0), 2),
                'historical_oracle_regret_s': round(max(t_act['historical'] - t_oracle, 0.0), 2),
                'lightgbm_oracle_regret_s': round(max(t_act['lightgbm'] - t_oracle, 0.0), 2),
                'oracle_regret_s': 0.0,

                # Oracle Gap (%)
                'static_oracle_gap_pct': round((max(t_static - t_oracle, 0.0) / t_oracle) * 100.0, 4) if t_oracle > 0 else 0.0,
                'persistence_oracle_gap_pct': round((max(t_act['persistence'] - t_oracle, 0.0) / t_oracle) * 100.0, 4) if t_oracle > 0 else 0.0,
                'historical_oracle_gap_pct': round((max(t_act['historical'] - t_oracle, 0.0) / t_oracle) * 100.0, 4) if t_oracle > 0 else 0.0,
                'lightgbm_oracle_gap_pct': round((max(t_act['lightgbm'] - t_oracle, 0.0) / t_oracle) * 100.0, 4) if t_oracle > 0 else 0.0,

                # Overlaps vs Static
                'persistence_static_overlap': round(compute_edge_jaccard_overlap(res['static'].edge_path, res['persistence'].edge_path), 4),
                'historical_static_overlap': round(compute_edge_jaccard_overlap(res['static'].edge_path, res['historical'].edge_path), 4),
                'lightgbm_static_overlap': round(compute_edge_jaccard_overlap(res['static'].edge_path, res['lightgbm'].edge_path), 4),
                'oracle_static_overlap': round(compute_edge_jaccard_overlap(res['static'].edge_path, res['oracle'].edge_path), 4),

                # Overlaps vs Oracle
                'static_oracle_overlap': round(compute_edge_jaccard_overlap(res['oracle'].edge_path, res['static'].edge_path), 4),
                'persistence_oracle_overlap': round(compute_edge_jaccard_overlap(res['oracle'].edge_path, res['persistence'].edge_path), 4),
                'historical_oracle_overlap': round(compute_edge_jaccard_overlap(res['oracle'].edge_path, res['historical'].edge_path), 4),
                'lightgbm_oracle_overlap': round(compute_edge_jaccard_overlap(res['oracle'].edge_path, res['lightgbm'].edge_path), 4),
                'oracle_oracle_overlap': 1.0
            }
            records.append(rec)

    df_runs = pd.DataFrame(records)

    # -------------------------------------------------------------------------
    # SUMMARY AGGREGATION
    # -------------------------------------------------------------------------
    summary_rows = []
    strategies_meta = [
        ('Static Baseline', 'static'),
        ('Persistence Prediction', 'persistence'),
        ('Historical Baseline', 'historical'),
        ('LightGBM Prediction', 'lightgbm'),
        ('Current-Traffic Oracle', 'oracle')
    ]

    n_total = len(df_runs)
    t_stat_series = df_runs['static_actual_time_s']

    for strat_label, strat_k in strategies_meta:
        t_series = df_runs[f'{strat_k}_actual_time_s']
        d_series = df_runs[f'{strat_k}_distance_m']
        e_series = df_runs[f'{strat_k}_edge_count']
        
        # Improvement / savings vs static
        sav_series = t_stat_series - t_series
        imp_pct_series = (sav_series / t_stat_series) * 100.0

        wins = int((t_series < t_stat_series).sum())
        ties = int((t_series == t_stat_series).sum())
        losses = int((t_series > t_stat_series).sum())

        win_rate = (wins / n_total) * 100.0
        tie_rate = (ties / n_total) * 100.0
        loss_rate = (losses / n_total) * 100.0

        # Regret & gap
        if strat_k == 'oracle':
            regret_series = pd.Series([0.0] * n_total)
            gap_series = pd.Series([0.0] * n_total)
            overlap_ora = 1.0
        else:
            regret_series = df_runs[f'{strat_k}_oracle_regret_s']
            gap_series = df_runs[f'{strat_k}_oracle_gap_pct']
            overlap_ora = df_runs[f'{strat_k}_oracle_overlap'].mean()

        overlap_stat = df_runs[f'{strat_k}_static_overlap'].mean() if strat_k != 'static' else 1.0

        # Confidence Interval (95%)
        mean_t = t_series.mean()
        std_t = t_series.std()
        ci_95_t = 1.96 * (std_t / np.sqrt(n_total))

        summary_rows.append({
            'strategy': strat_label,
            'sample_count': n_total,
            'mean_travel_time_s': round(mean_t, 2),
            'median_travel_time_s': round(t_series.median(), 2),
            'std_travel_time_s': round(std_t, 2),
            'ci95_lower_s': round(mean_t - ci_95_t, 2),
            'ci95_upper_s': round(mean_t + ci_95_t, 2),
            'mean_saving_vs_static_s': round(sav_series.mean(), 2),
            'median_saving_vs_static_s': round(sav_series.median(), 2),
            'mean_improvement_pct': round(imp_pct_series.mean(), 2),
            'median_improvement_pct': round(imp_pct_series.median(), 2),
            'win_rate_vs_static_pct': round(win_rate, 2),
            'tie_rate_vs_static_pct': round(tie_rate, 2),
            'loss_rate_vs_static_pct': round(loss_rate, 2),
            'mean_oracle_regret_s': round(regret_series.mean(), 2),
            'median_oracle_regret_s': round(regret_series.median(), 2),
            'mean_oracle_gap_pct': round(gap_series.mean(), 2),
            'mean_route_distance_m': round(d_series.mean(), 2),
            'mean_edge_count': round(e_series.mean(), 2),
            'mean_overlap_with_static': round(overlap_stat, 4),
            'mean_overlap_with_oracle': round(overlap_ora, 4)
        })

    df_summary = pd.DataFrame(summary_rows)
    return df_runs, df_summary
