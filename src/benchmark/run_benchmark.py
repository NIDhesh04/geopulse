"""GeoPulse Stage 3 batch temporal benchmark runner.

Reuses a single TemporalJourneyEngine (caching prediction weights, realized
speeds, and reverse-Dijkstra remaining-cost trees safely) across all selected
OD pairs and valid historical departure timestamps, executing Static Dijkstra,
Dynamic Dijkstra, and GeoPulse Two-Edge Selection under identical inputs.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import networkx as nx
import numpy as np
import pandas as pd

from src.benchmark.evaluation import (
    TIE_ABS_THRESHOLD_S,
    TIE_PCT_THRESHOLD,
    compute_coverage_and_length_report,
    compute_head_to_head,
    compute_strategy_summary,
    generate_benchmark_report,
)
from src.benchmark.od_selection import DEFAULT_MAX_PAIRS, DEFAULT_SEED, select_od_pairs
from src.experiments.temporal_journey import STRATEGIES, TemporalJourneyEngine
from src.routing.traffic_weights import GraphWeightManager
from src.traffic.replay import HistoricalTrafficReplay

DEFAULT_DEPARTURES_PER_OD = 5
DEFAULT_GRAPH_PATH = "data/raw/osm/bhubaneswar_drive.graphml"
DEFAULT_MAPPING_PATH = "data/processed/traffic_to_osm_mapping_final.parquet"
DEFAULT_PREDICTIONS_PATH = "results/phase7_predictions.parquet"


def select_departure_schedules(
    valid_times: Sequence[pd.Timestamp],
    final_valid_until: pd.Timestamp,
    max_departures: int = DEFAULT_DEPARTURES_PER_OD,
    pre_boundary_minute: int = 58,
    min_remaining_hours: float = 2.5,
) -> List[Dict[str, str]]:
    """Select valid UTC departure timestamps spanning distinct IST diurnal periods.

    Departing at minute ``:58`` within a valid hourly frame guarantees the vehicle
    starts under frame ``t``'s forecast and experiences the next hourly frame
    ``t+1`` at the first intersection reached after +120 seconds, while leaving
    >= ``min_remaining_hours`` before ``final_valid_until``.
    """
    usable_frames = [
        pd.Timestamp(ts) for ts in valid_times
        if (final_valid_until - (pd.Timestamp(ts) + pd.Timedelta(minutes=pre_boundary_minute))).total_seconds()
        >= min_remaining_hours * 3600.0
    ]
    if not usable_frames:
        usable_frames = [
            pd.Timestamp(ts) for ts in valid_times[:-1]
        ] if len(valid_times) > 1 else [pd.Timestamp(valid_times[0])]

    def _classify_ist_period(ts_utc: pd.Timestamp) -> Tuple[str, str]:
        ist = ts_utc.tz_convert("Asia/Kolkata")
        h = ist.hour
        if 8 <= h <= 11:
            label = "Morning Peak"
        elif 12 <= h <= 14:
            label = "Midday"
        elif 15 <= h <= 16:
            label = "Afternoon"
        elif 17 <= h <= 21:
            label = "Evening Peak"
        else:
            label = "Off-Peak Night"
        return label, ist.strftime("%Y-%m-%d %H:%M IST")

    selected_frames: List[pd.Timestamp] = []
    if len(usable_frames) <= max_departures:
        selected_frames = list(usable_frames)
    else:
        # Target one representative from distinct diurnal periods across the horizon
        target_periods = ["Afternoon", "Evening Peak", "Off-Peak Night", "Morning Peak", "Midday"]
        used_set: Set[pd.Timestamp] = set()
        for target in target_periods[:max_departures]:
            for ts in usable_frames:
                cand = ts + pd.Timedelta(minutes=pre_boundary_minute)
                if cand >= final_valid_until:
                    continue
                p_label, _ = _classify_ist_period(cand)
                if p_label == target and ts not in used_set:
                    selected_frames.append(ts)
                    used_set.add(ts)
                    break
        # Fill any remaining slots evenly across usable frames
        if len(selected_frames) < max_departures:
            indices = np.linspace(0, len(usable_frames) - 1, max_departures, dtype=int)
            for idx in indices:
                ts = usable_frames[int(idx)]
                if ts not in used_set and len(selected_frames) < max_departures:
                    selected_frames.append(ts)
                    used_set.add(ts)
        selected_frames.sort()

    schedules: List[Dict[str, str]] = []
    for dep_idx, base_ts in enumerate(selected_frames):
        offset = pd.Timedelta(minutes=pre_boundary_minute)
        dep_ts = base_ts + offset
        if dep_ts >= final_valid_until:
            dep_ts = base_ts
        p_label, ist_text = _classify_ist_period(dep_ts)
        schedules.append({
            "departure_index": dep_idx,
            "departure_utc": dep_ts.isoformat(),
            "period_label": p_label,
            "ist_time": ist_text,
            "initial_target_valid_utc": base_ts.isoformat(),
        })
    return schedules


def _get_git_commit() -> Optional[str]:
    try:
        res = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5)
        return res.stdout.strip() if res.returncode == 0 else None
    except Exception:
        return None


def _get_package_versions() -> Dict[str, str]:
    versions: Dict[str, str] = {}
    for pkg in ("numpy", "pandas", "networkx", "scipy", "pygame"):
        try:
            mod = __import__(pkg)
            versions[pkg] = str(getattr(mod, "__version__", "unknown"))
        except ImportError:
            versions[pkg] = "not installed"
    return versions


def run_stage3_benchmark(
    max_pairs: int = DEFAULT_MAX_PAIRS,
    max_departures: int = DEFAULT_DEPARTURES_PER_OD,
    seed: int = DEFAULT_SEED,
    graph_path: str = DEFAULT_GRAPH_PATH,
    mapping_path: str = DEFAULT_MAPPING_PATH,
    predictions_path: str = DEFAULT_PREDICTIONS_PATH,
    output_dir: Optional[str] = None,
    reproduction_command: Optional[str] = None,
) -> Dict[str, Any]:
    """Run full Stage 3 benchmark and emit all 7 validated output artifacts."""
    wall_start = perf_counter()
    now_utc = datetime.now(timezone.utc)
    exp_id = f"stage3_benchmark_{now_utc.strftime('%Y%m%d_%H%M%S')}"
    out_dir = Path(output_dir) if output_dir else Path("results") / exp_id
    out_dir.mkdir(parents=True, exist_ok=False)

    print(f"{'='*72}")
    print(f"GeoPulse Stage 3 Temporal Benchmark — {exp_id}")
    print(f"{'='*72}")

    # 1. Load real graph, traffic mapping, and historical replay
    print("[1/6] Loading OSM graph, mapping, and historical replay...")
    G = nx.read_graphml(graph_path)
    if not isinstance(G, nx.MultiDiGraph):
        G = nx.MultiDiGraph(G)
    mapping_df = pd.read_parquet(mapping_path)
    wm = GraphWeightManager(G, mapping_df)
    replay = HistoricalTrafficReplay(predictions_path)
    frames = [replay.get_frame(ts) for ts in replay.available_timestamps]
    engine = TemporalJourneyEngine(wm, frames)
    dynamic_edge_set: Set[Tuple[str, str, Any]] = set(wm.dynamic_edge_segments.keys())

    # 2. Select OD pairs deterministically
    print(f"[2/6] Selecting up to {max_pairs} balanced OD pairs (seed={seed})...")
    od_csv_path = out_dir / "od_manifest.csv"
    od_pairs, od_meta = select_od_pairs(
        max_pairs=max_pairs,
        seed=seed,
        graph_path=graph_path,
        mapping_path=mapping_path,
        output_csv_path=str(od_csv_path),
        weight_manager=wm,
        graph=G,
    )
    od_df = pd.DataFrame(od_pairs)
    print(f"  Selected {len(od_pairs)} reachable OD pairs.")
    print(f"  Distance bins: {od_meta['selected_distance_distribution']}")
    print(f"  Coverage bins: {od_meta['selected_coverage_distribution']}")

    # 3. Select departure timestamps within valid historical horizon
    print(f"[3/6] Selecting {max_departures} departure timestamps across historical horizon...")
    dep_schedules = select_departure_schedules(
        engine.valid_times,
        engine.final_valid_until,
        max_departures=max_departures,
    )
    for ds in dep_schedules:
        print(f"  {ds['departure_utc']} ({ds['ist_time']} — {ds['period_label']})")

    # 4. Pre-validate scenario feasibility (common reachability & horizon bounds)
    initial_weights = engine._prediction_weights(0)
    valid_scenarios: List[Tuple[str, Dict[str, Any], Dict[str, str]]] = []
    excluded_scenarios: List[Dict[str, Any]] = []
    for od in od_pairs:
        origin = od["origin_node"]
        dest = od["destination_node"]
        for ds in dep_schedules:
            scen_id = f"OD{int(od['od_id']):02d}_D{int(ds['departure_index'])}"
            dep_ts = pd.Timestamp(ds["departure_utc"])
            if dep_ts < engine.valid_times[0] or dep_ts >= engine.final_valid_until:
                excluded_scenarios.append({
                    "scenario_id": scen_id,
                    "od_id": int(od["od_id"]),
                    "departure_utc": ds["departure_utc"],
                    "reason": "departure_outside_valid_horizon",
                })
                continue
            if not engine._route(origin, dest, initial_weights).is_reached:
                excluded_scenarios.append({
                    "scenario_id": scen_id,
                    "od_id": int(od["od_id"]),
                    "departure_utc": ds["departure_utc"],
                    "reason": "destination_unreachable_initial_frame",
                })
                continue
            valid_scenarios.append((scen_id, od, ds))

    total_scenarios = len(valid_scenarios)
    total_runs = total_scenarios * len(STRATEGIES)
    print(f"[4/6] Executing {total_scenarios} scenarios ({total_runs} strategy journeys)...")

    # 5. Execute all three strategies per scenario on identical engine & inputs
    journey_rows: List[Dict[str, Any]] = []
    for idx, (scen_id, od, ds) in enumerate(valid_scenarios, start=1):
        origin = od["origin_node"]
        dest = od["destination_node"]
        dep_utc = ds["departure_utc"]

        for strategy in STRATEGIES:
            res = engine.run(origin, dest, dep_utc, strategy)
            trav = res.traversed_edge_path
            dyn_trav = sum(1 for e in trav if e in dynamic_edge_set)
            stat_trav = len(trav) - dyn_trav
            cov_pct = (100.0 * dyn_trav / len(trav)) if trav else 0.0

            row = res.to_dict()
            row.update({
                "scenario_id": scen_id,
                "od_id": int(od["od_id"]),
                "departure_period": ds["period_label"],
                "traversed_dynamic_edges": int(dyn_trav),
                "traversed_static_edges": int(stat_trav),
                "traversed_dynamic_coverage_pct": round(cov_pct, 2),
                "od_distance_category": od["distance_category"],
                "od_coverage_category": od["coverage_category"],
                "od_planned_coverage_pct": od["dynamic_coverage_pct"],
                "od_planned_distance_m": od["shortest_path_distance_m"],
            })
            journey_rows.append(row)

        if idx % 25 == 0 or idx == total_scenarios:
            ok_so_far = sum(1 for r in journey_rows if r["success"])
            elapsed = perf_counter() - wall_start
            print(f"  Progress: {idx}/{total_scenarios} scenarios "
                  f"({ok_so_far}/{len(journey_rows)} completed) [{elapsed:.1f}s]", flush=True)

    # 6. Aggregate statistics and emit all 7 artifacts
    print(f"[5/6] Aggregating statistics & hypothesis tests...")
    results_df = pd.DataFrame(journey_rows)
    results_df.to_csv(out_dir / "journey_results.csv", index=False)

    summary_df = compute_strategy_summary(results_df)
    summary_df.to_csv(out_dir / "strategy_summary.csv", index=False)

    h2h_df = compute_head_to_head(results_df)
    h2h_df.to_csv(out_dir / "head_to_head_comparison.csv", index=False)

    coverage_report = compute_coverage_and_length_report(
        results_df,
        network_total_edges=len(wm.edge_lengths),
        network_dynamic_edges=len(dynamic_edge_set),
    )
    (out_dir / "coverage_report.json").write_text(
        json.dumps(coverage_report, indent=2), encoding="utf-8"
    )

    elapsed_total = round(perf_counter() - wall_start, 2)
    cmd = reproduction_command or (
        f"python scripts/run_stage3_benchmark.py --max-pairs {max_pairs} "
        f"--max-departures {max_departures} --seed {seed}"
    )

    manifest = {
        "experiment_id": exp_id,
        "execution_timestamp": now_utc.isoformat(),
        "git_commit": _get_git_commit(),
        "random_seed": seed,
        "graph_file": graph_path,
        "graph_statistics": {
            "nodes": int(G.number_of_nodes()),
            "directed_edges": int(G.number_of_edges()),
            "largest_scc_nodes": int(od_meta["largest_scc_nodes"]),
            "dynamically_mapped_edges": int(len(dynamic_edge_set)),
        },
        "dataset_paths": {
            "graph": graph_path,
            "mapping": mapping_path,
            "structured_traffic": "datasets/traffic_structured_v1.parquet",
            "predictions": predictions_path,
        },
        "prediction_artifact_path": predictions_path,
        "realized_speed_source": "Phase 7 next-hour observed currentSpeed (actual_speed column)",
        "data_time_horizon": {
            "frame_count": len(frames),
            "origin_start_utc": frames[0].origin_timestamp.isoformat(),
            "origin_end_utc": frames[-1].origin_timestamp.isoformat(),
            "target_valid_start_utc": frames[0].target_valid_timestamp.isoformat(),
            "target_valid_end_utc": frames[-1].target_valid_timestamp.isoformat(),
            "final_valid_until_utc": engine.final_valid_until.isoformat(),
        },
        "od_count": len(od_pairs),
        "departure_count": len(dep_schedules),
        "departure_schedules": dep_schedules,
        "scenario_count": total_scenarios,
        "strategy_run_count": len(results_df),
        "completed_runs": int(results_df["success"].astype(bool).sum()),
        "failed_runs": int((~results_df["success"].astype(bool)).sum()),
        "excluded_od_candidates": od_meta["rejection_counts"],
        "excluded_scenarios": excluded_scenarios,
        "od_selection_metadata": {
            "selected_distance_distribution": od_meta["selected_distance_distribution"],
            "selected_coverage_distribution": od_meta["selected_coverage_distribution"],
            "selected_cell_distribution": od_meta["selected_cell_distribution"],
        },
        "strategy_configuration": list(STRATEGIES),
        "simulation_parameters": {
            "tie_abs_threshold_s": TIE_ABS_THRESHOLD_S,
            "tie_pct_threshold": TIE_PCT_THRESHOLD,
            "pre_boundary_departure_minute": 58,
            "update_application_policy": "applied_at_next_reached_intersection_after_target_valid",
            "horizon_policy": "stop_as_incomplete_at_final_valid_until_no_extrapolation",
        },
        "runtime_environment": {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "packages": _get_package_versions(),
        },
        "total_execution_time_s": elapsed_total,
        "reproduction_command": cmd,
    }
    (out_dir / "benchmark_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    print(f"[6/6] Writing benchmark_report.md...")
    report_text = generate_benchmark_report(
        manifest, od_df, results_df, summary_df, h2h_df, coverage_report
    )
    (out_dir / "benchmark_report.md").write_text(report_text, encoding="utf-8")

    print(f"\nStage 3 benchmark complete in {elapsed_total:.1f}s -> {out_dir}")
    return {
        "experiment_id": exp_id,
        "output_dir": str(out_dir),
        "od_count": len(od_pairs),
        "departure_count": len(dep_schedules),
        "scenario_count": total_scenarios,
        "strategy_run_count": len(results_df),
        "completed_runs": manifest["completed_runs"],
        "failed_runs": manifest["failed_runs"],
        "elapsed_s": elapsed_total,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-pairs", type=int, default=DEFAULT_MAX_PAIRS)
    parser.add_argument("--max-departures", type=int, default=DEFAULT_DEPARTURES_PER_OD)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--graph", default=DEFAULT_GRAPH_PATH)
    parser.add_argument("--mapping", default=DEFAULT_MAPPING_PATH)
    parser.add_argument("--predictions", default=DEFAULT_PREDICTIONS_PATH)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    res = run_stage3_benchmark(
        max_pairs=args.max_pairs,
        max_departures=args.max_departures,
        seed=args.seed,
        graph_path=args.graph,
        mapping_path=args.mapping,
        predictions_path=args.predictions,
        output_dir=args.output_dir,
    )
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
