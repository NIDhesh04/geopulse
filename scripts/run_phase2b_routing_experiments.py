"""Controlled Phase 2B routing ablations on the Bhubaneswar OSM graph.

Screening reproduces Phase 2A's first 10 O-D pairs at 2026-01-15 14:00 UTC.
Validation uses O-D IDs 10-29 at 08:00, 14:00, and 20:00 UTC. All methods in
each scenario share the same predicted edge weights. Bounded search examines
only a capped local tree; Dijkstra remains an independently counted safety
recovery and reference baseline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import run_phase2a_real_network_evaluation as phase2a
from src.routing.candidate_generator import CandidateGenerationStrategy, CandidateGenerator
from src.routing.decision_strategies import (
    AdaptiveDecisionStrategy,
    BoundedReachabilityDecisionStrategy,
    DestinationAwareDecisionStrategy,
    GreedyDecisionStrategy,
    LimitedLookaheadDecisionStrategy,
)
from src.routing.lookahead import BoundedReachabilityEvaluator, LimitedLookaheadEvaluator
from src.routing.route_controller import RouteController
from src.routing.traffic_weights import GraphWeightManager
from src.routing.two_edge_selector import TwoEdgeSelector

Edge = Tuple[str, str, int]
TIMESTAMPS = (
    pd.Timestamp("2026-01-15 08:00:00", tz="UTC"),
    pd.Timestamp("2026-01-15 14:00:00", tz="UTC"),
    pd.Timestamp("2026-01-15 20:00:00", tz="UTC"),
)


@dataclass(frozen=True)
class AlgorithmConfig:
    name: str
    kind: str
    heuristic_speed_kmh: float = 25.0
    depth: int = 2
    branch_limit: int = 4
    branch_ranking: str = "immediate"
    candidate_policy: Optional[str] = None
    congestion_threshold_kmh: float = 25.0
    local_backtracking: bool = False
    max_hops_multiplier: float = 3.0


def candidate_policy(value: Optional[str]) -> Optional[CandidateGenerationStrategy]:
    if value is None or value == "auto":
        return None
    return CandidateGenerationStrategy(value)


def screening_configs() -> List[AlgorithmConfig]:
    configs = [
        AlgorithmConfig("Dijkstra", "dijkstra"),
        AlgorithmConfig("Greedy Two-Edge", "greedy"),
        AlgorithmConfig("Destination-Aware Two-Edge (25 km/h)", "destination"),
        AlgorithmConfig("Lookahead Two-Edge (depth=2, branches=4)", "lookahead", depth=2, branch_limit=4),
        AlgorithmConfig(
            "Adaptive Two-Edge (Phase 2A candidate pool)",
            "adaptive",
            depth=2,
            branch_limit=4,
            candidate_policy=CandidateGenerationStrategy.DESTINATION_AWARE.value,
        ),
        AlgorithmConfig(
            "Adaptive Two-Edge (diverse destination/lookahead pair)",
            "adaptive",
            depth=2,
            branch_limit=4,
            candidate_policy=CandidateGenerationStrategy.ADAPTIVE_DIVERSE.value,
        ),
    ]

    # Historical bounded lookahead: vary depth and branching independently.
    for depth, branches in ((1, 2), (1, 4), (2, 2), (3, 2), (3, 4), (5, 2), (5, 4)):
        name = f"Lookahead Two-Edge (depth={depth}, branches={branches})"
        if name not in {item.name for item in configs}:
            configs.append(
                AlgorithmConfig(name, "lookahead", depth=depth, branch_limit=branches)
            )

    # Reachability-aware bounded search uses the admissible 120 km/h geometric
    # lower bound and treats a locally trapped continuation as nonviable.
    for depth, branches, ranking in (
        (1, 2, "destination"),
        (1, 4, "destination"),
        (2, 2, "destination"),
        (2, 4, "destination"),
        (3, 2, "immediate"),
        (3, 2, "destination"),
        (3, 4, "destination"),
        (3, 4, "connectivity"),
        (5, 2, "destination"),
        (5, 4, "destination"),
    ):
        name = f"Reachability Two-Edge (depth={depth}, branches={branches}, rank={ranking})"
        configs.append(
            AlgorithmConfig(
                name,
                "reachability",
                heuristic_speed_kmh=120.0,
                depth=depth,
                branch_limit=branches,
                branch_ranking=ranking,
            )
        )

    configs.extend(
        [
            AlgorithmConfig(
                "Reachability d3b4 + fastest/progress pair",
                "reachability",
                heuristic_speed_kmh=120.0,
                depth=3,
                branch_limit=4,
                branch_ranking="destination",
                candidate_policy=CandidateGenerationStrategy.FASTEST_PLUS_PROGRESS.value,
            ),
            AlgorithmConfig(
                "Reachability d3b4 + destination/lookahead pair",
                "reachability",
                heuristic_speed_kmh=120.0,
                depth=3,
                branch_limit=4,
                branch_ranking="destination",
                candidate_policy=CandidateGenerationStrategy.DESTINATION_PLUS_LOOKAHEAD.value,
            ),
            AlgorithmConfig(
                "Lookahead Two-Edge (depth=2, branches=4) + local backtracking",
                "lookahead",
                depth=2,
                branch_limit=4,
                local_backtracking=True,
                max_hops_multiplier=10.0,
            ),
            AlgorithmConfig(
                "Lookahead Two-Edge (depth=5, branches=4) + local backtracking",
                "lookahead",
                depth=5,
                branch_limit=4,
                local_backtracking=True,
                max_hops_multiplier=10.0,
            ),
            AlgorithmConfig(
                "Reachability Two-Edge (depth=3, branches=4, rank=destination) + local backtracking",
                "reachability",
                heuristic_speed_kmh=120.0,
                depth=3,
                branch_limit=4,
                branch_ranking="destination",
                local_backtracking=True,
                max_hops_multiplier=10.0,
            ),
        ]
    )
    return configs


def validation_configs() -> List[AlgorithmConfig]:
    # The selected configuration is filled in by the CLI after screening.
    return [
        AlgorithmConfig("Dijkstra", "dijkstra"),
        AlgorithmConfig("Destination-Aware Two-Edge (25 km/h)", "destination"),
        AlgorithmConfig("Lookahead Two-Edge (depth=2, branches=4)", "lookahead", depth=2, branch_limit=4),
        AlgorithmConfig(
            "Adaptive Two-Edge (Phase 2A candidate pool)",
            "adaptive",
            depth=2,
            branch_limit=4,
            candidate_policy=CandidateGenerationStrategy.DESTINATION_AWARE.value,
        ),
        AlgorithmConfig(
            "Adaptive Two-Edge (diverse destination/lookahead pair)",
            "adaptive",
            depth=2,
            branch_limit=4,
            candidate_policy=CandidateGenerationStrategy.ADAPTIVE_DIVERSE.value,
        ),
    ]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_inputs():
    graph_path = ROOT / "data/raw/osm/bhubaneswar_drive.graphml"
    mapping_path = ROOT / "data/processed/traffic_to_osm_mapping_final.parquet"
    predictions_path = ROOT / "results/phase7_predictions.parquet"
    od_path = ROOT / "results/phase8_od_pairs.csv"
    graph = nx.read_graphml(graph_path)
    mapping = pd.read_parquet(mapping_path)
    wm = GraphWeightManager(graph, mapping)
    predictions = pd.read_parquet(predictions_path)
    rounded = pd.to_datetime(predictions["timestamp"], utc=True).dt.round("h")
    od_table = pd.read_csv(od_path)
    od_table["source_node"] = od_table["source_node"].map(lambda value: str(int(value)))
    od_table["destination_node"] = od_table["destination_node"].map(lambda value: str(int(value)))
    metadata = {
        "graph_nodes": int(graph.number_of_nodes()),
        "graph_directed_edges": int(graph.number_of_edges()),
        "prediction_rows_total": int(len(predictions)),
        "od_rows_available": int(len(od_table)),
        "inputs_sha256": {
            "graphml": file_sha256(graph_path),
            "mapping_parquet": file_sha256(mapping_path),
            "predictions_parquet": file_sha256(predictions_path),
            "od_csv": file_sha256(od_path),
        },
    }
    return graph, wm, predictions, rounded, od_table, metadata


def weights_for_timestamp(wm, predictions, rounded, timestamp):
    rows = predictions.loc[rounded == timestamp]
    if rows["traffic_segment_id"].nunique() != 700:
        raise RuntimeError(
            f"Expected 700 prediction segments at {timestamp.isoformat()}, "
            f"found {rows['traffic_segment_id'].nunique()}."
        )
    speeds_by_segment = dict(zip(rows["traffic_segment_id"], rows["predicted_speed"]))
    weights, speeds, dynamic_edges = wm.build_scenario_weights(speeds_by_segment)
    return weights, speeds, int(len(rows)), int(len(dynamic_edges))


def make_selector(wm, config: AlgorithmConfig, seed: int):
    node_coords = {
        str(node): (float(data["y"]), float(data["x"]))
        for node, data in wm.G.nodes(data=True)
        if "y" in data and "x" in data
    }
    generator = CandidateGenerator(
        wm.adjacency,
        wm.edge_lengths,
        node_coords,
        default_free_flow_speed_kmh=config.heuristic_speed_kmh,
        random_seed=seed,
    )
    if config.kind == "greedy":
        strategy = GreedyDecisionStrategy()
    elif config.kind == "destination":
        strategy = DestinationAwareDecisionStrategy()
    elif config.kind == "lookahead":
        evaluator = LimitedLookaheadEvaluator(
            wm.adjacency,
            {},
            generator.estimate_remaining_time,
            depth=config.depth,
            max_expansions_per_node=config.branch_limit,
        )
        strategy = LimitedLookaheadDecisionStrategy(evaluator)
    elif config.kind == "reachability":
        evaluator = BoundedReachabilityEvaluator(
            wm.adjacency,
            {},
            generator.estimate_remaining_time,
            depth=config.depth,
            max_expansions_per_node=config.branch_limit,
            branch_ranking=config.branch_ranking,
        )
        strategy = BoundedReachabilityDecisionStrategy(evaluator)
    elif config.kind == "adaptive":
        evaluator = LimitedLookaheadEvaluator(
            wm.adjacency,
            {},
            generator.estimate_remaining_time,
            depth=config.depth,
            max_expansions_per_node=config.branch_limit,
        )
        strategy = AdaptiveDecisionStrategy(
            DestinationAwareDecisionStrategy(),
            LimitedLookaheadDecisionStrategy(evaluator),
            congestion_speed_threshold_kmh=config.congestion_threshold_kmh,
        )
    else:
        raise ValueError(f"Unknown algorithm kind: {config.kind}")

    return phase2a.TimedTwoEdgeSelector(
        generator,
        strategy,
        candidate_strategy=candidate_policy(config.candidate_policy),
        avoid_visited_successors=True,
    )


def evaluate_two_edge(wm, config, weights, speeds, source, destination, dijkstra, seed):
    selector = make_selector(wm, config, seed)
    controller = RouteController(
        wm.adjacency,
        wm.edge_lengths,
        selector,
        max_hops_multiplier=config.max_hops_multiplier,
        local_backtracking=config.local_backtracking,
        strict_loop_avoidance=True,
    )
    started = time.perf_counter()
    result = controller.execute_journey(
        source=source,
        destination=destination,
        initial_weights=weights,
        initial_speeds=speeds,
        reference_dijkstra=dijkstra,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    calls = selector.selector_calls
    cycle_recoveries = sum(
        any(tag in step.strategy_name for tag in ("[RECOVERY_CYCLE_BREAKER]", "[RECOVERY_CYCLE_BACKTRACK]"))
        for step in result.decision_steps
    )
    fallback_steps = sum(
        any(tag in step.strategy_name for tag in ("[RECOVERY_CYCLE_BREAKER]", "[RECOVERY_SHORTEST_PATH]", "[RECOVERY_FORWARD]"))
        for step in result.decision_steps
    )
    backtracking_steps = sum("BACKTRACK]" in step.strategy_name for step in result.decision_steps)
    primary_steps = [step for step in result.decision_steps if "[RECOVERY_" not in step.strategy_name]
    intersection_latencies = [call["latency_ms"] for call in calls if call["is_intersection"]]
    all_latencies = [call["latency_ms"] for call in calls]
    loop_traps = sum(call["is_dead_end"] and "Loop trap" in str(call.get("decision_reason", "")) for call in calls)
    repeated = phase2a.repeated_node_arrivals(result.node_path) + cycle_recoveries
    row = {
        "algorithm": config.name,
        "kind": config.kind,
        "journey_success": bool(result.is_success),
        "two_edge_only_success": bool(result.is_success and fallback_steps == 0 and backtracking_steps == 0),
        "two_edge_with_local_backtracking_success": bool(result.is_success and fallback_steps == 0),
        "total_travel_time_s": float(result.total_travel_time_s),
        "total_distance_m": float(result.total_distance_m),
        "intersection_decisions": int(sum(call["is_intersection"] for call in calls)),
        "selector_calls": int(len(calls)),
        "two_edge_traversal_steps": int(len(primary_steps)),
        "total_route_steps": int(result.total_decisions),
        "repeated_node_visits": int(repeated),
        "cycle_recoveries": int(cycle_recoveries),
        "loop_trap_recoveries": int(loop_traps),
        "dijkstra_fallback_steps": int(fallback_steps),
        "backtracking_steps": int(backtracking_steps),
        "execution_time_ms": float(elapsed_ms),
        "mean_decision_latency_ms": (
            float(sum(intersection_latencies) / len(intersection_latencies))
            if intersection_latencies
            else (float(sum(all_latencies) / len(all_latencies)) if all_latencies else 0.0)
        ),
        "p95_decision_latency_ms": (
            float(pd.Series(intersection_latencies or all_latencies).quantile(0.95))
            if intersection_latencies or all_latencies
            else 0.0
        ),
        "two_edge_prefix_time_s": float(sum(step.travel_time_s for step in primary_steps)),
        "two_edge_prefix_distance_m": float(sum(step.length_m for step in primary_steps)),
        "termination_reason": result.termination_reason,
        "dijkstra_reference_time_s": float(dijkstra.total_cost),
        "dijkstra_reference_distance_m": float(sum(wm.edge_lengths.get(e, 0.0) for e in dijkstra.edge_path)),
        "algorithm_config_json": json.dumps(asdict(config), sort_keys=True),
    }
    trace = calls
    cycle_steps = {
        step.step_index
        for step in result.decision_steps
        if "[RECOVERY_CYCLE_BREAKER]" in step.strategy_name or "[RECOVERY_CYCLE_BACKTRACK]" in step.strategy_name
    }
    for call in trace:
        call["attempt_triggered_cycle_recovery"] = call["step_index"] in cycle_steps
        call["algorithm_config_json"] = json.dumps(asdict(config), sort_keys=True)
    return row, trace


def summarize(records: pd.DataFrame) -> pd.DataFrame:
    keys = ["stage", "prediction_timestamp_utc", "algorithm"]
    rows = []
    for (stage, timestamp, algorithm), group in records.groupby(keys, sort=False):
        non_null = group["two_edge_only_success"].dropna()
        route_steps = group["total_route_steps"].sum()
        rows.append({
            "stage": stage,
            "prediction_timestamp_utc": timestamp,
            "algorithm": algorithm,
            "journeys": int(len(group)),
            "journey_success_rate_pct": float(group["journey_success"].mean() * 100.0),
            "two_edge_only_success_rate_pct": float(non_null.mean() * 100.0) if len(non_null) else None,
            "mean_travel_time_s": float(group["total_travel_time_s"].mean()),
            "mean_distance_m": float(group["total_distance_m"].mean()),
            "mean_repeated_node_visits": float(group["repeated_node_visits"].mean()),
            "loop_trap_recoveries": int(group["loop_trap_recoveries"].sum()),
            "cycle_recoveries": int(group["cycle_recoveries"].sum()),
            "dijkstra_fallback_steps": int(group["dijkstra_fallback_steps"].sum()),
            "dijkstra_fallback_step_share_pct": (
                float(group["dijkstra_fallback_steps"].sum() / route_steps * 100.0)
                if route_steps else 0.0
            ),
            "backtracking_steps": int(group["backtracking_steps"].sum()),
            "mean_intersection_decisions": float(group["intersection_decisions"].mean()),
            "mean_decision_latency_ms": float(group["mean_decision_latency_ms"].mean()),
            "mean_p95_decision_latency_ms": float(group["p95_decision_latency_ms"].mean()),
            "mean_execution_time_ms": float(group["execution_time_ms"].mean()),
        })
    return pd.DataFrame(rows)


def run_stage(stage: str, output_dir: Path, selected_config: Optional[AlgorithmConfig], seed: int = 42):
    graph, wm, predictions, rounded, od_table, input_metadata = load_inputs()
    if stage == "screen":
        od_ids = list(range(10))
        timestamps = [pd.Timestamp("2026-01-15 14:00:00", tz="UTC")]
        configs = screening_configs()
    elif stage == "validate":
        od_ids = list(range(10, 30))
        timestamps = list(TIMESTAMPS)
        configs = validation_configs()
        if selected_config is None:
            raise ValueError("Validation requires --selected-config from the screening results.")
        configs.append(selected_config)
    else:
        raise ValueError(f"Unknown stage: {stage}")

    selected_ods = od_table[od_table.od_id.isin(od_ids)].copy()
    if selected_ods.od_id.astype(int).tolist() != od_ids:
        raise RuntimeError(f"Expected ordered O-D ids {od_ids}; found {selected_ods.od_id.tolist()}.")

    records: List[Dict[str, Any]] = []
    traces: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    scenario_metadata = []
    for timestamp in timestamps:
        weights, speeds, prediction_rows, dynamic_edges = weights_for_timestamp(
            wm, predictions, rounded, timestamp
        )
        scenario_metadata.append({
            "prediction_timestamp_utc": timestamp.isoformat(),
            "prediction_rows": prediction_rows,
            "dynamic_weighted_edges": dynamic_edges,
        })
        for od in selected_ods.itertuples(index=False):
            dijkstra_row, dijkstra = phase2a.evaluate_dijkstra(
                wm.adjacency, wm.edge_lengths, weights, od.source_node, od.destination_node
            )
            if not dijkstra.is_reached:
                raise RuntimeError(f"Unreachable O-D {od.source_node}->{od.destination_node} at {timestamp}.")
            od_configs = configs if stage == "screen" else configs
            for config in od_configs:
                if config.kind == "dijkstra":
                    row, trace = dict(dijkstra_row), []
                else:
                    row, trace = evaluate_two_edge(
                        wm, config, weights, speeds,
                        od.source_node, od.destination_node, dijkstra, seed,
                    )
                row.update({
                    "stage": stage,
                    "od_id": int(od.od_id),
                    "source_node": od.source_node,
                    "destination_node": od.destination_node,
                    "haversine_distance_m": float(od.haversine_dist_m),
                    "prediction_timestamp_utc": timestamp.isoformat(),
                    "random_seed": int(seed),
                    "algorithm_config_json": json.dumps(asdict(config), sort_keys=True),
                })
                records.append(row)
                for item in trace:
                    traces.append({
                        "stage": stage,
                        "od_id": int(od.od_id),
                        "source_node": od.source_node,
                        "destination_node": od.destination_node,
                        "algorithm": config.name,
                        "prediction_timestamp_utc": timestamp.isoformat(),
                        **item,
                    })
                if config.kind != "dijkstra" and (
                    not row["two_edge_only_success"]
                    or row["repeated_node_visits"]
                    or row["loop_trap_recoveries"]
                    or row["dijkstra_fallback_steps"]
                ):
                    failures.append({
                        "stage": stage,
                        "od_id": int(od.od_id),
                        "source_node": od.source_node,
                        "destination_node": od.destination_node,
                        "prediction_timestamp_utc": timestamp.isoformat(),
                        "algorithm": config.name,
                        "journey_success": row["journey_success"],
                        "two_edge_only_success": row["two_edge_only_success"],
                        "repeated_node_visits": row["repeated_node_visits"],
                        "loop_trap_recoveries": row["loop_trap_recoveries"],
                        "dijkstra_fallback_steps": row["dijkstra_fallback_steps"],
                        "backtracking_steps": row["backtracking_steps"],
                        "total_travel_time_s": row["total_travel_time_s"],
                        "two_edge_prefix_time_s": row["two_edge_prefix_time_s"],
                        "termination_reason": row["termination_reason"],
                    })
            print(f"{stage}: {timestamp.isoformat()} O-D {od.od_id} complete ({len(configs)} configurations)")

    result_df = pd.DataFrame(records)
    summary = summarize(result_df)
    output_dir.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(output_dir / "journey_results.csv", index=False)
    summary.to_csv(output_dir / "summary_metrics.csv", index=False)
    pd.DataFrame(traces).to_csv(output_dir / "decision_trace.csv", index=False)
    pd.DataFrame(failures).to_csv(output_dir / "failure_analysis.csv", index=False)
    metadata = {
        **input_metadata,
        "stage": stage,
        "od_ids": od_ids,
        "timestamps": [timestamp.isoformat() for timestamp in timestamps],
        "scenario_weights": scenario_metadata,
        "seed": seed,
        "algorithm_configurations": [asdict(config) for config in configs],
        "safety_recovery_enabled": True,
        "strict_active_path_loop_avoidance": True,
        "local_backtracking_enabled": any(config.local_backtracking for config in configs),
        "max_hops_multiplier_by_algorithm": {
            config.name: config.max_hops_multiplier for config in configs
        },
        "two_edge_only_definition": "Destination reached with zero Dijkstra fallback steps and zero backtracking steps.",
        "dijkstra_fallback_counting": "RECOVERY_FORWARD, RECOVERY_CYCLE_BREAKER, and RECOVERY_SHORTEST_PATH route edges only.",
        "result_rows": int(len(result_df)),
        "trace_rows": int(len(traces)),
    }
    with (output_dir / "run_metadata.json").open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)
    make_figures(summary, output_dir)
    print(summary.to_string(index=False))
    print(f"Saved {len(result_df)} journey rows and {len(traces)} selector traces to {output_dir}")
    return result_df, summary


def make_figures(summary: pd.DataFrame, output_dir: Path) -> None:
    figure_dir = output_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    for stage, group in summary.groupby("stage", sort=False):
        group = group.reset_index(drop=True)
        names = group.algorithm.tolist()
        x = range(len(group))
        fig, axes = plt.subplots(1, 3, figsize=(max(18, len(group) * 0.8), 6))
        axes[0].bar(x, group.two_edge_only_success_rate_pct, color="#15803d")
        axes[0].set_title("Standalone Two-Edge completion")
        axes[0].set_ylabel("% journeys")
        axes[0].set_ylim(0, 105)
        axes[1].bar(x, group.dijkstra_fallback_steps, color="#ea580c")
        axes[1].set_title("Dijkstra fallback steps")
        axes[2].bar(x, group.mean_decision_latency_ms, color="#2563eb")
        axes[2].set_title("Mean intersection latency")
        for ax in axes:
            ax.set_xticks(list(x), names, rotation=70, ha="right", fontsize=8)
            ax.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        fig.savefig(figure_dir / f"{stage}_comparison.png", dpi=160)
        plt.close(fig)


def config_from_name(name: str) -> AlgorithmConfig:
    for config in screening_configs():
        if config.name == name:
            return config
    raise ValueError(f"Selected configuration was not in the screening registry: {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("screen", "validate"), required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--selected-config", help="Exact screening configuration name for validation.")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    output = Path(args.output_dir)
    if not output.is_absolute():
        output = ROOT / output
    selected = config_from_name(args.selected_config) if args.selected_config else None
    run_stage(args.stage, output, selected, args.seed)


if __name__ == "__main__":
    main()
