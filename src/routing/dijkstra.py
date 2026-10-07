"""
GeoPulse Custom Dijkstra Shortest Path Solver

Pure Python implementation of Dijkstra's algorithm written completely from scratch.
DO NOT use networkx.shortest_path, osmnx, or any external library solvers.
Supports directed graphs, MultiDiGraphs with parallel edges, edge-weight dictionaries,
and early termination upon reaching target.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Any
import heapq


@dataclass
class DijkstraResult:
    """Encapsulates the complete pathfinding output."""
    node_path: List[Any]
    edge_path: List[Tuple[Any, Any, int]]
    total_cost: float
    visited_nodes_count: int
    is_reached: bool


def custom_dijkstra(
    adjacency: Dict[Any, List[Tuple[Any, int]]],
    edge_weights: Dict[Tuple[Any, Any, int], float],
    source: Any,
    target: Any
) -> DijkstraResult:
    """
    Find the shortest path from source to target using custom Dijkstra's algorithm.

    Parameters
    ----------
    adjacency : Dict[Any, List[Tuple[Any, int]]]
        Graph adjacency mapping node u -> list of (v, key) transitions.
    edge_weights : Dict[Tuple[Any, Any, int], float]
        Dictionary mapping directed edge (u, v, key) -> traversal cost (travel time in seconds).
    source : Any
        Origin node identifier.
    target : Any
        Destination node identifier.

    Returns
    -------
    DijkstraResult
        Object containing node_path, edge_path, total_cost, visited_nodes_count, and is_reached.
    """
    # Trivial source == target
    if source == target:
        return DijkstraResult(
            node_path=[source],
            edge_path=[],
            total_cost=0.0,
            visited_nodes_count=1,
            is_reached=True
        )

    # Initialize data structures
    dist: Dict[Any, float] = {source: 0.0}
    pred: Dict[Any, Tuple[Any, int, float]] = {}  # node -> (predecessor_node, edge_key, edge_cost)
    pq: List[Tuple[float, Any]] = [(0.0, source)]
    visited_count = 0
    reached = False

    while pq:
        curr_dist, u = heapq.heappop(pq)

        # Skip if a shorter path to u was already settled
        if curr_dist > dist.get(u, float('inf')):
            continue

        visited_count += 1

        # Early termination upon reaching destination
        if u == target:
            reached = True
            break

        # Explore outgoing transitions
        out_transitions = adjacency.get(u)
        if not out_transitions:
            continue

        for v, k in out_transitions:
            weight = edge_weights.get((u, v, k), float('inf'))
            if weight <= 0.0:
                # Fallback guardrail for zero/negative weights
                weight = 1e-4

            new_dist = curr_dist + weight

            if new_dist < dist.get(v, float('inf')):
                dist[v] = new_dist
                pred[v] = (u, k, weight)
                heapq.heappush(pq, (new_dist, v))

    if not reached or target not in dist:
        return DijkstraResult(
            node_path=[],
            edge_path=[],
            total_cost=float('inf'),
            visited_nodes_count=visited_count,
            is_reached=False
        )

    # Reconstruct shortest path from target back to source
    node_path = []
    edge_path = []
    curr = target

    while curr != source:
        prev_node, key, _ = pred[curr]
        edge_path.append((prev_node, curr, key))
        node_path.append(curr)
        curr = prev_node

    node_path.append(source)
    node_path.reverse()
    edge_path.reverse()

    return DijkstraResult(
        node_path=node_path,
        edge_path=edge_path,
        total_cost=dist[target],
        visited_nodes_count=visited_count,
        is_reached=True
    )
