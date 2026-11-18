"""
GeoPulse Limited Lookahead Search Engine

Evaluates the forward consequences of selecting an outgoing candidate edge
by exploring paths up to a specified depth k in the road network.

Supports configurable depths:
- Depth 1: Immediate edge cost + heuristic from target node to destination.
- Depth 2: Best 2-edge sequence + heuristic.
- Depth 3: Best 3-edge sequence + heuristic.
- Depth 5: Best 5-edge sequence + heuristic (with branch-and-bound pruning).
"""

from typing import Dict, List, Tuple, Set, Optional, Callable
import heapq


class LimitedLookaheadEvaluator:
    """
    Computes lookahead scores for candidate branches using bounded depth-first or best-first search.
    """

    def __init__(
        self,
        adjacency: Dict[str, List[Tuple[str, int]]],
        edge_weights: Dict[Tuple[str, str, int], float],
        heuristic_fn: Callable[[str, str], float],
        depth: int = 2,
        max_expansions_per_node: int = 4
    ):
        """
        Parameters
        ----------
        adjacency : Dict[str, List[Tuple[str, int]]]
            Adjacency mapping node u -> list of (v, key).
        edge_weights : Dict[Tuple[str, str, int], float]
            Active travel times in seconds for edges.
        heuristic_fn : Callable[[str, str], float]
            Function estimating remaining travel time h(node, destination).
        depth : int
            Lookahead depth k >= 1.
        max_expansions_per_node : int
            Maximum top branches explored per level to prevent exponential explosion.
        """
        self.adjacency = adjacency
        self.edge_weights = edge_weights
        self.heuristic_fn = heuristic_fn
        self.depth = max(1, int(depth))
        self.max_expansions = max(1, int(max_expansions_per_node))

    def evaluate_edge(
        self,
        edge: Tuple[str, str, int],
        destination: str,
        visited_nodes: Optional[Set[str]] = None
    ) -> float:
        """
        Evaluates the total lookahead cost of selecting `edge` = (u, v, key).

        Returns
        -------
        float : Estimated cost (cumulative travel time over lookahead horizon + remaining heuristic).
        """
        u, v, key = str(edge[0]), str(edge[1]), int(edge[2])
        w0 = self.edge_weights.get((u, v, key), 10.0)

        # Target destination reached immediately
        if v == str(destination):
            return w0

        # Depth 1: immediate edge cost + heuristic from v to destination
        if self.depth == 1:
            h_cost = self.heuristic_fn(v, str(destination))
            return w0 + h_cost

        # Depth >= 2: forward branch exploration
        visited = set(visited_nodes) if visited_nodes else set()
        visited.add(u)
        visited.add(v)

        best_continuation_cost = self._explore_continuation(
            current_node=v,
            destination=str(destination),
            remaining_depth=self.depth - 1,
            visited=visited
        )

        return w0 + best_continuation_cost

    def _explore_continuation(
        self,
        current_node: str,
        destination: str,
        remaining_depth: int,
        visited: Set[str]
    ) -> float:
        """
        Recursively explores the best outgoing continuation up to remaining_depth.
        """
        if current_node == destination:
            return 0.0

        if remaining_depth <= 0:
            return self.heuristic_fn(current_node, destination)

        transitions = self.adjacency.get(current_node, [])
        if not transitions:
            # Dead end in forward lookahead
            return 1e6

        # Rank transitions by immediate weight to bound expansion
        candidate_transitions = []
        for next_node_raw, next_key in transitions:
            next_node = str(next_node_raw)
            if next_node in visited:
                continue
            e = (current_node, next_node, int(next_key))
            w = self.edge_weights.get(e, 10.0)
            candidate_transitions.append((w, next_node, e))

        if not candidate_transitions:
            # All outgoing paths lead to visited nodes or dead-ends
            return 1e5

        # Sort and take up to max_expansions
        candidate_transitions.sort(key=lambda x: x[0])
        branches_to_explore = candidate_transitions[:self.max_expansions]

        min_total_cost = float('inf')
        for step_w, next_node, edge_tuple in branches_to_explore:
            if next_node == destination:
                sub_cost = step_w
            else:
                new_visited = visited.copy()
                new_visited.add(next_node)
                continuation = self._explore_continuation(
                    current_node=next_node,
                    destination=destination,
                    remaining_depth=remaining_depth - 1,
                    visited=new_visited
                )
                sub_cost = step_w + continuation

            if sub_cost < min_total_cost:
                min_total_cost = sub_cost

        return min_total_cost
