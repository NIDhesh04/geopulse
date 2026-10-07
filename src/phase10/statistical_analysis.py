"""
GeoPulse Phase 10: Statistical Hypothesis Testing Engine (Section 13)

Conducts formal hypothesis tests on paired travel-time distributions:
  - Normality testing (Shapiro-Wilk / D'Agostino-Pearson)
  - Paired Student's t-test (parametric)
  - Wilcoxon signed-rank test (non-parametric, robust to skew and ties)
  - 95% Confidence Intervals of mean differences
  - Effect size (Cohen's d)
"""

from typing import Dict, List, Tuple, Any, Optional
import numpy as np
import pandas as pd
from scipy import stats


def run_paired_comparison_tests(
    series_a: pd.Series,
    series_b: pd.Series,
    label_a: str,
    label_b: str
) -> Dict[str, Any]:
    """
    Executes a comprehensive battery of paired statistical tests between series A and B.
    Difference is defined as diff = series_a - series_b (positive = B is faster than A).
    """
    diff = series_a - series_b
    n = len(diff)
    mean_diff = float(diff.mean())
    median_diff = float(diff.median())
    std_diff = float(diff.std())
    se_diff = std_diff / np.sqrt(n)
    ci95_low = mean_diff - 1.96 * se_diff
    ci95_high = mean_diff + 1.96 * se_diff

    # Effect size (Cohen's d)
    cohens_d = mean_diff / std_diff if std_diff > 1e-6 else 0.0

    # Normality test (D'Agostino-Pearson)
    if n >= 20:
        stat_norm, p_norm = stats.normaltest(diff)
        is_normal = (p_norm >= 0.05)
    else:
        stat_norm, p_norm = stats.shapiro(diff)
        is_normal = (p_norm >= 0.05)

    # Paired Student's t-test
    t_stat, t_pval = stats.ttest_rel(series_a, series_b)

    # Wilcoxon signed-rank test (exclude zero ties)
    non_zero_diff = diff[diff.abs() > 1e-4]
    if len(non_zero_diff) > 0:
        w_stat, w_pval = stats.wilcoxon(non_zero_diff)
    else:
        w_stat, w_pval = np.nan, 1.0

    # Recommended test justification
    primary_test = "Wilcoxon Signed-Rank Test" if not is_normal else "Paired Student's t-test"
    primary_pval = w_pval if not is_normal else t_pval
    sig_str = "Statistically Significant (p < 0.01)" if primary_pval < 0.01 else (
        "Statistically Significant (p < 0.05)" if primary_pval < 0.05 else "Not Significant (p >= 0.05)"
    )

    return {
        'comparison': f"{label_b} vs {label_a}",
        'sample_size': n,
        'mean_difference_s': round(mean_diff, 2),
        'median_difference_s': round(median_diff, 2),
        'std_difference_s': round(std_diff, 2),
        'ci95_lower_s': round(ci95_low, 2),
        'ci95_upper_s': round(ci95_high, 2),
        'cohens_d': round(cohens_d, 4),
        'normality_test_p_value': float(f"{p_norm:.4e}") if p_norm < 1e-4 else round(float(p_norm), 4),
        'is_normal_distribution': bool(is_normal),
        'paired_t_statistic': round(t_stat, 4),
        'paired_t_p_value': float(f"{t_pval:.4e}") if t_pval < 1e-4 else round(float(t_pval), 4),
        'wilcoxon_w_statistic': round(w_stat, 1) if not np.isnan(w_stat) else np.nan,
        'wilcoxon_p_value': float(f"{w_pval:.4e}") if w_pval < 1e-4 else round(float(w_pval), 4),
        'recommended_primary_test': primary_test,
        'significance_verdict': sig_str
    }


def run_all_statistical_tests(
    df_runs: pd.DataFrame,
    df_replay: Optional[pd.DataFrame] = None
) -> pd.DataFrame:
    """
    Conducts paired hypothesis tests across all core comparisons.
    """
    records = []

    # 1. LightGBM vs Static
    records.append(run_paired_comparison_tests(
        df_runs['static_actual_time_s'],
        df_runs['lightgbm_actual_time_s'],
        'Static Baseline',
        'LightGBM Prediction'
    ))

    # 2. Historical vs Static
    records.append(run_paired_comparison_tests(
        df_runs['static_actual_time_s'],
        df_runs['historical_actual_time_s'],
        'Static Baseline',
        'Historical Baseline'
    ))

    # 3. Persistence vs Static
    records.append(run_paired_comparison_tests(
        df_runs['static_actual_time_s'],
        df_runs['persistence_actual_time_s'],
        'Static Baseline',
        'Persistence Prediction'
    ))

    # 4. LightGBM vs Historical
    records.append(run_paired_comparison_tests(
        df_runs['historical_actual_time_s'],
        df_runs['lightgbm_actual_time_s'],
        'Historical Baseline',
        'LightGBM Prediction'
    ))

    # 5. LightGBM vs Persistence
    records.append(run_paired_comparison_tests(
        df_runs['persistence_actual_time_s'],
        df_runs['lightgbm_actual_time_s'],
        'Persistence Prediction',
        'LightGBM Prediction'
    ))

    # 6. Current-Traffic Oracle vs Static
    records.append(run_paired_comparison_tests(
        df_runs['static_actual_time_s'],
        df_runs['oracle_actual_time_s'],
        'Static Baseline',
        'Current-Traffic Oracle'
    ))

    # 7. Dynamic Rerouting vs No Rerouting (Replay)
    if df_replay is not None:
        records.append(run_paired_comparison_tests(
            df_replay['total_time_no_reroute_s'],
            df_replay['total_time_dynamic_s'],
            'No Rerouting (Baseline)',
            'GeoPulse Dynamic Reroute'
        ))

    return pd.DataFrame(records)
