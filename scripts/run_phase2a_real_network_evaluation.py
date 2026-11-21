"""Reproducible real-network validation of the GeoPulse Two-Edge strategies.

Usage:
    python scripts/run_phase2a_real_network_evaluation.py --output-dir results/phase2a_20261122_v1

The default evaluation uses the first ten fixed O-D rows in phase8_od_pairs.csv
and the stored Phase 7 prediction slice rounded to 2026-01-15 14:00 UTC.
It runs the independent Dijkstra baseline and five Two-Edge configurations on
the same directed graph and predicted edge weights. Safety recovery remains
enabled in RouteController, but recovery edges and independent Two-Edge
completion are recorded separately.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
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

from src.routing.candidate_generator import CandidateGenerator
from src.routing.dijkstra import custom_dijkstra
from src.routing.decision_strategies import (
    AdaptiveDecisionStrategy,
    DestinationAwareDecisionStrategy,
    GreedyDecisionStrategy,
    LimitedLookaheadDecisionStrategy,
)
from src.routing.lookahead import LimitedLookaheadEvaluator
from src.routing.route_controller import RouteController
from src.routing.traffic_weights import GraphWeightManager
from src.routing.two_edge_selector import TwoEdgeSelector


Edge = Tuple[str, str, int]
PREDICTION_TIME = pd.Timestamp("2026-01-15 14:00:00", tz="UTC")
OD_IDS = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9)


class TimedTwoEdgeSelector(TwoEdgeSelector):
    """Collect complete selector-call latency, including candidate generation."""

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.selector_calls: List[Dict[str, Any]] = []

    def decide_next_edge(
        self,
        step_index: int,
        current_node: str,
        destination: str,
        edge_weights: Dict[Edge, float],
        edge_speeds: Optional[Dict[Edge, float]] = None,
        previous_node: Optional[str] = None,
        visited_nodes: Optional[set] = None,
        excluded_edges: Optional[set] = None,
    ):
        started = time.perf_counter()
        result = super().decide_next_edge(
            step_index=step_index,
            current_node=current_node,
            destination=destination,
            edge_weights=edge_weights,
            edge_speeds=edge_speeds,
            previous_node=previous_node,
            visited_nodes=visited_nodes,
            excluded_edges=excluded_edges,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        self.selector_calls.append(
            {
                "step_index": int(step_index),
                "current_node": str(current_node),
                "destination_node": str(destination),
                "previous_node": None if previous_node is None else str(previous_node),
                "out_degree": len(self.candidate_generator.adjacency.get(str(current_node), [])),
                "latency_ms": latency_ms,
                "is_intersection": result.candidate_a is not None
                and result.candidate_b is not None,
                "is_dead_end": result.is_dead_end,
                "is_forced": result.is_forced,
                "selected_next_node": result.next_node,
                "selected_edge": result.selected_edge,
                "strategy_used": result.strategy_name,
                "decision_reason": result.decision_reason,
                "candidate_a_node": (
                    result.candidate_a.v if result.candidate_a is not None else None
                ),
                "candidate_a_cost_s": (
                    result.candidate_a.travel_time_s if result.candidate_a is not None else None
                ),
                "candidate_a_heuristic_s": (
                    result.candidate_a.heuristic_remaining_s
                    if result.candidate_a is not None else None
                ),
                "candidate_a_visited": (
                    result.candidate_a.v in (visited_nodes or set())
                    if result.candidate_a is not None else None
                ),
                "candidate_b_node": (
                    result.candidate_b.v if result.candidate_b is not None else None
                ),
                "candidate_b_cost_s": (
                    result.candidate_b.travel_time_s if result.candidate_b is not None else None
                ),
                "candidate_b_heuristic_s": (
                    result.candidate_b.heuristic_remaining_s
                    if result.candidate_b is not None else None
                ),
                "candidate_b_visited": (
                    result.candidate_b.v in (visited_nodes or set())
                    if result.candidate_b is not None else None
                ),
            }
        )
        return result


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_inputs() -> Tuple[nx.MultiDiGraph, GraphWeightManager, Dict[Edge, float], Dict[Edge, float], pd.DataFrame, Dict[str, Any]]:
    graph_path = ROOT / "data/raw/osm/bhubaneswar_drive.graphml"
    mapping_path = ROOT / "data/processed/traffic_to_osm_mapping_final.parquet"
    predictions_path = ROOT / "results/phase7_predictions.parquet"
    od_path = ROOT / "results/phase8_od_pairs.csv"

    graph = nx.read_graphml(graph_path)
    mapping = pd.read_parquet(mapping_path)
    weight_manager = GraphWeightManager(graph, mapping)

    predictions = pd.read_parquet(predictions_path)
    prediction_times = pd.to_datetime(predictions["timestamp"], utc=True).dt.round("h")
    prediction_slice = predictions.loc[prediction_times == PREDICTION_TIME]
    if prediction_slice.empty:
        raise RuntimeError(f"No stored prediction rows for {PREDICTION_TIME.isoformat()}.")
    if prediction_slice["traffic_segment_id"].nunique() != 700:
        raise RuntimeError(
            "Expected predictions for 700 distinct traffic segments at the fixed timestamp; "
            f"found {prediction_slice['traffic_segment_id'].nunique()}."
        )

    predicted_speeds = dict(
        zip(prediction_slice["traffic_segment_id"], prediction_slice["predicted_speed"])
    )
    weights, speeds, dynamic_edges = weight_manager.build_scenario_weights(predicted_speeds)

    ods = pd.read_csv(od_path)
    selected = ods[ods["od_id"].isin(OD_IDS)].copy()
    if tuple(selected["od_id"].astype(int)) != OD_IDS:
        raise RuntimeError(f"Could not load the fixed O-D IDs in order: {OD_IDS}.")
    selected["source_node"] = selected["source_node"].map(lambda value: str(int(value)))
    selected["destination_node"] = selected["destination_node"].map(lambda value: str(int(value)))

    metadata = {
        "prediction_timestamp_utc": PREDICTION_TIME.isoformat(),
        "prediction_rows": int(len(prediction_slice)),
        "prediction_segments": int(prediction_slice["traffic_segment_id"].nunique()),
        "graph_nodes": int(graph.number_of_nodes()),
        "graph_directed_edges": int(graph.number_of_edges()),
        "dynamic_weighted_edges": int(len(dynamic_edges)),
        "od_ids": list(OD_IDS),
        "od_pairs": [
            {
                "od_id": int(row.od_id),
                "source_node": row.source_node,
                "destination_node": row.destination_node,
                "haversine_distance_m": float(row.haversine_dist_m),
            }
            for row in selected.itertuples(index=False)
        ],
        "inputs_sha256": {
            "graphml": sha256_file(graph_path),
            "mapping_parquet": sha256_file(mapping_path),
            "predictions_parquet": sha256_file(predictions_path),
            "od_csv": sha256_file(od_path),
        },
    }
    return graph, weight_manager, weights, speeds, selected, metadata


def make_selector(
    weight_manager: GraphWeightManager,
    heuristic_speed_kmh: float,
    algorithm: str,
    seed: int,
    strict_loop_avoidance: bool,
) -> TimedTwoEdgeSelector:
    node_coords = {
        str(node): (float(data["y"]), float(data["x"]))
        for node, data in weight_manager.G.nodes(data=True)
        if "y" in data and "x" in data
    }
    generator = CandidateGenerator(
        adjacency=weight_manager.adjacency,
        edge_lengths=weight_manager.edge_lengths,
        node_coords=node_coords,
        default_free_flow_speed_kmh=heuristic_speed_kmh,
        random_seed=seed,
    )

    if algorithm == "Greedy Two-Edge":
        strategy = GreedyDecisionStrategy()
    elif algorithm.startswith("Destination-Aware"):
        strategy = DestinationAwareDecisionStrategy()
    elif algorithm == "Lookahead Two-Edge (depth=2)":
        evaluator = LimitedLookaheadEvaluator(
            weight_manager.adjacency,
            weight_manager.get_static_weights(),
            generator.estimate_remaining_time,
            depth=2,
            max_expansions_per_node=4,
        )
        strategy = LimitedLookaheadDecisionStrategy(evaluator)
    elif algorithm == "Adaptive Two-Edge":
        evaluator = LimitedLookaheadEvaluator(
            weight_manager.adjacency,
            weight_manager.get_static_weights(),
            generator.estimate_remaining_time,
            depth=2,
            max_expansions_per_node=4,
        )
        strategy = AdaptiveDecisionStrategy(
            DestinationAwareDecisionStrategy(),
            LimitedLookaheadDecisionStrategy(evaluator),
            congestion_speed_threshold_kmh=25.0,
        )
    else:
        raise ValueError(f"Unknown algorithm: {algorithm}")

    return TimedTwoEdgeSelector(
        generator,
        strategy,
        avoid_visited_successors=strict_loop_avoidance,
    )


def repeated_node_arrivals(node_path: List[str]) -> int:
    seen = set()
    repeats = 0
    for node in node_path:
        if node in seen:
            repeats += 1
        else:
            seen.add(node)
    return repeats


def evaluate_dijkstra(
    adjacency: Dict[str, List[Tuple[str, int]]],
    edge_lengths: Dict[Edge, float],
    weights: Dict[Edge, float],
    source: str,
    destination: str,
) -> Tuple[Dict[str, Any], Any]:
    started = time.perf_counter()
    result = custom_dijkstra(adjacency, weights, source, destination)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    distance_m = sum(edge_lengths.get(edge, 0.0) for edge in result.edge_path)
    row = {
        "algorithm": "Dijkstra",
        "journey_success": bool(result.is_reached),
        "two_edge_only_success": None,
        "two_edge_with_local_backtracking_success": None,
        "total_travel_time_s": float(result.total_cost) if result.is_reached else None,
        "total_distance_m": float(distance_m) if result.is_reached else None,
        "intersection_decisions": 0,
        "selector_calls": 0,
        "two_edge_traversal_steps": 0,
        "total_route_steps": int(len(result.edge_path)),
        "repeated_node_visits": repeated_node_arrivals(result.node_path),
        "cycle_recoveries": 0,
        "dijkstra_fallback_steps": 0,
        "backtracking_steps": 0,
        "execution_time_ms": elapsed_ms,
        "mean_decision_latency_ms": None,
        "p95_decision_latency_ms": None,
        "two_edge_prefix_time_s": None,
        "two_edge_prefix_distance_m": None,
        "termination_reason": (
            "Dijkstra reached destination." if result.is_reached else "Dijkstra found no path."
        ),
    }
    return row, result


def evaluate_two_edge(
    weight_manager: GraphWeightManager,
    weights: Dict[Edge, float],
    speeds: Dict[Edge, float],
    source: str,
    destination: str,
    algorithm: str,
    heuristic_speed_kmh: float,
    seed: int,
    dijkstra_reference: Any,
    local_backtracking: bool,
    max_hops_multiplier: float,
    strict_loop_avoidance: bool,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    selector = make_selector(
        weight_manager,
        heuristic_speed_kmh,
        algorithm,
        seed,
        strict_loop_avoidance,
    )
    controller = RouteController(
        weight_manager.adjacency,
        weight_manager.edge_lengths,
        selector,
        max_hops_multiplier=max_hops_multiplier,
        local_backtracking=local_backtracking,
        strict_loop_avoidance=strict_loop_avoidance,
    )
    started = time.perf_counter()
    result = controller.execute_journey(
        source=source,
        destination=destination,
        initial_weights=weights,
        initial_speeds=speeds,
        reference_dijkstra=dijkstra_reference,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0

    cycle_recoveries = sum(
        any(
            tag in decision.strategy_name
            for tag in ("[RECOVERY_CYCLE_BREAKER]", "[RECOVERY_CYCLE_BACKTRACK]")
        )
        for decision in result.decision_steps
    )
    loop_trap_recoveries = sum(
        call["is_dead_end"] and "Loop trap" in str(call.get("decision_reason", ""))
        for call in selector.selector_calls
    )
    dijkstra_fallback_steps = sum(
        any(
            tag in decision.strategy_name
            for tag in (
                "[RECOVERY_CYCLE_BREAKER]",
                "[RECOVERY_SHORTEST_PATH]",
                "[RECOVERY_FORWARD]",
            )
        )
        for decision in result.decision_steps
    )
    backtracking_steps = sum(
        "BACKTRACK]" in decision.strategy_name
        for decision in result.decision_steps
    )
    recovery_step_count = dijkstra_fallback_steps + backtracking_steps
    primary_steps = [
        decision
        for decision in result.decision_steps
        if "[RECOVERY_" not in decision.strategy_name
    ]
    latencies = [call["latency_ms"] for call in selector.selector_calls]
    intersection_latencies = [
        call["latency_ms"]
        for call in selector.selector_calls
        if call["is_intersection"]
    ]
    repeated_visits = repeated_node_arrivals(result.node_path) + sum(
        "[RECOVERY_CYCLE_BREAKER]" in decision.strategy_name
        for decision in result.decision_steps
    )

    row = {
        "algorithm": algorithm,
        "journey_success": bool(result.is_success),
        "two_edge_only_success": bool(
            result.is_success and dijkstra_fallback_steps == 0 and backtracking_steps == 0
        ),
        "two_edge_with_local_backtracking_success": bool(
            result.is_success and dijkstra_fallback_steps == 0
        ),
        "total_travel_time_s": float(result.total_travel_time_s),
        "total_distance_m": float(result.total_distance_m),
        "intersection_decisions": int(
            sum(call["is_intersection"] for call in selector.selector_calls)
        ),
        "selector_calls": int(len(selector.selector_calls)),
        "two_edge_traversal_steps": int(len(primary_steps)),
        "total_route_steps": int(result.total_decisions),
        "repeated_node_visits": int(repeated_visits),
        "cycle_recoveries": int(cycle_recoveries),
        "loop_trap_recoveries": int(loop_trap_recoveries),
        "dijkstra_fallback_steps": int(dijkstra_fallback_steps),
        "backtracking_steps": int(backtracking_steps),
        "execution_time_ms": elapsed_ms,
        "mean_decision_latency_ms": (
            sum(intersection_latencies) / len(intersection_latencies)
            if intersection_latencies
            else (sum(latencies) / len(latencies) if latencies else 0.0)
        ),
        "p95_decision_latency_ms": (
            float(pd.Series(intersection_latencies or latencies).quantile(0.95))
            if intersection_latencies or latencies
            else 0.0
        ),
        "two_edge_prefix_time_s": float(sum(item.travel_time_s for item in primary_steps)),
        "two_edge_prefix_distance_m": float(sum(item.length_m for item in primary_steps)),
        "termination_reason": result.termination_reason,
        "recovery_steps_total": int(recovery_step_count),
        "dijkstra_reference_time_s": float(dijkstra_reference.total_cost),
        "dijkstra_reference_distance_m": float(
            sum(weight_manager.edge_lengths.get(edge, 0.0) for edge in dijkstra_reference.edge_path)
        ),
        "controller_recovery_events": int(result.recovery_events),
    }
    cycle_steps = {
        decision.step_index
        for decision in result.decision_steps
        if any(
            tag in decision.strategy_name
            for tag in ("[RECOVERY_CYCLE_BREAKER]", "[RECOVERY_CYCLE_BACKTRACK]")
        )
    }
    for call in selector.selector_calls:
        call["attempt_triggered_cycle_recovery"] = call["step_index"] in cycle_steps
    return row, selector.selector_calls


def summarize(results: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for algorithm, group in results.groupby("algorithm", sort=False):
        two_edge_success = group["two_edge_only_success"].dropna()
        rows.append(
            {
                "algorithm": algorithm,
                "journeys": int(len(group)),
                "journey_success_rate_pct": float(group["journey_success"].mean() * 100.0),
                "two_edge_only_success_rate_pct": (
                    float(two_edge_success.mean() * 100.0) if len(two_edge_success) else None
                ),
                "two_edge_with_local_backtracking_success_rate_pct": (
                    float(
                        group["two_edge_with_local_backtracking_success"]
                        .dropna()
                        .mean()
                        * 100.0
                    )
                    if group["two_edge_with_local_backtracking_success"].notna().any()
                    else None
                ),
                "mean_travel_time_s": float(group["total_travel_time_s"].mean()),
                "mean_distance_m": float(group["total_distance_m"].mean()),
                "mean_intersection_decisions": float(group["intersection_decisions"].mean()),
                "mean_two_edge_traversal_steps": float(group["two_edge_traversal_steps"].mean()),
                "mean_total_route_steps": float(group["total_route_steps"].mean()),
                "mean_repeated_node_visits": float(group["repeated_node_visits"].mean()),
                "cycle_recoveries": int(group["cycle_recoveries"].sum()),
                "loop_trap_recoveries": int(group["loop_trap_recoveries"].sum()),
                "dijkstra_fallback_steps": int(group["dijkstra_fallback_steps"].sum()),
                "dijkstra_fallback_step_share_pct": (
                    float(
                        group["dijkstra_fallback_steps"].sum()
                        / group["total_route_steps"].sum()
                        * 100.0
                    )
                    if group["total_route_steps"].sum() > 0
                    else 0.0
                ),
                "backtracking_steps": int(group["backtracking_steps"].sum()),
                "mean_execution_time_ms": float(group["execution_time_ms"].mean()),
                "mean_decision_latency_ms": float(group["mean_decision_latency_ms"].mean()),
                "mean_p95_decision_latency_ms": float(group["p95_decision_latency_ms"].mean()),
            }
        )
    return pd.DataFrame(rows)


def make_figures(summary: pd.DataFrame, output_dir: Path) -> None:
    figure_dir = output_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    labels = summary["algorithm"].tolist()
    x = range(len(labels))

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    axes[0].bar(x, summary["mean_travel_time_s"], color="#3b82f6")
    axes[0].set_title("Mean journey travel time")
    axes[0].set_ylabel("seconds")
    axes[1].bar(
        x,
        summary["two_edge_with_local_backtracking_success_rate_pct"].fillna(100),
        color="#10b981",
    )
    axes[1].set_title("Completion without Dijkstra")
    axes[1].set_ylabel("percent (Dijkstra baseline: n/a)")
    axes[1].set_ylim(0, 105)
    axes[2].bar(x, summary["dijkstra_fallback_steps"], color="#f97316")
    axes[2].set_title("Dijkstra safety-recovery steps")
    axes[2].set_ylabel("steps across O-D set")
    for axis in axes:
        axis.set_xticks(list(x))
        axis.set_xticklabels(labels, rotation=28, ha="right")
        axis.grid(axis="y", alpha=0.25)
    fig.suptitle("Bhubaneswar real-network routing validation")
    fig.tight_layout()
    fig.savefig(figure_dir / "routing_comparison.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def run(
    output_dir: Path,
    seed: int = 42,
    heuristic_speed_kmh: float = 25.0,
    local_backtracking: bool = False,
    max_hops_multiplier: float = 3.0,
    strict_loop_avoidance: bool = True,
) -> pd.DataFrame:
    graph, wm, weights, speeds, ods, input_metadata = load_inputs()
    algorithms = [
        ("Dijkstra", None),
        ("Greedy Two-Edge", heuristic_speed_kmh),
        ("Destination-Aware Two-Edge (25 km/h)", heuristic_speed_kmh),
        ("Lookahead Two-Edge (depth=2)", heuristic_speed_kmh),
        ("Adaptive Two-Edge", heuristic_speed_kmh),
        ("Destination-Aware Two-Edge (safe h=120 km/h)", 120.0),
    ]

    records: List[Dict[str, Any]] = []
    failure_records: List[Dict[str, Any]] = []
    trace_records: List[Dict[str, Any]] = []
    for od in ods.itertuples(index=False):
        source, destination = od.source_node, od.destination_node
        dijkstra_row, dijkstra_result = evaluate_dijkstra(
            wm.adjacency, wm.edge_lengths, weights, source, destination
        )
        if not dijkstra_result.is_reached:
            raise RuntimeError(f"Fixed O-D {source}->{destination} is unreachable under the shared costs.")

        rows = [dijkstra_row]
        for algorithm, heuristic_speed in algorithms[1:]:
            evaluated_row, trace = evaluate_two_edge(
                wm,
                weights,
                speeds,
                source,
                destination,
                algorithm,
                float(heuristic_speed),
                seed,
                dijkstra_result,
                local_backtracking,
                max_hops_multiplier,
                strict_loop_avoidance,
            )
            rows.append(evaluated_row)
            for trace_row in trace:
                trace_records.append(
                    {
                        "od_id": int(od.od_id),
                        "source_node": source,
                        "destination_node": destination,
                        "algorithm": algorithm,
                        **trace_row,
                    }
                )

        for row in rows:
            row.update(
                {
                    "od_id": int(od.od_id),
                    "source_node": source,
                    "destination_node": destination,
                    "haversine_distance_m": float(od.haversine_dist_m),
                    "prediction_timestamp_utc": input_metadata["prediction_timestamp_utc"],
                    "heuristic_speed_kmh": (
                        None if row["algorithm"] == "Dijkstra" else
                        (120.0 if "safe h=120" in row["algorithm"] else heuristic_speed_kmh)
                    ),
                    "random_seed": int(seed),
                    "recovery_steps_total": row.get("recovery_steps_total", 0),
                    "dijkstra_reference_time_s": row.get(
                        "dijkstra_reference_time_s", dijkstra_result.total_cost
                    ),
                    "dijkstra_reference_distance_m": row.get(
                        "dijkstra_reference_distance_m",
                        sum(wm.edge_lengths.get(edge, 0.0) for edge in dijkstra_result.edge_path),
                    ),
                    "controller_recovery_events": row.get("controller_recovery_events", 0),
                }
            )
            records.append(row)
            if (
                row["algorithm"] != "Dijkstra"
                and (
                    not row["two_edge_only_success"]
                    or row["repeated_node_visits"] > 0
                    or row["backtracking_steps"] > 0
                    or row["dijkstra_fallback_steps"] > 0
                    or row["loop_trap_recoveries"] > 0
                )
            ):
                symptoms = []
                if not row["journey_success"]:
                    symptoms.append("journey_failed")
                if not row["two_edge_only_success"]:
                    symptoms.append("needed_safety_recovery")
                if (
                    row["two_edge_with_local_backtracking_success"]
                    and row["backtracking_steps"] > 0
                ):
                    symptoms.append("local_backtracking_required")
                if row["repeated_node_visits"]:
                    symptoms.append("repeated_node_or_cycle")
                if row["backtracking_steps"]:
                    symptoms.append("backtracked")
                if row["loop_trap_recoveries"]:
                    symptoms.append("visited_only_loop_trap")
                failure_records.append(
                    {
                        "od_id": int(od.od_id),
                        "source_node": source,
                        "destination_node": destination,
                        "algorithm": row["algorithm"],
                        "symptoms": ";".join(symptoms),
                        "journey_success": row["journey_success"],
                        "two_edge_only_success": row["two_edge_only_success"],
                        "two_edge_with_local_backtracking_success": row[
                            "two_edge_with_local_backtracking_success"
                        ],
                        "repeated_node_visits": row["repeated_node_visits"],
                        "cycle_recoveries": row["cycle_recoveries"],
                        "loop_trap_recoveries": row["loop_trap_recoveries"],
                        "dijkstra_fallback_steps": row["dijkstra_fallback_steps"],
                        "backtracking_steps": row["backtracking_steps"],
                        "two_edge_prefix_time_s": row["two_edge_prefix_time_s"],
                        "total_travel_time_s": row["total_travel_time_s"],
                        "termination_reason": row["termination_reason"],
                    }
                )

    results = pd.DataFrame(records)
    summary = summarize(results)
    output_dir.mkdir(parents=True, exist_ok=True)
    results.to_csv(output_dir / "journey_results.csv", index=False)
    summary.to_csv(output_dir / "summary_metrics.csv", index=False)
    pd.DataFrame(trace_records).to_csv(output_dir / "decision_trace.csv", index=False)
    pd.DataFrame(
        failure_records,
        columns=[
            "od_id", "source_node", "destination_node", "algorithm", "symptoms",
            "journey_success", "two_edge_only_success",
            "two_edge_with_local_backtracking_success", "repeated_node_visits",
            "cycle_recoveries", "loop_trap_recoveries",
            "dijkstra_fallback_steps", "backtracking_steps",
            "two_edge_prefix_time_s", "total_travel_time_s", "termination_reason",
        ],
    ).to_csv(output_dir / "failure_analysis.csv", index=False)
    input_metadata.update(
        {
            "evaluation_seed": seed,
            "default_heuristic_speed_kmh": heuristic_speed_kmh,
            "safe_heuristic_speed_kmh": 120.0,
            "safe_heuristic_note": (
                "The current speed model caps dynamic mapped speeds at 120 km/h and static "
                "speeds are at most 50 km/h. Straight-line distance divided by 120 km/h is "
                "therefore a lower bound under these configured edge speeds."
            ),
            "algorithm_configurations": [name for name, _ in algorithms],
            "safety_recovery_enabled": True,
            "strict_active_path_loop_avoidance": strict_loop_avoidance,
            "local_backtracking_enabled": local_backtracking,
            "max_hops_multiplier": max_hops_multiplier,
            "success_definitions": {
                "journey_success": "Destination reached with any enabled safety recovery.",
                "two_edge_only_success": (
                    "Destination reached with no Dijkstra fallback and no backtracking."
                ),
                "two_edge_with_local_backtracking_success": (
                    "Destination reached without Dijkstra fallback; local backtracking may be used."
                ),
            },
            "fallback_counting": (
                "RECOVERY_FORWARD, RECOVERY_CYCLE_BREAKER, and RECOVERY_SHORTEST_PATH edges "
                "are Dijkstra fallback steps. All BACKTRACK-tagged edges are counted separately."
            ),
            "results_rows": int(len(results)),
        }
    )
    with (output_dir / "run_metadata.json").open("w", encoding="utf-8") as handle:
        json.dump(input_metadata, handle, indent=2)
    make_figures(summary, output_dir)
    print(summary.to_string(index=False))
    print(f"Saved {len(results)} journey/algorithm rows to {output_dir}")
    print(f"Fallback and repeat analysis: {output_dir / 'failure_analysis.csv'}")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default="results/phase2a_20261122_v1",
        help="Versioned result directory; existing files in this directory are overwritten.",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--heuristic-speed-kmh", type=float, default=25.0)
    parser.add_argument("--local-backtracking", action="store_true")
    parser.add_argument("--max-hops-multiplier", type=float, default=3.0)
    parser.add_argument(
        "--legacy-soft-loop-penalty",
        action="store_true",
        help="Reproduce the original finite loop-penalty behavior for a paired baseline.",
    )
    args = parser.parse_args()
    output = Path(args.output_dir)
    if not output.is_absolute():
        output = ROOT / output
    run(
        output,
        seed=args.seed,
        heuristic_speed_kmh=args.heuristic_speed_kmh,
        local_backtracking=args.local_backtracking,
        max_hops_multiplier=args.max_hops_multiplier,
        strict_loop_avoidance=not args.legacy_soft_loop_penalty,
    )


if __name__ == "__main__":
    main()
