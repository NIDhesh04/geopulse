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

from dataclasses import dataclass
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


@dataclass(frozen=True)
class ReachabilityEstimate:
    """Bounded continuation evidence for one candidate edge."""

    viable: bool
    estimated_cost_s: float
    viable_frontiers: int
    dead_end_frontiers: int
    expanded_edges: int


class BoundedReachabilityEvaluator:
    """Score a candidate with bounded, simple-path local exploration.

    This evaluator never searches the full graph. It explores at most
    ``max_expansions`` outgoing edges at each level and stops at ``depth``.
    A candidate is viable if at least one explored branch reaches the
    destination or reaches the horizon with a legal unvisited continuation.
    Branches that terminate or can only return to an active-path node are
    marked nonviable and cannot beat a viable branch merely by having low cost.
    """

    def __init__(
        self,
        adjacency: Dict[str, List[Tuple[str, int]]],
        edge_weights: Dict[Tuple[str, str, int], float],
        heuristic_fn: Callable[[str, str], float],
        depth: int = 3,
        max_expansions_per_node: int = 4,
        branch_ranking: str = "destination",
    ):
        self.adjacency = adjacency
        self.edge_weights = edge_weights
        self.heuristic_fn = heuristic_fn
        self.depth = max(1, int(depth))
        self.max_expansions = max(1, int(max_expansions_per_node))
        if branch_ranking not in {"immediate", "destination", "connectivity"}:
            raise ValueError(f"Unknown bounded-search branch ranking: {branch_ranking}")
        self.branch_ranking = branch_ranking
        self._cache: Dict[Tuple[Tuple[str, str, int], str, frozenset], ReachabilityEstimate] = {}

    def evaluate_edge_details(
        self,
        edge: Tuple[str, str, int],
        destination: str,
        visited_nodes: Optional[Set[str]] = None,
    ) -> ReachabilityEstimate:
        u, v, key = str(edge[0]), str(edge[1]), int(edge[2])
        edge_key = (u, v, key)
        visited = frozenset(str(node) for node in (visited_nodes or set()))
        cache_key = (edge_key, str(destination), visited)
        if cache_key in self._cache:
            return self._cache[cache_key]

        path_nodes = set(visited)
        path_nodes.update((u, v))
        initial_cost = float(self.edge_weights.get(edge_key, 10.0))
        viable, continuation_cost, frontiers, dead_ends, expansions = self._explore(
            current_node=v,
            destination=str(destination),
            remaining_depth=self.depth - 1,
            visited=path_nodes,
        )
        estimate = ReachabilityEstimate(
            viable=viable,
            estimated_cost_s=(initial_cost + continuation_cost) if viable else float("inf"),
            viable_frontiers=frontiers,
            dead_end_frontiers=dead_ends,
            expanded_edges=expansions,
        )
        self._cache[cache_key] = estimate
        return estimate

    def evaluate_edge(
        self,
        edge: Tuple[str, str, int],
        destination: str,
        visited_nodes: Optional[Set[str]] = None,
    ) -> float:
        """Return a sortable score; nonviable bounded branches rank last."""
        estimate = self.evaluate_edge_details(edge, destination, visited_nodes)
        if not estimate.viable:
            return float("inf")
        # Connectivity is only a deterministic tie-breaker; it cannot outweigh
        # even a millisecond of estimated travel-time difference.
        return estimate.estimated_cost_s - min(estimate.viable_frontiers, 1000) * 1e-7

    def _explore(
        self,
        current_node: str,
        destination: str,
        remaining_depth: int,
        visited: Set[str],
    ) -> Tuple[bool, float, int, int, int]:
        if current_node == destination:
            return True, 0.0, 1, 0, 0

        transitions = []
        for next_node_raw, next_key in self.adjacency.get(current_node, []):
            next_node = str(next_node_raw)
            if next_node in visited:
                continue
            edge = (current_node, next_node, int(next_key))
            cost = float(self.edge_weights.get(edge, 10.0))
            future_nodes = {
                str(future_node)
                for future_node, _ in self.adjacency.get(next_node, [])
                if str(future_node) not in visited and str(future_node) != next_node
            }
            heuristic = float(self.heuristic_fn(next_node, destination))
            if self.branch_ranking == "immediate":
                rank = (cost, heuristic, next_node, int(next_key))
            elif self.branch_ranking == "connectivity":
                rank = (0 if future_nodes else 1, cost + heuristic, -len(future_nodes), next_node, int(next_key))
            else:
                rank = (cost + heuristic, cost, -len(future_nodes), next_node, int(next_key))
            transitions.append((rank, cost, next_node, edge))

        if not transitions:
            return False, float("inf"), 0, 1, 0

        # At the horizon, an actual dead end or active-path-only return is still
        # detectable because successor eligibility was checked above.
        if remaining_depth <= 0:
            return True, float(self.heuristic_fn(current_node, destination)), 1, 0, 0

        transitions.sort(key=lambda item: item[0])
        outcomes = []
        total_expansions = 0
        total_dead_ends = 0
        for _, step_cost, next_node, _edge in transitions[: self.max_expansions]:
            total_expansions += 1
            child_visited = set(visited)
            child_visited.add(next_node)
            viable, cost, frontiers, dead_ends, expansions = self._explore(
                current_node=next_node,
                destination=destination,
                remaining_depth=remaining_depth - 1,
                visited=child_visited,
            )
            total_dead_ends += dead_ends
            total_expansions += expansions
            if viable:
                outcomes.append((step_cost + cost, frontiers))

        if not outcomes:
            return False, float("inf"), 0, max(1, total_dead_ends), total_expansions
        best_cost = min(cost for cost, _ in outcomes)
        viable_frontiers = sum(frontiers for _, frontiers in outcomes)
        return True, best_cost, viable_frontiers, total_dead_ends, total_expansions
