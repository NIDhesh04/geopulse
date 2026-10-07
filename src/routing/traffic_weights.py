"""
GeoPulse Traffic & Routing Weight Policy Implementation

Computes physical edge traversal times for:
1. Static routing (OSM road hierarchy baseline)
2. Observed/current traffic routing
3. ML-predicted next-hour traffic routing

Enforces Phase 6 policies:
- travel_time_seconds = length_m / (speed_kmh / 3.6)
- Minimum crawl speed guardrail: speed >= 3.0 km/h
- Twin-sensor aggregation: arithmetic mean of validated sensor pairs
- Bidirectional symmetric assignment on two-way undivided roads
- Static fallback on unmonitored or uncertain edges
"""

from typing import Dict, List, Tuple, Set, Optional, Any
import numpy as np
import pandas as pd
import networkx as nx


def get_static_speed_kmh(edge_data: Dict[str, Any]) -> float:
    """
    Determine baseline static speed in km/h based on OSM highway classification.
    Adheres strictly to docs/routing_weight_policy.md.
    """
    highway = str(edge_data.get('highway', '')).lower()

    if 'motorway' in highway or 'trunk' in highway:
        return 50.0
    elif 'primary' in highway:
        return 40.0
    elif 'secondary' in highway:
        return 30.0
    elif 'tertiary' in highway:
        return 25.0
    elif any(kw in highway for kw in ['residential', 'living_street', 'unclassified']):
        return 20.0
    else:
        return 15.0


def calculate_travel_time_seconds(length_m: float, speed_kmh: float) -> float:
    """
    Calculate deterministic kinematic edge traversal time in seconds.
    Enforces minimum crawl speed guardrail of 3.0 km/h.
    """
    clamped_speed = max(float(speed_kmh), 3.0)
    speed_ms = clamped_speed / 3.6
    return max(float(length_m) / speed_ms, 0.001)


class GraphWeightManager:
    """
    Manages road network topology, static edge attributes, and
    dynamic edge weight generation for Bhubaneswar road graph.
    """

    def __init__(self, G: nx.MultiDiGraph, mapping_df: pd.DataFrame):
        self.G = G
        self.mapping_df = mapping_df.copy()

        # Cache graph topology & static attributes
        self.adjacency: Dict[str, List[Tuple[str, int]]] = {}
        self.edge_lengths: Dict[Tuple[str, str, int], float] = {}
        self.edge_static_speeds: Dict[Tuple[str, str, int], float] = {}
        self.static_weights: Dict[Tuple[str, str, int], float] = {}

        self._init_graph_topology()
        self._init_mapping_lookup()

    def _init_graph_topology(self):
        """Precompute adjacency structure and static weights across all edges."""
        for u, v, k, d in self.G.edges(data=True, keys=True):
            u_str, v_str = str(u), str(v)
            length_m = float(d.get('length', 10.0))
            static_speed = get_static_speed_kmh(d)
            travel_time = calculate_travel_time_seconds(length_m, static_speed)

            if u_str not in self.adjacency:
                self.adjacency[u_str] = []
            self.adjacency[u_str].append((v_str, k))

            edge_key = (u_str, v_str, k)
            self.edge_lengths[edge_key] = length_m
            self.edge_static_speeds[edge_key] = static_speed
            self.static_weights[edge_key] = travel_time

    def _init_mapping_lookup(self):
        """Index traffic segment mapping policies for rapid per-timestamp lookup."""
        self.segment_policy = {}
        for _, row in self.mapping_df.iterrows():
            seg_id = int(row['traffic_segment_id'])
            elig = row['routing_eligibility']
            u_str = str(row['u'])
            v_str = str(row['v'])
            key = int(row['key'])
            self.segment_policy[seg_id] = {
                'eligibility': elig,
                'directed_edge': (u_str, v_str, key),
                'u': u_str,
                'v': v_str
            }

    def get_static_weights(self) -> Dict[Tuple[str, str, int], float]:
        """Return the baseline static edge weights."""
        return self.static_weights

    def build_scenario_weights(
        self,
        segment_speeds: Dict[int, float]
    ) -> Tuple[Dict[Tuple[str, str, int], float], Dict[Tuple[str, str, int], float], Set[Tuple[str, str, int]]]:
        """
        Build edge weights under a given dynamic traffic state (observed or predicted).

        Parameters
        ----------
        segment_speeds : Dict[int, float]
            Mapping of traffic_segment_id -> speed_kmh.

        Returns
        -------
        weights_dict : Dict[Tuple[str, str, int], float]
            Edge traversal times in seconds.
        speeds_dict : Dict[Tuple[str, str, int], float]
            Effective speed in km/h for every edge.
        dynamic_edges : Set[Tuple[str, str, int]]
            Set of edges receiving dynamic speeds.
        """
        # Collect candidate speeds for each edge
        edge_candidate_speeds: Dict[Tuple[str, str, int], List[float]] = {}

        for seg_id, spd in segment_speeds.items():
            if seg_id not in self.segment_policy:
                continue

            policy = self.segment_policy[seg_id]
            elig = policy['eligibility']

            # Reject static fallback segments from dynamic weighting
            if elig == 'STATIC_FALLBACK':
                continue

            dir_edge = policy['directed_edge']
            if dir_edge not in edge_candidate_speeds:
                edge_candidate_speeds[dir_edge] = []
            edge_candidate_speeds[dir_edge].append(spd)

            # Bidirectional symmetric assignment
            if elig == 'DYNAMIC_BIDIRECTIONAL':
                u, v = policy['u'], policy['v']
                if self.G.has_edge(v, u):
                    for rev_k in self.G[v][u]:
                        rev_edge = (v, u, rev_k)
                        if rev_edge not in edge_candidate_speeds:
                            edge_candidate_speeds[rev_edge] = []
                        edge_candidate_speeds[rev_edge].append(spd)

        # Aggregate twin sensors by arithmetic mean
        dynamic_edges: Set[Tuple[str, str, int]] = set()
        weights_dict: Dict[Tuple[str, str, int], float] = dict(self.static_weights)
        speeds_dict: Dict[Tuple[str, str, int], float] = dict(self.edge_static_speeds)

        for edge, speed_list in edge_candidate_speeds.items():
            if edge not in self.edge_lengths:
                continue

            # Deterministic mean aggregation
            avg_speed = float(np.mean(speed_list))
            avg_speed = np.clip(avg_speed, 3.0, 120.0)

            length_m = self.edge_lengths[edge]
            travel_time = calculate_travel_time_seconds(length_m, avg_speed)

            weights_dict[edge] = travel_time
            speeds_dict[edge] = avg_speed
            dynamic_edges.add(edge)

        return weights_dict, speeds_dict, dynamic_edges
