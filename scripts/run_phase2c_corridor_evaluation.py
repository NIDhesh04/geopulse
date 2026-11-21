"""Reproduce the Phase 2B depth-5 baseline and evaluate bounded corridors.

Run in two steps so the Phase 2B profile is measured before corridor variants:

    python scripts/run_phase2c_corridor_evaluation.py --stage baseline \
        --output-dir results/phase2c_20261122_baseline
    python scripts/run_phase2c_corridor_evaluation.py --stage compare \
        --baseline-dir results/phase2c_20261122_baseline \
        --output-dir results/phase2c_20261122_comparison

All routing variants use O-D IDs 0-29 and the three stored Phase 2B prediction
timestamps. The corridor check follows only forced one-exit continuations and
does not run a global path search.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import run_phase2a_real_network_evaluation as phase2a
from scripts import run_phase2b_routing_experiments as phase2b
from src.routing.candidate_generator import CandidateGenerator
from src.routing.decision_strategies import (
    CorridorRankingDecisionStrategy,
    DestinationAwareDecisionStrategy,
    LimitedLookaheadDecisionStrategy,
)
from src.routing.lookahead import LimitedLookaheadEvaluator
from src.routing.route_controller import RouteController
from src.routing.two_edge_selector import TwoEdgeSelector

Edge = Tuple[str, str, int]
TIMESTAMPS = phase2b.TIMESTAMPS
BASELINE_NAME = "Lookahead Two-Edge (depth=5, branches=4)"


@dataclass(frozen=True)
class Variant:
    name: str
    base: str
    cap: Optional[int] = None
    policy: Optional[str] = None


CORRIDOR_VARIANTS = [
    Variant(f"Destination-Aware + Corridor cap {cap} (ranking)", "destination", cap, "ranking")
    for cap in (5, 10, 20)
] + [
    Variant(f"Destination-Aware + Corridor cap {cap} (conservative rejection)", "destination", cap, "conservative_rejection")
    for cap in (5, 10, 20)
] + [
    Variant("Depth-5 Lookahead + Corridor cap 10 (ranking)", "depth5", 10, "ranking"),
    Variant("Depth-5 Lookahead + Corridor cap 10 (conservative rejection)", "depth5", 10, "conservative_rejection"),
]
COMPARISON_VARIANTS = [
    Variant("Destination-Aware Two-Edge (no corridor)", "destination"),
    *CORRIDOR_VARIANTS,
]


class TimedCorridorSelector(phase2a.TimedTwoEdgeSelector):
    """Phase 2A selector trace enriched with per-call corridor measurements."""

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.corridor_events: List[Dict[str, Any]] = []

    def decide_next_edge(self, *args: Any, **kwargs: Any):
        decision = super().decide_next_edge(*args, **kwargs)
        call = self.selector_calls[-1]
        assessments = list(self.last_corridor_checks)
        call["corridor_checks_this_call"] = len(assessments)
        call["corridor_check_latency_ms"] = sum(
            float(item.get("check_latency_ms", 0.0)) for item in assessments
        )
        call["corridor_checks_json"] = json.dumps(assessments, sort_keys=True)
        for item in assessments:
            self.corridor_events.append({
                "step_index": call["step_index"],
                "current_node": call["current_node"],
                "destination_node": call["destination_node"],
                **item,
            })
        return decision


def make_variant_selector(wm, variant: Variant, seed: int) -> TimedCorridorSelector:
    node_coords = {
        str(node): (float(data["y"]), float(data["x"]))
        for node, data in wm.G.nodes(data=True)
        if "y" in data and "x" in data
    }
    generator = CandidateGenerator(
        wm.adjacency,
        wm.edge_lengths,
        node_coords,
        default_free_flow_speed_kmh=25.0,
        random_seed=seed,
    )
    if variant.base == "destination":
        strategy = DestinationAwareDecisionStrategy()
    elif variant.base == "depth5":
        evaluator = LimitedLookaheadEvaluator(
            wm.adjacency,
            {},
            generator.estimate_remaining_time,
            depth=5,
            max_expansions_per_node=4,
        )
        strategy = LimitedLookaheadDecisionStrategy(evaluator)
    else:
        raise ValueError(f"Unknown variant base: {variant.base}")

    if variant.policy == "ranking":
        strategy = CorridorRankingDecisionStrategy(strategy)
    return TimedCorridorSelector(
        generator,
        strategy,
        avoid_visited_successors=True,
        corridor_policy=variant.policy,
        corridor_edge_cap=variant.cap or 10,
    )


def evaluate_two_edge(wm, weights, speeds, od, timestamp, dijkstra, variant: Variant, seed: int):
    selector = make_variant_selector(wm, variant, seed)
    controller = RouteController(
        wm.adjacency,
        wm.edge_lengths,
        selector,
        max_hops_multiplier=3.0,
        local_backtracking=False,
        strict_loop_avoidance=True,
    )
    started = time.perf_counter()
    result = controller.execute_journey(
        source=od.source_node,
        destination=od.destination_node,
        initial_weights=weights,
        initial_speeds=speeds,
        reference_dijkstra=dijkstra,
    )
    execution_ms = (time.perf_counter() - started) * 1000.0
    decisions = result.decision_steps
    cycle_recoveries = sum(
        any(tag in step.strategy_name for tag in ("[RECOVERY_CYCLE_BREAKER]", "[RECOVERY_CYCLE_BACKTRACK]"))
        for step in decisions
    )
    fallback_steps = sum(
        any(tag in step.strategy_name for tag in ("[RECOVERY_CYCLE_BREAKER]", "[RECOVERY_SHORTEST_PATH]", "[RECOVERY_FORWARD]"))
        for step in decisions
    )
    backtracking_steps = sum("BACKTRACK]" in step.strategy_name for step in decisions)
    primary_steps = [
        step for step in decisions
        if "[RECOVERY_" not in step.strategy_name and "BACKTRACK]" not in step.strategy_name
    ]
    calls = selector.selector_calls
    decision_latencies = [float(call["latency_ms"]) for call in calls if call["is_intersection"]]
    if not decision_latencies:
        decision_latencies = [float(call["latency_ms"]) for call in calls]
    all_call_latencies = [float(call["latency_ms"]) for call in calls]
    loop_traps = sum(
        bool(call["is_dead_end"]) and "Loop trap" in str(call.get("decision_reason", ""))
        for call in calls
    )
    repeated = phase2a.repeated_node_arrivals(result.node_path) + cycle_recoveries
    corridor_latencies = [float(item.get("check_latency_ms", 0.0)) for item in selector.corridor_events]
    row = {
        "stage": "comparison",
        "algorithm": variant.name,
        "kind": variant.base,
        "od_id": int(od.od_id),
        "source_node": str(od.source_node),
        "destination_node": str(od.destination_node),
        "prediction_timestamp_utc": timestamp.isoformat(),
        "journey_success": bool(result.is_success),
        "two_edge_only_success": bool(result.is_success and fallback_steps == 0 and backtracking_steps == 0),
        "total_travel_time_s": float(result.total_travel_time_s),
        "total_distance_m": float(result.total_distance_m),
        "intersection_decisions": int(sum(call["is_intersection"] for call in calls)),
        "selector_calls": len(calls),
        "two_edge_traversal_steps": len(primary_steps),
        "total_route_steps": int(result.total_decisions),
        "repeated_node_visits": int(repeated),
        "cycle_recoveries": int(cycle_recoveries),
        "loop_traps": int(loop_traps),
        "dijkstra_fallback_steps": int(fallback_steps),
        "dijkstra_fallback_share_pct": float(fallback_steps / result.total_decisions * 100.0) if result.total_decisions else 0.0,
        "backtracking_steps": int(backtracking_steps),
        "corridor_checks": len(selector.corridor_events),
        "mean_corridor_check_latency_ms": float(pd.Series(corridor_latencies).mean()) if corridor_latencies else 0.0,
        "p95_corridor_check_latency_ms": float(pd.Series(corridor_latencies).quantile(0.95)) if corridor_latencies else 0.0,
        "mean_decision_latency_ms": float(pd.Series(decision_latencies).mean()) if decision_latencies else 0.0,
        "p95_decision_latency_ms": float(pd.Series(decision_latencies).quantile(0.95)) if decision_latencies else 0.0,
        "total_decision_latency_ms": float(sum(all_call_latencies)),
        "execution_time_ms": execution_ms,
        "two_edge_prefix_time_s": float(sum(step.travel_time_s for step in primary_steps)),
        "two_edge_prefix_distance_m": float(sum(step.length_m for step in primary_steps)),
        "termination_reason": result.termination_reason,
        "dijkstra_reference_time_s": float(dijkstra.total_cost),
        "dijkstra_reference_distance_m": float(sum(wm.edge_lengths.get(edge, 0.0) for edge in dijkstra.edge_path)),
        "algorithm_config_json": json.dumps(asdict(variant), sort_keys=True),
    }
    traces = []
    cycle_steps = {
        step.step_index for step in decisions
        if any(tag in step.strategy_name for tag in ("[RECOVERY_CYCLE_BREAKER]", "[RECOVERY_CYCLE_BACKTRACK]"))
    }
    for call in calls:
        traces.append({
            "stage": "comparison",
            "od_id": int(od.od_id),
            "algorithm": variant.name,
            "prediction_timestamp_utc": timestamp.isoformat(),
            "attempt_triggered_cycle_recovery": call["step_index"] in cycle_steps,
            **call,
        })
    corridor_rows = [
        {
            "od_id": int(od.od_id),
            "algorithm": variant.name,
            "prediction_timestamp_utc": timestamp.isoformat(),
            **event,
        }
        for event in selector.corridor_events
    ]
    return row, traces, corridor_rows


def _write_summary(rows: pd.DataFrame, output_dir: Path, filename: str = "summary_metrics.csv") -> pd.DataFrame:
    summaries = []
    for (algorithm, timestamp), group in rows.groupby(["algorithm", "prediction_timestamp_utc"], sort=False):
        fallback_total = int(group["dijkstra_fallback_steps"].sum())
        route_total = int(group["total_route_steps"].sum())
        checks = int(group["corridor_checks"].sum()) if "corridor_checks" in group else 0
        summaries.append({
            "algorithm": algorithm,
            "prediction_timestamp_utc": timestamp,
            "journeys": len(group),
            "journey_successes": int(group["journey_success"].sum()),
            "journey_success_rate_pct": float(group["journey_success"].mean() * 100.0),
            "two_edge_only_successes": int(group["two_edge_only_success"].fillna(False).sum()),
            "two_edge_only_success_rate_pct": float(group["two_edge_only_success"].dropna().mean() * 100.0) if group["two_edge_only_success"].notna().any() else None,
            "dijkstra_fallback_steps": fallback_total,
            "dijkstra_fallback_step_share_pct": float(fallback_total / route_total * 100.0) if route_total else 0.0,
            "backtracking_steps": int(group["backtracking_steps"].sum()),
            "mean_travel_time_s": float(group["total_travel_time_s"].mean()),
            "mean_distance_m": float(group["total_distance_m"].mean()),
            "mean_repeated_node_visits": float(group["repeated_node_visits"].mean()),
            "loop_traps": int(group["loop_traps"].sum()),
            "cycle_recoveries": int(group["cycle_recoveries"].sum()),
            "mean_intersection_decisions": float(group["intersection_decisions"].mean()),
            "corridor_checks": checks,
            "mean_corridor_checks_per_journey": float(group["corridor_checks"].mean()) if "corridor_checks" in group else 0.0,
            "mean_corridor_check_latency_ms": float(group["mean_corridor_check_latency_ms"].mean()) if "mean_corridor_check_latency_ms" in group else 0.0,
            "p95_corridor_check_latency_ms": float(group["p95_corridor_check_latency_ms"].quantile(0.95)) if "p95_corridor_check_latency_ms" in group else 0.0,
            "mean_decision_latency_ms": float(group["mean_decision_latency_ms"].mean()),
            "p95_decision_latency_ms": float(group["p95_decision_latency_ms"].quantile(0.95)),
            "total_decision_latency_ms": float(group["total_decision_latency_ms"].sum()) if "total_decision_latency_ms" in group else 0.0,
            "mean_execution_time_ms": float(group["execution_time_ms"].mean()),
            "total_execution_time_ms": float(group["execution_time_ms"].sum()),
        })
    summary = pd.DataFrame(summaries)
    summary.to_csv(output_dir / filename, index=False)
    return summary


def _load_world():
    graph, wm, predictions, rounded, od_table, metadata = phase2b.load_inputs()
    selected = od_table[od_table.od_id.isin(range(30))].copy()
    if selected.od_id.astype(int).tolist() != list(range(30)):
        raise RuntimeError("Phase 2B's ordered O-D IDs 0 through 29 were not available.")
    return wm, predictions, rounded, selected, metadata


def _scenario(wm, predictions, rounded, timestamp):
    return phase2b.weights_for_timestamp(wm, predictions, rounded, timestamp)


def run_baseline(output_dir: Path, seed: int = 42) -> pd.DataFrame:
    wm, predictions, rounded, ods, metadata = _load_world()
    rows: List[Dict[str, Any]] = []
    traces: List[Dict[str, Any]] = []
    scenarios = []
    for timestamp in TIMESTAMPS:
        weights, speeds, prediction_rows, dynamic_edges = _scenario(wm, predictions, rounded, timestamp)
        scenarios.append({"prediction_timestamp_utc": timestamp.isoformat(), "prediction_rows": prediction_rows, "dynamic_weighted_edges": dynamic_edges})
        for od in ods.itertuples(index=False):
            dijkstra_row, dijkstra = phase2a.evaluate_dijkstra(wm.adjacency, wm.edge_lengths, weights, od.source_node, od.destination_node)
            for row, config_name in ((dijkstra_row, "Dijkstra"),):
                item = dict(row)
                item.update({"stage": "baseline", "od_id": int(od.od_id), "source_node": od.source_node, "destination_node": od.destination_node,
                             "prediction_timestamp_utc": timestamp.isoformat(), "loop_traps": 0,
                             "corridor_checks": 0, "mean_corridor_check_latency_ms": 0.0,
                             "p95_corridor_check_latency_ms": 0.0,
                             "dijkstra_fallback_share_pct": 0.0,
                             "algorithm_config_json": json.dumps({"kind": "dijkstra"}, sort_keys=True)})
                rows.append(item)
            base_config = phase2b.AlgorithmConfig(BASELINE_NAME, "lookahead", depth=5, branch_limit=4)
            base_row, trace = phase2b.evaluate_two_edge(wm, base_config, weights, speeds, od.source_node, od.destination_node, dijkstra, seed)
            base_row.update({"stage": "baseline", "od_id": int(od.od_id), "source_node": od.source_node, "destination_node": od.destination_node,
                             "prediction_timestamp_utc": timestamp.isoformat(),
                             "loop_traps": int(base_row.get("loop_trap_recoveries", 0)),
                             "corridor_checks": 0, "mean_corridor_check_latency_ms": 0.0,
                             "p95_corridor_check_latency_ms": 0.0,
                             "dijkstra_fallback_share_pct": float(base_row["dijkstra_fallback_steps"] / base_row["total_route_steps"] * 100.0) if base_row["total_route_steps"] else 0.0})
            rows.append(base_row)
            for call in trace:
                traces.append({"stage": "baseline", "od_id": int(od.od_id), "source_node": od.source_node, "destination_node": od.destination_node,
                               "algorithm": BASELINE_NAME, "prediction_timestamp_utc": timestamp.isoformat(), **call})
        print(f"baseline complete: {timestamp.isoformat()} ({len(ods)} O-D pairs)", flush=True)

    output_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    frame.to_csv(output_dir / "journey_results.csv", index=False)
    pd.DataFrame(traces).to_csv(output_dir / "decision_trace.csv", index=False)
    summary = _write_summary(frame, output_dir)
    metadata.update({
        "stage": "baseline",
        "od_ids": list(range(30)),
        "timestamps": [time.isoformat() for time in TIMESTAMPS],
        "scenario_weights": scenarios,
        "seed": seed,
        "algorithm_configurations": [{"algorithm": "Dijkstra"}, asdict(phase2b.AlgorithmConfig(BASELINE_NAME, "lookahead", depth=5, branch_limit=4))],
        "strict_active_path_loop_avoidance": True,
        "local_backtracking_enabled": False,
        "two_edge_only_definition": "Destination reached with zero Dijkstra fallback steps and zero local backtracking steps.",
    })
    (output_dir / "run_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    _make_figures(summary, output_dir)
    print(summary.to_string(index=False), flush=True)
    return frame


def verify_baseline_reproduction(baseline_dir: Path) -> pd.DataFrame:
    baseline_metadata = json.loads((baseline_dir / "run_metadata.json").read_text(encoding="utf-8"))
    old_path = ROOT / "results/phase2b_20261122_validation/journey_results.csv"
    if not old_path.exists():
        raise FileNotFoundError(f"Required Phase 2B validation results missing: {old_path}")
    historical = pd.read_csv(old_path)
    reproduced = pd.read_csv(baseline_dir / "journey_results.csv")
    old = historical[historical.algorithm == BASELINE_NAME].copy()
    new = reproduced[(reproduced.algorithm == BASELINE_NAME) & reproduced.od_id.between(10, 29)].copy()
    keys = ["od_id", "prediction_timestamp_utc"]
    compare_fields = ["journey_success", "two_edge_only_success", "total_travel_time_s", "total_distance_m", "dijkstra_fallback_steps", "backtracking_steps", "repeated_node_visits", "loop_trap_recoveries", "intersection_decisions", "total_route_steps"]
    merged = old[keys + compare_fields].merge(new[keys + compare_fields], on=keys, suffixes=("_phase2b", "_phase2c"), how="outer", indicator=True)
    if len(merged) != 60 or not (merged["_merge"] == "both").all():
        raise RuntimeError("Phase 2C baseline does not cover all 60 Phase 2B validation cases.")
    for field in compare_fields:
        left, right = merged[f"{field}_phase2b"], merged[f"{field}_phase2c"]
        if field in ("total_travel_time_s", "total_distance_m"):
            matches = (left.fillna(-1).sub(right.fillna(-1)).abs() <= 1e-8).all()
        else:
            matches = (left.fillna("<NA>").astype(str) == right.fillna("<NA>").astype(str)).all()
        if not matches:
            bad = merged.loc[~(left.fillna(-1).sub(right.fillna(-1)).abs() <= 1e-8) if field in ("total_travel_time_s", "total_distance_m") else left.fillna("<NA>").astype(str).ne(right.fillna("<NA>").astype(str)), keys].head().to_dict("records")
            raise RuntimeError(f"Phase 2C depth-5 baseline differs from Phase 2B in {field}; sample {bad}")
    if baseline_metadata.get("od_ids") != list(range(30)):
        raise RuntimeError("Baseline metadata does not describe O-D IDs 0 through 29.")
    merged.to_csv(baseline_dir / "phase2b_reproduction_check.csv", index=False)
    return merged


def run_comparison(baseline_dir: Path, output_dir: Path, seed: int = 42):
    check = verify_baseline_reproduction(baseline_dir)
    print(f"Baseline reproduction verified against Phase 2B validation: {len(check)}/60 journeys match.", flush=True)
    wm, predictions, rounded, ods, metadata = _load_world()
    rows: List[Dict[str, Any]] = []
    traces: List[Dict[str, Any]] = []
    corridor_rows: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    scenarios = []
    for timestamp in TIMESTAMPS:
        weights, speeds, prediction_rows, dynamic_edges = _scenario(wm, predictions, rounded, timestamp)
        scenarios.append({"prediction_timestamp_utc": timestamp.isoformat(), "prediction_rows": prediction_rows, "dynamic_weighted_edges": dynamic_edges})
        for od in ods.itertuples(index=False):
            _, dijkstra = phase2a.evaluate_dijkstra(wm.adjacency, wm.edge_lengths, weights, od.source_node, od.destination_node)
            for variant in COMPARISON_VARIANTS:
                row, trace, checks = evaluate_two_edge(wm, weights, speeds, od, timestamp, dijkstra, variant, seed)
                rows.append(row)
                traces.extend({"source_node": od.source_node, "destination_node": od.destination_node, **item} for item in trace)
                corridor_rows.extend({"source_node": od.source_node, "destination_node": od.destination_node, **item} for item in checks)
                if not row["two_edge_only_success"] or row["loop_traps"] or row["dijkstra_fallback_steps"]:
                    failures.append({key: row[key] for key in (
                        "od_id", "source_node", "destination_node", "algorithm", "prediction_timestamp_utc", "journey_success", "two_edge_only_success",
                        "dijkstra_fallback_steps", "dijkstra_fallback_share_pct", "loop_traps", "repeated_node_visits", "total_travel_time_s", "total_distance_m", "termination_reason")})
        print(f"comparison complete: {timestamp.isoformat()} ({len(ods)} O-D pairs, {len(COMPARISON_VARIANTS)} variants)", flush=True)

    output_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    frame.to_csv(output_dir / "journey_results.csv", index=False)
    pd.DataFrame(traces).to_csv(output_dir / "decision_trace.csv", index=False)
    pd.DataFrame(corridor_rows).to_csv(output_dir / "corridor_checks.csv", index=False)
    pd.DataFrame(failures).to_csv(output_dir / "failure_analysis.csv", index=False)
    summary = _write_summary(frame, output_dir)
    trace_frame = pd.DataFrame(traces)
    latency_rows = []
    for (algorithm, timestamp), group in trace_frame.groupby(["algorithm", "prediction_timestamp_utc"], sort=False):
        all_calls = group["latency_ms"].astype(float)
        intersection_calls = group.loc[group["is_intersection"].fillna(False), "latency_ms"].astype(float)
        latency_rows.append({
            "algorithm": algorithm,
            "prediction_timestamp_utc": timestamp,
            "selector_calls": len(all_calls),
            "intersection_calls": len(intersection_calls),
            "mean_all_call_latency_ms": float(all_calls.mean()),
            "p95_all_call_latency_ms": float(all_calls.quantile(0.95)),
            "mean_intersection_latency_ms": float(intersection_calls.mean()) if len(intersection_calls) else 0.0,
            "p95_intersection_latency_ms": float(intersection_calls.quantile(0.95)) if len(intersection_calls) else 0.0,
            "total_decision_latency_ms": float(all_calls.sum()),
        })
    pd.DataFrame(latency_rows).to_csv(output_dir / "decision_latency_summary.csv", index=False)
    check_frame = pd.DataFrame(corridor_rows)
    if not check_frame.empty:
        corridor_latency = check_frame.groupby(["algorithm", "prediction_timestamp_utc"], sort=False).agg(
            corridor_checks=("check_latency_ms", "size"),
            mean_corridor_check_latency_ms=("check_latency_ms", "mean"),
            p95_corridor_check_latency_ms=("check_latency_ms", lambda series: series.quantile(0.95)),
        ).reset_index()
        status_counts = check_frame.groupby(["algorithm", "prediction_timestamp_utc", "status"], sort=False).size().unstack(fill_value=0).reset_index()
        corridor_latency = corridor_latency.merge(status_counts, on=["algorithm", "prediction_timestamp_utc"], how="left")
    else:
        corridor_latency = pd.DataFrame()
    corridor_latency.to_csv(output_dir / "corridor_latency_and_status_summary.csv", index=False)
    metadata.update({
        "stage": "comparison",
        "baseline_dir": str(baseline_dir.relative_to(ROOT)) if baseline_dir.is_relative_to(ROOT) else str(baseline_dir),
        "baseline_reproduction_cases_verified": len(check),
        "od_ids": list(range(30)),
        "timestamps": [time.isoformat() for time in TIMESTAMPS],
        "scenario_weights": scenarios,
        "seed": seed,
        "variants": [asdict(variant) for variant in COMPARISON_VARIANTS],
        "strict_active_path_loop_avoidance": True,
        "local_backtracking_enabled": False,
        "corridor_cap_semantics": "Cap counts the initial candidate edge. Reaching the cap is incomplete, not a proven dead end and is never rejected solely for incompleteness.",
        "two_edge_only_definition": "Destination reached with zero Dijkstra fallback steps and zero local backtracking steps.",
    })
    (output_dir / "run_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    _make_figures(summary, output_dir)

    baseline = pd.read_csv(baseline_dir / "journey_results.csv")
    baseline = baseline[baseline.algorithm == BASELINE_NAME].copy()
    baseline["dijkstra_fallback_share_pct"] = baseline.apply(
        lambda row: 100.0 * row.dijkstra_fallback_steps / row.total_route_steps if row.total_route_steps else 0.0,
        axis=1,
    )
    baseline["corridor_checks"] = 0
    baseline["mean_corridor_check_latency_ms"] = 0.0
    baseline["p95_corridor_check_latency_ms"] = 0.0
    baseline["stage"] = "baseline"
    baseline["algorithm_config_json"] = json.dumps({"kind": "lookahead", "depth": 5, "branch_limit": 4}, sort_keys=True)
    baseline["loop_traps"] = baseline["loop_trap_recoveries"]
    baseline_trace = pd.read_csv(baseline_dir / "decision_trace.csv")
    baseline_latency = baseline_trace.groupby(["od_id", "prediction_timestamp_utc"], sort=False).latency_ms.sum().rename("total_decision_latency_ms").reset_index()
    baseline = baseline.merge(baseline_latency, on=["od_id", "prediction_timestamp_utc"], how="left")
    baseline["total_decision_latency_ms"] = baseline.total_decision_latency_ms.fillna(0.0)
    combined = pd.concat([baseline, frame], ignore_index=True, sort=False)
    # Carry the same independent Dijkstra reference rows used during baseline.
    dijkstra_rows = pd.read_csv(baseline_dir / "journey_results.csv")
    dijkstra_rows = dijkstra_rows[dijkstra_rows.algorithm == "Dijkstra"].copy()
    dijkstra_rows["dijkstra_fallback_share_pct"] = 0.0
    dijkstra_rows["loop_traps"] = 0
    dijkstra_rows["corridor_checks"] = 0
    dijkstra_rows["mean_corridor_check_latency_ms"] = 0.0
    dijkstra_rows["p95_corridor_check_latency_ms"] = 0.0
    dijkstra_rows["total_decision_latency_ms"] = 0.0
    combined = pd.concat([dijkstra_rows, combined], ignore_index=True, sort=False)
    combined["od_id"] = combined.od_id.astype(int)
    combined.sort_values(["prediction_timestamp_utc", "od_id", "algorithm"], inplace=True)
    combined.to_csv(ROOT / "GEOPULSE_PHASE2C_BENCHMARK_RESULTS.csv", index=False)
    combined.to_csv(output_dir / "GEOPULSE_PHASE2C_BENCHMARK_RESULTS.csv", index=False)
    summary.to_csv(output_dir / "corridor_variants_summary_metrics.csv", index=False)
    all_summary = _write_summary(combined, output_dir)
    latency_all = pd.concat([baseline_trace.assign(stage="baseline"), trace_frame], ignore_index=True, sort=False)
    pooled_rows = []
    for (algorithm, timestamp), group in latency_all.groupby(["algorithm", "prediction_timestamp_utc"], sort=False):
        all_calls = group.latency_ms.astype(float)
        intersection_calls = group.loc[group.is_intersection.fillna(False), "latency_ms"].astype(float)
        pooled_rows.append({
            "algorithm": algorithm,
            "prediction_timestamp_utc": timestamp,
            "selector_calls": len(all_calls),
            "intersection_calls": len(intersection_calls),
            "mean_all_call_latency_ms": float(all_calls.mean()),
            "p95_all_call_latency_ms": float(all_calls.quantile(0.95)),
            "mean_intersection_latency_ms": float(intersection_calls.mean()) if len(intersection_calls) else None,
            "p95_intersection_latency_ms": float(intersection_calls.quantile(0.95)) if len(intersection_calls) else None,
            "total_decision_latency_ms": float(all_calls.sum()),
        })
    pooled_frame = pd.DataFrame(pooled_rows)
    pooled_frame.to_csv(output_dir / "decision_latency_summary.csv", index=False)
    trap_trace = latency_all.loc[
        latency_all.get("is_dead_end", pd.Series(False, index=latency_all.index)).fillna(False)
        & latency_all.get("decision_reason", pd.Series("", index=latency_all.index)).astype(str).str.contains("Loop trap", regex=False)
    ].copy()
    if trap_trace.empty:
        trap_summary = pd.DataFrame(columns=["algorithm", "out_degree", "loop_traps"])
    else:
        trap_summary = trap_trace.groupby(["algorithm", "out_degree"], dropna=False, sort=False).size().rename("loop_traps").reset_index()
    trap_summary.to_csv(output_dir / "loop_trap_analysis.csv", index=False)
    overall_rows = []
    for algorithm, group in combined.groupby("algorithm", sort=False):
        fallback = int(group.dijkstra_fallback_steps.fillna(0).sum())
        route_steps = int(group.total_route_steps.fillna(0).sum())
        overall_rows.append({
            "algorithm": algorithm,
            "journeys": len(group),
            "journey_successes": int(group.journey_success.fillna(False).sum()),
            "journey_success_rate_pct": float(group.journey_success.fillna(False).mean() * 100.0),
            "two_edge_only_successes": int(group.two_edge_only_success.fillna(False).sum()),
            "two_edge_only_success_rate_pct": float(group.two_edge_only_success.dropna().mean() * 100.0) if group.two_edge_only_success.notna().any() else None,
            "dijkstra_fallback_steps": fallback,
            "dijkstra_fallback_step_share_pct": 100.0 * fallback / route_steps if route_steps else 0.0,
            "backtracking_steps": int(group.backtracking_steps.fillna(0).sum()),
            "mean_travel_time_s": float(group.total_travel_time_s.mean()),
            "mean_distance_m": float(group.total_distance_m.mean()),
            "mean_repeated_node_visits": float(group.repeated_node_visits.mean()),
            "loop_traps": int(group.loop_traps.fillna(0).sum()),
            "corridor_checks": int(group.corridor_checks.fillna(0).sum()),
            "mean_corridor_checks_per_journey": float(group.corridor_checks.fillna(0).mean()),
            "mean_execution_time_ms": float(group.execution_time_ms.mean()),
            "total_execution_time_ms": float(group.execution_time_ms.sum()),
        })
    overall = pd.DataFrame(overall_rows)
    overall.to_csv(output_dir / "overall_summary_metrics.csv", index=False)
    failure_rows = combined.loc[
        (~combined.journey_success.fillna(False))
        | combined.dijkstra_fallback_steps.fillna(0).gt(0)
        | combined.loop_traps.fillna(0).gt(0)
    ].copy()
    failure_columns = [
        "algorithm", "od_id", "source_node", "destination_node", "prediction_timestamp_utc",
        "journey_success", "two_edge_only_success", "dijkstra_fallback_steps",
        "dijkstra_fallback_share_pct", "backtracking_steps", "loop_traps",
        "repeated_node_visits", "total_travel_time_s", "total_distance_m", "termination_reason",
    ]
    for column in failure_columns:
        if column not in failure_rows:
            failure_rows[column] = None
    failure_rows[failure_columns].to_csv(output_dir / "failure_analysis.csv", index=False)
    _make_figures(all_summary, output_dir)
    print(overall.to_string(index=False), flush=True)
    print(f"Saved {len(combined)} matched journey rows and {len(traces)} decision traces.", flush=True)
    return frame, summary


def _make_figures(summary: pd.DataFrame, output_dir: Path):
    overall = summary.groupby("algorithm", sort=False).agg({
        "two_edge_only_success_rate_pct": "mean",
        "dijkstra_fallback_steps": "sum",
        "mean_travel_time_s": "mean",
        "mean_decision_latency_ms": "mean",
        "p95_decision_latency_ms": "mean",
    }).reset_index()
    figure_dir = output_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    x = range(len(overall))
    axes[0, 0].bar(x, overall.two_edge_only_success_rate_pct, color="#15803d")
    axes[0, 0].set_title("Two-Edge-only success rate")
    axes[0, 1].bar(x, overall.dijkstra_fallback_steps, color="#ea580c")
    axes[0, 1].set_title("Dijkstra fallback steps")
    axes[1, 0].bar(x, overall.mean_travel_time_s, color="#2563eb")
    axes[1, 0].set_title("Mean trip time (seconds)")
    axes[1, 1].bar(x, overall.p95_decision_latency_ms, color="#7c3aed")
    axes[1, 1].set_title("Mean of per-journey p95 decision latency (ms)")
    for ax in axes.flat:
        ax.set_xticks(list(x), overall.algorithm, rotation=75, ha="right", fontsize=7)
        ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    fig.savefig(figure_dir / "corridor_comparison.png", dpi=170)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("baseline", "compare"), required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--baseline-dir")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    if args.stage == "baseline":
        run_baseline(output_dir, args.seed)
    else:
        if not args.baseline_dir:
            parser.error("--baseline-dir is required for --stage compare")
        baseline_dir = Path(args.baseline_dir)
        if not baseline_dir.is_absolute():
            baseline_dir = ROOT / baseline_dir
        run_comparison(baseline_dir, output_dir, args.seed)


if __name__ == "__main__":
    main()
