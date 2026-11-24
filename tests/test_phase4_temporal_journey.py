"""Regression tests for prediction/realization separation and temporal routing."""

from __future__ import annotations

from pathlib import Path

import networkx as nx
import pandas as pd
import pytest

from src.experiments.temporal_journey import RouteTraceCounter, TemporalJourneyEngine
from src.routing.dijkstra import DijkstraResult
from src.routing.traffic_weights import GraphWeightManager
from src.simulation.vehicle import Vehicle
from src.traffic.replay import HistoricalTrafficReplay


ROOT = Path(__file__).resolve().parents[1]


def _toy_inputs():
    graph = nx.MultiDiGraph()
    graph.add_edge("S", "A", key=0, length=22_000, highway="primary")
    graph.add_edge("S", "B", key=0, length=22_000, highway="primary")
    graph.add_edge("A", "T", key=0, length=1_000, highway="primary")
    graph.add_edge("B", "T", key=0, length=1_000, highway="primary")
    graph.add_edge("A", "B", key=0, length=1_000, highway="primary")
    mapping = pd.DataFrame([
        {"traffic_segment_id": sid, "u": u, "v": v, "key": 0,
         "routing_eligibility": "DYNAMIC"}
        for sid, u, v in (
            (1, "S", "A"), (2, "S", "B"), (3, "A", "T"),
            (4, "B", "T"), (5, "A", "B"),
        )
    ])
    rows = []
    initial_predictions = {1: 120.0, 2: 30.0, 3: 120.0, 4: 120.0, 5: 120.0}
    updated_predictions = {1: 120.0, 2: 120.0, 3: 3.0, 4: 120.0, 5: 120.0}
    observed = {sid: 120.0 for sid in initial_predictions}
    for timestamp, predictions in (
        ("2026-01-15 08:00:00+00:00", initial_predictions),
        ("2026-01-15 09:00:00+00:00", updated_predictions),
        ("2026-01-15 10:00:00+00:00", updated_predictions),
    ):
        for segment_id, predicted_speed in predictions.items():
            rows.append({
                "timestamp": timestamp,
                "traffic_segment_id": segment_id,
                "predicted_speed": predicted_speed,
                "actual_speed": observed[segment_id],
            })
    replay = HistoricalTrafficReplay(pd.DataFrame(rows))
    frames = [replay.get_frame(timestamp) for timestamp in replay.available_timestamps]
    return graph, mapping, frames


def _run_all():
    graph, mapping, frames = _toy_inputs()
    engine = TemporalJourneyEngine(GraphWeightManager(graph, mapping), frames)
    departure = "2026-01-15T09:55:00Z"
    return {
        strategy: engine.run("S", "T", departure, strategy)
        for strategy in ("static_dijkstra", "dynamic_dijkstra", "geopulse_two_edge")
    }


def test_actual_speed_is_separate_from_prediction_and_drives_motion():
    rows = pd.DataFrame([
        {"timestamp": timestamp, "traffic_segment_id": 7,
         "predicted_speed": 120.0, "actual_speed": 36.0}
        for timestamp in ("2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z")
    ])
    frame = HistoricalTrafficReplay(rows).get_frame("2026-01-01T00:00:00Z")
    assert frame.predicted_speeds[7] == 120.0
    assert frame.realized_speeds[7] == 36.0
    assert frame.has_realized_observations

    graph = nx.MultiDiGraph()
    graph.add_edge("S", "T", key=0, length=1_000, highway="primary")
    mapping = pd.DataFrame([{
        "traffic_segment_id": 7, "u": "S", "v": "T", "key": 0,
        "routing_eligibility": "DYNAMIC",
    }])
    result = TemporalJourneyEngine(
        GraphWeightManager(graph, mapping), [
            frame,
            HistoricalTrafficReplay(rows).get_frame("2026-01-01T01:00:00Z"),
        ]
    ).run("S", "T", "2026-01-01T01:00:00Z", "static_dijkstra")
    assert result.success
    assert result.travel_time_s == pytest.approx(100.0)
    assert result.travel_time_s != pytest.approx(30.0)  # 120 km/h prediction cost


def test_phase7_actual_speed_labels_match_observed_next_hour_source_rows():
    predictions = pd.read_parquet(ROOT / "results/phase7_predictions.parquet")
    structured = pd.read_parquet(ROOT / "datasets/traffic_structured_v1.parquet")
    predictions["origin"] = pd.to_datetime(predictions["timestamp"], utc=True).dt.round("h")
    predictions["target"] = predictions["origin"] + pd.Timedelta(hours=1)
    source = structured.assign(
        segment_id=pd.to_numeric(structured["segment_id"]).astype("int64"),
        hour_utc=pd.to_datetime(structured["hour"], utc=True).dt.floor("h"),
    ).set_index(["segment_id", "hour_utc"])["currentSpeed"]
    keys = pd.MultiIndex.from_arrays([
        pd.to_numeric(predictions["traffic_segment_id"]).astype("int64"),
        predictions["target"],
    ])
    aligned = pd.to_numeric(source.reindex(keys), errors="coerce").to_numpy()
    actual = pd.to_numeric(predictions["actual_speed"], errors="coerce").to_numpy()
    assert len(predictions) == 30_800
    assert pd.notna(aligned).all()
    assert (actual == aligned).all()


def test_static_route_stays_fixed_while_dynamic_dijkstra_reroutes_on_update():
    results = _run_all()
    static = results["static_dijkstra"]
    dynamic = results["dynamic_dijkstra"]
    assert static.success and dynamic.success
    assert [edge[:2] for edge in static.traversed_edge_path] == [("S", "A"), ("A", "T")]
    assert [edge[:2] for edge in dynamic.traversed_edge_path] == [
        ("S", "A"), ("A", "B"), ("B", "T")
    ]
    assert dynamic.prediction_updates_applied == 1
    assert dynamic.dijkstra_reroutes == 1
    assert static.prediction_updates_applied == 0


def test_geopulse_uses_two_reachable_destination_costed_candidates():
    result = _run_all()["geopulse_two_edge"]
    assert result.success
    assert [edge[:2] for edge in result.traversed_edge_path] == [
        ("S", "A"), ("A", "B"), ("B", "T")
    ]
    assert result.intersection_decisions >= 2
    assert result.two_edge_alternative_selections >= 1
    assert result.two_edge_only_success is True
    decisions = [row for row in result.decision_trace if row.get("event") == "two_edge_decision"]
    assert decisions
    for decision in decisions:
        assert decision["candidate_a"]
        assert decision["candidate_b"]
        assert decision["score_a"] > 0
        assert decision["score_b"] > 0
        assert decision["selected_edge"] in (
            decision["candidate_a"], decision["candidate_b"]
        )
    at_a = next(row for row in decisions if row["current_node"] == "A")
    assert at_a["candidate_a"] == ("A", "T", 0)
    assert at_a["candidate_b"] == ("A", "B", 0)
    assert at_a["selected_edge"] == at_a["candidate_b"]
    assert result.dijkstra_fallback_steps == 0


def test_realized_speed_integrates_update_mid_edge_but_route_update_waits_for_node():
    _, mapping, frames = _toy_inputs()
    # Make the observed speed drop at 10:00 while keeping the predicted choice
    # stream independent. The vehicle starts a 22 km edge at 09:55.
    frames[1] = type(frames[1])(
        origin_timestamp=frames[1].origin_timestamp,
        target_valid_timestamp=frames[1].target_valid_timestamp,
        predicted_speeds=frames[1].predicted_speeds,
        realized_speeds={sid: (18.0 if sid == 1 else 120.0) for sid in frames[1].realized_speeds},
        source_origin_timestamps=frames[1].source_origin_timestamps,
        missing_segment_ids=frames[1].missing_segment_ids,
        invalid_segment_ids=frames[1].invalid_segment_ids,
        missing_realized_segment_ids=frozenset(),
        invalid_realized_segment_ids=frozenset(),
        has_realized_observations=True,
    )
    graph, mapping, _ = _toy_inputs()
    engine = TemporalJourneyEngine(GraphWeightManager(graph, mapping), frames)
    result = engine.run("S", "T", "2026-01-15T09:55:00Z", "dynamic_dijkstra")
    first = result.decision_trace[0]
    assert first["realized_travel_time_s"] == pytest.approx(2_700.0)
    # The new prediction is used after reaching A, not while traversing S -> A.
    assert first["prediction_target_valid_timestamp"] == "2026-01-15T09:00:00+00:00"
    assert result.prediction_updates_applied == 1
    assert result.traversed_edge_path[0][:2] == ("S", "A")


def test_unreachable_destination_fails_without_fabricating_fallback_success():
    graph = nx.MultiDiGraph()
    graph.add_edge("S", "A", key=0, length=100.0, highway="primary")
    mapping = pd.DataFrame(columns=[
        "traffic_segment_id", "u", "v", "key", "routing_eligibility"
    ])
    rows = pd.DataFrame([{
        "timestamp": "2026-01-01T00:00:00Z",
        "traffic_segment_id": 1,
        "predicted_speed": 30.0,
        "actual_speed": 30.0,
    }])
    replay = HistoricalTrafficReplay(rows)
    frame = replay.get_frame("2026-01-01T00:00:00Z")
    result = TemporalJourneyEngine(GraphWeightManager(graph, mapping), [frame]).run(
        "S", "Z", "2026-01-01T01:00:00Z", "geopulse_two_edge"
    )
    assert not result.success
    assert result.failure_reason == "destination_unreachable_at_departure"
    assert result.dijkstra_fallback_steps == 0
    assert result.traversed_edges == 0


def test_safety_fallback_steps_are_separate_from_two_edge_only_success(monkeypatch):
    graph, mapping, frames = _toy_inputs()
    engine = TemporalJourneyEngine(GraphWeightManager(graph, mapping), frames)
    monkeypatch.setattr(
        engine,
        "_two_edge_choice",
        lambda current, destination, planned_edges, weights, visited:
            (None, [], {"reason": "injected_no_candidate"}, False, False),
    )
    result = engine.run("S", "T", "2026-01-15T09:00:00Z", "geopulse_two_edge")
    assert result.success
    assert result.dijkstra_fallback_steps == result.traversed_edges
    assert result.dijkstra_fallback_steps > 0
    assert result.two_edge_only_success is False


def test_multiple_hour_updates_during_one_edge_are_applied_at_next_node():
    graph = nx.MultiDiGraph()
    graph.add_edge("S", "A", key=0, length=200_000, highway="primary")
    graph.add_edge("A", "T", key=0, length=100, highway="primary")
    mapping = pd.DataFrame([
        {"traffic_segment_id": sid, "u": u, "v": v, "key": 0,
         "routing_eligibility": "DYNAMIC"}
        for sid, u, v in ((1, "S", "A"), (2, "A", "T"))
    ])
    rows = []
    for origin_hour in (8, 9, 10, 11):
        timestamp = f"2026-01-15 {origin_hour:02d}:00:00+00:00"
        for segment_id in (1, 2):
            rows.append({
                "timestamp": timestamp,
                "traffic_segment_id": segment_id,
                "predicted_speed": 60.0 + origin_hour,
                "actual_speed": 120.0,
            })
    replay = HistoricalTrafficReplay(pd.DataFrame(rows))
    frames = [replay.get_frame(hour) for hour in replay.available_timestamps]
    engine = TemporalJourneyEngine(GraphWeightManager(graph, mapping), frames)
    result = engine.run("S", "T", "2026-01-15T09:30:00Z", "dynamic_dijkstra")
    assert result.success
    assert result.decision_trace[0]["realized_travel_time_s"] == pytest.approx(6_000.0)
    # Forecasts valid at 10:00 and 11:00 arrived during S -> A; the latest is
    # used once the vehicle reaches A and makes its next route decision.
    assert result.prediction_updates_applied == 1
    assert result.decision_trace[1]["prediction_target_valid_timestamp"] == (
        "2026-01-15T11:00:00+00:00"
    )


def test_vehicle_keeps_elapsed_motion_when_temporal_plan_changes():
    vehicle = Vehicle("phase4-test", "S", "T", "2026-01-01T00:00:00Z")
    vehicle.begin_temporal_journey(["S", "T"], [("S", "T", 0)], "2026-01-01T00:00:00Z")
    vehicle.set_temporal_plan(
        ["S", "A", "T"], [("S", "A", 0), ("A", "T", 0)],
        "2026-01-01T00:00:00Z", "Two-Edge selected a longer path",
    )
    vehicle.record_realized_edge_traversal(
        ("S", "A", 0), 1.5, 30.0, "2026-01-01T00:00:01.5Z"
    )
    assert vehicle.current_node == "A"
    assert vehicle.elapsed_travel_time_s == pytest.approx(1.5)
    assert vehicle.accumulated_distance_m == pytest.approx(30.0)
    assert vehicle.progress_pct == 100.0
    assert vehicle.timeline[-2]["edge_index"] == 0
    vehicle.record_realized_edge_traversal(
        ("A", "T", 0), 2.0, 40.0, "2026-01-01T00:00:03.5Z"
    )
    vehicle.finish_temporal_journey("2026-01-01T00:00:03.5Z")
    assert vehicle.is_journey_complete
    assert vehicle.elapsed_travel_time_s == pytest.approx(3.5)
    assert vehicle.accumulated_distance_m == pytest.approx(70.0)
    assert vehicle.progress_pct == 100.0


def test_route_trace_counter_distinguishes_backtrack_repeat_and_loop_trap():
    reversal = RouteTraceCounter("S")
    assert reversal.record(("S", "A", 0)) == {
        "backtracking_event": False, "repeated_node_visit": False, "loop_trap": False,
    }
    event = reversal.record(("A", "S", 0))
    assert event == {
        "backtracking_event": True, "repeated_node_visit": True, "loop_trap": False,
    }
    assert reversal.backtracking_events == 1
    assert reversal.repeated_node_visits == 1
    assert reversal.loop_traps == 0

    triangle = RouteTraceCounter("S")
    triangle.record(("S", "A", 0))
    triangle.record(("A", "B", 0))
    event = triangle.record(("B", "S", 0))
    assert event == {
        "backtracking_event": False, "repeated_node_visit": True, "loop_trap": True,
    }
    assert triangle.backtracking_events == 0
    assert triangle.repeated_node_visits == 1
    assert triangle.loop_traps == 1


def test_temporal_engine_reports_nonzero_backtracking_when_route_reverses(monkeypatch):
    graph = nx.MultiDiGraph()
    graph.add_edge("S", "A", key=0, length=100, highway="primary")
    graph.add_edge("A", "S", key=0, length=100, highway="primary")
    graph.add_edge("S", "T", key=0, length=100, highway="primary")
    mapping = pd.DataFrame(columns=[
        "traffic_segment_id", "u", "v", "key", "routing_eligibility"
    ])
    rows = pd.DataFrame([
        {"timestamp": timestamp, "traffic_segment_id": 1,
         "predicted_speed": 30.0, "actual_speed": 30.0}
        for timestamp in ("2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z")
    ])
    replay = HistoricalTrafficReplay(rows)
    frames = [replay.get_frame(hour) for hour in replay.available_timestamps]
    engine = TemporalJourneyEngine(GraphWeightManager(graph, mapping), frames)
    monkeypatch.setattr(
        engine,
        "_route",
        lambda *args, **kwargs: DijkstraResult(
            node_path=["S", "A", "S", "T"],
            edge_path=[("S", "A", 0), ("A", "S", 0), ("S", "T", 0)],
            total_cost=1.0,
            visited_nodes_count=4,
            is_reached=True,
        ),
    )
    result = engine.run("S", "T", "2026-01-01T01:00:00Z", "static_dijkstra")
    assert result.success
    assert result.backtracking_events == 1
    assert result.to_dict()["backtracking_steps"] == 1
    assert result.repeated_node_visits == 1
    assert result.loop_traps == 0


def test_final_realized_frame_is_held_only_until_its_next_hour_boundary():
    graph, mapping, frames = _toy_inputs()
    manager = GraphWeightManager(graph, mapping)
    engine = TemporalJourneyEngine(manager, frames)
    edge = ("S", "A", 0)
    final_valid = engine.valid_times[-1]

    # Before the final sample becomes valid, traversal uses the prior hourly
    # observation and then the final sample after crossing its boundary.
    before_time, before_arrival = engine._traverse_realized(
        edge, final_valid - pd.Timedelta(minutes=1)
    )
    assert before_time == pytest.approx(660.0)
    assert before_arrival == final_valid + pd.Timedelta(minutes=10)

    at_time, at_arrival = engine._traverse_realized(edge, final_valid)
    assert at_time == pytest.approx(660.0)
    assert at_arrival == final_valid + pd.Timedelta(minutes=11)

    after_time, after_arrival = engine._traverse_realized(
        edge, final_valid + pd.Timedelta(minutes=30)
    )
    assert after_time == pytest.approx(660.0)
    assert after_arrival == final_valid + pd.Timedelta(minutes=41)

    with pytest.raises(ValueError, match="timeline ended at"):
        engine._traverse_realized(edge, engine.final_valid_until)

    with pytest.raises(ValueError, match="timeline ended at"):
        engine._traverse_realized(edge, engine.final_valid_until + pd.Timedelta(seconds=1))
