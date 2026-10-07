"""
GeoPulse Dynamic Rerouter Module

Implements the core dynamic routing lifecycle:
Predict -> Plan -> Observe -> Compare -> Re-route

Provides:
1. Initial predictive route planning (t0)
2. Traversal progression along initial route R0
3. Downstream route degradation detection upon real traffic update (t1)
4. Dynamic threshold-based rerouting via custom Dijkstra
5. Counterfactual comparison:
   - Strategy A: No Rerouting (vehicle continues on initial route R0)
   - Strategy B: GeoPulse Dynamic Rerouting (vehicle switches to R1)
"""

from typing import Dict, List, Tuple, Set, Optional, Any
import numpy as np
from src.routing.dijkstra import custom_dijkstra, DijkstraResult
from src.routing.traffic_weights import GraphWeightManager
from src.routing.route_evaluator import compute_edge_jaccard_overlap


class DynamicRerouter:
    """
    Manages journey replay and dynamic rerouting logic across time steps.
    """

    def __init__(
        self,
        weight_manager: GraphWeightManager,
        reroute_threshold_seconds: float = 10.0,
        reroute_threshold_percent: float = 3.0
    ):
        self.weight_manager = weight_manager
        self.reroute_threshold_seconds = float(reroute_threshold_seconds)
        self.reroute_threshold_percent = float(reroute_threshold_percent)

    def plan_initial_route(
        self,
        source: str,
        destination: str,
        predicted_weights: Dict[Tuple[str, str, int], float]
    ) -> DijkstraResult:
        """
        State 0: Plan initial route R0 at planning time t0 using predicted edge weights.
        """
        return custom_dijkstra(
            self.weight_manager.adjacency,
            predicted_weights,
            source,
            destination
        )

    def evaluate_edge_sequence(
        self,
        edge_path: List[Tuple[str, str, int]],
        weights_dict: Dict[Tuple[str, str, int], float]
    ) -> float:
        """Calculate total travel time along an edge sequence under given weights."""
        return sum(weights_dict.get(e, 0.0) for e in edge_path)

    def compute_alternative_route(
        self,
        current_node: str,
        destination: str,
        observed_weights: Dict[Tuple[str, str, int], float]
    ) -> DijkstraResult:
        """
        State 3: Recompute shortest path from vehicle's current position to destination
        using newly observed traffic weights.
        """
        return custom_dijkstra(
            self.weight_manager.adjacency,
            observed_weights,
            current_node,
            destination
        )

    def should_reroute(
        self,
        current_remaining_time: float,
        alternative_time: float
    ) -> Tuple[bool, float, float, str]:
        """
        State 2: Evaluate route degradation and decide whether rerouting is justified.
        """
        absolute_saving = current_remaining_time - alternative_time
        if current_remaining_time > 0:
            relative_saving = (absolute_saving / current_remaining_time) * 100.0
        else:
            relative_saving = 0.0

        if (
            absolute_saving >= self.reroute_threshold_seconds and
            relative_saving >= self.reroute_threshold_percent
        ):
            reason = (
                f"Degradation detected: Alternative saves {absolute_saving:.1f}s "
                f"({relative_saving:.1f}%), exceeding thresholds "
                f"({self.reroute_threshold_seconds}s / {self.reroute_threshold_percent}%)."
            )
            return True, absolute_saving, relative_saving, reason
        else:
            reason = (
                f"No reroute triggered: Potential saving {max(absolute_saving, 0.0):.1f}s "
                f"({max(relative_saving, 0.0):.1f}%) below trigger threshold."
            )
            return False, max(absolute_saving, 0.0), max(relative_saving, 0.0), reason

    def simulate_journey(
        self,
        scenario_id: int,
        od_id: int,
        source: str,
        destination: str,
        t0: Any,
        t1: Any,
        t0_ist: Any,
        t1_ist: Any,
        period_label: str,
        w_pred_t0: Dict[Tuple[str, str, int], float],
        w_obs_t1: Dict[Tuple[str, str, int], float],
        dynamic_edges_set: Set[Tuple[str, str, int]],
        decision_frac: float = 0.33
    ) -> Dict[str, Any]:
        """
        Execute an end-to-end time-progressive journey simulation.
        """
        # 1. State 0: Initial planning at t0
        res_r0 = self.plan_initial_route(source, destination, w_pred_t0)
        if not res_r0.is_reached:
            raise ValueError(f"Unreachable origin-destination pair {source} -> {destination}")

        path_nodes = res_r0.node_path
        path_edges = res_r0.edge_path
        initial_predicted_time = res_r0.total_cost

        # Determine decision point along R0 where traffic update arrives
        k = max(1, min(int(len(path_nodes) * decision_frac), len(path_nodes) - 2))
        curr_node = path_nodes[k]

        traversed_edges = path_edges[:k]
        remaining_r0_edges = path_edges[k:]

        # Travel time already elapsed on traversed portion (under initial traffic)
        time_traversed = self.evaluate_edge_sequence(traversed_edges, w_pred_t0)
        dist_traversed = sum(self.weight_manager.edge_lengths.get(e, 0.0) for e in traversed_edges)

        # 2. State 1: Traffic update arrives at t1
        # Evaluate remaining edges of R0 under new observed traffic state
        remaining_r0_actual_time = self.evaluate_edge_sequence(remaining_r0_edges, w_obs_t1)
        dist_remaining_r0 = sum(self.weight_manager.edge_lengths.get(e, 0.0) for e in remaining_r0_edges)

        # Counterfactual Strategy A: No Rerouting total journey
        total_time_no_reroute = time_traversed + remaining_r0_actual_time
        total_dist_no_reroute = dist_traversed + dist_remaining_r0

        # 3. State 2: Check alternative from decision node curr_node under observed traffic
        res_alt = self.compute_alternative_route(curr_node, destination, w_obs_t1)
        remaining_alt_time = res_alt.total_cost
        dist_remaining_alt = sum(self.weight_manager.edge_lengths.get(e, 0.0) for e in res_alt.edge_path)

        # Check rerouting condition
        reroute_triggered, abs_saving, rel_saving, trigger_reason = self.should_reroute(
            remaining_r0_actual_time,
            remaining_alt_time
        )

        # 4. State 3 & 4: Select executed route
        if reroute_triggered:
            executed_remaining_edges = res_alt.edge_path
            executed_remaining_nodes = res_alt.node_path
            remaining_executed_time = remaining_alt_time
            dist_remaining_executed = dist_remaining_alt
        else:
            executed_remaining_edges = remaining_r0_edges
            executed_remaining_nodes = path_nodes[k:]
            remaining_executed_time = remaining_r0_actual_time
            dist_remaining_executed = dist_remaining_r0

        # Strategy B: Dynamic Rerouting journey
        total_time_dynamic = time_traversed + remaining_executed_time
        total_dist_dynamic = dist_traversed + dist_remaining_executed

        final_node_path = path_nodes[:k] + executed_remaining_nodes
        final_edge_path = traversed_edges + executed_remaining_edges

        # Time saved
        actual_time_saved = total_time_no_reroute - total_time_dynamic
        if total_time_no_reroute > 0:
            actual_improvement_pct = (actual_time_saved / total_time_no_reroute) * 100.0
        else:
            actual_improvement_pct = 0.0

        # Overlap and edge changes
        set_orig = set(path_edges)
        set_final = set(final_edge_path)
        route_overlap = compute_edge_jaccard_overlap(path_edges, final_edge_path)
        changed_edges_count = len(set_final - set_orig)

        # Dynamic coverage
        dyn_count = sum(1 for e in final_edge_path if e in dynamic_edges_set)
        dyn_fraction = dyn_count / len(final_edge_path) if len(final_edge_path) > 0 else 0.0

        return {
            'scenario_id': scenario_id,
            'od_id': od_id,
            'initial_timestamp': str(t0),
            'update_timestamp': str(t1),
            'initial_ist_timestamp': str(t0_ist),
            'update_ist_timestamp': str(t1_ist),
            'period': period_label,
            'source_node': str(source),
            'destination_node': str(destination),
            'decision_node': str(curr_node),
            'decision_step': k,
            'decision_frac': decision_frac,
            
            # Initial Route R0
            'initial_route_distance_m': round(total_dist_no_reroute, 2),
            'initial_route_edges': len(path_edges),
            'initial_predicted_time_s': round(initial_predicted_time, 2),
            'initial_actual_time_s': round(total_time_no_reroute, 2),
            
            # Update state
            'updated_route_time_s': round(total_time_no_reroute, 2),
            'best_current_route_time_s': round(time_traversed + remaining_alt_time, 2),
            'reroute_triggered': bool(reroute_triggered),
            'trigger_reason': trigger_reason,
            'reroute_threshold_s': self.reroute_threshold_seconds,
            'reroute_threshold_pct': self.reroute_threshold_percent,
            
            # Post-reroute Strategy B
            'reroute_time_s': round(total_time_dynamic, 2),
            'new_route_distance_m': round(total_dist_dynamic, 2),
            'new_route_edges': len(final_edge_path),
            'changed_edges_count': changed_edges_count,
            'time_saved_s': round(actual_time_saved, 2),
            'improvement_pct': round(actual_improvement_pct, 2),
            'route_overlap_before_after': round(route_overlap, 4),
            'dynamic_edge_fraction': round(dyn_fraction, 4),
            
            # Counterfactual summary
            'total_time_no_reroute_s': round(total_time_no_reroute, 2),
            'total_time_dynamic_s': round(total_time_dynamic, 2),
            
            # Paths for visualization
            'r0_node_path': path_nodes,
            'r0_edge_path': path_edges,
            'r1_node_path': final_node_path,
            'r1_edge_path': final_edge_path,
            'traversed_edge_path': traversed_edges,
            'remaining_r0_edge_path': remaining_r0_edges,
            'remaining_r1_edge_path': executed_remaining_edges
        }
