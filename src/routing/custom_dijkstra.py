"""Custom Modified Dijkstra Engine for GeoPulse Bhubaneswar.

Implements a priority-queue Dijkstra search from scratch with dynamic travel time
weighting, multi-objective cost optimization (alpha * length + beta * travel_time),
and real-time / predicted speed updates on monitored segments.
"""
import heapq
from typing import Dict, List, Optional, Tuple, Union
import networkx as nx


def custom_dijkstra(
    G: Union[nx.Graph, nx.DiGraph, nx.MultiGraph, nx.MultiDiGraph],
    source: Union[int, str],
    target: Union[int, str],
    alpha: float = 1.0,
    beta: float = 1.0,
    current_time: Optional[object] = None,
    edge_speeds_dict: Optional[Dict[Union[int, str], float]] = None,
) -> Tuple[List[Union[int, str]], float]:
    """Computes the shortest path from source to target using dynamic edge costs.

    Cost Formula:
        Cost(u, v) = alpha * Length + beta * TravelTime(u, v)

    Parameters
    ----------
    G : nx.Graph or nx.DiGraph or nx.MultiDiGraph
        The road network graph (metric CRS, lengths in meters).
    source : int or str
        Origin node identifier.
    target : int or str
        Destination node identifier.
    alpha : float, optional
        Weight for physical distance in meters (default 1.0).
    beta : float, optional
        Weight for traversal time in seconds (default 1.0).
    current_time : object, optional
        Current time bucket (reserved for temporal indexing).
    edge_speeds_dict : dict, optional
        Mapping from segment_id to current/predicted speed in km/h.

    Returns
    -------
    tuple:
        (path, total_cost) where path is a list of node IDs [source, ..., target]
        and total_cost is the accumulated cost (float).
        If target is unreachable, returns ([], float('inf')).
    """
    # Normalize node IDs if needed
    if source not in G:
        if str(source) in G:
            source = str(source)
        elif isinstance(source, str) and source.isdigit() and int(source) in G:
            source = int(source)
        else:
            raise ValueError(f"Source node {source} not found in graph.")

    if target not in G:
        if str(target) in G:
            target = str(target)
        elif isinstance(target, str) and target.isdigit() and int(target) in G:
            target = int(target)
        else:
            raise ValueError(f"Target node {target} not found in graph.")

    if source == target:
        return [source], 0.0

    # Ensure edge speeds dict lookup is robust for int and str keys
    speeds = {}
    if edge_speeds_dict:
        for k, v in edge_speeds_dict.items():
            speeds[k] = float(v)
            try:
                speeds[int(k)] = float(v)
                speeds[str(k)] = float(v)
            except (ValueError, TypeError):
                pass

    # Priority queue stores tuples of: (cost_so_far, node)
    pq = [(0.0, source)]
    distances = {source: 0.0}
    prev = {source: None}
    visited = set()

    is_multigraph = G.is_multigraph()

    while pq:
        current_cost, u = heapq.heappop(pq)

        if u in visited:
            continue
        visited.add(u)

        if u == target:
            break

        # Explore outgoing edges
        for v in G.neighbors(u):
            if v in visited:
                continue

            # In MultiDiGraph, multiple parallel edges may exist between u and v
            if is_multigraph:
                edge_dict = G[u][v]
            else:
                edge_dict = {0: G[u][v]}

            # Find the minimum cost edge between u and v
            best_edge_cost = float("inf")
            for key, d in edge_dict.items():
                length = float(d.get("length", 10.0))

                # Check monitored status
                is_mon = d.get("is_monitored") is True or str(d.get("is_monitored")).lower() == "true"
                sid = d.get("segment_id")

                # Compute travel time
                if is_mon and sid is not None and sid in speeds:
                    speed_kmh = max(speeds[sid], 1.0)  # strict zero-division protection
                    travel_time = length / (speed_kmh / 3.6)
                else:
                    travel_time = float(d.get("free_flow_time", 0.0))
                    if travel_time <= 0.0:
                        ff_speed = float(d.get("free_flow_speed", 30.0))
                        ff_speed = max(ff_speed, 1.0)
                        travel_time = length / (ff_speed / 3.6)

                edge_cost = alpha * length + beta * travel_time
                if edge_cost < best_edge_cost:
                    best_edge_cost = edge_cost

            tentative_cost = current_cost + best_edge_cost

            if tentative_cost < distances.get(v, float("inf")):
                distances[v] = tentative_cost
                prev[v] = u
                heapq.heappush(pq, (tentative_cost, v))

    # Reconstruct path
    if target not in prev or distances.get(target, float("inf")) == float("inf"):
        return [], float("inf")

    path = []
    curr = target
    while curr is not None:
        path.append(curr)
        curr = prev[curr]
    path.reverse()

    return path, distances[target]
