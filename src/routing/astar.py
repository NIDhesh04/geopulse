"""
GeoPulse Custom A* Shortest-Time Path Solver

Pure Python implementation of the A* algorithm written from scratch.
Uses min-heap priority queue with admissible heuristic: f(n) = g(n) + h(n).
Supports directed MultiDiGraphs with parallel edges and early termination upon target arrival.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Any, Callable
import heapq


@dataclass
class AStarResult:
    """Encapsulates the complete A* pathfinding output."""
    node_path: List[Any]
    edge_path: List[Tuple[Any, Any, int]]
    total_cost: float
    visited_nodes_count: int
    is_reached: bool


def custom_astar(
    adjacency: Dict[Any, List[Tuple[Any, int]]],
    edge_weights: Dict[Tuple[Any, Any, int], float],
    heuristic_fn: Callable[[Any, Any], float],
    source: Any,
    target: Any
) -> AStarResult:
    """
    Finds shortest path from source to target using scratch-built A* algorithm.

    Parameters
    ----------
    adjacency : Dict[Any, List[Tuple[Any, int]]]
        Graph adjacency mapping node u -> list of (v, key) transitions.
    edge_weights : Dict[Tuple[Any, Any, int], float]
        Mapping directed edge (u, v, key) -> traversal cost (seconds).
    heuristic_fn : Callable[[Any, Any], float]
        Admissible heuristic function estimating remaining travel time h(u, target).
    source : Any
        Origin node identifier.
    target : Any
        Destination node identifier.

    Returns
    -------
    AStarResult
        Object containing node_path, edge_path, total_cost, visited_nodes_count, and is_reached.
    """
    if source == target:
        return AStarResult(
            node_path=[source],
            edge_path=[],
            total_cost=0.0,
            visited_nodes_count=1,
            is_reached=True
        )

    # g_score: cost from start along best known path
    g_score: Dict[Any, float] = {source: 0.0}
    # f_score: g_score + heuristic
    h_start = heuristic_fn(source, target)
    f_score: Dict[Any, float] = {source: h_start}

    # pred: node -> (predecessor_node, edge_key, edge_cost)
    pred: Dict[Any, Tuple[Any, int, float]] = {}

    # Priority queue stores (f_score, node)
    pq: List[Tuple[float, Any]] = [(h_start, source)]
    visited_count = 0
    reached = False

    while pq:
        curr_f, u = heapq.heappop(pq)

        if curr_f > f_score.get(u, float('inf')):
            continue

        visited_count += 1

        if u == target:
            reached = True
            break

        out_transitions = adjacency.get(u)
        if not out_transitions:
            continue

        curr_g = g_score[u]

        for v, k in out_transitions:
            weight = edge_weights.get((u, v, k), float('inf'))
            if weight <= 0.0:
                weight = 1e-4

            tentative_g = curr_g + weight

            if tentative_g < g_score.get(v, float('inf')):
                g_score[v] = tentative_g
                h_v = heuristic_fn(v, target)
                f_val = tentative_g + h_v
                f_score[v] = f_val
                pred[v] = (u, k, weight)
                heapq.heappush(pq, (f_val, v))

    if not reached or target not in g_score:
        return AStarResult(
            node_path=[],
            edge_path=[],
            total_cost=float('inf'),
            visited_nodes_count=visited_count,
            is_reached=False
        )

    # Reconstruct path from target to source
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

    return AStarResult(
        node_path=node_path,
        edge_path=edge_path,
        total_cost=g_score[target],
        visited_nodes_count=visited_count,
        is_reached=True
    )
