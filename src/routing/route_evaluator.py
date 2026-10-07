"""
GeoPulse Route Evaluation Engine

Evaluates Static, Current-Traffic (Oracle), and ML-Predicted routing scenarios
for given OD pairs and timestamps, computing physical kinematics, oracle regret,
dynamic edge coverage, and route overlap.
"""

from typing import Dict, List, Tuple, Set, Any
import numpy as np
import pandas as pd
from src.routing.dijkstra import custom_dijkstra, DijkstraResult
from src.routing.traffic_weights import GraphWeightManager


def compute_edge_jaccard_overlap(
    edge_path_a: List[Tuple[str, str, int]],
    edge_path_b: List[Tuple[str, str, int]]
) -> float:
    """
    Calculate edge-level Jaccard similarity between two routes.
    J(A, B) = |A ∩ B| / |A ∪ B|. Returns 1.0 if identical, 0.0 if disjoint.
    """
    set_a = set(edge_path_a)
    set_b = set(edge_path_b)
    union_len = len(set_a | set_b)
    if union_len == 0:
        return 1.0
    return len(set_a & set_b) / union_len


def evaluate_od_timestamp(
    od_id: int,
    source: str,
    target: str,
    timestamp: Any,
    ist_timestamp: Any,
    period_label: str,
    is_peak: int,
    weight_manager: GraphWeightManager,
    current_weights: Dict[Tuple[str, str, int], float],
    predicted_weights: Dict[Tuple[str, str, int], float],
    dynamic_edges_set: Set[Tuple[str, str, int]]
) -> Dict[str, Any]:
    """
    Run the 3 routing scenarios and evaluate their performance under actual observed traffic.
    """
    static_weights = weight_manager.get_static_weights()

    # 1. SCENARIO A: Static Routing
    res_static = custom_dijkstra(weight_manager.adjacency, static_weights, source, target)

    # 2. SCENARIO B: Current-Traffic Routing (Oracle Benchmark)
    res_current = custom_dijkstra(weight_manager.adjacency, current_weights, source, target)

    # 3. SCENARIO C: ML-Predicted Routing (Decision based strictly on predicted weights)
    res_ml = custom_dijkstra(weight_manager.adjacency, predicted_weights, source, target)

    if not (res_static.is_reached and res_current.is_reached and res_ml.is_reached):
        raise ValueError(f"Unreachable route encountered for OD #{od_id} ({source} -> {target})")

    # Evaluate all paths on the SAME actual/observed traffic state
    static_actual_time = sum(current_weights.get(e, 0.0) for e in res_static.edge_path)
    current_actual_time = sum(current_weights.get(e, 0.0) for e in res_current.edge_path)
    ml_actual_time = sum(current_weights.get(e, 0.0) for e in res_ml.edge_path)

    # Predicted time is the model's anticipation of travel time
    ml_predicted_time = sum(predicted_weights.get(e, 0.0) for e in res_ml.edge_path)

    # Route distances
    static_dist = sum(weight_manager.edge_lengths.get(e, 0.0) for e in res_static.edge_path)
    current_dist = sum(weight_manager.edge_lengths.get(e, 0.0) for e in res_current.edge_path)
    ml_dist = sum(weight_manager.edge_lengths.get(e, 0.0) for e in res_ml.edge_path)

    # Edge counts and dynamic coverage
    ml_total_edges = len(res_ml.edge_path)
    ml_dyn_edges = sum(1 for e in res_ml.edge_path if e in dynamic_edges_set)
    ml_static_edges = ml_total_edges - ml_dyn_edges
    ml_dyn_fraction = ml_dyn_edges / ml_total_edges if ml_total_edges > 0 else 0.0

    # Comparative evaluation metrics
    ml_regret_s = max(ml_actual_time - current_actual_time, 0.0)
    ml_vs_static_imp_pct = ((static_actual_time - ml_actual_time) / static_actual_time) * 100.0 if static_actual_time > 0 else 0.0
    ml_oracle_gap_pct = (ml_regret_s / current_actual_time) * 100.0 if current_actual_time > 0 else 0.0
    static_vs_current_imp_pct = ((static_actual_time - current_actual_time) / static_actual_time) * 100.0 if static_actual_time > 0 else 0.0
    ml_vs_current_time_diff = ml_actual_time - current_actual_time

    # Overlaps
    static_ml_overlap = compute_edge_jaccard_overlap(res_static.edge_path, res_ml.edge_path)
    ml_current_overlap = compute_edge_jaccard_overlap(res_ml.edge_path, res_current.edge_path)
    static_current_overlap = compute_edge_jaccard_overlap(res_static.edge_path, res_current.edge_path)

    return {
        'od_id': od_id,
        'timestamp': str(timestamp),
        'ist_timestamp': str(ist_timestamp),
        'period': period_label,
        'is_peak': is_peak,
        'source_node': str(source),
        'destination_node': str(target),
        
        # Static
        'static_distance_m': round(static_dist, 2),
        'static_actual_time_s': round(static_actual_time, 2),
        'static_edge_count': len(res_static.edge_path),
        
        # Current
        'current_distance_m': round(current_dist, 2),
        'current_actual_time_s': round(current_actual_time, 2),
        'current_edge_count': len(res_current.edge_path),
        
        # ML
        'ml_distance_m': round(ml_dist, 2),
        'ml_predicted_time_s': round(ml_predicted_time, 2),
        'ml_actual_time_s': round(ml_actual_time, 2),
        'ml_edge_count': ml_total_edges,
        'ml_dynamic_edge_count': ml_dyn_edges,
        'ml_static_fallback_edges': ml_static_edges,
        'ml_dynamic_edge_fraction': round(ml_dyn_fraction, 4),
        
        # Comparisons
        'ml_vs_static_improvement_pct': round(ml_vs_static_imp_pct, 4),
        'ml_regret_s': round(ml_regret_s, 2),
        'ml_oracle_gap_pct': round(ml_oracle_gap_pct, 4),
        'static_vs_current_improvement_pct': round(static_vs_current_imp_pct, 4),
        'ml_vs_current_time_difference_s': round(ml_vs_current_time_diff, 2),
        'static_ml_route_overlap': round(static_ml_overlap, 4),
        'ml_current_route_overlap': round(ml_current_overlap, 4),
        'static_current_route_overlap': round(static_current_overlap, 4),
        
        # Route objects (for visualization)
        'static_node_path': res_static.node_path,
        'current_node_path': res_current.node_path,
        'ml_node_path': res_ml.node_path,
        'static_edge_path': res_static.edge_path,
        'current_edge_path': res_current.edge_path,
        'ml_edge_path': res_ml.edge_path,
    }
