"""Run Phase 4.1 matched temporal routing evaluation over the full replay horizon."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

import networkx as nx
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.experiments.temporal_journey import STRATEGIES, TemporalJourneyEngine
from src.routing.traffic_weights import GraphWeightManager
from src.traffic.replay import HistoricalTrafficReplay


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_cell(value: Any) -> Any:
    if isinstance(value, (tuple, list, dict, set)):
        return json.dumps(value, default=str, sort_keys=True)
    return value


def _safe_timestamp(value: pd.Timestamp) -> str:
    return value.strftime("%Y%m%d_%H%M")


def _percentile(values: Iterable[float], q: float) -> float | None:
    array = np.asarray(list(values), dtype=float)
    if array.size == 0:
        return None
    return float(np.percentile(array, q))


def _latency_stats(trace: pd.DataFrame, strategy: str) -> Dict[str, float | None]:
    if trace.empty or strategy == "static_dijkstra":
        return {
            "mean_decision_latency_ms": None,
            "p95_decision_latency_ms": None,
            "mean_two_edge_decision_latency_ms": None,
            "p95_two_edge_decision_latency_ms": None,
        }
    selected = trace.loc[
        (trace["strategy"] == strategy) & trace["decision_latency_ms"].notna()
    ]
    all_latency = pd.to_numeric(selected["decision_latency_ms"], errors="coerce").dropna()
    two_edge_latency = pd.to_numeric(
        selected.loc[selected["event"] == "two_edge_decision", "decision_latency_ms"],
        errors="coerce",
    ).dropna()
    return {
        "mean_decision_latency_ms": float(all_latency.mean()) if len(all_latency) else None,
        "p95_decision_latency_ms": _percentile(all_latency, 95),
        "mean_two_edge_decision_latency_ms": (
            float(two_edge_latency.mean()) if len(two_edge_latency) else None
        ),
        "p95_two_edge_decision_latency_ms": _percentile(two_edge_latency, 95),
    }


def _strategy_metrics(journeys: pd.DataFrame, trace: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    output: Dict[str, Dict[str, Any]] = {}
    for strategy in STRATEGIES:
        rows = journeys.loc[journeys["strategy"] == strategy]
        completed = rows.loc[rows["success"].astype(bool)]
        traversed = int(pd.to_numeric(rows["traversed_edges"], errors="coerce").fillna(0).sum())
        fallback_steps = int(
            pd.to_numeric(rows["dijkstra_fallback_steps"], errors="coerce").fillna(0).sum()
        )
        stats: Dict[str, Any] = {
            "journeys": int(len(rows)),
            "completed_journeys": int(len(completed)),
            "completion_rate_pct": 100.0 * len(completed) / len(rows) if len(rows) else None,
            "two_edge_only_completed_journeys": int(
                rows["two_edge_only_success"].fillna(False).astype(bool).sum()
            ),
            "mean_actual_travel_time_s_completed": (
                float(completed["travel_time_s"].mean()) if len(completed) else None
            ),
            "median_actual_travel_time_s_completed": (
                float(completed["travel_time_s"].median()) if len(completed) else None
            ),
            "p95_actual_travel_time_s_completed": (
                float(completed["travel_time_s"].quantile(0.95)) if len(completed) else None
            ),
            "mean_distance_m_completed": (
                float(completed["distance_m"].mean()) if len(completed) else None
            ),
            "total_reroutes": int(
                pd.to_numeric(rows["dijkstra_reroutes"], errors="coerce").fillna(0).sum()
            ),
            "total_two_edge_decisions": int(
                pd.to_numeric(rows["intersection_decisions"], errors="coerce").fillna(0).sum()
            ),
            "total_two_edge_alternative_selections": int(
                pd.to_numeric(rows["two_edge_alternative_selections"], errors="coerce")
                .fillna(0).sum()
            ),
            "total_dijkstra_fallback_steps": fallback_steps,
            "fallback_share_pct_of_traversed_edges": (
                100.0 * fallback_steps / traversed if traversed else 0.0
            ),
            "total_backtracking_events": int(
                pd.to_numeric(rows["backtracking_events"], errors="coerce").fillna(0).sum()
            ),
            "total_repeated_node_visits": int(
                pd.to_numeric(rows["repeated_node_visits"], errors="coerce").fillna(0).sum()
            ),
            "total_loop_traps": int(
                pd.to_numeric(rows["loop_traps"], errors="coerce").fillna(0).sum()
            ),
            "mean_execution_time_s": (
                float(pd.to_numeric(rows["execution_time_s"], errors="coerce").mean())
                if len(rows) else None
            ),
            "total_execution_time_s": float(
                pd.to_numeric(rows["execution_time_s"], errors="coerce").fillna(0).sum()
            ),
        }
        stats.update(_latency_stats(trace, strategy))
        output[strategy] = stats
    return output


def _comparison_rows(journeys: pd.DataFrame) -> pd.DataFrame:
    key = ["departure_timestamp", "od_id"]
    wide = journeys.pivot(index=key, columns="strategy", values=["success", "travel_time_s"])
    records: List[Dict[str, Any]] = []
    for index, row in wide.iterrows():
        departure, od_id = index
        geo_success = bool(row[("success", "geopulse_two_edge")])
        geo_time = float(row[("travel_time_s", "geopulse_two_edge")])
        for baseline in ("static_dijkstra", "dynamic_dijkstra"):
            base_success = bool(row[("success", baseline)])
            base_time = float(row[("travel_time_s", baseline)])
            if geo_success and not base_success:
                outcome = "win"
            elif base_success and not geo_success:
                outcome = "loss"
            elif not geo_success and not base_success:
                outcome = "tie"
            else:
                delta = base_time - geo_time
                outcome = "win" if delta > 1e-6 else "loss" if delta < -1e-6 else "tie"
            improvement = (
                100.0 * (base_time - geo_time) / base_time
                if geo_success and base_success and base_time > 0 else np.nan
            )
            records.append({
                "departure_timestamp": departure,
                "od_id": int(od_id),
                "baseline_strategy": baseline,
                "geopulse_success": geo_success,
                "baseline_success": base_success,
                "geopulse_travel_time_s": geo_time,
                "baseline_travel_time_s": base_time,
                "outcome": outcome,
                "travel_time_improvement_pct_joint_success_only": improvement,
            })
    return pd.DataFrame.from_records(records)


def _comparison_summary(comparisons: pd.DataFrame, group_departure: bool) -> pd.DataFrame:
    group = ["baseline_strategy"]
    if group_departure:
        group.insert(0, "departure_timestamp")
    rows = []
    for keys, values in comparisons.groupby(group, sort=True, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        key_values = dict(zip(group, keys))
        both = values.loc[values["geopulse_success"] & values["baseline_success"]]
        rows.append({
            **key_values,
            "matched_journeys": int(len(values)),
            "geopulse_wins": int((values["outcome"] == "win").sum()),
            "geopulse_losses": int((values["outcome"] == "loss").sum()),
            "ties_including_both_failed": int((values["outcome"] == "tie").sum()),
            "jointly_completed_pairs": int(len(both)),
            "mean_pairwise_travel_time_improvement_pct_joint_success_only": (
                float(both["travel_time_improvement_pct_joint_success_only"].mean())
                if len(both) else None
            ),
        })
    return pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", default="data/raw/osm/bhubaneswar_drive.graphml")
    parser.add_argument("--mapping", default="data/processed/traffic_to_osm_mapping_final.parquet")
    parser.add_argument("--predictions", default="results/phase7_predictions.parquet")
    parser.add_argument("--od-pairs", default="results/phase8_od_pairs.csv")
    parser.add_argument("--output-dir", default="results/phase4_1_20261124_full_horizon_v1")
    parser.add_argument("--resume", action="store_true", help="Resume validated existing batches")
    args = parser.parse_args()

    started_at = datetime.now(timezone.utc)
    wall_started = perf_counter()
    paths = {
        "graph": (ROOT / args.graph).resolve(),
        "mapping": (ROOT / args.mapping).resolve(),
        "predictions": (ROOT / args.predictions).resolve(),
        "od_pairs": (ROOT / args.od_pairs).resolve(),
    }
    out = (ROOT / args.output_dir).resolve()
    if not out.is_relative_to(ROOT):
        raise ValueError(f"Output directory must stay inside repository: {out}")
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    hashes = {name: _sha256(path) for name, path in paths.items()}
    settings = {"strategies": list(STRATEGIES), "departure_policy": "all target-valid hourly frames"}
    if out.exists():
        if not args.resume:
            raise FileExistsError(f"Refusing to overwrite {out}; use --resume for existing batches")
        old_manifest_path = out / "run_manifest.json"
        if not old_manifest_path.exists():
            raise ValueError("Cannot resume: run_manifest.json is missing")
        old_manifest = json.loads(old_manifest_path.read_text(encoding="utf-8"))
        if old_manifest.get("input_sha256") != hashes or old_manifest.get("settings") != settings:
            raise ValueError("Cannot resume: inputs or benchmark settings differ from the manifest")
    else:
        out.mkdir(parents=True, exist_ok=False)
    journey_dir = out / "batches" / "journeys"
    trace_dir = out / "batches" / "traces"
    journey_dir.mkdir(parents=True, exist_ok=True)
    trace_dir.mkdir(parents=True, exist_ok=True)

    graph = nx.read_graphml(paths["graph"])
    mapping = pd.read_parquet(paths["mapping"])
    manager = GraphWeightManager(graph, mapping)
    replay = HistoricalTrafficReplay(paths["predictions"])
    frames = [replay.get_frame(timestamp) for timestamp in replay.available_timestamps]
    engine = TemporalJourneyEngine(manager, frames)
    od_pairs = pd.read_csv(paths["od_pairs"])
    required_od_cols = {"od_id", "source_node", "destination_node"}
    if not required_od_cols.issubset(od_pairs.columns):
        raise ValueError(f"O-D file lacks required columns: {sorted(required_od_cols - set(od_pairs.columns))}")
    if od_pairs["od_id"].duplicated().any():
        raise ValueError("O-D source contains duplicate od_id values")
    if od_pairs[["source_node", "destination_node"]].duplicated().any():
        raise ValueError("O-D source contains duplicate origin-destination pairs")

    valid_pairs = []
    excluded_pairs = []
    initial_weights = engine._prediction_weights(0)
    for row in od_pairs.itertuples(index=False):
        origin, destination = str(row.source_node), str(row.destination_node)
        if origin not in manager.adjacency:
            excluded_pairs.append({"od_id": int(row.od_id), "reason": "origin_not_in_graph"})
        elif destination not in manager.graph_node_ids:
            excluded_pairs.append({"od_id": int(row.od_id), "reason": "destination_not_in_graph"})
        elif not engine._route(origin, destination, initial_weights).is_reached:
            excluded_pairs.append({"od_id": int(row.od_id), "reason": "unreachable_in_first_target_frame"})
        else:
            valid_pairs.append(row)
    if len(valid_pairs) < 50:
        print(f"Valid reproducible O-D pairs: {len(valid_pairs)} / 50; excluded={excluded_pairs}", flush=True)
    if not valid_pairs:
        raise ValueError("No valid reachable O-D pairs remain")

    departure_times = [pd.Timestamp(frame.target_valid_timestamp) for frame in frames]
    run_metadata = {
        "experiment": "GeoPulse Phase 4.1 full-horizon temporal routing evaluation",
        "created_utc": started_at.isoformat(),
        "input_files": {name: str(path.relative_to(ROOT)) for name, path in paths.items()},
        "input_sha256": hashes,
        "settings": settings,
        "strategies": list(STRATEGIES),
        "graph_nodes": graph.number_of_nodes(),
        "graph_directed_edges": graph.number_of_edges(),
        "dynamic_mapped_edges": len(manager.dynamic_edge_segments),
        "od_source_count": int(len(od_pairs)),
        "valid_od_count": len(valid_pairs),
        "excluded_od_pairs": excluded_pairs,
        "departure_count": len(departure_times),
        "departure_timestamps_target_valid_utc": [time.isoformat() for time in departure_times],
        "replay_frame_count": len(frames),
        "first_target_valid_timestamp_utc": frames[0].target_valid_timestamp.isoformat(),
        "last_target_valid_timestamp_utc": frames[-1].target_valid_timestamp.isoformat(),
        "final_frame_policy": "Last observed frame held constant on [last_target_valid, next hourly boundary); no motion beyond that exclusive boundary.",
        "observation_policy": "Use only stored predicted_speed and actual_speed; no synthetic observations.",
        "backtracking_definition": "One event per traversal of a directed edge in reverse of any earlier traversed edge, ignoring OSM parallel-edge keys.",
        "repeated_node_definition": "Each arrival at a node previously present in the traversed node path.",
        "loop_trap_definition": "A repeated-node arrival that closes a cycle of at least three traversed edges.",
        "two_edge_only_success_definition": "Successful GeoPulse completion with no Dijkstra safety fallback step and no counted backtracking event.",
        "comparison_definition": "GeoPulse wins if it succeeds while baseline fails, or both succeed and GeoPulse is faster by >1e-6 seconds; losses are symmetric; both failures and exact ties count as ties. Percent improvement is computed only for jointly completed pairs.",
        "traffic_timing": "Each stored replay frame's target_valid_timestamp is its start boundary; all strategies share the same predicted route-cost frames and realized actual-speed stream.",
        "status": "running",
    }
    manifest_path = out / "run_manifest.json"
    if args.resume:
        run_metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest_path.write_text(json.dumps(run_metadata, indent=2), encoding="utf-8")

    completed_departures = set(run_metadata.get("completed_departure_timestamps", []))
    for dep_index, departure in enumerate(departure_times):
        departure_key = departure.isoformat()
        batch_stem = f"{dep_index:02d}_{_safe_timestamp(departure)}"
        journey_path = journey_dir / f"{batch_stem}.csv"
        trace_path = trace_dir / f"{batch_stem}.csv"
        if departure_key in completed_departures and journey_path.exists() and trace_path.exists():
            print(f"Resume: skip departure {dep_index + 1}/{len(departure_times)} {departure_key}", flush=True)
            continue
        journey_rows: List[Dict[str, Any]] = []
        trace_rows: List[Dict[str, Any]] = []
        dep_started = perf_counter()
        for pair in valid_pairs:
            od_id = int(pair.od_id)
            origin, destination = str(pair.source_node), str(pair.destination_node)
            for strategy in STRATEGIES:
                result = engine.run(origin, destination, departure, strategy)
                journey_rows.append({"od_id": od_id, **result.to_dict()})
                for event in result.decision_trace:
                    trace_rows.append({
                        "departure_timestamp": departure_key,
                        "od_id": od_id,
                        "strategy": strategy,
                        **{key: _json_cell(value) for key, value in event.items()},
                    })
        pd.DataFrame(journey_rows).to_csv(journey_path, index=False)
        pd.DataFrame(trace_rows).to_csv(trace_path, index=False)
        completed_departures.add(departure_key)
        run_metadata["completed_departure_timestamps"] = [
            time.isoformat() for time in departure_times if time.isoformat() in completed_departures
        ]
        run_metadata["completed_journey_rows"] = len(completed_departures) * len(valid_pairs) * len(STRATEGIES)
        run_metadata["last_completed_utc"] = datetime.now(timezone.utc).isoformat()
        manifest_path.write_text(json.dumps(run_metadata, indent=2), encoding="utf-8")
        print(
            f"Completed departure {dep_index + 1}/{len(departure_times)} {departure_key}: "
            f"{len(journey_rows)} journeys, {len(trace_rows)} trace events, "
            f"{perf_counter() - dep_started:.1f}s; total elapsed {perf_counter() - wall_started:.1f}s",
            flush=True,
        )

    journey_frames = [pd.read_csv(path) for path in sorted(journey_dir.glob("*.csv"))]
    trace_frames = [pd.read_csv(path) for path in sorted(trace_dir.glob("*.csv"))]
    journeys = pd.concat(journey_frames, ignore_index=True)
    traces = pd.concat(trace_frames, ignore_index=True) if trace_frames else pd.DataFrame()
    if len(journeys) != len(valid_pairs) * len(departure_times) * len(STRATEGIES):
        raise RuntimeError(f"Incomplete journey rows: got {len(journeys)}")
    journeys["two_edge_only_success"] = journeys["two_edge_only_success"].map(
        lambda value: str(value).strip().lower() == "true" if pd.notna(value) else False
    )
    journeys["success"] = journeys["success"].map(
        lambda value: str(value).strip().lower() == "true"
    )
    journeys["departure_timestamp"] = pd.to_datetime(journeys["departure_timestamp"], utc=True).map(
        lambda value: value.isoformat()
    )
    journeys.to_csv(out / "journey_results.csv", index=False)
    traces.to_csv(out / "decision_trace.csv", index=False)

    overall_metrics = _strategy_metrics(journeys, traces)
    pd.DataFrame([{"strategy": strategy, **values} for strategy, values in overall_metrics.items()])\
        .to_csv(out / "strategy_summary.csv", index=False)
    departure_rows = []
    for departure, group in journeys.groupby("departure_timestamp", sort=True):
        group_trace = traces.loc[traces["departure_timestamp"] == departure] if not traces.empty else traces
        for strategy, values in _strategy_metrics(group, group_trace).items():
            departure_rows.append({"departure_timestamp": departure, "strategy": strategy, **values})
    pd.DataFrame(departure_rows).to_csv(out / "departure_summary.csv", index=False)

    comparisons = _comparison_rows(journeys)
    comparisons.to_csv(out / "pairwise_comparison.csv", index=False)
    _comparison_summary(comparisons, group_departure=False).to_csv(
        out / "pairwise_comparison_summary.csv", index=False
    )
    _comparison_summary(comparisons, group_departure=True).to_csv(
        out / "pairwise_comparison_by_departure.csv", index=False
    )
    run_metadata.update({
        "status": "complete",
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "completed_journey_rows": int(len(journeys)),
        "decision_trace_rows": int(len(traces)),
        "overall_strategy_metrics": overall_metrics,
        "overall_pairwise_comparison": _comparison_summary(comparisons, False).to_dict(orient="records"),
        "runner_wall_time_s": perf_counter() - wall_started,
    })
    manifest_path.write_text(json.dumps(run_metadata, indent=2, default=str), encoding="utf-8")
    print(f"Complete: {len(journeys)} matched journeys, {len(traces)} trace events; output={out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
