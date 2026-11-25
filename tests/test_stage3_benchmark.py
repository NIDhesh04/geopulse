"""Comprehensive tests for GeoPulse Stage 3 OD selection, temporal routing, and benchmark evaluation."""

from __future__ import annotations

import json
import math
from pathlib import Path

import networkx as nx
import pandas as pd
import pytest

from src.benchmark.evaluation import (
    TIE_ABS_THRESHOLD_S,
    compute_coverage_and_length_report,
    compute_head_to_head,
    compute_strategy_summary,
    paired_comparison,
)
from src.benchmark.od_selection import (
    SpatialNodeIndex,
    haversine_distance_m,
    parse_od_input,
    select_od_pairs,
    validate_lat_lon,
)
from src.benchmark.run_benchmark import run_stage3_benchmark, select_departure_schedules
from src.experiments.temporal_journey import STRATEGIES, TemporalJourneyEngine
from src.routing.traffic_weights import GraphWeightManager
from src.traffic.replay import HistoricalTrafficReplay


def _build_synthetic_network(tmp_path: Path):
    """Create a synthetic multi-route directed network + replay artifact for end-to-end tests."""
    graph = nx.MultiDiGraph()
    coords = {
        "N0": (20.290, 85.820),
        "N1": (20.295, 85.825),
        "N2": (20.300, 85.830),
        "N3": (20.295, 85.835),
        "N4": (20.305, 85.835),
        "N5": (20.310, 85.840),
        "ISOLATED": (20.350, 85.900),
    }
    for nid, (lat, lon) in coords.items():
        graph.add_node(nid, y=lat, x=lon)

    edges = [
        ("N0", "N1", 0, 1200.0, "primary"),
        ("N1", "N2", 0, 1400.0, "primary"),
        ("N2", "N4", 0, 1400.0, "primary"),
        ("N4", "N5", 0, 1200.0, "primary"),
        ("N1", "N3", 0, 1500.0, "secondary"),
        ("N3", "N4", 0, 1500.0, "secondary"),
        ("N5", "N0", 0, 4000.0, "tertiary"),  # Close main SCC N0..N5
        ("ISOLATED", "N5", 0, 2000.0, "residential"),  # Cannot reach ISOLATED from N0
    ]
    for u, v, k, length, hw in edges:
        graph.add_edge(u, v, key=k, length=length, highway=hw)

    mapping_df = pd.DataFrame([
        {"traffic_segment_id": 101, "u": "N0", "v": "N1", "key": 0, "routing_eligibility": "DYNAMIC"},
        {"traffic_segment_id": 102, "u": "N1", "v": "N2", "key": 0, "routing_eligibility": "DYNAMIC"},
        {"traffic_segment_id": 103, "u": "N1", "v": "N3", "key": 0, "routing_eligibility": "DYNAMIC"},
        {"traffic_segment_id": 104, "u": "N2", "v": "N4", "key": 0, "routing_eligibility": "DYNAMIC"},
    ])

    rows = []
    for hour_offset in range(6):
        origin_ts = pd.Timestamp("2026-01-15T08:00:00Z") + pd.Timedelta(hours=hour_offset)
        # Frame >= 2 flips N1->N2 slow so dynamic/geopulse prefer N1->N3 after update
        n1_n2_pred = 60.0 if hour_offset < 1 else 6.0
        n1_n2_real = 60.0 if hour_offset < 1 else 6.0
        speeds = {
            101: (40.0, 36.0),
            102: (n1_n2_pred, n1_n2_real),
            103: (45.0, 45.0),
            104: (60.0, 60.0),
        }
        for sid, (pred, real) in speeds.items():
            rows.append({
                "timestamp": origin_ts.isoformat(),
                "traffic_segment_id": sid,
                "predicted_speed": pred,
                "actual_speed": real,
            })

    g_path = tmp_path / "net.graphml"
    m_path = tmp_path / "map.parquet"
    p_path = tmp_path / "preds.parquet"
    nx.write_graphml(graph, g_path)
    mapping_df.to_parquet(m_path, index=False)
    pd.DataFrame(rows).to_parquet(p_path, index=False)
    return graph, mapping_df, g_path, m_path, p_path


def test_coordinate_validation_and_metric_kdtree_snapping():
    with pytest.raises(ValueError, match="Non-finite"):
        validate_lat_lon(float("nan"), 85.8)
    with pytest.raises(ValueError, match="Non-finite"):
        validate_lat_lon(20.3, float("inf"))
    with pytest.raises(ValueError, match="Out-of-range"):
        validate_lat_lon(91.0, 85.8)
    with pytest.raises(ValueError, match="Out-of-range"):
        validate_lat_lon(20.3, -181.0)

    # Latitude-aware longitude scaling: 0.001 deg lon at lat 20 is ~104.5m (<111.2m lat)
    idx = SpatialNodeIndex({
        "A": (20.3000, 85.8200),
        "B": (20.3010, 85.8200),  # +111.2 m north
    })
    parsed = parse_od_input("20.3002, 85.8200", idx, max_snap_distance_m=100.0)
    assert parsed["input_type"] == "coordinates"
    assert parsed["node_id"] == "A"
    assert parsed["snap_distance_m"] == pytest.approx(haversine_distance_m(20.3002, 85.8200, 20.3000, 85.8200), rel=1e-4)

    with pytest.raises(ValueError, match="exceeding limit"):
        parse_od_input("20.4000, 85.8200", idx, max_snap_distance_m=150.0)
    with pytest.raises(ValueError, match="does not exist"):
        parse_od_input("NON_EXISTENT", idx)


def test_od_selection_determinism_reachability_and_no_duplicates(tmp_path):
    _, _, g_path, m_path, _ = _build_synthetic_network(tmp_path)
    pairs_1, meta_1 = select_od_pairs(
        max_pairs=10, seed=123, graph_path=str(g_path), mapping_path=str(m_path)
    )
    pairs_2, meta_2 = select_od_pairs(
        max_pairs=10, seed=123, graph_path=str(g_path), mapping_path=str(m_path)
    )
    assert pairs_1 == pairs_2
    assert len(pairs_1) > 0
    seen = set()
    for p in pairs_1:
        assert p["origin_node"] != p["destination_node"]
        assert p["destination_node"] != "ISOLATED"
        assert p["reachable"] is True
        assert p["route_edge_count"] >= 1
        assert p["dynamic_mapped_edge_count"] + p["static_fallback_edge_count"] == p["route_edge_count"]
        assert 0.0 <= p["dynamic_coverage_pct"] <= 100.0
        key = (p["origin_node"], p["destination_node"])
        assert key not in seen
        seen.add(key)
    assert meta_1["rejection_counts"]["self_pair"] > 0
    assert meta_1["rejection_counts"]["unreachable"] > 0


def test_geopulse_candidate_scoring_fallback_and_backtracking_instrumentation(monkeypatch, tmp_path):
    graph, mapping_df, _, _, p_path = _build_synthetic_network(tmp_path)
    wm = GraphWeightManager(graph, mapping_df)
    replay = HistoricalTrafficReplay(p_path)
    frames = [replay.get_frame(ts) for ts in replay.available_timestamps]

    # 1. Verify GeoPulse candidate A, reachable candidate B, and predicted edge + Dijkstra tail scoring
    engine = TemporalJourneyEngine(wm, frames)
    res_geo = engine.run("N0", "N5", "2026-01-15T09:58:30Z", "geopulse_two_edge")
    decisions = [e for e in res_geo.decision_trace if e.get("event") == "two_edge_decision"]
    assert len(decisions) >= 1
    at_n1 = next(e for e in decisions if e["current_node"] == "N1")
    assert at_n1["candidate_a"] == ("N1", "N2", 0)
    assert at_n1["candidate_b"] == ("N1", "N3", 0)
    w_frame1 = engine._prediction_weights(1)
    expected_b = w_frame1[("N1", "N3", 0)] + engine._route("N3", "N5", w_frame1).total_cost
    assert at_n1["score_b"] == pytest.approx(expected_b)
    assert res_geo.forced_single_edge_decisions >= 1  # N0->N1, N3->N4, N4->N5 are single-exit nodes

    # 2. Verify safety fallback and dead-end exclusion from two_edge_only_success
    engine_fb = TemporalJourneyEngine(wm, frames)
    monkeypatch.setattr(
        engine_fb,
        "_two_edge_choice",
        lambda *args, **kwargs: (None, [], {"reason": "test_forced_fallback"}, False, False),
    )
    res_fb = engine_fb.run("N0", "N5", "2026-01-15T09:00:00Z", "geopulse_two_edge")
    assert res_fb.success is True
    assert res_fb.dijkstra_fallback_steps == res_fb.traversed_edges
    assert res_fb.two_edge_only_success is False
    assert res_fb.route_changes >= 0

    # 3. Verify backtracking instrumentation on an actual link reversal
    rev_graph = nx.MultiDiGraph()
    rev_graph.add_edge("S", "A", key=0, length=100.0, highway="primary")
    rev_graph.add_edge("A", "S", key=0, length=100.0, highway="primary")
    rev_graph.add_edge("S", "T", key=0, length=100.0, highway="primary")
    rev_wm = GraphWeightManager(rev_graph, pd.DataFrame(columns=["traffic_segment_id", "u", "v", "key", "routing_eligibility"]))
    rev_engine = TemporalJourneyEngine(rev_wm, frames[:2])
    from src.routing.dijkstra import DijkstraResult
    monkeypatch.setattr(
        rev_engine,
        "_route",
        lambda *args, **kwargs: DijkstraResult(["S", "A", "S", "T"], [("S", "A", 0), ("A", "S", 0), ("S", "T", 0)], 1.0, 4, True),
    )
    res_rev = rev_engine.run("S", "T", frames[0].target_valid_timestamp.isoformat(), "static_dijkstra")
    assert res_rev.success is True
    assert res_rev.backtracking_events == 1
    assert res_rev.repeated_node_visits == 1
    assert res_rev.loop_traps == 0


def test_departure_schedule_selection_within_horizon():
    valid_times = [pd.Timestamp("2026-01-15T09:00:00Z") + pd.Timedelta(hours=h) for h in range(44)]
    final_until = valid_times[-1] + pd.Timedelta(hours=1)
    schedules = select_departure_schedules(valid_times, final_until, max_departures=5)
    assert len(schedules) == 5
    periods = {s["period_label"] for s in schedules}
    assert len(periods) >= 4  # Morning Peak, Midday, Afternoon, Evening Peak, Off-Peak Night
    for s in schedules:
        dep = pd.Timestamp(s["departure_utc"])
        assert valid_times[0] <= dep < final_until


def test_temporal_engine_incomplete_beyond_horizon_and_route_changes(tmp_path):
    graph, mapping_df, _, _, p_path = _build_synthetic_network(tmp_path)
    wm = GraphWeightManager(graph, mapping_df)
    replay = HistoricalTrafficReplay(p_path)
    frames = [replay.get_frame(ts) for ts in replay.available_timestamps]
    engine = TemporalJourneyEngine(wm, frames)

    # Departure right before horizon ends must fail cleanly as incomplete
    near_end = (engine.final_valid_until - pd.Timedelta(seconds=5)).isoformat()
    res_end = engine.run("N0", "N5", near_end, "geopulse_two_edge")
    assert res_end.success is False
    assert "realized_traffic_unavailable" in res_end.failure_reason
    assert res_end.incomplete_decisions >= 1

    # Departure across boundary triggers update & compares strategies fairly
    dep = "2026-01-15T09:58:30Z"
    res_static = engine.run("N0", "N5", dep, "static_dijkstra")
    res_dyn = engine.run("N0", "N5", dep, "dynamic_dijkstra")
    res_geo = engine.run("N0", "N5", dep, "geopulse_two_edge")
    assert res_static.success and res_dyn.success and res_geo.success
    assert res_static.prediction_updates_applied == 0
    assert res_static.route_changes == 0
    assert res_dyn.prediction_updates_applied == 1
    assert res_dyn.dijkstra_reroutes == 1
    assert res_geo.prediction_updates_applied == 1
    assert res_geo.two_edge_alternative_selections >= 1
    assert res_geo.route_changes >= 1
    # Dynamic and GeoPulse should both avoid congested N1->N2 and finish faster than Static
    assert res_dyn.travel_time_s < res_static.travel_time_s
    assert res_geo.travel_time_s < res_static.travel_time_s
    assert res_geo.arrival_timestamp > dep


def test_paired_comparison_tie_threshold_and_failure_separation():
    df = pd.DataFrame([
        # S0: GeoPulse wins by 10s (> max(1, 0.1))
        {"scenario_id": "S0", "od_id": 0, "departure_timestamp": "t0", "strategy": "static_dijkstra",
         "success": True, "travel_time_s": 100.0, "distance_m": 1000.0, "traversed_dynamic_coverage_pct": 20.0,
         "od_coverage_category": "low", "od_distance_category": "short"},
        {"scenario_id": "S0", "od_id": 0, "departure_timestamp": "t0", "strategy": "dynamic_dijkstra",
         "success": True, "travel_time_s": 95.0, "distance_m": 1000.0, "traversed_dynamic_coverage_pct": 20.0,
         "od_coverage_category": "low", "od_distance_category": "short"},
        {"scenario_id": "S0", "od_id": 0, "departure_timestamp": "t0", "strategy": "geopulse_two_edge",
         "success": True, "travel_time_s": 90.0, "distance_m": 1000.0, "traversed_dynamic_coverage_pct": 20.0,
         "od_coverage_category": "low", "od_distance_category": "short"},
        # S1: Tie within max(1s, 0.1% of 100 = 1.0s)
        {"scenario_id": "S1", "od_id": 1, "departure_timestamp": "t0", "strategy": "static_dijkstra",
         "success": True, "travel_time_s": 100.0, "distance_m": 1000.0, "traversed_dynamic_coverage_pct": 50.0,
         "od_coverage_category": "medium", "od_distance_category": "medium"},
        {"scenario_id": "S1", "od_id": 1, "departure_timestamp": "t0", "strategy": "dynamic_dijkstra",
         "success": True, "travel_time_s": 100.0, "distance_m": 1000.0, "traversed_dynamic_coverage_pct": 50.0,
         "od_coverage_category": "medium", "od_distance_category": "medium"},
        {"scenario_id": "S1", "od_id": 1, "departure_timestamp": "t0", "strategy": "geopulse_two_edge",
         "success": True, "travel_time_s": 99.5, "distance_m": 1000.0, "traversed_dynamic_coverage_pct": 50.0,
         "od_coverage_category": "medium", "od_distance_category": "medium"},
        # S2: GeoPulse fails, Static succeeds — must NOT count failed 0s run in mean time
        {"scenario_id": "S2", "od_id": 2, "departure_timestamp": "t0", "strategy": "static_dijkstra",
         "success": True, "travel_time_s": 200.0, "distance_m": 2000.0, "traversed_dynamic_coverage_pct": 80.0,
         "od_coverage_category": "high", "od_distance_category": "long"},
        {"scenario_id": "S2", "od_id": 2, "departure_timestamp": "t0", "strategy": "dynamic_dijkstra",
         "success": True, "travel_time_s": 200.0, "distance_m": 2000.0, "traversed_dynamic_coverage_pct": 80.0,
         "od_coverage_category": "high", "od_distance_category": "long"},
        {"scenario_id": "S2", "od_id": 2, "departure_timestamp": "t0", "strategy": "geopulse_two_edge",
         "success": False, "travel_time_s": 0.0, "distance_m": 0.0, "traversed_dynamic_coverage_pct": 0.0,
         "od_coverage_category": "high", "od_distance_category": "long"},
    ])
    summary = compute_strategy_summary(df)
    gp_row = summary[summary["strategy"] == "geopulse_two_edge"].iloc[0]
    assert gp_row["completed_runs"] == 2
    assert gp_row["failed_runs"] == 1
    assert gp_row["travel_time_s_mean"] == pytest.approx(94.75)

    comp = paired_comparison(df, "static_dijkstra", "geopulse_two_edge")
    assert comp["total_scenarios"] == 3
    assert comp["paired_completed_count"] == 2
    assert comp["baseline_only_completed"] == 1
    assert comp["wins"] == 1
    assert comp["ties"] == 1
    assert comp["losses"] == 0
    assert comp["mean_improvement_pct"] == pytest.approx(5.25, rel=1e-3)

    h2h = compute_head_to_head(df)
    assert len(h2h) == 3

    cov_rep = compute_coverage_and_length_report(df, network_total_edges=100, network_dynamic_edges=10)
    assert cov_rep["network_coverage"]["network_dynamic_coverage_pct"] == pytest.approx(10.0)
    assert set(cov_rep["coverage_groups"].keys()) == {"low", "medium", "high"}


def test_end_to_end_benchmark_outputs_and_schemas(tmp_path):
    _, _, g_path, m_path, p_path = _build_synthetic_network(tmp_path)
    out_dir = tmp_path / "stage3_out"
    res = run_stage3_benchmark(
        max_pairs=4,
        max_departures=2,
        seed=42,
        graph_path=str(g_path),
        mapping_path=str(m_path),
        predictions_path=str(p_path),
        output_dir=str(out_dir),
    )
    assert res["strategy_run_count"] == res["scenario_count"] * len(STRATEGIES)
    expected_files = [
        "od_manifest.csv",
        "journey_results.csv",
        "strategy_summary.csv",
        "head_to_head_comparison.csv",
        "coverage_report.json",
        "benchmark_manifest.json",
        "benchmark_report.md",
    ]
    for fname in expected_files:
        assert (out_dir / fname).is_file(), f"Missing output file: {fname}"

    jdf = pd.read_csv(out_dir / "journey_results.csv")
    assert len(jdf) == res["strategy_run_count"]
    assert set(jdf["strategy"].unique()) == set(STRATEGIES)
    for col in (
        "scenario_id", "od_id", "strategy", "origin", "destination",
        "departure_timestamp", "arrival_timestamp", "success", "travel_time_s",
        "distance_m", "route_changes", "forced_single_edge_decisions",
        "dijkstra_fallback_steps", "backtracking_events", "repeated_node_visits",
        "loop_traps", "incomplete_decisions", "traversed_dynamic_coverage_pct",
    ):
        assert col in jdf.columns

    manifest = json.loads((out_dir / "benchmark_manifest.json").read_text(encoding="utf-8"))
    assert manifest["random_seed"] == 42
    assert manifest["strategy_run_count"] == len(jdf)
    assert "## 16. Conclusion" in (out_dir / "benchmark_report.md").read_text(encoding="utf-8")
