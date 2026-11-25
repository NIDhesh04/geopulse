"""Statistical evaluation, paired hypothesis testing, and report generation for Stage 3."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
import numpy as np
import pandas as pd
from scipy import stats

from src.experiments.temporal_journey import STRATEGIES


TIE_ABS_THRESHOLD_S = 1.0
TIE_PCT_THRESHOLD = 0.001  # 0.1%


def summarize_numeric(series: pd.Series) -> Dict[str, Optional[float]]:
    """Compute Mean, Median, Std, P95, Min, Max for a numeric series."""
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if len(clean) == 0:
        return {
            "mean": None, "median": None, "std": None,
            "p95": None, "min": None, "max": None,
        }
    return {
        "mean": round(float(clean.mean()), 4),
        "median": round(float(clean.median()), 4),
        "std": round(float(clean.std(ddof=1)), 4) if len(clean) > 1 else 0.0,
        "p95": round(float(np.percentile(clean, 95)), 4),
        "min": round(float(clean.min()), 4),
        "max": round(float(clean.max()), 4),
    }


def compute_strategy_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Compute strategy-level summary statistics (never treating failed runs as 0s)."""
    rows: List[Dict[str, Any]] = []
    metric_specs = [
        ("travel_time_s", True),
        ("distance_m", True),
        ("route_changes", False),
        ("prediction_updates_applied", False),
        ("two_edge_alternative_selections", False),
        ("forced_single_edge_decisions", False),
        ("dijkstra_fallback_steps", False),
        ("backtracking_events", False),
        ("repeated_node_visits", False),
        ("loop_traps", False),
        ("incomplete_decisions", False),
        ("mean_decision_latency_ms", False),
        ("mean_two_edge_decision_latency_ms", False),
        ("execution_time_s", False),
        ("traversed_dynamic_coverage_pct", True),
    ]

    for strategy in STRATEGIES:
        sdf = df[df["strategy"] == strategy]
        completed = sdf[sdf["success"].astype(bool)]
        total_n = len(sdf)
        comp_n = len(completed)
        fail_n = total_n - comp_n

        row: Dict[str, Any] = {
            "strategy": strategy,
            "total_runs": int(total_n),
            "completed_runs": int(comp_n),
            "failed_runs": int(fail_n),
            "completion_rate_pct": round(100.0 * comp_n / total_n, 2) if total_n else 0.0,
            "two_edge_only_completed": int(
                sdf["two_edge_only_success"].map(lambda v: v is True or str(v).strip().lower() == "true").sum()
            ) if "two_edge_only_success" in sdf.columns else 0,
        }

        for col, completed_only in metric_specs:
            src = completed[col] if (completed_only and col in completed.columns) else sdf.get(col, pd.Series(dtype=float))
            s = summarize_numeric(src)
            for stat_name, val in s.items():
                row[f"{col}_{stat_name}"] = val

        # Exact integer totals for event counters across all runs
        for count_col in (
            "route_changes",
            "prediction_updates_applied",
            "intersection_decisions",
            "two_edge_alternative_selections",
            "forced_single_edge_decisions",
            "dijkstra_reroutes",
            "dijkstra_fallback_steps",
            "backtracking_events",
            "repeated_node_visits",
            "loop_traps",
            "incomplete_decisions",
        ):
            if count_col in sdf.columns:
                row[f"total_{count_col}"] = int(pd.to_numeric(sdf[count_col], errors="coerce").fillna(0).sum())

        rows.append(row)
    return pd.DataFrame(rows)


def paired_comparison(
    df: pd.DataFrame,
    baseline_strategy: str,
    test_strategy: str,
    tie_abs_s: float = TIE_ABS_THRESHOLD_S,
    tie_pct: float = TIE_PCT_THRESHOLD,
) -> Dict[str, Any]:
    """Perform strict paired head-to-head comparison on identical scenario_ids."""
    base_all = df[df["strategy"] == baseline_strategy]
    test_all = df[df["strategy"] == test_strategy]

    merged_all = base_all.merge(
        test_all,
        on=["scenario_id", "od_id", "departure_timestamp"],
        suffixes=("_base", "_test"),
        how="inner",
    )

    total_scenarios = len(merged_all)
    if total_scenarios == 0:
        return {
            "comparison": f"{test_strategy}_vs_{baseline_strategy}",
            "baseline_strategy": baseline_strategy,
            "test_strategy": test_strategy,
            "total_scenarios": 0,
            "paired_completed_count": 0,
        }

    base_ok = merged_all["success_base"].astype(bool)
    test_ok = merged_all["success_test"].astype(bool)
    both_ok = merged_all[base_ok & test_ok]
    test_only = int((test_ok & ~base_ok).sum())
    base_only = int((~test_ok & base_ok).sum())
    both_fail = int((~test_ok & ~base_ok).sum())

    base_rate = 100.0 * float(base_ok.mean())
    test_rate = 100.0 * float(test_ok.mean())

    out: Dict[str, Any] = {
        "comparison": f"{test_strategy}_vs_{baseline_strategy}",
        "baseline_strategy": baseline_strategy,
        "test_strategy": test_strategy,
        "total_scenarios": int(total_scenarios),
        "paired_completed_count": int(len(both_ok)),
        "test_only_completed": test_only,
        "baseline_only_completed": base_only,
        "both_failed": both_fail,
        "baseline_completion_rate_pct": round(base_rate, 2),
        "test_completion_rate_pct": round(test_rate, 2),
        "completion_rate_diff_pct": round(test_rate - base_rate, 2),
    }

    if len(both_ok) == 0:
        return out

    base_t = both_ok["travel_time_s_base"].to_numpy(dtype=float)
    test_t = both_ok["travel_time_s_test"].to_numpy(dtype=float)
    diffs = base_t - test_t  # Positive => test is faster
    thresholds = np.maximum(tie_abs_s, tie_pct * base_t)

    wins = int(np.sum(diffs > thresholds))
    losses = int(np.sum(diffs < -thresholds))
    ties = int(len(diffs) - wins - losses)
    n = len(diffs)

    valid_base = base_t > 0
    impr_pct = np.where(valid_base, (diffs / np.where(valid_base, base_t, 1.0)) * 100.0, 0.0)

    out.update({
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "win_pct": round(100.0 * wins / n, 2),
        "loss_pct": round(100.0 * losses / n, 2),
        "tie_pct": round(100.0 * ties / n, 2),
        "mean_base_time_s": round(float(np.mean(base_t)), 3),
        "median_base_time_s": round(float(np.median(base_t)), 3),
        "p95_base_time_s": round(float(np.percentile(base_t, 95)), 3),
        "mean_test_time_s": round(float(np.mean(test_t)), 3),
        "median_test_time_s": round(float(np.median(test_t)), 3),
        "p95_test_time_s": round(float(np.percentile(test_t, 95)), 3),
        "mean_abs_time_diff_s": round(float(np.mean(diffs)), 4),
        "median_abs_time_diff_s": round(float(np.median(diffs)), 4),
        "mean_improvement_pct": round(float(np.mean(impr_pct)), 4),
        "median_improvement_pct": round(float(np.median(impr_pct)), 4),
    })

    # Paired statistical hypothesis testing
    std_diff = float(np.std(diffs, ddof=1)) if n > 1 else 0.0
    out["cohens_d"] = round(float(np.mean(diffs)) / std_diff, 4) if std_diff > 1e-12 else 0.0

    if n >= 3:
        se = std_diff / np.sqrt(n)
        t_crit = float(stats.t.ppf(0.975, df=n - 1))
        mean_d = float(np.mean(diffs))
        out["ci95_time_diff_lower_s"] = round(mean_d - t_crit * se, 4)
        out["ci95_time_diff_upper_s"] = round(mean_d + t_crit * se, 4)

        if std_diff > 1e-12:
            if n >= 20:
                _, p_norm = stats.normaltest(diffs)
            else:
                _, p_norm = stats.shapiro(diffs)
            is_norm = bool(p_norm >= 0.05)
            t_stat, t_pval = stats.ttest_rel(base_t, test_t)
            nz = diffs[np.abs(diffs) > 1e-6]
            if len(nz) > 0:
                w_stat, w_pval = stats.wilcoxon(nz)
            else:
                w_stat, w_pval = np.nan, 1.0
            primary_test = "Paired Student's t-test" if is_norm else "Wilcoxon Signed-Rank Test"
            primary_p = float(t_pval if is_norm else w_pval)
            out.update({
                "normality_p_value": round(float(p_norm), 6),
                "is_normal_diff": is_norm,
                "paired_t_statistic": round(float(t_stat), 4),
                "paired_t_p_value": round(float(t_pval), 6),
                "wilcoxon_statistic": round(float(w_stat), 2) if not np.isnan(w_stat) else None,
                "wilcoxon_p_value": round(float(w_pval), 6),
                "primary_test": primary_test,
                "primary_p_value": round(primary_p, 6),
                "statistically_significant_0_05": bool(primary_p < 0.05),
            })
        else:
            out.update({
                "normality_p_value": None,
                "is_normal_diff": None,
                "paired_t_statistic": 0.0,
                "paired_t_p_value": 1.0,
                "wilcoxon_statistic": None,
                "wilcoxon_p_value": 1.0,
                "primary_test": "Identical Outcomes (Zero Variance)",
                "primary_p_value": 1.0,
                "statistically_significant_0_05": False,
            })

    return out


def compute_head_to_head(df: pd.DataFrame) -> pd.DataFrame:
    """Return paired comparisons for all three required baseline/test pairs."""
    return pd.DataFrame([
        paired_comparison(df, "static_dijkstra", "geopulse_two_edge"),
        paired_comparison(df, "dynamic_dijkstra", "geopulse_two_edge"),
        paired_comparison(df, "static_dijkstra", "dynamic_dijkstra"),
    ])


def _group_breakdown(
    df: pd.DataFrame,
    group_col: str,
    categories: Sequence[str],
) -> Dict[str, Any]:
    groups: Dict[str, Any] = {}
    for cat in categories:
        sub = df[df[group_col] == cat]
        if sub.empty:
            continue
        entry: Dict[str, Any] = {
            "scenario_count": int(sub["scenario_id"].nunique()),
            "strategies": {},
        }
        for strategy in STRATEGIES:
            s_all = sub[sub["strategy"] == strategy]
            s_comp = s_all[s_all["success"].astype(bool)]
            tt = pd.to_numeric(s_comp.get("travel_time_s", pd.Series(dtype=float)), errors="coerce").dropna()
            cov = pd.to_numeric(s_comp.get("traversed_dynamic_coverage_pct", pd.Series(dtype=float)), errors="coerce").dropna()
            lat = pd.to_numeric(s_all.get("mean_decision_latency_ms", pd.Series(dtype=float)), errors="coerce").dropna()
            fb = pd.to_numeric(s_all.get("dijkstra_fallback_steps", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
            alt = pd.to_numeric(s_all.get("two_edge_alternative_selections", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
            entry["strategies"][strategy] = {
                "total_runs": int(len(s_all)),
                "completed_runs": int(len(s_comp)),
                "completion_rate_pct": round(100.0 * len(s_comp) / len(s_all), 2) if len(s_all) else 0.0,
                "mean_travel_time_s": round(float(tt.mean()), 2) if len(tt) else None,
                "median_travel_time_s": round(float(tt.median()), 2) if len(tt) else None,
                "p95_travel_time_s": round(float(np.percentile(tt, 95)), 2) if len(tt) else None,
                "mean_traversed_coverage_pct": round(float(cov.mean()), 2) if len(cov) else None,
                "total_dijkstra_fallbacks": int(fb),
                "total_alternative_selections": int(alt),
                "mean_decision_latency_ms": round(float(lat.mean()), 4) if len(lat) else None,
            }
        entry["geopulse_vs_static"] = paired_comparison(sub, "static_dijkstra", "geopulse_two_edge")
        entry["geopulse_vs_dynamic"] = paired_comparison(sub, "dynamic_dijkstra", "geopulse_two_edge")
        entry["dynamic_vs_static"] = paired_comparison(sub, "static_dijkstra", "dynamic_dijkstra")
        groups[cat] = entry
    return groups


def compute_coverage_and_length_report(
    df: pd.DataFrame,
    network_total_edges: int,
    network_dynamic_edges: int,
) -> Dict[str, Any]:
    """Compute coverage-wise and journey-length-wise breakdown report."""
    net_cov_pct = (100.0 * network_dynamic_edges / network_total_edges) if network_total_edges else 0.0
    trav_cov = pd.to_numeric(
        df.loc[df["success"].astype(bool), "traversed_dynamic_coverage_pct"], errors="coerce"
    ).dropna()
    return {
        "network_coverage": {
            "total_directed_edges": int(network_total_edges),
            "dynamically_mapped_edges": int(network_dynamic_edges),
            "network_dynamic_coverage_pct": round(net_cov_pct, 4),
            "note": (
                "Only a small subset of Bhubaneswar OSM edges have dynamic sensor mapping; "
                "all remaining edges use deterministic static highway-class speeds."
            ),
        },
        "traversed_route_coverage_summary": summarize_numeric(trav_cov),
        "coverage_groups": _group_breakdown(df, "od_coverage_category", ("low", "medium", "high")),
        "distance_groups": _group_breakdown(df, "od_distance_category", ("short", "medium", "long")),
    }


def generate_benchmark_report(
    manifest: Dict[str, Any],
    od_df: pd.DataFrame,
    results_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    h2h_df: pd.DataFrame,
    coverage_report: Dict[str, Any],
) -> str:
    """Generate comprehensive 16-section benchmark_report.md backed strictly by measured outputs."""
    lines: List[str] = []
    exp_id = manifest["experiment_id"]
    lines.append("# GeoPulse Stage 3 — Large-Scale Temporal Benchmark Report\n")
    lines.append(f"- **Experiment ID:** `{exp_id}`")
    lines.append(f"- **Execution Timestamp (UTC):** `{manifest['execution_timestamp']}`")
    if manifest.get("git_commit"):
        lines.append(f"- **Git Commit:** `{manifest['git_commit']}`")
    lines.append(f"- **Random Seed:** `{manifest['random_seed']}`")
    lines.append(f"- **Reproduction Command:** `{manifest['reproduction_command']}`\n")

    # Helper lookups
    sum_map = {row["strategy"]: row for _, row in summary_df.iterrows()}
    h2h_map = {row["comparison"]: row for _, row in h2h_df.iterrows()}

    # 1. Executive Summary
    lines.append("## 1. Executive Summary\n")
    lines.append(
        f"This benchmark evaluates **Static Dijkstra**, **Dynamic Dijkstra**, and **GeoPulse (Sequential Two-Edge Selection)** "
        f"across **{manifest['od_count']} OD pairs** × **{manifest['departure_count']} departure timestamps** = "
        f"**{manifest['scenario_count']} paired scenarios** (**{manifest['strategy_run_count']} journey executions**) "
        f"on the real Bhubaneswar OSM drive network (`{manifest['graph_statistics']['nodes']:,}` nodes, "
        f"`{manifest['graph_statistics']['directed_edges']:,}` directed edges).\n"
    )
    gp_st = h2h_map.get("geopulse_two_edge_vs_static_dijkstra", {})
    gp_dy = h2h_map.get("geopulse_two_edge_vs_dynamic_dijkstra", {})
    dy_st = h2h_map.get("dynamic_dijkstra_vs_static_dijkstra", {})
    lines.append(
        f"- **GeoPulse vs Static Dijkstra:** {gp_st.get('wins', 0)} wins / {gp_st.get('losses', 0)} losses / "
        f"{gp_st.get('ties', 0)} ties ({gp_st.get('paired_completed_count', 0)} paired; "
        f"mean improvement: {gp_st.get('mean_improvement_pct', 0.0):.4f}%)."
    )
    lines.append(
        f"- **GeoPulse vs Dynamic Dijkstra:** {gp_dy.get('wins', 0)} wins / {gp_dy.get('losses', 0)} losses / "
        f"{gp_dy.get('ties', 0)} ties ({gp_dy.get('paired_completed_count', 0)} paired; "
        f"mean improvement: {gp_dy.get('mean_improvement_pct', 0.0):.4f}%)."
    )
    lines.append(
        f"- **Dynamic Dijkstra vs Static Dijkstra:** {dy_st.get('wins', 0)} wins / {dy_st.get('losses', 0)} losses / "
        f"{dy_st.get('ties', 0)} ties ({dy_st.get('paired_completed_count', 0)} paired; "
        f"mean improvement: {dy_st.get('mean_improvement_pct', 0.0):.4f}%).\n"
    )

    # 2. Research Objective
    lines.append("## 2. Research Objective\n")
    lines.append(
        "Determine under strictly controlled, paired experimental conditions whether GeoPulse's intersection-level "
        "sequential two-edge selection reduces realized journey travel time compared with fixed-route Static Dijkstra "
        "and update-triggered full-recomputation Dynamic Dijkstra when navigating dynamic predicted traffic and realized "
        "observed road speeds.\n"
    )

    # 3. Experimental Setup
    lines.append("## 3. Experimental Setup\n")
    lines.append("- Identical directed graph, edge lengths, static fallback speeds, and dynamic traffic mapping per scenario.")
    lines.append("- Identical origin node, destination node, and UTC departure timestamp across all three strategies.")
    lines.append("- Identical Phase 7 hourly predicted-speed frames (for routing choices) and realized observed-speed timeline (for physical movement).")
    lines.append(f"- Tie definition: `|baseline_time - test_time| <= max({TIE_ABS_THRESHOLD_S}s, {TIE_PCT_THRESHOLD*100:.1f}% of baseline_time)`.\n")

    # 4. Dataset and Graph Description
    lines.append("## 4. Dataset and Graph Description\n")
    net_cov = coverage_report["network_coverage"]
    lines.append(f"- **Graph File:** `{manifest['graph_file']}`")
    lines.append(f"- **Nodes / Directed Edges:** {net_cov['total_directed_edges']:,} directed edges across {manifest['graph_statistics']['nodes']:,} nodes "
                 f"(largest SCC: {manifest['graph_statistics']['largest_scc_nodes']:,} nodes).")
    lines.append(f"- **Dynamic Mapping:** `{manifest['dataset_paths']['mapping']}` maps "
                 f"**{net_cov['dynamically_mapped_edges']}** directed edges (**{net_cov['network_dynamic_coverage_pct']:.2f}%** of network edges).")
    lines.append(f"- **Prediction & Realized Stream:** `{manifest['prediction_artifact_path']}` "
                 f"({manifest['data_time_horizon']['frame_count']} hourly frames; origin `{manifest['data_time_horizon']['origin_start_utc']}` -> "
                 f"`{manifest['data_time_horizon']['origin_end_utc']}`; target-valid `{manifest['data_time_horizon']['target_valid_start_utc']}` -> "
                 f"`{manifest['data_time_horizon']['target_valid_end_utc']}`, final realized boundary `{manifest['data_time_horizon']['final_valid_until_utc']}`).\n")

    # 5. OD Selection Methodology
    lines.append("## 5. OD Selection Methodology\n")
    lines.append(
        "Candidate nodes were sampled deterministically (`seed={}`) across both dynamically monitored intersections and general SCC intersections, "
        "using single-source Dijkstra trees to verify directed reachability and stratify OD pairs across all distance bins "
        "(short `<5 km`, medium `5–15 km`, long `>=15 km`) and route-specific dynamic coverage bins (low `<30%`, medium `30–70%`, high `>=70%`).\n"
        .format(manifest["random_seed"])
    )
    if not od_df.empty:
        lines.append("**Selected OD Distribution:**\n")
        lines.append(f"- Distance bins: {od_df['distance_category'].value_counts().to_dict()}")
        lines.append(f"- Coverage bins: {od_df['coverage_category'].value_counts().to_dict()}\n")

    # 6. Temporal Validity and Horizon Handling
    lines.append("## 6. Temporal Validity and Horizon Handling\n")
    lines.append(
        "- Each prediction frame (`origin_timestamp`) becomes valid at `target_valid_timestamp = origin_timestamp + 1h` and remains active over `[target_valid_timestamp, next_hour)`.\n"
        "- `predicted_speed` guides routing decisions only; `actual_speed` (aligned observed `currentSpeed` at the target hour) drives vehicle physics and integrates across hour boundaries.\n"
        "- Traffic prediction updates affect route choices only at the next reached intersection after `target_valid_timestamp`.\n"
        "- Journeys reaching `final_valid_until` without arriving terminate immediately as incomplete (`realized_traffic_unavailable`).\n"
    )
    lines.append("**Selected Departure Timestamps (UTC / IST):**\n")
    for dep in manifest["departure_schedules"]:
        lines.append(f"- `{dep['departure_utc']}` ({dep['ist_time']} — {dep['period_label']})")
    lines.append("")

    # 7. Strategy Definitions
    lines.append("## 7. Strategy Definitions\n")
    lines.append("1. **Static Dijkstra (`static_dijkstra`):** Computes one shortest path at departure using departure-frame predicted speeds and never reroutes.")
    lines.append("2. **Dynamic Dijkstra (`dynamic_dijkstra`):** Recomputes full shortest path from the current node whenever arriving at an intersection after a new hourly forecast becomes valid.")
    lines.append("3. **GeoPulse Two-Edge (`geopulse_two_edge`):** At every intersection, evaluates Candidate A (planned next edge) vs Candidate B (best destination-reachable alternative) using `predicted_edge_time + exact Dijkstra remaining tail cost`, switching when strictly beneficial while preserving loop avoidance and Dijkstra safety fallbacks.\n")

    # 8. Evaluation Metrics
    lines.append("## 8. Evaluation Metrics\n")
    lines.append(
        "Journey-level instrumentation records completion status, realized travel time (s), actual distance (m), traffic updates applied, "
        "route changes, two-edge decisions, alternative selections, forced single-edge decisions, Dijkstra safety fallbacks, "
        "backtracking events, repeated-node visits, loop traps, incomplete decisions, decision latencies (mean/P95/max ms), wall execution time, "
        "and actually traversed dynamic edge coverage (%).\n"
    )

    # 9. Overall Results
    lines.append("## 9. Overall Results\n")
    lines.append("| Strategy | Completed / Total | Completion % | Mean Time (s) | Median Time (s) | P95 Time (s) | Std Time (s) | Mean Dist (m) | Mean Traversed Cov (%) |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for strat in STRATEGIES:
        r = sum_map.get(strat, {})
        lines.append(
            f"| `{strat}` | {r.get('completed_runs', 0)}/{r.get('total_runs', 0)} | {r.get('completion_rate_pct', 0):.2f}% | "
            f"{r.get('travel_time_s_mean', 'N/A')} | {r.get('travel_time_s_median', 'N/A')} | "
            f"{r.get('travel_time_s_p95', 'N/A')} | {r.get('travel_time_s_std', 'N/A')} | "
            f"{r.get('distance_m_mean', 'N/A')} | {r.get('traversed_dynamic_coverage_pct_mean', 'N/A')} |"
        )
    lines.append("")

    # 10. Paired Head-to-Head Comparison
    lines.append("## 10. Paired Head-to-Head Comparison\n")
    lines.append("| Comparison | Paired | Wins | Losses | Ties | Win % | Mean Diff (s) | Mean Impr (%) | Median Impr (%) | Primary Test | p-value |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|")
    for _, r in h2h_df.iterrows():
        lines.append(
            f"| `{r.get('comparison')}` | {r.get('paired_completed_count', 0)} | {r.get('wins', 0)} | "
            f"{r.get('losses', 0)} | {r.get('ties', 0)} | {r.get('win_pct', 0):.2f}% | "
            f"{r.get('mean_abs_time_diff_s', 'N/A')} | {r.get('mean_improvement_pct', 'N/A')} | "
            f"{r.get('median_improvement_pct', 'N/A')} | {r.get('primary_test', 'N/A')} | {r.get('primary_p_value', 'N/A')} |"
        )
    lines.append("")

    # 11. Coverage-Wise Results
    lines.append("## 11. Coverage-Wise Results\n")
    lines.append("| Coverage Bin | Scenarios | Static Mean (s) | Dynamic Mean (s) | GeoPulse Mean (s) | GP vs Static (W/L/T, Impr%) | GP vs Dynamic (W/L/T, Impr%) |")
    lines.append("|---|---:|---:|---:|---:|---|---|")
    for cov_bin in ("low", "medium", "high"):
        g = coverage_report.get("coverage_groups", {}).get(cov_bin)
        if not g:
            continue
        st_m = g["strategies"]["static_dijkstra"]["mean_travel_time_s"]
        dy_m = g["strategies"]["dynamic_dijkstra"]["mean_travel_time_s"]
        gp_m = g["strategies"]["geopulse_two_edge"]["mean_travel_time_s"]
        gs = g["geopulse_vs_static"]
        gd = g["geopulse_vs_dynamic"]
        lines.append(
            f"| `{cov_bin}` | {g['scenario_count']} | {st_m} | {dy_m} | {gp_m} | "
            f"{gs.get('wins', 0)}/{gs.get('losses', 0)}/{gs.get('ties', 0)} ({gs.get('mean_improvement_pct', 0):.3f}%) | "
            f"{gd.get('wins', 0)}/{gd.get('losses', 0)}/{gd.get('ties', 0)} ({gd.get('mean_improvement_pct', 0):.3f}%) |"
        )
    lines.append("")

    # 12. Journey-Length-Wise Results
    lines.append("## 12. Journey-Length-Wise Results\n")
    lines.append("| Distance Bin | Scenarios | Static Mean (s) | Dynamic Mean (s) | GeoPulse Mean (s) | GP vs Static (W/L/T, Impr%) | GP vs Dynamic (W/L/T, Impr%) |")
    lines.append("|---|---:|---:|---:|---:|---|---|")
    for d_bin in ("short", "medium", "long"):
        g = coverage_report.get("distance_groups", {}).get(d_bin)
        if not g:
            continue
        st_m = g["strategies"]["static_dijkstra"]["mean_travel_time_s"]
        dy_m = g["strategies"]["dynamic_dijkstra"]["mean_travel_time_s"]
        gp_m = g["strategies"]["geopulse_two_edge"]["mean_travel_time_s"]
        gs = g["geopulse_vs_static"]
        gd = g["geopulse_vs_dynamic"]
        lines.append(
            f"| `{d_bin}` | {g['scenario_count']} | {st_m} | {dy_m} | {gp_m} | "
            f"{gs.get('wins', 0)}/{gs.get('losses', 0)}/{gs.get('ties', 0)} ({gs.get('mean_improvement_pct', 0):.3f}%) | "
            f"{gd.get('wins', 0)}/{gd.get('losses', 0)}/{gd.get('ties', 0)} ({gd.get('mean_improvement_pct', 0):.3f}%) |"
        )
    lines.append("")

    # 13. Failure and Fallback Analysis
    lines.append("## 13. Failure and Fallback Analysis\n")
    failed_df = results_df[~results_df["success"].astype(bool)]
    if failed_df.empty:
        lines.append("- **Incomplete Journeys:** `0` across all strategy executions (100% completion rate).\n")
    else:
        lines.append(f"- **Total Incomplete Journeys:** {len(failed_df)}\n")
        for (strat, reason), cnt in failed_df.groupby(["strategy", "failure_reason"]).size().items():
            lines.append(f"  - `{strat}` — `{reason}`: {cnt}")
        lines.append("")
    gp_r = sum_map.get("geopulse_two_edge", {})
    lines.append(f"- **GeoPulse Two-Edge-Only Completions:** {gp_r.get('two_edge_only_completed', 0)} / {gp_r.get('total_runs', 0)}")
    lines.append(f"- **Total Two-Edge Decisions:** {gp_r.get('total_intersection_decisions', 0)}")
    lines.append(f"- **Total Alternative Selections:** {gp_r.get('total_two_edge_alternative_selections', 0)}")
    lines.append(f"- **Total Forced Single-Edge Continuations:** {gp_r.get('total_forced_single_edge_decisions', 0)}")
    lines.append(f"- **Total Route Changes:** {gp_r.get('total_route_changes', 0)}")
    lines.append(f"- **Total Dijkstra Safety Fallbacks:** {gp_r.get('total_dijkstra_fallback_steps', 0)}")
    lines.append(f"- **Total Backtracking Events:** {gp_r.get('total_backtracking_events', 0)}")
    lines.append(f"- **Total Repeated-Node Visits:** {gp_r.get('total_repeated_node_visits', 0)}")
    lines.append(f"- **Total Loop Traps:** {gp_r.get('total_loop_traps', 0)}\n")

    # 14. Computational Overhead
    lines.append("## 14. Computational Overhead\n")
    for strat in STRATEGIES:
        r = sum_map.get(strat, {})
        lines.append(
            f"- **`{strat}`:** mean wall execution = `{r.get('execution_time_s_mean', 'N/A')}s` "
            f"(P95 `{r.get('execution_time_s_p95', 'N/A')}s`), "
            f"mean decision latency = `{r.get('mean_decision_latency_ms_mean', 'N/A')} ms`, "
            f"two-edge mean latency = `{r.get('mean_two_edge_decision_latency_ms_mean', 'N/A')} ms`."
        )
    lines.append("")

    # 15. Limitations
    lines.append("## 15. Limitations\n")
    lines.append(f"1. **Sparse Sensor Coverage:** Dynamic speed mapping covers only **{net_cov['dynamically_mapped_edges']}/{net_cov['total_directed_edges']} ({net_cov['network_dynamic_coverage_pct']:.2f}%)** of directed OSM edges; all remaining road links use static highway speeds.")
    lines.append(f"2. **Limited Forecast Horizon:** Phase 7 predictions span **{manifest['data_time_horizon']['frame_count']} hours** (Jan 15–17, 2026), preventing multi-week seasonal evaluation.")
    lines.append("3. **Hourly Update Granularity:** Traffic forecasts update once per hour, so urban trips typically cross at most one forecast transition unless departed right before the hourly boundary.")
    lines.append("4. **No Microscopic Queueing:** Travel times integrate realized link speeds without intersection signal delays or turning penalties.\n")

    # 16. Conclusion
    lines.append("## 16. Conclusion\n")
    lines.append(
        "This Stage 3 benchmark measured realized journey travel times under identical graph, OD, prediction, and actual-speed conditions. "
        f"Against Static Dijkstra, GeoPulse achieved **{gp_st.get('wins', 0)} wins, {gp_st.get('losses', 0)} losses, and {gp_st.get('ties', 0)} ties** "
        f"(mean improvement `{gp_st.get('mean_improvement_pct', 0.0):.4f}%`, p=`{gp_st.get('primary_p_value', 'N/A')}`). "
        f"Against Dynamic Dijkstra, GeoPulse achieved **{gp_dy.get('wins', 0)} wins, {gp_dy.get('losses', 0)} losses, and {gp_dy.get('ties', 0)} ties** "
        f"(mean improvement `{gp_dy.get('mean_improvement_pct', 0.0):.4f}%`, p=`{gp_dy.get('primary_p_value', 'N/A')}`).\n"
    )
    if gp_dy.get("ties", 0) > gp_dy.get("wins", 0) and gp_dy.get("ties", 0) > gp_dy.get("losses", 0):
        lines.append(
            "Because GeoPulse evaluates predicted edge time plus the exact remaining Dijkstra tail cost using the same hourly forecast tensor as Dynamic Dijkstra, "
            "its realized routes closely match Dynamic Dijkstra when forecasts update once per hour—providing identical or near-identical travel times with "
            "higher per-intersection decision compute overhead.\n"
        )
    return "\n".join(lines)
