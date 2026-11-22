"""Static and traffic-aware travel-time costs for directed OSM edges."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple
import math

import networkx as nx
import numpy as np
import pandas as pd


EdgeKey = Tuple[str, str, Any]


def get_static_speed_kmh(edge_data: Dict[str, Any]) -> float:
    """Return the existing highway-class fallback speed in km/h."""
    highway = str(edge_data.get("highway", "")).lower()

    if "motorway" in highway or "trunk" in highway:
        return 50.0
    if "primary" in highway:
        return 40.0
    if "secondary" in highway:
        return 30.0
    if "tertiary" in highway:
        return 25.0
    if any(tag in highway for tag in ("residential", "living_street", "unclassified")):
        return 20.0
    return 15.0


def calculate_travel_time_seconds(length_m: float, speed_kmh: float) -> float:
    """Compute kinematic edge time, retaining the project's 3 km/h crawl guard."""
    try:
        length = float(length_m)
        speed = float(speed_kmh)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Edge length and speed must be numeric") from exc

    if not math.isfinite(length) or length <= 0:
        raise ValueError(f"Edge length must be finite and positive; got {length_m!r}")
    if not math.isfinite(speed):
        raise ValueError(f"Speed must be finite; got {speed_kmh!r}")

    clamped_speed = max(speed, 3.0)
    travel_time = length / (clamped_speed * 1000.0 / 3600.0)
    if not math.isfinite(travel_time) or travel_time <= 0:
        raise ValueError("Calculated edge travel time is not finite and positive")
    return travel_time


def _finite_positive_speed(value: Any) -> Optional[float]:
    """Return a valid positive speed or None; invalid values use static costs."""
    try:
        speed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(speed) or speed <= 0:
        return None
    return float(np.clip(speed, 3.0, 120.0))


def _as_segment_id(value: Any) -> Optional[int]:
    try:
        numeric = Decimal(str(value).strip())
        if not numeric.is_finite() or numeric != numeric.to_integral_value():
            return None
        return int(numeric)
    except (InvalidOperation, TypeError, ValueError, OverflowError):
        return None


def _canonical_prediction_value(value: Any) -> Tuple[str, Any]:
    """Normalize equivalent speed values for duplicate segment-ID detection."""
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return ("non_numeric", type(value).__qualname__, repr(value))
    if math.isnan(numeric):
        return ("nan", None)
    if math.isinf(numeric):
        return ("infinity", 1 if numeric > 0 else -1)
    return ("finite", numeric)


def _normalize_segment_speeds(segment_speeds: Mapping[int, Any]) -> Dict[int, Any]:
    """Normalize segment keys and reject conflicting aliases deterministically.

    Invalid segment IDs are ignored. Distinct keys that normalize to one ID are
    accepted only when their speed values have the same canonical value.
    """
    normalized: Dict[int, Any] = {}
    canonical_values: Dict[int, Tuple[str, Any]] = {}
    original_keys: Dict[int, Any] = {}
    for raw_segment_id, speed in segment_speeds.items():
        segment_id = _as_segment_id(raw_segment_id)
        if segment_id is None:
            continue
        canonical = _canonical_prediction_value(speed)
        if segment_id in canonical_values:
            if canonical_values[segment_id] != canonical:
                raise ValueError(
                    "Conflicting prediction values for normalized traffic segment "
                    f"{segment_id}: keys {original_keys[segment_id]!r} and "
                    f"{raw_segment_id!r}"
                )
            continue
        normalized[segment_id] = speed
        canonical_values[segment_id] = canonical
        original_keys[segment_id] = raw_segment_id
    return normalized


@dataclass(frozen=True)
class TrafficCoverageDiagnostics:
    """Disjoint final edge classifications plus aggregate fallback totals."""
    total_directed_edges: int
    dynamically_updated_edges: int
    static_fallback_edges: int
    unmapped_edges: int
    missing_predictions: int
    invalid_predictions: int
    dynamic_coverage_pct: float
    origin_timestamp: Optional[str]
    target_valid_timestamp: Optional[str]
    explicit_static_fallback_edges: int = 0
    dynamic_missing_prediction_edges: int = 0
    dynamic_invalid_prediction_edges: int = 0
    invalid_mapping_references: int = 0
    ignored_prediction_segments: int = 0

    @property
    def mapped_static_fallback_edges(self) -> int:
        """Compatibility alias for explicitly static edges in the final partition."""
        return self.explicit_static_fallback_edges

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_directed_edges": self.total_directed_edges,
            "dynamically_updated_edges": self.dynamically_updated_edges,
            "static_fallback_edges": self.static_fallback_edges,
            "unmapped_edges": self.unmapped_edges,
            "missing_predictions": self.missing_predictions,
            "invalid_predictions": self.invalid_predictions,
            "dynamic_coverage_pct": self.dynamic_coverage_pct,
            "origin_timestamp": self.origin_timestamp,
            "target_valid_timestamp": self.target_valid_timestamp,
            "explicit_static_fallback_edges": self.explicit_static_fallback_edges,
            # Legacy key retained as an alias; it is not a separate category.
            "mapped_static_fallback_edges": self.explicit_static_fallback_edges,
            "dynamic_missing_prediction_edges": self.dynamic_missing_prediction_edges,
            "dynamic_invalid_prediction_edges": self.dynamic_invalid_prediction_edges,
            "invalid_mapping_references": self.invalid_mapping_references,
            "ignored_prediction_segments": self.ignored_prediction_segments,
        }


@dataclass(frozen=True)
class TrafficEdgeCostUpdate:
    """New edge weights and an independently mutable graph copy."""
    working_graph: nx.MultiDiGraph
    weights: Mapping[EdgeKey, float]
    speeds_kmh: Mapping[EdgeKey, float]
    dynamic_edges: Set[EdgeKey]
    diagnostics: TrafficCoverageDiagnostics


class GraphWeightManager:
    """Cache graph edge lengths, static costs, and directed sensor mappings."""

    REQUIRED_MAPPING_COLUMNS = {
        "traffic_segment_id", "u", "v", "key", "routing_eligibility"
    }
    DYNAMIC_ELIGIBILITY = {"DYNAMIC", "DYNAMIC_BIDIRECTIONAL"}

    def __init__(self, G: nx.MultiDiGraph, mapping_df: pd.DataFrame):
        self.G = G
        self.mapping_df = mapping_df.copy()
        missing_columns = self.REQUIRED_MAPPING_COLUMNS - set(self.mapping_df.columns)
        if missing_columns:
            raise ValueError(f"Traffic mapping lacks required columns: {sorted(missing_columns)}")

        self.adjacency: Dict[str, List[Tuple[str, Any]]] = {}
        self.edge_lengths: Dict[EdgeKey, float] = {}
        self.edge_static_speeds: Dict[EdgeKey, float] = {}
        self.static_weights: Dict[EdgeKey, float] = {}
        self._edge_lookup: Dict[Tuple[str, str, str], EdgeKey] = {}
        self.graph_node_ids: Dict[str, Any] = {str(node): node for node in G.nodes}
        self.segment_policy: Dict[int, List[Dict[str, Any]]] = {}
        self.mapped_edges: Set[EdgeKey] = set()
        self.explicit_static_edges: Set[EdgeKey] = set()
        self.dynamic_segment_ids: Set[int] = set()
        self.dynamic_edge_segments: Dict[EdgeKey, Set[int]] = {}
        self.invalid_mapping_references: List[Tuple[int, str, str, Any]] = []

        self._init_graph_topology()
        self._init_mapping_lookup()

    def _init_graph_topology(self) -> None:
        """Precompute all existing graph edges and finite static fallback costs."""
        for u, v, key, data in self.G.edges(data=True, keys=True):
            u_str, v_str = str(u), str(v)
            raw_length = data.get("length", 10.0)
            try:
                length_m = float(raw_length)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(f"Invalid OSM length for edge {(u_str, v_str, key)}") from exc
            if not math.isfinite(length_m) or length_m <= 0:
                raise ValueError(
                    f"OSM edge {(u_str, v_str, key)} length must be finite and positive; "
                    f"got {raw_length!r}"
                )

            edge = (u_str, v_str, key)
            static_speed = get_static_speed_kmh(data)
            static_time = calculate_travel_time_seconds(length_m, static_speed)
            self.adjacency.setdefault(u_str, []).append((v_str, key))
            self.edge_lengths[edge] = length_m
            self.edge_static_speeds[edge] = static_speed
            self.static_weights[edge] = static_time
            lookup_key = (u_str, v_str, str(key))
            if lookup_key in self._edge_lookup:
                raise ValueError(f"Graph edge keys are ambiguous after string conversion: {lookup_key}")
            self._edge_lookup[lookup_key] = edge

    def _resolve_edge(self, u: str, v: str, raw_key: Any) -> Optional[EdgeKey]:
        """Resolve Parquet integer keys against the graph's key representation."""
        return self._edge_lookup.get((u, v, str(raw_key)))

    def _reverse_edges(self, u: str, v: str) -> List[EdgeKey]:
        return sorted(
            (edge for edge in self.edge_lengths if edge[0] == v and edge[1] == u),
            key=lambda edge: str(edge[2]),
        )

    def _init_mapping_lookup(self) -> None:
        """Keep every unique mapping row; duplicate sensors on one edge aggregate later."""
        seen = set()
        for _, row in self.mapping_df.iterrows():
            segment_id = _as_segment_id(row["traffic_segment_id"])
            if segment_id is None:
                raise ValueError(f"Invalid traffic_segment_id in mapping: {row['traffic_segment_id']!r}")
            eligibility = str(row["routing_eligibility"]).strip().upper()
            if eligibility not in self.DYNAMIC_ELIGIBILITY | {"STATIC_FALLBACK"}:
                raise ValueError(f"Unknown routing_eligibility {eligibility!r} for segment {segment_id}")

            u, v = str(row["u"]), str(row["v"])
            edge = self._resolve_edge(u, v, row["key"])
            identity = (segment_id, edge, eligibility, u, v, str(row["key"]))
            if identity in seen:
                continue
            seen.add(identity)

            if edge is None:
                self.invalid_mapping_references.append((segment_id, u, v, row["key"]))
            else:
                self.mapped_edges.add(edge)
                if eligibility == "STATIC_FALLBACK":
                    self.explicit_static_edges.add(edge)

            targets: List[EdgeKey] = []
            if edge is not None and eligibility in self.DYNAMIC_ELIGIBILITY:
                targets.append(edge)
                if eligibility == "DYNAMIC_BIDIRECTIONAL":
                    targets.extend(self._reverse_edges(u, v))
                self.dynamic_segment_ids.add(segment_id)
                self.mapped_edges.update(targets)
                for target in targets:
                    self.dynamic_edge_segments.setdefault(target, set()).add(segment_id)

            policy = {
                "eligibility": eligibility,
                "directed_edge": edge,
                "dynamic_edges": tuple(dict.fromkeys(targets)),
            }
            policies = self.segment_policy.setdefault(segment_id, [])
            if policy not in policies:
                policies.append(policy)

    def get_static_weights(self) -> Dict[EdgeKey, float]:
        """Return static highway-class costs for all directed edges."""
        return dict(self.static_weights)

    def build_scenario_weights(
        self,
        segment_speeds: Mapping[int, Any],
    ) -> Tuple[Dict[EdgeKey, float], Dict[EdgeKey, float], Set[EdgeKey]]:
        """Create dynamic costs, averaging valid mapped sensors per directed edge.

        A sensor's speed is validated and clipped to the model's 3-120 km/h range
        before aggregation. Invalid or absent speeds leave the edge at its static
        fallback cost. Exact duplicate mapping rows and duplicate sensor assignments
        cannot overweight an edge.
        """
        normalized_speeds = _normalize_segment_speeds(segment_speeds)
        edge_candidate_speeds: Dict[EdgeKey, Dict[int, float]] = {}
        for segment_id, raw_speed in normalized_speeds.items():
            speed = _finite_positive_speed(raw_speed)
            if speed is None:
                continue
            for policy in self.segment_policy.get(segment_id, []):
                if policy["eligibility"] not in self.DYNAMIC_ELIGIBILITY:
                    continue
                for edge in policy["dynamic_edges"]:
                    # One segment contributes no more than once to each edge.
                    edge_candidate_speeds.setdefault(edge, {})[segment_id] = speed

        weights = dict(self.static_weights)
        speeds = dict(self.edge_static_speeds)
        dynamic_edges: Set[EdgeKey] = set()
        for edge, by_segment in edge_candidate_speeds.items():
            if edge not in self.edge_lengths or not by_segment:
                continue
            mean_speed = float(np.mean([by_segment[sid] for sid in sorted(by_segment)]))
            length_m = self.edge_lengths[edge]
            travel_time = calculate_travel_time_seconds(length_m, mean_speed)
            weights[edge] = travel_time
            speeds[edge] = mean_speed
            dynamic_edges.add(edge)

        if any(not math.isfinite(float(value)) or float(value) <= 0 for value in weights.values()):
            raise RuntimeError("Scenario produced a non-finite or non-positive edge cost")
        return weights, speeds, dynamic_edges


class TrafficEdgeCostUpdater:
    """Apply replay predictions to a working graph and expose coverage diagnostics."""

    def __init__(self, weight_manager: GraphWeightManager):
        self.weight_manager = weight_manager

    @staticmethod
    def _timestamp_text(value: Any) -> Optional[str]:
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    def update_working_copy(
        self,
        segment_speeds: Mapping[int, Any],
        origin_timestamp: Any = None,
        target_valid_timestamp: Any = None,
    ) -> TrafficEdgeCostUpdate:
        """Return a graph copy with finite `travel_time_seconds` on every edge.

        The source graph is not modified. Unmapped edges and edges whose mapped
        predictions are absent or invalid retain their static fallback weights.
        """
        manager = self.weight_manager
        normalized_speeds = _normalize_segment_speeds(segment_speeds)
        weights, speeds, dynamic_edges = manager.build_scenario_weights(normalized_speeds)
        graph_copy = manager.G.copy(as_view=False)

        for u, v, key in manager.edge_lengths:
            edge = (u, v, key)
            weight = float(weights[edge])
            speed = float(speeds[edge])
            if not math.isfinite(weight) or weight <= 0 or not math.isfinite(speed) or speed <= 0:
                raise RuntimeError(f"Invalid final edge state for {edge}: speed={speed}, time={weight}")
            graph_u = manager.graph_node_ids[u]
            graph_v = manager.graph_node_ids[v]
            edge_data = graph_copy[graph_u][graph_v][key]
            edge_data["travel_time_seconds"] = weight
            edge_data["effective_speed_kmh"] = speed
            edge_data["traffic_cost_source"] = (
                "predicted_speed" if edge in dynamic_edges else "static_fallback"
            )

        total_edges = len(manager.edge_lengths)
        graph_edges = set(manager.edge_lengths)
        unmapped_edge_set = graph_edges - manager.mapped_edges
        dynamic_eligible_edges = set(manager.dynamic_edge_segments)
        dynamic_fallback_edges = dynamic_eligible_edges - dynamic_edges
        expected_segments = manager.dynamic_segment_ids
        present_segments = set(normalized_speeds)
        missing_segment_ids = expected_segments - present_segments
        invalid_segment_ids = {
            segment_id for segment_id in expected_segments & present_segments
            if _finite_positive_speed(normalized_speeds[segment_id]) is None
        }
        dynamic_invalid_edge_set = {
            edge for edge in dynamic_fallback_edges
            if manager.dynamic_edge_segments[edge] & invalid_segment_ids
        }
        # Invalid takes precedence when one failed sensor and one absent sensor
        # both map to the same non-updated edge. A valid contributing sensor has
        # already made the edge dynamic, so its final state takes precedence.
        dynamic_missing_edge_set = dynamic_fallback_edges - dynamic_invalid_edge_set
        explicit_static_edge_set = (
            manager.explicit_static_edges - dynamic_eligible_edges - dynamic_edges
        )
        classified_edge_sets = (
            set(dynamic_edges),
            explicit_static_edge_set,
            unmapped_edge_set,
            dynamic_missing_edge_set,
            dynamic_invalid_edge_set,
        )
        classified_count = sum(len(edge_set) for edge_set in classified_edge_sets)
        if classified_count != total_edges or set().union(*classified_edge_sets) != graph_edges:
            raise RuntimeError("Traffic edge diagnostic categories do not partition the graph")

        static_edges = total_edges - len(dynamic_edges)
        missing_predictions = len(missing_segment_ids)
        invalid_predictions = len(invalid_segment_ids)
        ignored_predictions = len(present_segments - set(manager.segment_policy))
        diagnostics = TrafficCoverageDiagnostics(
            total_directed_edges=total_edges,
            dynamically_updated_edges=len(dynamic_edges),
            static_fallback_edges=static_edges,
            unmapped_edges=len(unmapped_edge_set),
            missing_predictions=missing_predictions,
            invalid_predictions=invalid_predictions,
            dynamic_coverage_pct=(100.0 * len(dynamic_edges) / total_edges) if total_edges else 0.0,
            origin_timestamp=self._timestamp_text(origin_timestamp),
            target_valid_timestamp=self._timestamp_text(target_valid_timestamp),
            explicit_static_fallback_edges=len(explicit_static_edge_set),
            dynamic_missing_prediction_edges=len(dynamic_missing_edge_set),
            dynamic_invalid_prediction_edges=len(dynamic_invalid_edge_set),
            invalid_mapping_references=len(manager.invalid_mapping_references),
            ignored_prediction_segments=ignored_predictions,
        )
        return TrafficEdgeCostUpdate(
            working_graph=graph_copy,
            weights=weights,
            speeds_kmh=speeds,
            dynamic_edges=dynamic_edges,
            diagnostics=diagnostics,
        )
