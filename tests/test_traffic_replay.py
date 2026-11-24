"""Unit tests for historical prediction replay and dynamic edge-cost updates."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
import pytest

from src.cloud.model_service import CloudModelService
from src.routing.traffic_weights import (
    GraphWeightManager,
    TrafficEdgeCostUpdater,
    _as_segment_id,
    calculate_travel_time_seconds,
)
from src.traffic.replay import HistoricalTrafficReplay, MissingReplayTimestampError

ROOT = Path(__file__).resolve().parents[1]


def prediction_rows(hours=("2026-01-01 00:00:01+00:00", "2026-01-01 01:00:02+00:00")):
    rows = []
    for timestamp in hours:
        for segment_id, speed in ((1, 36.0), (2, 45.0)):
            rows.append({
                "timestamp": timestamp,
                "traffic_segment_id": segment_id,
                "predicted_speed": speed,
            })
    return pd.DataFrame(rows)


def make_graph_and_mapping():
    graph = nx.MultiDiGraph()
    graph.add_edge("A", "B", key=0, length="1000", highway="primary")
    graph.add_edge("B", "A", key=0, length="1000", highway="primary")
    graph.add_edge("B", "A", key=1, length="1200", highway="primary")
    graph.add_edge("B", "C", key=0, length="500", highway="secondary")
    graph.add_edge("C", "D", key=0, length="200", highway="tertiary")
    graph.add_edge("E", "F", key=0, length="1000", highway="primary")
    graph.add_edge("F", "G", key=0, length="1000", highway="primary")
    graph.add_edge("G", "H", key=0, length="1000", highway="primary")
    graph.add_edge("H", "I", key=0, length="1000", highway="primary")
    graph.add_edge("I", "J", key=0, length="1000", highway="primary")
    graph.add_edge("J", "K", key=0, length="1000", highway="primary")
    mapping = pd.DataFrame([
        {"traffic_segment_id": 1, "u": "A", "v": "B", "key": 0, "routing_eligibility": "DYNAMIC_BIDIRECTIONAL"},
        {"traffic_segment_id": 1, "u": "A", "v": "B", "key": 0, "routing_eligibility": "DYNAMIC_BIDIRECTIONAL"},
        {"traffic_segment_id": 2, "u": "A", "v": "B", "key": 0, "routing_eligibility": "DYNAMIC_BIDIRECTIONAL"},
        {"traffic_segment_id": 3, "u": "B", "v": "C", "key": 0, "routing_eligibility": "STATIC_FALLBACK"},
        {"traffic_segment_id": 4, "u": "E", "v": "F", "key": 0, "routing_eligibility": "DYNAMIC"},
        {"traffic_segment_id": 5, "u": "F", "v": "G", "key": 0, "routing_eligibility": "DYNAMIC"},
        {"traffic_segment_id": 6, "u": "G", "v": "H", "key": 0, "routing_eligibility": "DYNAMIC"},
        {"traffic_segment_id": 7, "u": "H", "v": "I", "key": 0, "routing_eligibility": "DYNAMIC"},
        {"traffic_segment_id": 8, "u": "I", "v": "J", "key": 0, "routing_eligibility": "DYNAMIC"},
        {"traffic_segment_id": 9, "u": "J", "v": "K", "key": 0, "routing_eligibility": "DYNAMIC"},
    ])
    return graph, mapping


def make_updater():
    graph, mapping = make_graph_and_mapping()
    manager = GraphWeightManager(graph, mapping)
    return graph, mapping, manager, TrafficEdgeCostUpdater(manager)


def test_load_saved_prediction_artifact_and_expected_hour_coverage():
    replay = HistoricalTrafficReplay(ROOT / "results/phase7_predictions.parquet")
    assert len(replay.available_timestamps) == 44
    assert replay.available_timestamps[0] == pd.Timestamp("2026-01-15 08:00:00+00:00")
    assert replay.available_timestamps[-1] == pd.Timestamp("2026-01-17 03:00:00+00:00")
    frame = replay.get_frame("2026-01-15T08:00:00Z")
    assert len(frame.predicted_speeds) == 700
    assert not frame.missing_segment_ids


def test_replay_advances_hourly_and_separates_origin_from_target_valid_time():
    replay = HistoricalTrafficReplay(prediction_rows())
    first = replay.start("2026-01-01T00:00:00Z")
    second = replay.advance()
    assert first.origin_timestamp == pd.Timestamp("2026-01-01T00:00:00Z")
    assert first.target_valid_timestamp == pd.Timestamp("2026-01-01T01:00:00Z")
    assert first.source_origin_timestamps[1] == pd.Timestamp("2026-01-01T00:00:01Z")
    assert second.origin_timestamp == pd.Timestamp("2026-01-01T01:00:00Z")
    assert second.target_valid_timestamp == pd.Timestamp("2026-01-01T02:00:00Z")
    assert replay.advance() is None


def test_replay_rejects_non_hourly_request_and_missing_exact_timestamp():
    replay = HistoricalTrafficReplay(prediction_rows())
    with pytest.raises(ValueError, match="exact hourly"):
        replay.start("2026-01-01T00:30:00Z")
    with pytest.raises(MissingReplayTimestampError, match="No prediction frame"):
        replay.start("2026-01-01T02:00:00Z")


def test_replay_advance_reports_gaps_without_skipping():
    rows = prediction_rows(hours=("2026-01-01 00:00:01+00:00", "2026-01-01 02:00:01+00:00"))
    replay = HistoricalTrafficReplay(rows)
    replay.start("2026-01-01T00:00:00Z")
    with pytest.raises(MissingReplayTimestampError, match="2026-01-01T01:00:00"):
        replay.advance()


def test_missing_segment_prediction_is_exposed():
    replay = HistoricalTrafficReplay(
        pd.DataFrame([{
            "timestamp": "2026-01-01 00:00:00+00:00",
            "traffic_segment_id": 1,
            "predicted_speed": 30.0,
        }]),
        expected_segment_ids={1, 2},
    )
    frame = replay.get_frame("2026-01-01T00:00:00Z")
    assert frame.missing_segment_ids == frozenset({2})
    assert frame.missing_prediction_count == 1


def test_duplicate_prediction_rows_fail_deterministically():
    rows = prediction_rows(hours=("2026-01-01 00:00:00+00:00",))
    rows = pd.concat([rows, rows.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="Duplicate prediction rows"):
        HistoricalTrafficReplay(rows)


def test_mapping_to_directed_edge_and_bidirectional_reverse_edges():
    _, _, manager, _ = make_updater()
    weights, speeds, dynamic_edges = manager.build_scenario_weights({1: 36.0, 2: 72.0})
    assert dynamic_edges == {("A", "B", 0), ("B", "A", 0), ("B", "A", 1)}
    for edge in dynamic_edges:
        assert speeds[edge] == 54.0
        assert weights[edge] == pytest.approx(manager.edge_lengths[edge] * 3.6 / 54.0)


def test_duplicate_mapping_rows_do_not_overweight_a_sensor():
    _, _, manager, _ = make_updater()
    _, speeds, _ = manager.build_scenario_weights({1: 36.0, 2: 72.0})
    # Sensor 1's duplicate mapping row is deduplicated: mean(36, 72), not mean(36, 36, 72).
    assert speeds[("A", "B", 0)] == 54.0


def test_unmapped_and_static_fallback_edges_keep_static_costs():
    _, _, manager, updater = make_updater()
    result = updater.update_working_copy({1: 36.0, 2: 72.0, 3: 120.0})
    assert result.weights[("B", "C", 0)] == manager.static_weights[("B", "C", 0)]
    assert result.weights[("C", "D", 0)] == manager.static_weights[("C", "D", 0)]
    assert ("B", "C", 0) not in result.dynamic_edges
    assert ("C", "D", 0) not in result.dynamic_edges


@pytest.mark.parametrize("bad_speed", [np.nan, np.inf, -np.inf, 0.0, -5.0, "bad"])
def test_invalid_predictions_use_static_fallback(bad_speed):
    _, _, manager, updater = make_updater()
    result = updater.update_working_copy({4: bad_speed})
    edge = ("E", "F", 0)
    assert edge not in result.dynamic_edges
    assert result.weights[edge] == manager.static_weights[edge]
    assert result.diagnostics.invalid_predictions == 1


def test_valid_speeds_are_clipped_to_model_bounds():
    _, _, manager, updater = make_updater()
    result = updater.update_working_copy({4: 1.0, 5: 180.0})
    assert result.speeds_kmh[("E", "F", 0)] == 3.0
    assert result.speeds_kmh[("F", "G", 0)] == 120.0
    assert result.weights[("E", "F", 0)] == pytest.approx(1000 * 3.6 / 3.0)
    assert result.weights[("F", "G", 0)] == pytest.approx(1000 * 3.6 / 120.0)


def test_kinematic_formula_and_edge_weights_are_finite_positive():
    assert calculate_travel_time_seconds(1000, 36) == pytest.approx(100.0)
    _, _, _, updater = make_updater()
    result = updater.update_working_copy({1: 40, 2: 60, 4: 0})
    assert all(np.isfinite(cost) and cost > 0 for cost in result.weights.values())
    assert all(
        np.isfinite(data["travel_time_seconds"]) and data["travel_time_seconds"] > 0
        for _, _, _, data in result.working_graph.edges(data=True, keys=True)
    )


def test_coverage_diagnostics_include_timestamp_missing_invalid_and_unmapped_counts():
    _, _, _, updater = make_updater()
    result = updater.update_working_copy(
        {1: 36.0, 2: 72.0, 4: 40.0, 5: 50.0, 6: np.nan, 7: np.inf, 8: 0.0},
        origin_timestamp=pd.Timestamp("2026-01-01T00:00:00Z"),
        target_valid_timestamp=pd.Timestamp("2026-01-01T01:00:00Z"),
    )
    diagnostics = result.diagnostics
    assert diagnostics.total_directed_edges == 11
    assert diagnostics.dynamically_updated_edges == 5
    assert diagnostics.static_fallback_edges == 6
    assert diagnostics.unmapped_edges == 1
    assert diagnostics.missing_predictions == 1
    assert diagnostics.invalid_predictions == 3
    assert diagnostics.explicit_static_fallback_edges == 1
    assert diagnostics.dynamic_missing_prediction_edges == 1
    assert diagnostics.dynamic_invalid_prediction_edges == 3
    assert diagnostics.mapped_static_fallback_edges == diagnostics.explicit_static_fallback_edges
    assert diagnostics.dynamic_coverage_pct == pytest.approx(100 * 5 / 11)
    assert diagnostics.origin_timestamp == "2026-01-01T00:00:00+00:00"
    assert diagnostics.target_valid_timestamp == "2026-01-01T01:00:00+00:00"
    assert diagnostics.static_fallback_edges == (
        diagnostics.explicit_static_fallback_edges
        + diagnostics.unmapped_edges
        + diagnostics.dynamic_missing_prediction_edges
        + diagnostics.dynamic_invalid_prediction_edges
    )
    assert (
        diagnostics.dynamically_updated_edges
        + diagnostics.explicit_static_fallback_edges
        + diagnostics.unmapped_edges
        + diagnostics.dynamic_missing_prediction_edges
        + diagnostics.dynamic_invalid_prediction_edges
        == diagnostics.total_directed_edges
    )


def test_edge_with_one_valid_and_one_invalid_sensor_is_classified_by_final_state():
    _, _, _, updater = make_updater()
    result = updater.update_working_copy({1: np.nan, 2: 72.0})
    assert ("A", "B", 0) in result.dynamic_edges
    assert result.diagnostics.dynamic_invalid_prediction_edges == 0
    assert result.diagnostics.dynamically_updated_edges == 3


def test_get_static_weights_returns_an_independent_copy():
    _, _, manager, _ = make_updater()
    original = dict(manager.static_weights)
    returned = manager.get_static_weights()
    returned.clear()
    assert manager.static_weights == original
    assert manager.get_static_weights() == original


def test_fractional_segment_ids_are_rejected_safely():
    assert _as_segment_id(1.5) is None
    assert _as_segment_id(float("nan")) is None
    assert _as_segment_id("2.25") is None

    graph, mapping = make_graph_and_mapping()
    mapping["traffic_segment_id"] = mapping["traffic_segment_id"].astype(float)
    mapping.loc[0, "traffic_segment_id"] = 1.5
    with pytest.raises(ValueError, match="Invalid traffic_segment_id"):
        GraphWeightManager(graph, mapping)


def test_conflicting_keys_that_normalize_to_same_segment_id_are_rejected():
    _, _, manager, _ = make_updater()
    with pytest.raises(ValueError, match="Conflicting prediction values.*segment 1"):
        manager.build_scenario_weights({1: 36.0, "1": 40.0})

    # Equal aliases are safely collapsed and contribute only once.
    _, speeds, _ = manager.build_scenario_weights({1: 36.0, "01": 36.0, 2: 72.0})
    assert speeds[("A", "B", 0)] == 54.0


def test_working_graph_is_a_copy_and_source_graph_is_unchanged():
    graph, _, _, updater = make_updater()
    original = deepcopy(dict(graph["A"]["B"][0]))
    result = updater.update_working_copy({1: 40.0})
    assert result.working_graph is not graph
    assert dict(graph["A"]["B"][0]) == original
    assert "travel_time_seconds" not in graph["A"]["B"][0]
    assert result.working_graph["A"]["B"][0]["traffic_cost_source"] == "predicted_speed"


def test_repeated_replay_and_updates_are_deterministic():
    rows = prediction_rows(hours=("2026-01-01 00:00:01+00:00",))
    replay_a = HistoricalTrafficReplay(rows)
    replay_b = HistoricalTrafficReplay(rows)
    frame_a = replay_a.get_frame("2026-01-01T00:00:00Z")
    frame_b = replay_b.get_frame("2026-01-01T00:00:00Z")
    _, _, _, updater = make_updater()
    result_a = updater.update_working_copy(frame_a.predicted_speeds)
    result_b = updater.update_working_copy(frame_b.predicted_speeds)
    assert dict(frame_a.predicted_speeds) == dict(frame_b.predicted_speeds)
    assert dict(result_a.weights) == dict(result_b.weights)
    assert result_a.diagnostics == result_b.diagnostics


def test_cloud_wrapper_replays_exact_frame_and_never_uses_nearest_hour():
    service = CloudModelService()
    message, _ = service.generate_predictions_broadcast("2026-01-15 08:00:00+00:00")
    assert message.origin_timestamp == "2026-01-15T08:00:00+00:00"
    assert message.target_valid_timestamp == "2026-01-15T09:00:00+00:00"
    assert message.total_segments == 700
    with pytest.raises(MissingReplayTimestampError):
        service.generate_predictions_broadcast("2026-01-15 07:00:00+00:00")
