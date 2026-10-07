"""
GeoPulse Phase 10: Dynamic Rerouting Ablation Engine (Experiment B)

Evaluates dynamic rerouting policies on the canonical replay scenarios:
  B1: No Rerouting (Counterfactual Baseline)
  B2: Always Reroute (Unrestricted: threshold >= 0s, >= 0%)
  B3: Percentage Threshold Only (1%, 3%, 5%, 10%)
  B4: Absolute Time Threshold Only (5s, 10s, 20s, 30s)
  B5: Final Dual Threshold (>= 10s AND >= 3.0%)
"""

from typing import Dict, List, Tuple, Any, Optional
import numpy as np
import pandas as pd


def evaluate_rerouting_policy(
    replay_df: pd.DataFrame,
    threshold_s: float,
    threshold_pct: float,
    policy_name: str
) -> Dict[str, Any]:
    """
    Evaluates a specific rerouting threshold policy across the replay journeys.

    Parameters
    ----------
    replay_df : pd.DataFrame
        Replay dataframe containing scenario metadata and candidate alternatives.
    threshold_s : float
        Absolute threshold in seconds.
    threshold_pct : float
        Percentage threshold relative to remaining route travel time.
    policy_name : str
        Human-readable policy name.

    Returns
    -------
    dict containing aggregated performance metrics.
    """
    n_total = len(replay_df)
    triggers = []
    savings = []
    imp_pcts = []
    journey_times = []
    overlaps = []
    changed_edges = []
    beneficial_count = 0
    detrimental_count = 0

    for _, r in replay_df.iterrows():
        t_no = float(r['total_time_no_reroute_s'])
        t_alt = float(r['best_current_route_time_s'])
        pot_sav_s = max(t_no - t_alt, 0.0)

        # Remaining travel time on R0 at decision point
        # In replay_df, decision occurred at step k.
        # pot_saving_pct was logged or computed from potential saving
        if pot_sav_s > 0 and 'decision_step' in r and t_no > 0:
            # If r has logged potential saving %, use it; otherwise compute from remaining time
            if 'potential_saving_pct' in r:
                pot_sav_pct = float(r['potential_saving_pct'])
            else:
                # Approximate from remaining fraction or improvement pct
                pot_sav_pct = (pot_sav_s / t_no) * 100.0 * (1.0 / max(1.0 - float(r.get('decision_frac', 0.33)), 0.1))
                # Bound between imp_pct and 100%
                pot_sav_pct = max(float(r.get('improvement_pct', 0.0)), pot_sav_pct)
        else:
            pot_sav_pct = 0.0

        # Special case: check if scenario had exact trigger reason in Phase 9
        # E.g. "Alternative saves 84.9s (9.2%)" -> exact pct is 9.2%
        if 'trigger_reason' in r and '(' in str(r['trigger_reason']) and '%)' in str(r['trigger_reason']):
            try:
                tr_str = str(r['trigger_reason'])
                pct_str = tr_str.split('(')[1].split('%')[0]
                pot_sav_pct = float(pct_str)
            except Exception:
                pass

        # Check threshold gating
        should_trigger = (pot_sav_s >= threshold_s) and (pot_sav_pct >= threshold_pct) and (pot_sav_s > 0.01)

        if should_trigger:
            triggers.append(True)
            j_time = t_alt
            sav = pot_sav_s
            pct = (sav / t_no) * 100.0 if t_no > 0 else 0.0
            ov = float(r['route_overlap_before_after'])
            ce = int(r.get('changed_edges_count', 1))

            if sav > 0.01:
                beneficial_count += 1
            elif sav < -0.01:
                detrimental_count += 1
        else:
            triggers.append(False)
            j_time = t_no
            sav = 0.0
            pct = 0.0
            ov = 1.0
            ce = 0

        savings.append(sav)
        imp_pcts.append(pct)
        journey_times.append(j_time)
        overlaps.append(ov)
        changed_edges.append(ce)

    trig_count = sum(triggers)
    trig_freq = (trig_count / n_total) * 100.0
    mean_sav = float(np.mean(savings))
    median_sav = float(np.median(savings))
    mean_imp = float(np.mean(imp_pcts))
    median_imp = float(np.median(imp_pcts))
    mean_time = float(np.mean(journey_times))
    mean_ov = float(np.mean(overlaps))
    mean_ce = float(np.mean(changed_edges))

    # Mean saving strictly when triggered
    if trig_count > 0:
        triggered_savings = [s for t, s in zip(triggers, savings) if t]
        triggered_imp = [p for t, p in zip(triggers, imp_pcts) if t]
        mean_sav_when_trig = float(np.mean(triggered_savings))
        mean_imp_when_trig = float(np.mean(triggered_imp))
    else:
        mean_sav_when_trig = 0.0
        mean_imp_when_trig = 0.0

    return {
        'policy': policy_name,
        'threshold_seconds': threshold_s,
        'threshold_percent': threshold_pct,
        'sample_count': n_total,
        'reroute_count': trig_count,
        'reroute_frequency_pct': round(trig_freq, 2),
        'beneficial_reroutes_count': beneficial_count,
        'detrimental_reroutes_count': detrimental_count,
        'beneficial_reroute_rate_pct': round((beneficial_count / trig_count * 100.0) if trig_count > 0 else 0.0, 2),
        'detrimental_reroute_rate_pct': round((detrimental_count / trig_count * 100.0) if trig_count > 0 else 0.0, 2),
        'mean_saving_seconds_overall': round(mean_sav, 2),
        'median_saving_seconds_overall': round(median_sav, 2),
        'mean_improvement_pct_overall': round(mean_imp, 2),
        'median_improvement_pct_overall': round(median_imp, 2),
        'mean_saving_seconds_when_rerouted': round(mean_sav_when_trig, 2),
        'mean_improvement_pct_when_rerouted': round(mean_imp_when_trig, 2),
        'mean_journey_time_s': round(mean_time, 2),
        'mean_route_overlap': round(mean_ov, 4),
        'mean_changed_edges': round(mean_ce, 2)
    }


def run_dynamic_rerouting_ablation(replay_df: pd.DataFrame) -> pd.DataFrame:
    """
    Runs Experiment B: Evaluates all defined policies.
    """
    policies = [
        # B1: No Rerouting
        (float('inf'), float('inf'), 'B1: No Rerouting (Baseline)'),
        # B2: Always Reroute
        (0.0, 0.0, 'B2: Always Reroute (Unrestricted)'),
        # B3: Percentage threshold only
        (0.0, 1.0, 'B3: Pct Only (>= 1%)'),
        (0.0, 3.0, 'B3: Pct Only (>= 3%)'),
        (0.0, 5.0, 'B3: Pct Only (>= 5%)'),
        (0.0, 10.0, 'B3: Pct Only (>= 10%)'),
        # B4: Absolute time threshold only
        (5.0, 0.0, 'B4: Abs Only (>= 5s)'),
        (10.0, 0.0, 'B4: Abs Only (>= 10s)'),
        (20.0, 0.0, 'B4: Abs Only (>= 20s)'),
        (30.0, 0.0, 'B4: Abs Only (>= 30s)'),
        # B5: Final Dual Threshold
        (10.0, 3.0, 'B5: Dual Threshold (>= 10s AND >= 3%) [GeoPulse]')
    ]

    records = []
    for th_s, th_pct, name in policies:
        res = evaluate_rerouting_policy(replay_df, th_s, th_pct, name)
        records.append(res)

    return pd.DataFrame(records)
