"""Deterministic OD selection and coordinate snapping for GeoPulse Stage 3.

Provides:
  1. Geographic coordinate validation and latitude-scaled KD-tree snapping
     (measured in metres) onto directed OSM graph nodes.
  2. Balanced, reproducible OD pair selection across distance categories
     (short / medium / long) and real route-level dynamic traffic coverage
     categories (low / medium / high) using single-source Dijkstra trees.
"""

from __future__ import annotations

import heapq
import json
import math
import random
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import networkx as nx
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from src.routing.traffic_weights import GraphWeightManager

DEFAULT_MAX_PAIRS = 50
DEFAULT_SEED = 42
DEFAULT_MAX_SNAP_METERS = 250.0
EARTH_RADIUS_M = 6_371_000.0
MIN_ROUTE_EDGES = 3
MIN_ROUTE_DISTANCE_M = 500.0

DISTANCE_BINS: List[Tuple[float, float, str]] = [
    (0.0, 5_000.0, "short"),
    (5_000.0, 15_000.0, "medium"),
    (15_000.0, math.inf, "long"),
]

COVERAGE_BINS: List[Tuple[float, float, str]] = [
    (0.0, 30.0, "low"),
    (30.0, 70.0, "medium"),
    (70.0, 100.0001, "high"),
]


def _categorise(value: float, bins: List[Tuple[float, float, str]]) -> str:
    for lo, hi, label in bins:
        if lo <= value < hi:
            return label
    return "unknown"


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute exact great-circle distance in metres between two WGS84 points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


class SpatialNodeIndex:
    """Equirectangular metric KD-tree index over directed graph nodes."""

    def __init__(self, node_coords: Dict[str, Tuple[float, float]]) -> None:
        if not node_coords:
            raise ValueError("Cannot build SpatialNodeIndex from empty node coordinates")
        self.node_ids: List[str] = sorted(node_coords.keys())
        lats = np.array([node_coords[n][0] for n in self.node_ids], dtype=float)
        lons = np.array([node_coords[n][1] for n in self.node_ids], dtype=float)
        self.node_coords = dict(node_coords)
        self.ref_lat_rad = math.radians(float(np.mean(lats)))
        self.cos_ref = max(1e-6, math.cos(self.ref_lat_rad))
        coords_m = self._project_arr(lats, lons)
        self._tree = cKDTree(coords_m)

    def _project_arr(self, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
        lon_m = np.radians(lon) * EARTH_RADIUS_M * self.cos_ref
        lat_m = np.radians(lat) * EARTH_RADIUS_M
        return np.column_stack((lon_m, lat_m))

    def project(self, lat: float, lon: float) -> Tuple[float, float]:
        lon_m = math.radians(lon) * EARTH_RADIUS_M * self.cos_ref
        lat_m = math.radians(lat) * EARTH_RADIUS_M
        return lon_m, lat_m

    def snap(
        self,
        lat: float,
        lon: float,
        max_snap_distance_m: float = DEFAULT_MAX_SNAP_METERS,
    ) -> Tuple[str, float]:
        """Snap validated (lat, lon) to nearest graph node and verify metre distance."""
        validate_lat_lon(lat, lon)
        if not math.isfinite(max_snap_distance_m) or max_snap_distance_m <= 0:
            raise ValueError(f"max_snap_distance_m must be finite and positive; got {max_snap_distance_m!r}")
        qx, qy = self.project(lat, lon)
        _, idx = self._tree.query([qx, qy], k=1)
        node_id = self.node_ids[int(idx)]
        n_lat, n_lon = self.node_coords[node_id]
        exact_m = haversine_distance_m(lat, lon, n_lat, n_lon)
        if exact_m > max_snap_distance_m:
            raise ValueError(
                f"Coordinate ({lat:.6f}, {lon:.6f}) is {exact_m:.1f}m from nearest node "
                f"{node_id}, exceeding limit {max_snap_distance_m:.1f}m"
            )
        return node_id, exact_m


def validate_lat_lon(lat: float, lon: float) -> Tuple[float, float]:
    """Validate finite geographic coordinates within WGS84 bounds."""
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"Non-numeric coordinates: ({lat!r}, {lon!r})") from exc
    if not (math.isfinite(lat_f) and math.isfinite(lon_f)):
        raise ValueError(f"Non-finite coordinates rejected: ({lat!r}, {lon!r})")
    if not (-90.0 <= lat_f <= 90.0) or not (-180.0 <= lon_f <= 180.0):
        raise ValueError(f"Out-of-range coordinates rejected: lat={lat_f}, lon={lon_f}")
    return lat_f, lon_f


_COORD_RE = re.compile(r"^\s*([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?|nan|inf|-inf)\s*,\s*([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?|nan|inf|-inf)\s*$", re.IGNORECASE)


def parse_od_input(
    raw_value: str,
    spatial_index: SpatialNodeIndex,
    max_snap_distance_m: float = DEFAULT_MAX_SNAP_METERS,
) -> Dict[str, Any]:
    """Parse either an OSM node ID or `lat, lon` coordinate string."""
    text = str(raw_value).strip()
    if not text:
        raise ValueError("OD location input cannot be empty")
    if "," in text:
        parts = [p.strip() for p in text.split(",")]
        if len(parts) != 2:
            raise ValueError(f"Expected 'lat, lon' coordinate format, got {raw_value!r}")
        lat, lon = validate_lat_lon(parts[0], parts[1])
        node_id, snap_m = spatial_index.snap(lat, lon, max_snap_distance_m=max_snap_distance_m)
        return {
            "input_type": "coordinates",
            "node_id": node_id,
            "input_lat": lat,
            "input_lon": lon,
            "snap_distance_m": snap_m,
        }
    if text not in spatial_index.node_coords:
        raise ValueError(f"OSM node ID {text!r} does not exist in road graph")
    lat, lon = spatial_index.node_coords[text]
    return {
        "input_type": "node_id",
        "node_id": text,
        "input_lat": lat,
        "input_lon": lon,
        "snap_distance_m": 0.0,
    }


def _single_source_dijkstra_tree(
    adjacency: Dict[str, List[Tuple[str, Any]]],
    edge_weights: Dict[Tuple[str, str, Any], float],
    source: str,
) -> Tuple[Dict[str, float], Dict[str, Tuple[str, Any]]]:
    """Compute shortest-path tree from source using the project's edge weights."""
    dist: Dict[str, float] = {source: 0.0}
    pred: Dict[str, Tuple[str, Any]] = {}
    pq: List[Tuple[float, str]] = [(0.0, source)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, float("inf")):
            continue
        for v, key in adjacency.get(u, ()):
            w = float(edge_weights.get((u, v, key), float("inf")))
            if w <= 0.0:
                w = 1e-4
            nd = d + w
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                pred[v] = (u, key)
                heapq.heappush(pq, (nd, v))
    return dist, pred


def _reconstruct_edge_path(
    source: str,
    target: str,
    pred: Dict[str, Tuple[str, Any]],
) -> List[Tuple[str, str, Any]]:
    edges: List[Tuple[str, str, Any]] = []
    curr = target
    while curr != source:
        if curr not in pred:
            return []
        pu, key = pred[curr]
        edges.append((pu, curr, key))
        curr = pu
    edges.reverse()
    return edges


def _route_coverage(
    edge_path: Sequence[Tuple[str, str, Any]],
    dynamic_edges: Set[Tuple[str, str, Any]],
) -> Tuple[int, int, float]:
    if not edge_path:
        return 0, 0, 0.0
    dyn = sum(1 for e in edge_path if e in dynamic_edges)
    stat = len(edge_path) - dyn
    pct = 100.0 * dyn / len(edge_path)
    return dyn, stat, pct


def select_od_pairs(
    max_pairs: int = DEFAULT_MAX_PAIRS,
    seed: int = DEFAULT_SEED,
    graph_path: str = "data/raw/osm/bhubaneswar_drive.graphml",
    mapping_path: str = "data/processed/traffic_to_osm_mapping_final.parquet",
    output_csv_path: Optional[str] = None,
    weight_manager: Optional[GraphWeightManager] = None,
    graph: Optional[nx.MultiDiGraph] = None,
    monitored_origin_sample: int = 90,
    general_origin_sample: int = 30,
    monitored_target_sample: int = 200,
    general_target_sample: int = 120,
    max_estimated_travel_time_s: Optional[float] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Select balanced, reachable OD pairs using actual graph and traffic mapping.

    Returns ``(selected_pairs, selection_metadata)`` where each selected pair
    contains full topology, coordinate, distance, and coverage fields.
    """
    if max_pairs <= 0:
        raise ValueError(f"max_pairs must be positive; got {max_pairs!r}")

    rng = random.Random(seed)
    G = graph if graph is not None else nx.read_graphml(graph_path)
    if not isinstance(G, nx.MultiDiGraph):
        G = nx.MultiDiGraph(G)
    if weight_manager is None:
        mapping_df = pd.read_parquet(mapping_path)
        wm = GraphWeightManager(G, mapping_df)
    else:
        wm = weight_manager

    dynamic_edge_set: Set[Tuple[str, str, Any]] = set(wm.dynamic_edge_segments.keys())
    node_coords: Dict[str, Tuple[float, float]] = {
        str(n): (float(d.get("y", d.get("lat", 0.0))), float(d.get("x", d.get("lon", 0.0))))
        for n, d in G.nodes(data=True)
    }

    # Build strongly connected component lookup for reachability filtering
    sccs = list(nx.strongly_connected_components(G))
    largest_scc_raw = max(sccs, key=len) if sccs else set()
    largest_scc: Set[str] = {str(n) for n in largest_scc_raw}

    all_nodes = sorted(wm.adjacency.keys())
    scc_nodes = sorted(n for n in all_nodes if n in largest_scc)
    monitored_nodes = sorted(
        ({str(u) for u, _, _ in dynamic_edge_set} | {str(v) for _, v, _ in dynamic_edge_set})
        & set(scc_nodes)
    )
    non_monitored_scc = sorted(set(scc_nodes) - set(monitored_nodes))

    # Deterministic sampling of origins and targets across monitored and unmapped corridors
    sampled_origins: List[str] = []
    if monitored_nodes:
        sampled_origins.extend(rng.sample(monitored_nodes, min(monitored_origin_sample, len(monitored_nodes))))
    if non_monitored_scc:
        sampled_origins.extend(rng.sample(non_monitored_scc, min(general_origin_sample, len(non_monitored_scc))))
    elif len(sampled_origins) < min(len(scc_nodes), monitored_origin_sample + general_origin_sample):
        remaining_scc = [n for n in scc_nodes if n not in set(sampled_origins)]
        sampled_origins.extend(rng.sample(remaining_scc, min(general_origin_sample, len(remaining_scc))))

    sampled_targets: List[str] = []
    if monitored_nodes:
        sampled_targets.extend(rng.sample(monitored_nodes, min(monitored_target_sample, len(monitored_nodes))))
    if non_monitored_scc:
        sampled_targets.extend(rng.sample(non_monitored_scc, min(general_target_sample, len(non_monitored_scc))))
    elif len(sampled_targets) < min(len(scc_nodes), monitored_target_sample + general_target_sample):
        remaining_scc = [n for n in scc_nodes if n not in set(sampled_targets)]
        sampled_targets.extend(rng.sample(remaining_scc, min(general_target_sample, len(remaining_scc))))

    # Deduplicate while preserving deterministic order
    sampled_origins = list(dict.fromkeys(sampled_origins))
    sampled_targets = list(dict.fromkeys(sampled_targets))

    # If the graph is tiny (e.g., synthetic unit-test graph), include all nodes
    if len(all_nodes) <= 200:
        sampled_origins = list(all_nodes)
        sampled_targets = list(all_nodes)

    static_weights = wm.get_static_weights()
    rejection_counts: Dict[str, int] = {
        "self_pair": 0,
        "unreachable": 0,
        "empty_or_too_short_route": 0,
        "exceeds_horizon": 0,
        "duplicate_pair": 0,
    }
    rejection_examples: List[Dict[str, Any]] = []

    def _log_rejection(origin: str, dest: str, reason: str) -> None:
        rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
        if len(rejection_examples) < 50:
            rejection_examples.append({"origin": origin, "destination": dest, "reason": reason})

    candidates: List[Dict[str, Any]] = []
    seen_pairs: Set[Tuple[str, str]] = set()
    min_edges_required = MIN_ROUTE_EDGES if len(all_nodes) > 20 else 1
    min_dist_required = MIN_ROUTE_DISTANCE_M if len(all_nodes) > 20 else 0.0

    for origin in sampled_origins:
        dist_map, pred_map = _single_source_dijkstra_tree(wm.adjacency, static_weights, origin)
        o_lat, o_lon = node_coords.get(origin, (0.0, 0.0))

        for dest in sampled_targets:
            if origin == dest:
                _log_rejection(origin, dest, "self_pair")
                continue
            if (origin, dest) in seen_pairs:
                _log_rejection(origin, dest, "duplicate_pair")
                continue
            if dest not in pred_map:
                _log_rejection(origin, dest, "unreachable")
                continue

            edge_path = _reconstruct_edge_path(origin, dest, pred_map)
            route_dist_m = sum(wm.edge_lengths.get(e, 0.0) for e in edge_path)
            est_time_s = float(dist_map[dest])
            edge_count = len(edge_path)

            if edge_count < min_edges_required or route_dist_m < min_dist_required:
                _log_rejection(origin, dest, "empty_or_too_short_route")
                continue
            if max_estimated_travel_time_s is not None and est_time_s > max_estimated_travel_time_s:
                _log_rejection(origin, dest, "exceeds_horizon")
                continue

            dyn_count, stat_count, cov_pct = _route_coverage(edge_path, dynamic_edge_set)
            d_lat, d_lon = node_coords.get(dest, (0.0, 0.0))

            candidates.append({
                "origin_node": origin,
                "destination_node": dest,
                "origin_lat": round(o_lat, 7),
                "origin_lon": round(o_lon, 7),
                "destination_lat": round(d_lat, 7),
                "destination_lon": round(d_lon, 7),
                "shortest_path_distance_m": round(route_dist_m, 2),
                "estimated_travel_time_s": round(est_time_s, 2),
                "route_edge_count": edge_count,
                "dynamic_mapped_edge_count": dyn_count,
                "static_fallback_edge_count": stat_count,
                "dynamic_coverage_pct": round(cov_pct, 2),
                "coverage_fraction": round(cov_pct / 100.0, 4),
                "distance_category": _categorise(route_dist_m, DISTANCE_BINS),
                "coverage_category": _categorise(cov_pct, COVERAGE_BINS),
                "reachable": True,
            })
            seen_pairs.add((origin, dest))

    # Stratify deterministically into distance x coverage buckets
    buckets: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for item in candidates:
        key = (item["distance_category"], item["coverage_category"])
        buckets.setdefault(key, []).append(item)

    selected: List[Dict[str, Any]] = []
    selected_keys: Set[Tuple[str, str]] = set()
    bucket_order = sorted(buckets.keys())

    # Shuffle deterministically within each bucket (sorted beforehand for seed stability)
    for key in bucket_order:
        buckets[key].sort(key=lambda r: (r["origin_node"], r["destination_node"]))
        rng.shuffle(buckets[key])

    # Round-robin across non-empty buckets so every populated cell gets fair share
    bucket_cursors = {key: 0 for key in bucket_order}
    while len(selected) < max_pairs:
        progressed = False
        for key in bucket_order:
            if len(selected) >= max_pairs:
                break
            idx = bucket_cursors[key]
            items = buckets[key]
            while idx < len(items):
                cand = items[idx]
                idx += 1
                pair_key = (cand["origin_node"], cand["destination_node"])
                if pair_key not in selected_keys:
                    selected.append(dict(cand))
                    selected_keys.add(pair_key)
                    progressed = True
                    break
            bucket_cursors[key] = idx
        if not progressed:
            break

    # Assign deterministic sequential od_id
    for od_id, pair in enumerate(selected):
        pair["od_id"] = od_id

    # Compute final category tallies
    dist_dist: Dict[str, int] = {}
    cov_dist: Dict[str, int] = {}
    cell_dist: Dict[str, int] = {}
    for p in selected:
        dist_dist[p["distance_category"]] = dist_dist.get(p["distance_category"], 0) + 1
        cov_dist[p["coverage_category"]] = cov_dist.get(p["coverage_category"], 0) + 1
        cell = f"{p['distance_category']}_{p['coverage_category']}"
        cell_dist[cell] = cell_dist.get(cell, 0) + 1

    if output_csv_path is not None:
        csv_path = Path(output_csv_path)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(selected).to_csv(csv_path, index=False)

    metadata = {
        "seed": seed,
        "max_pairs_requested": max_pairs,
        "selected_count": len(selected),
        "graph_path": graph_path,
        "mapping_path": mapping_path,
        "graph_nodes": G.number_of_nodes(),
        "graph_directed_edges": G.number_of_edges(),
        "largest_scc_nodes": len(largest_scc),
        "dynamic_mapped_edges_total": len(dynamic_edge_set),
        "monitored_scc_nodes": len(monitored_nodes),
        "sampled_origins": len(sampled_origins),
        "sampled_targets": len(sampled_targets),
        "candidate_pairs_valid": len(candidates),
        "rejection_counts": rejection_counts,
        "rejection_examples": rejection_examples[:20],
        "selected_distance_distribution": dist_dist,
        "selected_coverage_distribution": cov_dist,
        "selected_cell_distribution": cell_dist,
        "candidate_cell_distribution": {
            f"{k[0]}_{k[1]}": len(v) for k, v in sorted(buckets.items())
        },
    }
    return selected, metadata


if __name__ == "__main__":
    pairs, meta = select_od_pairs(output_csv_path="results/stage3_od_preview.csv")
    print(f"Selected {len(pairs)} OD pairs in seed={meta['seed']}")
    print("Distance distribution:", meta["selected_distance_distribution"])
    print("Coverage distribution:", meta["selected_coverage_distribution"])
    print("Cell distribution:", meta["selected_cell_distribution"])
    print("Rejection counts:", meta["rejection_counts"])
