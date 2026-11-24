"""Run the same observed traffic timeline through all Phase 4 route strategies."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import networkx as nx
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


def _json_value(value: Any) -> str:
    return json.dumps(value, default=str, sort_keys=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", default="data/raw/osm/bhubaneswar_drive.graphml")
    parser.add_argument("--mapping", default="data/processed/traffic_to_osm_mapping_final.parquet")
    parser.add_argument("--predictions", default="results/phase7_predictions.parquet")
    parser.add_argument("--od-pairs", default="results/phase8_od_pairs.csv")
    parser.add_argument("--departure", default="2026-01-15T15:59:00Z")
    parser.add_argument("--od-count", type=int, default=10)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--output-dir", default="results/phase4_20261124_temporal_v1")
    args = parser.parse_args()

    graph_path = (ROOT / args.graph).resolve()
    mapping_path = (ROOT / args.mapping).resolve()
    prediction_path = (ROOT / args.predictions).resolve()
    od_path = (ROOT / args.od_pairs).resolve()
    output_dir = (ROOT / args.output_dir).resolve()
    for path in (graph_path, mapping_path, prediction_path, od_path):
        if not path.is_file():
            raise FileNotFoundError(f"Input file not found: {path}")
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing experiment directory: {output_dir}")
    if args.od_count <= 0 or args.start_index < 0:
        raise ValueError("--od-count must be positive and --start-index non-negative")

    graph = nx.read_graphml(graph_path)
    mapping = pd.read_parquet(mapping_path)
    weight_manager = GraphWeightManager(graph, mapping)
    replay = HistoricalTrafficReplay(prediction_path)
    frames = [replay.get_frame(origin) for origin in replay.available_timestamps]
    engine = TemporalJourneyEngine(weight_manager, frames)
    od_pairs = pd.read_csv(od_path)
    selected_pairs = od_pairs.iloc[args.start_index:args.start_index + args.od_count]
    if selected_pairs.empty:
        raise ValueError("The requested O-D range contains no journeys")

    output_dir.mkdir(parents=True, exist_ok=False)
    comparison_rows = []
    trace_rows = []
    route_rows = []
    for row in selected_pairs.itertuples(index=False):
        od_id = int(row.od_id)
        origin = str(row.source_node)
        destination = str(row.destination_node)
        for strategy in STRATEGIES:
            result = engine.run(origin, destination, args.departure, strategy)
            comparison_rows.append({"od_id": od_id, **result.to_dict()})
            route_rows.append({
                "od_id": od_id,
                "strategy": strategy,
                "traversed_edge_path": _json_value(result.traversed_edge_path),
            })
            for event in result.decision_trace:
                trace_rows.append({
                    "od_id": od_id,
                    "strategy": strategy,
                    **{key: _json_value(value) if isinstance(value, (tuple, list, dict)) else value
                       for key, value in event.items()},
                })
            print(
                f"OD {od_id:02d} {strategy}: success={result.success} "
                f"time_s={result.travel_time_s:.2f} edges={result.traversed_edges} "
                f"decisions={result.intersection_decisions} "
                f"fallback_steps={result.dijkstra_fallback_steps} "
                f"execution_s={result.execution_time_s:.3f}"
            )

    comparison = pd.DataFrame(comparison_rows)
    comparison.to_csv(output_dir / "journey_comparison.csv", index=False)
    pd.DataFrame(trace_rows).to_csv(output_dir / "decision_trace.csv", index=False)
    pd.DataFrame(route_rows).to_csv(output_dir / "traversed_routes.csv", index=False)

    grouped = comparison.groupby("strategy", sort=False).agg(
        journeys=("success", "size"),
        completed=("success", "sum"),
        two_edge_only_completed=("two_edge_only_success", "sum"),
        mean_actual_travel_time_s=("travel_time_s", "mean"),
        mean_distance_m=("distance_m", "mean"),
        mean_intersection_decisions=("intersection_decisions", "mean"),
        total_two_edge_alternative_selections=("two_edge_alternative_selections", "sum"),
        mean_prediction_updates=("prediction_updates_applied", "mean"),
        total_dijkstra_fallback_steps=("dijkstra_fallback_steps", "sum"),
        total_backtracking_steps=("backtracking_steps", "sum"),
        total_repeated_node_visits=("repeated_node_visits", "sum"),
        total_loop_traps=("loop_traps", "sum"),
        mean_decision_latency_ms=("mean_decision_latency_ms", "mean"),
        p95_journey_decision_latency_ms=(
            "p95_decision_latency_ms", lambda values: values.quantile(0.95)
        ),
        mean_two_edge_latency_ms=("mean_two_edge_decision_latency_ms", "mean"),
        p95_two_edge_latency_ms=(
            "p95_two_edge_decision_latency_ms", lambda values: values.quantile(0.95)
        ),
        mean_execution_time_s=("execution_time_s", "mean"),
    ).reset_index()
    grouped.to_csv(output_dir / "strategy_summary.csv", index=False)

    summary = {
        "experiment": "GeoPulse Phase 4 temporal journey comparison",
        "departure_timestamp": args.departure,
        "strategies": list(STRATEGIES),
        "od_ids": [int(value) for value in selected_pairs["od_id"].tolist()],
        "graph_nodes": graph.number_of_nodes(),
        "graph_directed_edges": graph.number_of_edges(),
        "mapped_dynamic_edges": len(weight_manager.dynamic_edge_segments),
        "prediction_frames": len(frames),
        "target_valid_range": [
            frames[0].target_valid_timestamp.isoformat(),
            frames[-1].target_valid_timestamp.isoformat(),
        ],
        "actual_speed_observations": sum(len(frame.realized_speeds) for frame in frames),
        "realized_dynamic_edge_coverage": [
            {
                "target_valid_timestamp": frame.target_valid_timestamp.isoformat(),
                "dynamic_edges_with_valid_observations": len(
                    weight_manager.build_scenario_weights(frame.realized_speeds)[2]
                ),
                "missing_realized_segments": frame.missing_realized_count,
                "invalid_realized_segments": frame.invalid_realized_count,
            }
            for frame in frames
        ],
        "input_files": {
            str(path.relative_to(ROOT)): _sha256(path)
            for path in (graph_path, mapping_path, prediction_path, od_path)
        },
        "prediction_actual_semantics": (
            "actual_speed is stored next-hour observed currentSpeed; it is used only for motion"
        ),
        "routing_semantics": (
            "all three strategies use the same departure-time predicted route weights and the same "
            "hourly realized-speed stream; updates affect route choice at the next reached node"
        ),
        "strategy_summary": grouped.to_dict(orient="records"),
    }
    (output_dir / "run_manifest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Saved Phase 4 comparison to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
