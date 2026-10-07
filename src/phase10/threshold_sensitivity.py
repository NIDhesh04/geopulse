"""
GeoPulse Phase 10: Threshold Sensitivity Engine (Experiment C)

Performs a 2D parameter grid sweep across absolute time thresholds
(5s, 10s, 20s, 30s) and relative percentage thresholds (1%, 2%, 3%, 5%, 10%)
to quantify the trade-off between travel-time savings and route stability.
"""

from typing import List, Dict, Any
import pandas as pd
from src.phase10.rerouting_ablation import evaluate_rerouting_policy
from src.phase10.experiment_config import GRID_ABS_THRESHOLDS_S, GRID_PCT_THRESHOLDS


def run_threshold_sensitivity_grid(
    replay_df: pd.DataFrame,
    abs_thresholds: List[float] = GRID_ABS_THRESHOLDS_S,
    pct_thresholds: List[float] = GRID_PCT_THRESHOLDS
) -> pd.DataFrame:
    """
    Executes a complete 2D grid sweep of threshold combinations.

    Parameters
    ----------
    replay_df : pd.DataFrame
        Replay journey dataset.
    abs_thresholds : list of float
        Absolute threshold grid values (seconds).
    pct_thresholds : list of float
        Percentage threshold grid values (%).

    Returns
    -------
    pd.DataFrame
        Grid results containing sensitivity metrics for each parameter combination.
    """
    grid_records = []

    # Include unconstrained baseline (0s, 0%)
    res_base = evaluate_rerouting_policy(replay_df, 0.0, 0.0, "Unconstrained (0s, 0%)")
    res_base['is_default_geopulse'] = False
    grid_records.append(res_base)

    for th_s in abs_thresholds:
        for th_pct in pct_thresholds:
            label = f"{th_s:.0f}s + {th_pct:.0f}%"
            is_default = (abs(th_s - 10.0) < 1e-4) and (abs(th_pct - 3.0) < 1e-4)
            if is_default:
                label += " [GeoPulse Default]"

            res = evaluate_rerouting_policy(replay_df, th_s, th_pct, label)
            res['is_default_geopulse'] = is_default
            grid_records.append(res)

    df_grid = pd.DataFrame(grid_records)
    return df_grid
