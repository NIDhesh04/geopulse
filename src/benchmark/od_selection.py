"""OD pair selection for large-scale temporal benchmark.

Selects a balanced, deterministic set of origin-destination pairs from the
Bhubaneswar OSM graph using the actual traffic mapping to compute dynamic
coverage per route.

Root-cause fixes relative to the previous broken version:
  1. create_osm_network_scenario() returns a SimulationScenario object, not a
     tuple — the old code destructured it as ``graph, *_ = ...``.
  2. HistoricalTrafficReplay.load_default() does not exist.
  3. Node coordinates are stored as 'y' (lat) / 'x' (lon) in the GraphML,
     not 'lat' / 'lon'.
  4. Enumerating ALL reachable pairs on an 18 k-node graph is O(N^2) and
     infeasible. Instead we sample candidate nodes, check pairwise reachability,
     and compute route statistics only for the sampled pairs.
  5. Dynamic coverage is now computed using GraphWeightManager.dynamic_edge_segments
     (the actual mapping), not via a non-existent HistoricalTrafficReplay method.
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx
import pandas as pd

from src.routing.traffic_weights import GraphWeightManager
from src.routing.dijkstra import custom_dijkstra

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_MAX_PAIRS = 50
DEFAULT_SEED = 42
CANDIDATE_NODES_PER_SAMPLE = 400  # Sample this many nodes for pairing

DISTANCE_BINS: List[Tuple[float, float, str]] = [
    (0, 5_000, "short"),
    (5_000, 15_000, "medium"),
    (15_000, math.inf, "long"),
]

COVERAGE_BINS: List[Tuple[float, float, str]] = [
    (0.0, 0.30, "low"),
    (0.30, 0.70, "medium"),
    (0.70, 1.01, "high"),
]


def _categorise(value: float, bins: List[Tuple[float, float, str]]) -> str:
    for lo, hi, label in bins:
        if lo <= value < hi:
            return label
    return "unknown"


def _route_coverage(
    edge_path: List[Tuple[str, str, Any]],
    dynamic_edges: Set[Tuple[str, str, Any]],
) -> Tuple[int, int, float]:
    """Return (dynamic_count, static_count, coverage_fraction) for a route."""
    if not edge_path:
        return 0, 0, 0.0
    dynamic_count = sum(1 for e in edge_path if e in dynamic_edges)
    static_count = len(edge_path) - dynamic_count
    coverage = dynamic_count / len(edge_path)
    return dynamic_count, static_count, coverage


def select_od_pairs(
    max_pairs: int = DEFAULT_MAX_PAIRS,
    seed: int = DEFAULT_SEED,
    graph_path: str = "data/raw/osm/bhubaneswar_drive.graphml",
    mapping_path: str = "data/processed/traffic_to_osm_mapping_final.parquet",
    output_path: Optional[str] = None,
) -> Tuple[List[Dict], Dict[str, Any]]:
    """Select balanced OD pairs and return (pairs_list, manifest_dict).

    Uses the actual GraphWeightManager to identify which edges have dynamic
    traffic coverage.  Routes are computed with the project's own Dijkstra
    implementation using static highway-class weights.
    """
    rng = random.Random(seed)

    # -- Load graph and weight manager ----------------------------------------
    G = nx.read_graphml(graph_path)
    mapping_df = pd.read_parquet(mapping_path)
    wm = GraphWeightManager(G, mapping_df)

    # Set of edges that have at least one dynamic traffic segment mapped
    dynamic_edge_set: Set[Tuple[str, str, Any]] = set(wm.dynamic_edge_segments.keys())

    # Node coordinates (OSM GraphML stores y=lat, x=lon)
    node_coords: Dict[str, Tuple[float, float]] = {}
    for n, d in G.nodes(data=True):
        node_coords[str(n)] = (float(d.get("y", 0.0)), float(d.get("x", 0.0)))

    all_nodes = list(wm.adjacency.keys())
    print(f"[OD Selection] Graph loaded: {len(all_nodes)} nodes, "
          f"{len(wm.edge_lengths)} edges, "
          f"{len(dynamic_edge_set)} dynamic edges")

    # -- Sample candidate nodes -----------------------------------------------
    sample_size = min(CANDIDATE_NODES_PER_SAMPLE, len(all_nodes))
    candidate_nodes = rng.sample(all_nodes, sample_size)

    # -- Find reachable pairs and compute route stats -------------------------
    static_weights = wm.get_static_weights()
    enriched: List[Dict] = []
    seen_pairs: Set[Tuple[str, str]] = set()

    for i, origin in enumerate(candidate_nodes):
        if len(enriched) >= max_pairs * 10:
            break  # Enough candidates
        for dest in candidate_nodes:
            if origin == dest:
                continue
            if (origin, dest) in seen_pairs:
                continue
            # Quick reachability check via nx (faster than running full Dijkstra)
            if not nx.has_path(G, origin, dest):
                continue

            # Compute shortest path using the project's own Dijkstra
            try:
                result = custom_dijkstra(
                    wm.adjacency, dict(static_weights), origin, dest
                )
            except Exception:
                continue
            if not result.is_reached or not result.edge_path:
                continue

            # Compute route distance
            route_dist = sum(wm.edge_lengths.get(e, 0.0) for e in result.edge_path)
            edge_count = len(result.edge_path)

            # Dynamic coverage on this specific route
            dyn_count, stat_count, coverage = _route_coverage(
                result.edge_path, dynamic_edge_set
            )

            dist_cat = _categorise(route_dist, DISTANCE_BINS)
            cov_cat = _categorise(coverage, COVERAGE_BINS)

            o_lat, o_lon = node_coords.get(origin, (0.0, 0.0))
            d_lat, d_lon = node_coords.get(dest, (0.0, 0.0))

            enriched.append({
                "od_id": len(enriched),
                "origin": origin,
                "destination": dest,
                "origin_lat": o_lat,
                "origin_lon": o_lon,
                "dest_lat": d_lat,
                "dest_lon": d_lon,
                "distance_m": round(route_dist, 2),
                "edge_count": edge_count,
                "dynamic_edges": dyn_count,
                "static_edges": stat_count,
                "coverage": round(coverage, 4),
                "distance_category": dist_cat,
                "coverage_category": cov_cat,
            })
            seen_pairs.add((origin, dest))

    print(f"[OD Selection] Found {len(enriched)} reachable candidate pairs")

    # -- Balanced sampling across 3×3 categories ------------------------------
    buckets: Dict[Tuple[str, str], List[Dict]] = {}
    for item in enriched:
        key = (item["distance_category"], item["coverage_category"])
        buckets.setdefault(key, []).append(item)

    print(f"[OD Selection] Category distribution:")
    for key, items in sorted(buckets.items()):
        print(f"  {key}: {len(items)} pairs")

    selected: List[Dict] = []
    non_empty_buckets = {k: v for k, v in buckets.items() if v}

    if non_empty_buckets:
        bucket_target = max(1, max_pairs // len(non_empty_buckets))
        for key in sorted(non_empty_buckets.keys()):
            bucket_items = non_empty_buckets[key]
            rng.shuffle(bucket_items)
            selected.extend(bucket_items[:bucket_target])

        # Fill remaining capacity
        remaining = max_pairs - len(selected)
        if remaining > 0:
            selected_set = {(s["origin"], s["destination"]) for s in selected}
            leftovers = [
                item for items in non_empty_buckets.values()
                for item in items
                if (item["origin"], item["destination"]) not in selected_set
            ]
            rng.shuffle(leftovers)
            selected.extend(leftovers[:remaining])

    # Trim to exact limit and re-assign sequential OD IDs
    selected = selected[:max_pairs]
    for i, pair in enumerate(selected):
        pair["od_id"] = i

    print(f"[OD Selection] Selected {len(selected)} OD pairs")

    # -- Build manifest -------------------------------------------------------
    manifest = {
        "seed": seed,
        "max_pairs_requested": max_pairs,
        "total_selected": len(selected),
        "graph_path": graph_path,
        "mapping_path": mapping_path,
        "total_graph_nodes": len(all_nodes),
        "total_graph_edges": len(wm.edge_lengths),
        "total_dynamic_edges": len(dynamic_edge_set),
        "candidate_nodes_sampled": sample_size,
        "candidate_pairs_found": len(enriched),
        "category_distribution": {
            f"{k[0]}_{k[1]}": len(v) for k, v in sorted(buckets.items())
        },
        "pairs": selected,
    }

    # Write manifest
    if output_path is None:
        output_path_obj = Path("results") / "benchmark_manifest.json"
    else:
        output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    output_path_obj.write_text(json.dumps(manifest, indent=2))
    print(f"[OD Selection] Manifest written to {output_path_obj}")

    return selected, manifest


if __name__ == "__main__":
    pairs, _ = select_od_pairs()
    print(f"\nSelected {len(pairs)} OD pairs.")
    for p in pairs[:5]:
        print(f"  OD {p['od_id']}: {p['origin']} -> {p['destination']}  "
              f"dist={p['distance_m']:.0f}m  cov={p['coverage']:.1%}  "
              f"[{p['distance_category']}/{p['coverage_category']}]")
