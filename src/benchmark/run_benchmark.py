"""GeoPulse Stage 3: Batch temporal benchmark runner.

Executes all three routing strategies (Static Dijkstra, Dynamic Dijkstra,
GeoPulse Two-Edge) across a set of OD pairs and departure times using the
existing TemporalJourneyEngine from Phase 4.

Each scenario shares identical inputs: graph, weights, replay frames,
departure time.  Predicted speeds guide routing decisions; realized
(actual) speeds determine actual journey time.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx
import numpy as np
import pandas as pd

from src.routing.traffic_weights import GraphWeightManager
from src.traffic.replay import HistoricalTrafficReplay
from src.experiments.temporal_journey import (
    STRATEGIES,
    TemporalJourneyEngine,
    TemporalJourneyResult,
)
from src.benchmark.od_selection import select_od_pairs

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DEFAULT_SEED = 42
DEFAULT_MAX_PAIRS = 50
DEFAULT_DEPARTURES_PER_OD = 5
DEFAULT_GRAPH_PATH = "data/raw/osm/bhubaneswar_drive.graphml"
DEFAULT_MAPPING_PATH = "data/processed/traffic_to_osm_mapping_final.parquet"
DEFAULT_PREDICTIONS_PATH = "results/phase7_predictions.parquet"


def _select_departure_times(
    available_timestamps: List[pd.Timestamp],
    max_departures: int = DEFAULT_DEPARTURES_PER_OD,
) -> List[pd.Timestamp]:
    """Select evenly-spaced departure times from the available replay horizon.

    The last timestamp is excluded as a departure time because the journey
    needs at least one frame of realized speed data after departure.
    """
    # Exclude the last frame — a journey starting there has no future data
    usable = available_timestamps[:-1] if len(available_timestamps) > 1 else available_timestamps
    if len(usable) <= max_departures:
        return list(usable)
    # Evenly space across the available horizon
    indices = np.linspace(0, len(usable) - 1, max_departures, dtype=int)
    return [usable[i] for i in indices]


def _build_engine(
    wm: GraphWeightManager,
    replay: HistoricalTrafficReplay,
    departure_ts: pd.Timestamp,
) -> TemporalJourneyEngine:
    """Build a TemporalJourneyEngine for journeys departing at departure_ts.

    We need contiguous hourly frames starting from the departure hour.
    The engine requires frames whose target_valid_timestamp covers the
    journey's temporal extent.
    """
    # Find the departure hour in the replay
    dep_hour = departure_ts.floor("h")
    all_ts = list(replay.available_timestamps)

    # Find index of departure hour
    try:
        start_idx = all_ts.index(dep_hour)
    except ValueError:
        # Find the closest earlier timestamp
        earlier = [t for t in all_ts if t <= dep_hour]
        if not earlier:
            raise ValueError(f"No replay frame at or before {dep_hour}")
        start_idx = all_ts.index(max(earlier))

    # Take all contiguous frames from start_idx onward
    frames = []
    for i in range(start_idx, len(all_ts)):
        frame = replay.get_frame(all_ts[i])
        frames.append(frame)

    if not frames:
        raise ValueError(f"No replay frames available from {dep_hour}")

    return TemporalJourneyEngine(wm, frames)


def run_benchmark(
    max_pairs: int = DEFAULT_MAX_PAIRS,
    max_departures: int = DEFAULT_DEPARTURES_PER_OD,
    seed: int = DEFAULT_SEED,
    graph_path: str = DEFAULT_GRAPH_PATH,
    mapping_path: str = DEFAULT_MAPPING_PATH,
    predictions_path: str = DEFAULT_PREDICTIONS_PATH,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute the full Stage 3 benchmark.

    Returns a summary dict with counts, timing, and output paths.
    """
    start_time = time.time()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if output_dir is None:
        output_dir_path = Path("results") / f"benchmark_{run_id}"
    else:
        output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    print(f"{'='*70}")
    print(f"GeoPulse Stage 3 Benchmark — Run {run_id}")
    print(f"{'='*70}")

    # -- Step 1: Load graph and weight manager --------------------------------
    print("\n[1/6] Loading graph and traffic mapping...")
    G = nx.read_graphml(graph_path)
    mapping_df = pd.read_parquet(mapping_path)
    wm = GraphWeightManager(G, mapping_df)
    print(f"  Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    print(f"  Dynamic edges: {len(wm.dynamic_edge_segments)}")

    # -- Step 2: Load replay --------------------------------------------------
    print("\n[2/6] Loading historical traffic replay...")
    replay = HistoricalTrafficReplay(predictions_path)
    all_timestamps = list(replay.available_timestamps)
    print(f"  Timestamps: {len(all_timestamps)}")
    print(f"  Range: {all_timestamps[0]} to {all_timestamps[-1]}")

    # -- Step 3: Select OD pairs ----------------------------------------------
    print("\n[3/6] Selecting OD pairs...")
    od_manifest_path = str(output_dir_path / "od_manifest.json")
    od_pairs, od_manifest = select_od_pairs(
        max_pairs=max_pairs,
        seed=seed,
        graph_path=graph_path,
        mapping_path=mapping_path,
        output_path=od_manifest_path,
    )
    print(f"  Selected {len(od_pairs)} OD pairs")

    # Write OD manifest CSV
    od_df = pd.DataFrame(od_pairs)
    od_csv_path = output_dir_path / "od_manifest.csv"
    od_df.to_csv(od_csv_path, index=False)

    # -- Step 4: Select departure times ---------------------------------------
    print("\n[4/6] Selecting departure times...")
    departure_times = _select_departure_times(all_timestamps, max_departures)
    print(f"  Selected {len(departure_times)} departure times:")
    for dt in departure_times:
        print(f"    {dt.isoformat()}")

    total_scenarios = len(od_pairs) * len(departure_times)
    total_runs = total_scenarios * len(STRATEGIES)
    print(f"  Total scenarios: {total_scenarios}")
    print(f"  Total strategy runs: {total_runs}")

    # -- Step 5: Execute benchmark --------------------------------------------
    print(f"\n[5/6] Executing {total_runs} strategy journeys...")
    all_results: List[Dict[str, Any]] = []
    completed_count = 0
    failed_count = 0
    excluded_scenarios: List[Dict[str, str]] = []

    scenario_num = 0
    for od_idx, od in enumerate(od_pairs):
        origin = od["origin"]
        destination = od["destination"]
        od_id = od["od_id"]

        for dep_idx, dep_ts in enumerate(departure_times):
            scenario_num += 1
            scenario_label = f"Scenario {scenario_num}/{total_scenarios}: OD {od_id} @ {dep_ts.strftime('%Y-%m-%d %H:%M')}"

            # Build engine for this departure
            try:
                engine = _build_engine(wm, replay, dep_ts)
            except (ValueError, KeyError) as exc:
                reason = f"Engine build failed: {exc}"
                print(f"  SKIP {scenario_label} — {reason}")
                excluded_scenarios.append({
                    "od_id": od_id, "origin": origin, "destination": destination,
                    "departure": dep_ts.isoformat(), "reason": reason,
                })
                continue

            # Run all three strategies with identical inputs
            for strategy in STRATEGIES:
                try:
                    result = engine.run(origin, destination, dep_ts, strategy)
                    row = result.to_dict()
                    row["od_id"] = od_id
                    row["distance_category"] = od["distance_category"]
                    row["coverage_category"] = od["coverage_category"]
                    row["route_coverage"] = od["coverage"]

                    # Compute dynamic coverage of the ACTUALLY traversed route
                    dynamic_edges_set = set(wm.dynamic_edge_segments.keys())
                    traversed = result.traversed_edge_path
                    if traversed:
                        trav_dyn = sum(1 for e in traversed if e in dynamic_edges_set)
                        row["traversed_dynamic_edges"] = trav_dyn
                        row["traversed_static_edges"] = len(traversed) - trav_dyn
                        row["traversed_coverage"] = round(trav_dyn / len(traversed), 4) if traversed else 0.0
                    else:
                        row["traversed_dynamic_edges"] = 0
                        row["traversed_static_edges"] = 0
                        row["traversed_coverage"] = 0.0

                    all_results.append(row)

                    if result.success:
                        completed_count += 1
                    else:
                        failed_count += 1

                except Exception as exc:
                    tb = traceback.format_exc()
                    all_results.append({
                        "od_id": od_id,
                        "strategy": strategy,
                        "origin": origin,
                        "destination": destination,
                        "departure_timestamp": dep_ts.isoformat(),
                        "success": False,
                        "failure_reason": f"exception:{exc}",
                        "travel_time_s": 0.0,
                        "distance_m": 0.0,
                        "traversed_edges": 0,
                        "intersection_decisions": 0,
                        "two_edge_alternative_selections": 0,
                        "prediction_updates_applied": 0,
                        "dijkstra_reroutes": 0,
                        "dijkstra_fallback_steps": 0,
                        "backtracking_events": 0,
                        "backtracking_steps": 0,
                        "repeated_node_visits": 0,
                        "loop_traps": 0,
                        "mean_decision_latency_ms": None,
                        "p95_decision_latency_ms": None,
                        "mean_two_edge_decision_latency_ms": None,
                        "p95_two_edge_decision_latency_ms": None,
                        "execution_time_s": 0.0,
                        "two_edge_only_success": None,
                        "distance_category": od["distance_category"],
                        "coverage_category": od["coverage_category"],
                        "route_coverage": od["coverage"],
                        "traversed_dynamic_edges": 0,
                        "traversed_static_edges": 0,
                        "traversed_coverage": 0.0,
                    })
                    failed_count += 1
                    print(f"  ERROR {scenario_label}/{strategy}: {exc}")

            # Progress report every 10 scenarios
            if scenario_num % 10 == 0 or scenario_num == total_scenarios:
                elapsed = time.time() - start_time
                rate = scenario_num / elapsed if elapsed > 0 else 0
                print(f"  Progress: {scenario_num}/{total_scenarios} scenarios "
                      f"({completed_count} ok, {failed_count} fail) "
                      f"[{elapsed:.1f}s, {rate:.1f} scen/s]")

    # -- Step 6: Write results ------------------------------------------------
    print(f"\n[6/6] Writing results to {output_dir_path}...")

    # Journey results CSV
    results_df = pd.DataFrame(all_results)
    results_csv = output_dir_path / "journey_results.csv"
    results_df.to_csv(results_csv, index=False)
    print(f"  journey_results.csv: {len(results_df)} rows")

    # Strategy summary
    summary = _compute_strategy_summary(results_df)
    summary_csv = output_dir_path / "strategy_summary.csv"
    summary.to_csv(summary_csv, index=False)
    print(f"  strategy_summary.csv: {len(summary)} rows")

    # Head-to-head comparison
    h2h = _compute_head_to_head(results_df)
    h2h_csv = output_dir_path / "head_to_head_comparison.csv"
    h2h.to_csv(h2h_csv, index=False)
    print(f"  head_to_head_comparison.csv: {len(h2h)} rows")

    # Coverage report
    coverage_report = _compute_coverage_report(results_df)
    coverage_json = output_dir_path / "coverage_report.json"
    coverage_json.write_text(json.dumps(coverage_report, indent=2))

    # Benchmark manifest
    elapsed_total = time.time() - start_time
    bench_manifest = {
        "experiment_id": run_id,
        "execution_timestamp": datetime.now(timezone.utc).isoformat(),
        "git_hash": _get_git_hash(),
        "dataset_paths": {
            "graph": graph_path,
            "mapping": mapping_path,
            "predictions": predictions_path,
        },
        "historical_date_range": {
            "start": all_timestamps[0].isoformat(),
            "end": all_timestamps[-1].isoformat(),
        },
        "prediction_timestamp_count": len(all_timestamps),
        "random_seed": seed,
        "selected_od_count": len(od_pairs),
        "departure_count": len(departure_times),
        "departure_times": [t.isoformat() for t in departure_times],
        "total_scenarios": total_scenarios,
        "total_strategy_runs": total_runs,
        "completed_runs": completed_count,
        "failed_runs": failed_count,
        "excluded_scenarios": excluded_scenarios,
        "strategies": list(STRATEGIES),
        "tie_threshold": "max(1s, 0.1% of baseline)",
        "total_execution_time_s": round(elapsed_total, 2),
        "python_version": sys.version,
        "package_versions": _get_package_versions(),
    }
    manifest_json = output_dir_path / "benchmark_manifest.json"
    manifest_json.write_text(json.dumps(bench_manifest, indent=2))

    # Benchmark report
    report_md = _generate_report(
        bench_manifest, summary, h2h, coverage_report,
        results_df, od_pairs, departure_times
    )
    report_path = output_dir_path / "benchmark_report.md"
    report_path.write_text(report_md)
    print(f"  benchmark_report.md generated")

    print(f"\n{'='*70}")
    print(f"Benchmark complete in {elapsed_total:.1f}s")
    print(f"Results: {output_dir_path}")
    print(f"{'='*70}")

    return {
        "run_id": run_id,
        "output_dir": str(output_dir_path),
        "od_pairs": len(od_pairs),
        "departures": len(departure_times),
        "total_scenarios": total_scenarios,
        "total_runs": total_runs,
        "completed": completed_count,
        "failed": failed_count,
        "elapsed_s": round(elapsed_total, 2),
    }


# ---------------------------------------------------------------------------
# Statistical aggregation helpers
# ---------------------------------------------------------------------------

def _compute_strategy_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per-strategy aggregate statistics."""
    rows = []
    for strategy in STRATEGIES:
        sdf = df[df["strategy"] == strategy]
        completed = sdf[sdf["success"] == True]
        tt = completed["travel_time_s"]
        dist = completed["distance_m"]

        row = {
            "strategy": strategy,
            "total_runs": len(sdf),
            "completed": len(completed),
            "failed": len(sdf) - len(completed),
            "completion_rate": round(len(completed) / len(sdf), 4) if len(sdf) else 0,
            "mean_travel_time_s": round(float(tt.mean()), 2) if len(tt) else None,
            "median_travel_time_s": round(float(tt.median()), 2) if len(tt) else None,
            "p95_travel_time_s": round(float(tt.quantile(0.95)), 2) if len(tt) else None,
            "std_travel_time_s": round(float(tt.std()), 2) if len(tt) > 1 else None,
            "mean_distance_m": round(float(dist.mean()), 2) if len(dist) else None,
            "mean_execution_time_s": round(float(completed["execution_time_s"].mean()), 4) if len(completed) else None,
        }

        # Strategy-specific counters
        if strategy == "geopulse_two_edge":
            row["mean_intersection_decisions"] = round(float(completed["intersection_decisions"].mean()), 2) if len(completed) else None
            row["mean_alternative_selections"] = round(float(completed["two_edge_alternative_selections"].mean()), 2) if len(completed) else None
            row["mean_dijkstra_fallbacks"] = round(float(completed["dijkstra_fallback_steps"].mean()), 2) if len(completed) else None
            row["mean_backtracking"] = round(float(completed["backtracking_events"].mean()), 2) if len(completed) else None
            row["mean_repeated_nodes"] = round(float(completed["repeated_node_visits"].mean()), 2) if len(completed) else None
            row["mean_loop_traps"] = round(float(completed["loop_traps"].mean()), 2) if len(completed) else None
            lat = completed["mean_two_edge_decision_latency_ms"].dropna()
            row["mean_decision_latency_ms"] = round(float(lat.mean()), 4) if len(lat) else None
            p95_lat = completed["p95_two_edge_decision_latency_ms"].dropna()
            row["p95_decision_latency_ms"] = round(float(p95_lat.mean()), 4) if len(p95_lat) else None
        elif strategy == "dynamic_dijkstra":
            row["mean_reroutes"] = round(float(completed["dijkstra_reroutes"].mean()), 2) if len(completed) else None
            row["mean_prediction_updates"] = round(float(completed["prediction_updates_applied"].mean()), 2) if len(completed) else None
            lat = completed["mean_decision_latency_ms"].dropna()
            row["mean_decision_latency_ms"] = round(float(lat.mean()), 4) if len(lat) else None

        rows.append(row)
    return pd.DataFrame(rows)


def _paired_comparison(
    df: pd.DataFrame,
    baseline_strategy: str,
    test_strategy: str,
    tie_threshold_s: float = 1.0,
    tie_threshold_pct: float = 0.001,
) -> Dict[str, Any]:
    """Paired comparison of test vs baseline on identical scenarios."""
    base_df = df[(df["strategy"] == baseline_strategy) & (df["success"] == True)]
    test_df = df[(df["strategy"] == test_strategy) & (df["success"] == True)]

    # Match on (od_id, departure_timestamp)
    merged = base_df.merge(
        test_df,
        on=["od_id", "departure_timestamp"],
        suffixes=("_base", "_test"),
        how="inner",
    )

    if len(merged) == 0:
        return {
            "comparison": f"{test_strategy}_vs_{baseline_strategy}",
            "paired_count": 0,
            "note": "No paired completed scenarios",
        }

    base_times = merged["travel_time_s_base"].values
    test_times = merged["travel_time_s_test"].values
    diffs = base_times - test_times  # Positive = test is faster

    # Tie threshold: max(1s, 0.1% of baseline)
    thresholds = np.maximum(tie_threshold_s, tie_threshold_pct * base_times)

    wins = int(np.sum(diffs > thresholds))
    losses = int(np.sum(diffs < -thresholds))
    ties = int(len(diffs) - wins - losses)

    # Improvement percentages
    improvements = (diffs / base_times) * 100  # Positive = test faster

    result = {
        "comparison": f"{test_strategy}_vs_{baseline_strategy}",
        "paired_count": len(merged),
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "win_pct": round(100 * wins / len(merged), 2),
        "loss_pct": round(100 * losses / len(merged), 2),
        "tie_pct": round(100 * ties / len(merged), 2),
        "mean_improvement_pct": round(float(np.mean(improvements)), 4),
        "median_improvement_pct": round(float(np.median(improvements)), 4),
        "mean_base_time_s": round(float(np.mean(base_times)), 2),
        "mean_test_time_s": round(float(np.mean(test_times)), 2),
        "median_base_time_s": round(float(np.median(base_times)), 2),
        "median_test_time_s": round(float(np.median(test_times)), 2),
        "p95_base_time_s": round(float(np.percentile(base_times, 95)), 2),
        "p95_test_time_s": round(float(np.percentile(test_times, 95)), 2),
    }

    # Paired t-test if enough data
    if len(diffs) >= 3:
        from scipy import stats
        try:
            t_stat, p_value = stats.ttest_rel(test_times, base_times)
            result["paired_ttest_t_statistic"] = round(float(t_stat), 4)
            result["paired_ttest_p_value"] = round(float(p_value), 6)
            # 95% CI for mean difference
            se = float(np.std(diffs, ddof=1) / np.sqrt(len(diffs)))
            ci_half = stats.t.ppf(0.975, df=len(diffs)-1) * se
            mean_diff = float(np.mean(diffs))
            result["mean_time_saved_s"] = round(mean_diff, 4)
            result["ci95_time_saved_lower_s"] = round(mean_diff - ci_half, 4)
            result["ci95_time_saved_upper_s"] = round(mean_diff + ci_half, 4)
        except Exception:
            pass

    return result


def _compute_head_to_head(df: pd.DataFrame) -> pd.DataFrame:
    """Head-to-head comparisons: GeoPulse vs Static, GeoPulse vs Dynamic."""
    comparisons = [
        _paired_comparison(df, "static_dijkstra", "geopulse_two_edge"),
        _paired_comparison(df, "dynamic_dijkstra", "geopulse_two_edge"),
        _paired_comparison(df, "static_dijkstra", "dynamic_dijkstra"),
    ]
    return pd.DataFrame(comparisons)


def _compute_coverage_report(df: pd.DataFrame) -> Dict[str, Any]:
    """Coverage-grouped performance analysis."""
    report = {"coverage_groups": {}}
    for cov_cat in ["low", "medium", "high"]:
        group = df[df["coverage_category"] == cov_cat]
        if len(group) == 0:
            continue
        group_data = {"scenario_count": len(group) // 3}
        for strategy in STRATEGIES:
            sdf = group[(group["strategy"] == strategy) & (group["success"] == True)]
            tt = sdf["travel_time_s"]
            group_data[strategy] = {
                "completed": len(sdf),
                "failed": len(group[group["strategy"] == strategy]) - len(sdf),
                "mean_travel_time_s": round(float(tt.mean()), 2) if len(tt) else None,
                "median_travel_time_s": round(float(tt.median()), 2) if len(tt) else None,
            }

        # GeoPulse vs others within this coverage group
        for baseline in ["static_dijkstra", "dynamic_dijkstra"]:
            comp = _paired_comparison(group, baseline, "geopulse_two_edge")
            group_data[f"geopulse_vs_{baseline.replace('_dijkstra', '')}"] = {
                "paired": comp.get("paired_count", 0),
                "wins": comp.get("wins", 0),
                "losses": comp.get("losses", 0),
                "ties": comp.get("ties", 0),
                "mean_improvement_pct": comp.get("mean_improvement_pct", 0),
            }

        report["coverage_groups"][cov_cat] = group_data

    return report


def _get_git_hash() -> Optional[str]:
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def _get_package_versions() -> Dict[str, str]:
    versions = {}
    for pkg in ["numpy", "pandas", "networkx", "scipy", "pygame"]:
        try:
            mod = __import__(pkg)
            versions[pkg] = getattr(mod, "__version__", "unknown")
        except ImportError:
            versions[pkg] = "not installed"
    return versions


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _generate_report(
    manifest: Dict,
    summary: pd.DataFrame,
    h2h: pd.DataFrame,
    coverage_report: Dict,
    results_df: pd.DataFrame,
    od_pairs: List[Dict],
    departure_times: List[pd.Timestamp],
) -> str:
    """Generate the benchmark_report.md."""
    lines = []
    lines.append("# GeoPulse Stage 3 — Temporal Benchmark Report\n")
    lines.append(f"**Experiment ID:** {manifest['experiment_id']}")
    lines.append(f"**Execution:** {manifest['execution_timestamp']}")
    if manifest.get("git_hash"):
        lines.append(f"**Git Hash:** `{manifest['git_hash']}`")
    lines.append("")

    # Executive summary
    lines.append("## 1. Executive Summary\n")
    lines.append(f"This report presents the results of a large-scale temporal benchmark "
                 f"comparing three routing strategies on the Bhubaneswar OSM road network: "
                 f"**Static Dijkstra**, **Dynamic Dijkstra**, and **GeoPulse (Sequential Two-Edge Selection)**.\n")
    lines.append(f"- **OD pairs:** {manifest['selected_od_count']}")
    lines.append(f"- **Departure times:** {manifest['departure_count']}")
    lines.append(f"- **Total scenarios:** {manifest['total_scenarios']}")
    lines.append(f"- **Total strategy runs:** {manifest['total_strategy_runs']}")
    lines.append(f"- **Completed:** {manifest['completed_runs']}")
    lines.append(f"- **Failed:** {manifest['failed_runs']}")
    lines.append(f"- **Execution time:** {manifest['total_execution_time_s']}s\n")

    # Key results
    for _, row in h2h.iterrows():
        comp = row["comparison"]
        if "geopulse_two_edge_vs_static" in comp:
            lines.append(f"**GeoPulse vs Static Dijkstra:** "
                         f"{row.get('wins', 0)} wins, {row.get('losses', 0)} losses, "
                         f"{row.get('ties', 0)} ties "
                         f"(mean improvement: {row.get('mean_improvement_pct', 0):.2f}%)")
        elif "geopulse_two_edge_vs_dynamic" in comp:
            lines.append(f"**GeoPulse vs Dynamic Dijkstra:** "
                         f"{row.get('wins', 0)} wins, {row.get('losses', 0)} losses, "
                         f"{row.get('ties', 0)} ties "
                         f"(mean improvement: {row.get('mean_improvement_pct', 0):.2f}%)")
    lines.append("")

    # Methodology
    lines.append("## 2. Experimental Methodology\n")
    lines.append("### Strategy Descriptions\n")
    lines.append("1. **Static Dijkstra:** Computes the initial shortest path using predicted "
                 "traffic speeds at departure. This route is fixed for the entire journey. "
                 "Actual travel time uses realized speeds.\n")
    lines.append("2. **Dynamic Dijkstra:** Same initial route, but recomputes the shortest "
                 "path from the current node whenever a new traffic prediction frame becomes "
                 "valid. Updates are applied at the next reached intersection.\n")
    lines.append("3. **GeoPulse (Two-Edge Selection):** At every intersection, compares the "
                 "planned next edge with its best feasible alternative. Each candidate's cost "
                 "is: `predicted edge travel time + Dijkstra remaining-route cost`. Selects "
                 "the lower-cost candidate. Falls back to full Dijkstra when no two-edge "
                 "candidate reaches the destination.\n")
    lines.append("### Fairness Guarantees\n")
    lines.append("All three strategies receive identical inputs for each scenario:")
    lines.append("- Same graph and edge lengths")
    lines.append("- Same origin, destination, and departure time")
    lines.append("- Same predicted traffic weights for routing decisions")
    lines.append("- Same realized (actual) speeds for journey time calculation")
    lines.append("- Traffic updates applied at the next intersection after the update's target-valid time\n")
    lines.append(f"### Tie Threshold\n")
    lines.append(f"A scenario is a tie if the travel time difference is less than "
                 f"`max(1 second, 0.1% of baseline journey time)`.\n")

    # Dataset
    lines.append("## 3. Dataset and Graph Description\n")
    lines.append(f"- **Graph:** Bhubaneswar OSM drive network")
    lines.append(f"- **Nodes:** {manifest.get('dataset_paths', {}).get('graph', 'N/A')}")
    lines.append(f"- **Historical prediction range:** "
                 f"{manifest['historical_date_range']['start']} to "
                 f"{manifest['historical_date_range']['end']}")
    lines.append(f"- **Prediction timestamps:** {manifest['prediction_timestamp_count']}")
    lines.append(f"- **Random seed:** {manifest['random_seed']}\n")

    # OD Selection
    lines.append("## 4. OD Selection\n")
    if od_pairs:
        dist_cats = {}
        cov_cats = {}
        for p in od_pairs:
            dist_cats[p["distance_category"]] = dist_cats.get(p["distance_category"], 0) + 1
            cov_cats[p["coverage_category"]] = cov_cats.get(p["coverage_category"], 0) + 1
        lines.append("Distance categories:")
        for k, v in sorted(dist_cats.items()):
            lines.append(f"  - {k}: {v} pairs")
        lines.append("\nCoverage categories:")
        for k, v in sorted(cov_cats.items()):
            lines.append(f"  - {k}: {v} pairs")
    lines.append("")

    # Aggregate performance
    lines.append("## 5. Aggregate Performance\n")
    lines.append("| Strategy | Completed | Failed | Completion Rate | Mean Time (s) | Median Time (s) | P95 Time (s) | Std Dev (s) | Mean Dist (m) |")
    lines.append("|----------|-----------|--------|----------------|---------------|-----------------|--------------|-------------|---------------|")
    for _, row in summary.iterrows():
        lines.append(
            f"| {row['strategy']} | {row['completed']} | {row['failed']} | "
            f"{row['completion_rate']:.2%} | "
            f"{row.get('mean_travel_time_s', 'N/A')} | "
            f"{row.get('median_travel_time_s', 'N/A')} | "
            f"{row.get('p95_travel_time_s', 'N/A')} | "
            f"{row.get('std_travel_time_s', 'N/A')} | "
            f"{row.get('mean_distance_m', 'N/A')} |"
        )
    lines.append("")

    # Head-to-head
    lines.append("## 6. Head-to-Head Comparisons\n")
    for _, row in h2h.iterrows():
        lines.append(f"### {row['comparison']}\n")
        lines.append(f"- **Paired scenarios:** {row.get('paired_count', 0)}")
        lines.append(f"- **Wins:** {row.get('wins', 0)} ({row.get('win_pct', 0):.1f}%)")
        lines.append(f"- **Losses:** {row.get('losses', 0)} ({row.get('loss_pct', 0):.1f}%)")
        lines.append(f"- **Ties:** {row.get('ties', 0)} ({row.get('tie_pct', 0):.1f}%)")
        lines.append(f"- **Mean improvement:** {row.get('mean_improvement_pct', 0):.4f}%")
        lines.append(f"- **Median improvement:** {row.get('median_improvement_pct', 0):.4f}%")
        if "paired_ttest_p_value" in row and pd.notna(row.get("paired_ttest_p_value")):
            sig = "significant" if row["paired_ttest_p_value"] < 0.05 else "not significant"
            lines.append(f"- **Paired t-test:** t={row['paired_ttest_t_statistic']:.4f}, "
                         f"p={row['paired_ttest_p_value']:.6f} ({sig} at α=0.05)")
            if "mean_time_saved_s" in row and pd.notna(row.get("mean_time_saved_s")):
                lines.append(f"- **Mean time saved:** {row['mean_time_saved_s']:.4f}s "
                             f"(95% CI: [{row['ci95_time_saved_lower_s']:.4f}, "
                             f"{row['ci95_time_saved_upper_s']:.4f}]s)")
        lines.append("")

    # Coverage-wise performance
    lines.append("## 7. Coverage-Wise Performance\n")
    for cov_cat, data in coverage_report.get("coverage_groups", {}).items():
        lines.append(f"### {cov_cat.title()} Dynamic Coverage\n")
        lines.append(f"Scenarios: {data.get('scenario_count', 'N/A')}\n")
        for strategy in STRATEGIES:
            sd = data.get(strategy, {})
            lines.append(f"- **{strategy}:** completed={sd.get('completed', 0)}, "
                         f"mean={sd.get('mean_travel_time_s', 'N/A')}s, "
                         f"median={sd.get('median_travel_time_s', 'N/A')}s")
        for baseline_key in ["geopulse_vs_static", "geopulse_vs_dynamic"]:
            comp = data.get(baseline_key, {})
            if comp:
                lines.append(f"- **{baseline_key}:** W={comp.get('wins',0)}/L={comp.get('losses',0)}/T={comp.get('ties',0)}, "
                             f"improvement={comp.get('mean_improvement_pct',0):.2f}%")
        lines.append("")

    # GeoPulse decision statistics
    lines.append("## 8. GeoPulse Decision Statistics\n")
    gp_summary = summary[summary["strategy"] == "geopulse_two_edge"]
    if len(gp_summary):
        gp = gp_summary.iloc[0]
        for field, label in [
            ("mean_intersection_decisions", "Mean two-edge decisions per journey"),
            ("mean_alternative_selections", "Mean alternative edge selections"),
            ("mean_dijkstra_fallbacks", "Mean Dijkstra safety fallbacks"),
            ("mean_backtracking", "Mean backtracking events"),
            ("mean_repeated_nodes", "Mean repeated-node visits"),
            ("mean_loop_traps", "Mean loop traps"),
            ("mean_decision_latency_ms", "Mean two-edge decision latency (ms)"),
            ("p95_decision_latency_ms", "P95 two-edge decision latency (ms)"),
        ]:
            val = gp.get(field)
            if val is not None and pd.notna(val):
                lines.append(f"- **{label}:** {val}")
    lines.append("")

    # Completion and failure analysis
    lines.append("## 9. Completion and Failure Analysis\n")
    failures = results_df[results_df["success"] == False]
    if len(failures):
        reason_counts = failures["failure_reason"].value_counts()
        lines.append("| Failure Reason | Count |")
        lines.append("|----------------|-------|")
        for reason, count in reason_counts.items():
            lines.append(f"| {reason} | {count} |")
    else:
        lines.append("All journeys completed successfully.")
    lines.append("")

    # Execution latency
    lines.append("## 10. Execution Latency\n")
    for _, row in summary.iterrows():
        et = row.get("mean_execution_time_s")
        if et is not None:
            lines.append(f"- **{row['strategy']}:** mean execution time = {et:.4f}s")
    lines.append("")

    # Limitations
    lines.append("## 11. Limitations\n")
    lines.append("1. The historical replay covers only 44 hourly timestamps "
                 "(~2 days). This limits the number of distinct departure times.")
    lines.append("2. Dynamic traffic coverage affects only ~1.5% of directed edges. "
                 "Most edges use static highway-class speed fallbacks.")
    lines.append("3. GeoPulse's advantage is expected to be most visible on routes "
                 "with high dynamic coverage, which are a minority.")
    lines.append("4. The OSM graph may contain disconnected components; OD pairs "
                 "are filtered for reachability.")
    lines.append("")

    # Conclusion
    lines.append("## 12. Conclusion\n")
    lines.append("This benchmark provides a fair, reproducible comparison of three "
                 "routing strategies under identical experimental conditions. "
                 "Results should be interpreted in the context of the limited "
                 "dynamic traffic coverage available in the Bhubaneswar dataset.\n")

    # Check if GeoPulse actually won
    gp_vs_static = h2h[h2h["comparison"].str.contains("geopulse.*static", case=False, na=False)]
    gp_vs_dynamic = h2h[h2h["comparison"].str.contains("geopulse.*dynamic_dijkstra", case=False, na=False)]

    if len(gp_vs_static):
        gs = gp_vs_static.iloc[0]
        if gs.get("wins", 0) > gs.get("losses", 0):
            lines.append("GeoPulse outperforms Static Dijkstra in the majority of "
                         "paired scenarios, as expected from its ability to react to "
                         "traffic updates.")
        elif gs.get("wins", 0) < gs.get("losses", 0):
            lines.append("GeoPulse does not outperform Static Dijkstra in the majority "
                         "of paired scenarios. This may be due to the limited dynamic "
                         "coverage or the overhead of two-edge decisions.")
        else:
            lines.append("GeoPulse ties with Static Dijkstra in the majority of scenarios.")
    if len(gp_vs_dynamic):
        gd = gp_vs_dynamic.iloc[0]
        if gd.get("wins", 0) > gd.get("losses", 0):
            lines.append("GeoPulse outperforms Dynamic Dijkstra, suggesting that "
                         "intersection-level two-edge decisions provide benefit beyond "
                         "periodic full rerouting.")
        elif gd.get("wins", 0) < gd.get("losses", 0):
            lines.append("GeoPulse does not outperform Dynamic Dijkstra. The two-edge "
                         "selection overhead may not provide sufficient benefit given "
                         "the limited dynamic coverage in this dataset.")
        else:
            lines.append("GeoPulse ties with Dynamic Dijkstra in the majority of scenarios.")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="GeoPulse Stage 3 Benchmark")
    parser.add_argument("--max-pairs", type=int, default=DEFAULT_MAX_PAIRS)
    parser.add_argument("--max-departures", type=int, default=DEFAULT_DEPARTURES_PER_OD)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--output-dir", type=str, default=None)
    args = parser.parse_args()

    result = run_benchmark(
        max_pairs=args.max_pairs,
        max_departures=args.max_departures,
        seed=args.seed,
        output_dir=args.output_dir,
    )
    print(json.dumps(result, indent=2))
