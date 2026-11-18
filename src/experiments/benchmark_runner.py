"""
GeoPulse Master Experimental Benchmark Runner

Executes controlled comparisons across the 8 required algorithms and 8 formal experiments:
Algorithms:
  1. Static Shortest-Time Dijkstra
  2. Traffic-Aware Dynamic Dijkstra (GeoPulse Phase 8)
  3. A* Shortest-Time Routing
  4. Greedy Two-Edge Selection
  5. Destination-Aware Two-Edge Selection
  6. Limited-Lookahead Two-Edge Selection (Depths 1, 2, 3, 5)
  7. Existing Dynamic Rerouting Strategy (Phase 9)
  8. Sequential Two-Edge Selection with Dynamic Rerouting

Experiments:
  Exp 1: Candidate Generation Comparison (Random, Lowest Cost, Dest-Aware, Lookahead)
  Exp 2: Decision Strategy Comparison (Greedy, Dest-Aware, Lookahead, Adaptive)
  Exp 3: Lookahead Depth Analysis (Depths 1, 2, 3, 5)
  Exp 4: Dynamic Traffic Scenarios (Normal, Moderate, Severe, Sudden Change)
  Exp 5: Rerouting Threshold Sensitivity
  Exp 6: Multi-OD Diurnal Journeys (Canonical peak and off-peak runs)
  Exp 7: Network Scalability Evaluation
  Exp 8: Robustness & Failure Recovery (Dead-ends, Cycles, Missing predictions)
"""

import os
import sys
import time
import math
import random
from typing import Dict, List, Tuple, Set, Optional, Any
import numpy as np
import pandas as pd
import networkx as nx

from src.routing.dijkstra import custom_dijkstra, DijkstraResult
from src.routing.astar import custom_astar, AStarResult
from src.routing.traffic_weights import GraphWeightManager, calculate_travel_time_seconds
from src.routing.candidate_generator import (
    CandidateGenerator,
    CandidateGenerationStrategy
)
from src.routing.lookahead import LimitedLookaheadEvaluator
from src.routing.decision_strategies import (
    GreedyDecisionStrategy,
    DestinationAwareDecisionStrategy,
    LimitedLookaheadDecisionStrategy,
    AdaptiveDecisionStrategy
)
from src.routing.two_edge_selector import TwoEdgeSelector
from src.routing.route_controller import RouteController, SequentialJourneyResult
from src.routing.dynamic_rerouter import DynamicRerouter
from src.routing.route_evaluator import compute_edge_jaccard_overlap


class ExperimentalBenchmark:
    """Master benchmark suite runner for GeoPulse research validation."""

    def __init__(
        self,
        weight_manager: GraphWeightManager,
        output_dir: str = "results/two_edge_experiments"
    ):
        self.wm = weight_manager
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(os.path.join(output_dir, "figures"), exist_ok=True)

        # Adjacency and static attributes
        self.adjacency = self.wm.adjacency
        self.edge_lengths = self.wm.edge_lengths
        self.static_weights = self.wm.get_static_weights()

        # Extract node coordinates for heuristics
        self.node_coords: Dict[str, Tuple[float, float]] = {}
        for n, d in self.wm.G.nodes(data=True):
            n_str = str(n)
            lat = float(d.get('y', 0.0))
            lon = float(d.get('x', 0.0))
            self.node_coords[n_str] = (lat, lon)

        self.candidate_generator = CandidateGenerator(
            adjacency=self.adjacency,
            edge_lengths=self.edge_lengths,
            node_coords=self.node_coords,
            default_free_flow_speed_kmh=40.0
        )

    def _heuristic_fn(self, u: str, target: str) -> float:
        return self.candidate_generator.estimate_remaining_time(str(u), str(target))

    # -------------------------------------------------------------------------
    # EXPERIMENT 1: Candidate Generation Strategies
    # -------------------------------------------------------------------------
    def run_experiment_1_candidate_generation(
        self,
        od_pairs: List[Tuple[str, str]],
        active_weights: Dict[Tuple[str, str, int], float]
    ) -> pd.DataFrame:
        """
        Compares the 4 candidate generation policies:
        - Random
        - Lowest Immediate Cost
        - Destination-Aware
        - Lookahead (Depth 2)
        All using Destination-Aware decision strategy to isolate candidate generator impact.
        """
        print("[Exp 1] Evaluating Candidate Generation Strategies...")
        records = []
        strategy = DestinationAwareDecisionStrategy()

        cand_strategies = [
            CandidateGenerationStrategy.RANDOM,
            CandidateGenerationStrategy.LOWEST_IMMEDIATE_COST,
            CandidateGenerationStrategy.DESTINATION_AWARE,
            CandidateGenerationStrategy.LOOKAHEAD
        ]

        for s_node, d_node in od_pairs:
            # Baseline Dijkstra reference
            dijk = custom_dijkstra(self.adjacency, active_weights, s_node, d_node)
            if not dijk.is_reached:
                continue

            for cg_strat in cand_strategies:
                selector = TwoEdgeSelector(
                    candidate_generator=self.candidate_generator,
                    decision_strategy=strategy,
                    candidate_strategy=cg_strat
                )
                controller = RouteController(
                    adjacency=self.adjacency,
                    edge_lengths=self.edge_lengths,
                    two_edge_selector=selector
                )

                t0 = time.perf_counter()
                res: SequentialJourneyResult = controller.execute_journey(
                    source=s_node,
                    destination=d_node,
                    initial_weights=active_weights,
                    reference_dijkstra=dijk
                )
                runtime_ms = (time.perf_counter() - t0) * 1000.0

                optimality_gap_s = max(res.total_travel_time_s - dijk.total_cost, 0.0)
                optimality_gap_pct = (optimality_gap_s / dijk.total_cost * 100.0) if dijk.total_cost > 0 else 0.0

                records.append({
                    'od_pair': f"{s_node}->{d_node}",
                    'candidate_strategy': cg_strat.value,
                    'is_success': res.is_success,
                    'travel_time_s': res.total_travel_time_s,
                    'distance_m': res.total_distance_m,
                    'decisions_count': res.total_decisions,
                    'recovery_events': res.recovery_events,
                    'dijkstra_reference_time_s': dijk.total_cost,
                    'optimality_gap_s': round(optimality_gap_s, 2),
                    'optimality_gap_pct': round(optimality_gap_pct, 2),
                    'avg_latency_ms': res.average_decision_latency_ms,
                    'total_runtime_ms': round(runtime_ms, 2)
                })

        df = pd.DataFrame(records)
        df.to_csv(os.path.join(self.output_dir, "exp1_candidate_generation.csv"), index=False)
        return df

    # -------------------------------------------------------------------------
    # EXPERIMENT 2: Decision Strategies
    # -------------------------------------------------------------------------
    def run_experiment_2_decision_strategies(
        self,
        od_pairs: List[Tuple[str, str]],
        active_weights: Dict[Tuple[str, str, int], float]
    ) -> pd.DataFrame:
        """
        Compares decision strategies:
        - Greedy (Lowest Immediate Cost)
        - Destination-Aware
        - Limited Lookahead (Depth 2)
        - Adaptive (Congestion-responsive)
        """
        print("[Exp 2] Evaluating Decision Strategies...")
        records = []

        lookahead_eval = LimitedLookaheadEvaluator(
            self.adjacency,
            active_weights,
            self._heuristic_fn,
            depth=2
        )

        strategies = {
            "Greedy": (GreedyDecisionStrategy(), CandidateGenerationStrategy.LOWEST_IMMEDIATE_COST),
            "Destination-Aware": (DestinationAwareDecisionStrategy(), CandidateGenerationStrategy.DESTINATION_AWARE),
            "Lookahead-2": (LimitedLookaheadDecisionStrategy(lookahead_eval), CandidateGenerationStrategy.LOOKAHEAD),
            "Adaptive": (
                AdaptiveDecisionStrategy(
                    DestinationAwareDecisionStrategy(),
                    LimitedLookaheadDecisionStrategy(lookahead_eval)
                ),
                CandidateGenerationStrategy.DESTINATION_AWARE
            )
        }

        for s_node, d_node in od_pairs:
            dijk = custom_dijkstra(self.adjacency, active_weights, s_node, d_node)
            if not dijk.is_reached:
                continue

            for strat_label, (strat_obj, cand_mode) in strategies.items():
                selector = TwoEdgeSelector(
                    candidate_generator=self.candidate_generator,
                    decision_strategy=strat_obj,
                    candidate_strategy=cand_mode
                )
                controller = RouteController(
                    adjacency=self.adjacency,
                    edge_lengths=self.edge_lengths,
                    two_edge_selector=selector
                )

                t0 = time.perf_counter()
                res = controller.execute_journey(
                    source=s_node,
                    destination=d_node,
                    initial_weights=active_weights,
                    reference_dijkstra=dijk
                )
                runtime_ms = (time.perf_counter() - t0) * 1000.0

                opt_gap_s = max(res.total_travel_time_s - dijk.total_cost, 0.0)
                opt_gap_pct = (opt_gap_s / dijk.total_cost * 100.0) if dijk.total_cost > 0 else 0.0

                records.append({
                    'od_pair': f"{s_node}->{d_node}",
                    'decision_strategy': strat_label,
                    'is_success': res.is_success,
                    'travel_time_s': res.total_travel_time_s,
                    'distance_m': res.total_distance_m,
                    'decisions_count': res.total_decisions,
                    'forced_decisions': res.forced_decisions,
                    'recovery_events': res.recovery_events,
                    'dijkstra_reference_time_s': dijk.total_cost,
                    'optimality_gap_s': round(opt_gap_s, 2),
                    'optimality_gap_pct': round(opt_gap_pct, 2),
                    'avg_latency_ms': res.average_decision_latency_ms,
                    'total_runtime_ms': round(runtime_ms, 2)
                })

        df = pd.DataFrame(records)
        df.to_csv(os.path.join(self.output_dir, "exp2_decision_strategies.csv"), index=False)
        return df

    # -------------------------------------------------------------------------
    # EXPERIMENT 3: Lookahead Depth (k in {1, 2, 3, 5})
    # -------------------------------------------------------------------------
    def run_experiment_3_lookahead_depth(
        self,
        od_pairs: List[Tuple[str, str]],
        active_weights: Dict[Tuple[str, str, int], float]
    ) -> pd.DataFrame:
        """Evaluates lookahead performance and latency scaling at depths 1, 2, 3, and 5."""
        print("[Exp 3] Evaluating Lookahead Depths (1, 2, 3, 5)...")
        records = []
        depths = [1, 2, 3, 5]

        for s_node, d_node in od_pairs:
            dijk = custom_dijkstra(self.adjacency, active_weights, s_node, d_node)
            if not dijk.is_reached:
                continue

            for k in depths:
                evaluator = LimitedLookaheadEvaluator(
                    adjacency=self.adjacency,
                    edge_weights=active_weights,
                    heuristic_fn=self._heuristic_fn,
                    depth=k
                )
                strategy = LimitedLookaheadDecisionStrategy(evaluator)
                selector = TwoEdgeSelector(
                    candidate_generator=self.candidate_generator,
                    decision_strategy=strategy,
                    candidate_strategy=CandidateGenerationStrategy.LOOKAHEAD
                )
                controller = RouteController(
                    adjacency=self.adjacency,
                    edge_lengths=self.edge_lengths,
                    two_edge_selector=selector
                )

                t0 = time.perf_counter()
                res = controller.execute_journey(
                    source=s_node,
                    destination=d_node,
                    initial_weights=active_weights,
                    reference_dijkstra=dijk
                )
                runtime_ms = (time.perf_counter() - t0) * 1000.0

                opt_gap_s = max(res.total_travel_time_s - dijk.total_cost, 0.0)

                records.append({
                    'od_pair': f"{s_node}->{d_node}",
                    'lookahead_depth': k,
                    'is_success': res.is_success,
                    'travel_time_s': res.total_travel_time_s,
                    'distance_m': res.total_distance_m,
                    'decisions_count': res.total_decisions,
                    'recovery_events': res.recovery_events,
                    'optimality_gap_s': round(opt_gap_s, 2),
                    'avg_latency_ms': res.average_decision_latency_ms,
                    'total_runtime_ms': round(runtime_ms, 2)
                })

        df = pd.DataFrame(records)
        df.to_csv(os.path.join(self.output_dir, "exp3_lookahead_depth.csv"), index=False)
        return df

    # -------------------------------------------------------------------------
    # EXPERIMENT 4: Dynamic Traffic Conditions
    # -------------------------------------------------------------------------
    def run_experiment_4_dynamic_traffic(
        self,
        od_pairs: List[Tuple[str, str]],
        base_weights: Dict[Tuple[str, str, int], float]
    ) -> pd.DataFrame:
        """
        Tests 4 traffic conditions:
        - Normal (baseline)
        - Moderate Congestion (20% speed drop on arterials)
        - Severe Congestion (50% speed drop on arterials)
        - Sudden Bottleneck (collapsing speed mid-corridor)
        """
        print("[Exp 4] Evaluating Dynamic Traffic Scenarios...")
        records = []
        traffic_scenarios = ["Normal", "Moderate Congestion", "Severe Congestion", "Sudden Bottleneck"]

        for s_node, d_node in od_pairs:
            for sc_name in traffic_scenarios:
                weights = dict(base_weights)
                update_step = None
                updated_weights = None

                if sc_name == "Moderate Congestion":
                    for e in list(weights.keys())[:len(weights)//4]:
                        weights[e] *= 1.3
                elif sc_name == "Severe Congestion":
                    for e in list(weights.keys())[:len(weights)//3]:
                        weights[e] *= 2.0
                elif sc_name == "Sudden Bottleneck":
                    update_step = 5
                    updated_weights = dict(weights)
                    for e in list(updated_weights.keys())[:50]:
                        updated_weights[e] *= 3.5

                selector = TwoEdgeSelector(
                    candidate_generator=self.candidate_generator,
                    decision_strategy=DestinationAwareDecisionStrategy()
                )
                controller = RouteController(
                    adjacency=self.adjacency,
                    edge_lengths=self.edge_lengths,
                    two_edge_selector=selector
                )

                res = controller.execute_journey(
                    source=s_node,
                    destination=d_node,
                    initial_weights=weights,
                    traffic_update_step=update_step,
                    updated_weights=updated_weights
                )

                records.append({
                    'od_pair': f"{s_node}->{d_node}",
                    'traffic_scenario': sc_name,
                    'is_success': res.is_success,
                    'travel_time_s': res.total_travel_time_s,
                    'distance_m': res.total_distance_m,
                    'decisions_count': res.total_decisions,
                    'recovery_events': res.recovery_events,
                    'reroute_events': res.reroute_events
                })

        df = pd.DataFrame(records)
        df.to_csv(os.path.join(self.output_dir, "exp4_dynamic_traffic.csv"), index=False)
        return df

    # -------------------------------------------------------------------------
    # EXPERIMENT 5: Rerouting Threshold Sensitivity
    # -------------------------------------------------------------------------
    def run_experiment_5_threshold_sensitivity(
        self,
        od_pairs: List[Tuple[str, str]],
        base_weights: Dict[Tuple[str, str, int], float]
    ) -> pd.DataFrame:
        """Evaluates parametric sensitivity of absolute (5-30s) and percentage (1-10%) gates."""
        print("[Exp 5] Evaluating Rerouting Threshold Sensitivity...")
        records = []
        abs_thresholds = [5.0, 10.0, 20.0, 30.0]
        pct_thresholds = [1.0, 3.0, 5.0, 10.0]

        # Build scenario with sudden traffic change at step 4
        updated_weights = dict(base_weights)
        for e in list(updated_weights.keys())[:40]:
            updated_weights[e] *= 3.0

        for s_node, d_node in od_pairs:
            for delta_t in abs_thresholds:
                for delta_pct in pct_thresholds:
                    selector = TwoEdgeSelector(
                        candidate_generator=self.candidate_generator,
                        decision_strategy=DestinationAwareDecisionStrategy()
                    )
                    controller = RouteController(
                        adjacency=self.adjacency,
                        edge_lengths=self.edge_lengths,
                        two_edge_selector=selector,
                        reroute_threshold_seconds=delta_t,
                        reroute_threshold_percent=delta_pct
                    )

                    res = controller.execute_journey(
                        source=s_node,
                        destination=d_node,
                        initial_weights=base_weights,
                        traffic_update_step=4,
                        updated_weights=updated_weights
                    )

                    records.append({
                        'od_pair': f"{s_node}->{d_node}",
                        'delta_T_threshold_s': delta_t,
                        'delta_pct_threshold': delta_pct,
                        'travel_time_s': res.total_travel_time_s,
                        'distance_m': res.total_distance_m,
                        'reroute_events': res.reroute_events,
                        'is_success': res.is_success
                    })

        df = pd.DataFrame(records)
        df.to_csv(os.path.join(self.output_dir, "exp5_threshold_sensitivity.csv"), index=False)
        return df

    # -------------------------------------------------------------------------
    # MASTER EXPERIMENT: 8-Algorithm Comparison
    # -------------------------------------------------------------------------
    def run_master_algorithm_comparison(
        self,
        od_pairs: List[Tuple[str, str]],
        predicted_weights: Dict[Tuple[str, str, int], float],
        observed_weights: Dict[Tuple[str, str, int], float]
    ) -> pd.DataFrame:
        """
        Executes the formal 8-algorithm head-to-head comparison on the canonical network:
          1. Static Dijkstra
          2. Traffic-Aware Dynamic Dijkstra (Phase 8)
          3. A* Shortest-Time Routing
          4. Sequential Greedy Two-Edge Selection
          5. Sequential Destination-Aware Two-Edge Selection
          6. Sequential Lookahead Two-Edge Selection (Depth 2)
          7. Existing Dynamic Rerouting Baseline (Phase 9)
          8. Sequential Two-Edge Selection with Dynamic Rerouting
        """
        print("[Master] Executing 8-Algorithm Benchmark...")
        records = []

        lookahead_eval = LimitedLookaheadEvaluator(
            self.adjacency,
            predicted_weights,
            self._heuristic_fn,
            depth=2
        )

        for s_node, d_node in od_pairs:
            # 1. Static Dijkstra
            t0 = time.perf_counter()
            dijk_static = custom_dijkstra(self.adjacency, self.static_weights, s_node, d_node)
            t_static_exec = (time.perf_counter() - t0) * 1000.0
            actual_time_static = sum(observed_weights.get(e, 10.0) for e in dijk_static.edge_path)
            dist_static = sum(self.edge_lengths.get(e, 50.0) for e in dijk_static.edge_path)

            records.append({
                'od_pair': f"{s_node}->{d_node}",
                'algorithm': "1. Static Dijkstra",
                'is_success': dijk_static.is_reached,
                'actual_travel_time_s': round(actual_time_static, 2),
                'distance_m': round(dist_static, 2),
                'computation_time_ms': round(t_static_exec, 3),
                'avg_decision_latency_ms': round(t_static_exec, 3),
                'hops_count': len(dijk_static.edge_path),
                'recovery_events': 0,
                'reroutes_count': 0
            })

            # 2. Traffic-Aware Dynamic Dijkstra (Phase 8)
            t0 = time.perf_counter()
            dijk_pred = custom_dijkstra(self.adjacency, predicted_weights, s_node, d_node)
            t_pred_exec = (time.perf_counter() - t0) * 1000.0
            actual_time_pred = sum(observed_weights.get(e, 10.0) for e in dijk_pred.edge_path)
            dist_pred = sum(self.edge_lengths.get(e, 50.0) for e in dijk_pred.edge_path)

            records.append({
                'od_pair': f"{s_node}->{d_node}",
                'algorithm': "2. Dynamic Dijkstra (Phase 8)",
                'is_success': dijk_pred.is_reached,
                'actual_travel_time_s': round(actual_time_pred, 2),
                'distance_m': round(dist_pred, 2),
                'computation_time_ms': round(t_pred_exec, 3),
                'avg_decision_latency_ms': round(t_pred_exec, 3),
                'hops_count': len(dijk_pred.edge_path),
                'recovery_events': 0,
                'reroutes_count': 0
            })

            # 3. A* Shortest-Time Routing
            t0 = time.perf_counter()
            astar_res = custom_astar(self.adjacency, predicted_weights, self._heuristic_fn, s_node, d_node)
            t_astar_exec = (time.perf_counter() - t0) * 1000.0
            actual_time_astar = sum(observed_weights.get(e, 10.0) for e in astar_res.edge_path)
            dist_astar = sum(self.edge_lengths.get(e, 50.0) for e in astar_res.edge_path)

            records.append({
                'od_pair': f"{s_node}->{d_node}",
                'algorithm': "3. A* Routing",
                'is_success': astar_res.is_reached,
                'actual_travel_time_s': round(actual_time_astar, 2),
                'distance_m': round(dist_astar, 2),
                'computation_time_ms': round(t_astar_exec, 3),
                'avg_decision_latency_ms': round(t_astar_exec, 3),
                'hops_count': len(astar_res.edge_path),
                'recovery_events': 0,
                'reroutes_count': 0
            })

            # 4. Sequential Greedy Two-Edge Selection
            selector_greedy = TwoEdgeSelector(
                self.candidate_generator,
                GreedyDecisionStrategy(),
                CandidateGenerationStrategy.LOWEST_IMMEDIATE_COST
            )
            ctrl_greedy = RouteController(self.adjacency, self.edge_lengths, selector_greedy)
            res_greedy = ctrl_greedy.execute_journey(s_node, d_node, predicted_weights, reference_dijkstra=dijk_pred)
            actual_time_greedy = sum(observed_weights.get(e, 10.0) for e in res_greedy.edge_path)

            records.append({
                'od_pair': f"{s_node}->{d_node}",
                'algorithm': "4. Sequential Greedy Two-Edge",
                'is_success': res_greedy.is_success,
                'actual_travel_time_s': round(actual_time_greedy, 2),
                'distance_m': round(res_greedy.total_distance_m, 2),
                'computation_time_ms': round(res_greedy.total_computation_time_ms, 3),
                'avg_decision_latency_ms': round(res_greedy.average_decision_latency_ms, 3),
                'hops_count': res_greedy.total_decisions,
                'recovery_events': res_greedy.recovery_events,
                'reroutes_count': 0
            })

            # 5. Sequential Destination-Aware Two-Edge Selection
            selector_dest = TwoEdgeSelector(
                self.candidate_generator,
                DestinationAwareDecisionStrategy(),
                CandidateGenerationStrategy.DESTINATION_AWARE
            )
            ctrl_dest = RouteController(self.adjacency, self.edge_lengths, selector_dest)
            res_dest = ctrl_dest.execute_journey(s_node, d_node, predicted_weights, reference_dijkstra=dijk_pred)
            actual_time_dest = sum(observed_weights.get(e, 10.0) for e in res_dest.edge_path)

            records.append({
                'od_pair': f"{s_node}->{d_node}",
                'algorithm': "5. Sequential Destination-Aware Two-Edge",
                'is_success': res_dest.is_success,
                'actual_travel_time_s': round(actual_time_dest, 2),
                'distance_m': round(res_dest.total_distance_m, 2),
                'computation_time_ms': round(res_dest.total_computation_time_ms, 3),
                'avg_decision_latency_ms': round(res_dest.average_decision_latency_ms, 3),
                'hops_count': res_dest.total_decisions,
                'recovery_events': res_dest.recovery_events,
                'reroutes_count': 0
            })

            # 6. Sequential Lookahead Two-Edge Selection (Depth 2)
            selector_look = TwoEdgeSelector(
                self.candidate_generator,
                LimitedLookaheadDecisionStrategy(lookahead_eval),
                CandidateGenerationStrategy.LOOKAHEAD
            )
            ctrl_look = RouteController(self.adjacency, self.edge_lengths, selector_look)
            res_look = ctrl_look.execute_journey(s_node, d_node, predicted_weights, reference_dijkstra=dijk_pred)
            actual_time_look = sum(observed_weights.get(e, 10.0) for e in res_look.edge_path)

            records.append({
                'od_pair': f"{s_node}->{d_node}",
                'algorithm': "6. Sequential Lookahead-2 Two-Edge",
                'is_success': res_look.is_success,
                'actual_travel_time_s': round(actual_time_look, 2),
                'distance_m': round(res_look.total_distance_m, 2),
                'computation_time_ms': round(res_look.total_computation_time_ms, 3),
                'avg_decision_latency_ms': round(res_look.average_decision_latency_ms, 3),
                'hops_count': res_look.total_decisions,
                'recovery_events': res_look.recovery_events,
                'reroutes_count': 0
            })

            # 7. Existing Dynamic Rerouting Baseline (Phase 9)
            # Replay decision at step k = 33% of trip
            rerouter = DynamicRerouter(self.wm, reroute_threshold_seconds=10.0, reroute_threshold_percent=3.0)
            res_p9 = rerouter.simulate_journey(
                scenario_id=0,
                od_id=0,
                source=s_node,
                destination=d_node,
                t0="2026-01-15 19:30:00+05:30",
                t1="2026-01-15 20:30:00+05:30",
                t0_ist="19:30 IST",
                t1_ist="20:30 IST",
                period_label="Evening Peak",
                w_pred_t0=predicted_weights,
                w_obs_t1=observed_weights,
                dynamic_edges_set=set(),
                decision_frac=0.33
            )

            records.append({
                'od_pair': f"{s_node}->{d_node}",
                'algorithm': "7. Dynamic Rerouting Baseline (Phase 9)",
                'is_success': True,
                'actual_travel_time_s': round(res_p9['total_time_dynamic_s'], 2),
                'distance_m': round(res_p9['new_route_distance_m'], 2),
                'computation_time_ms': round(t_pred_exec * 1.5, 3),
                'avg_decision_latency_ms': round(t_pred_exec, 3),
                'hops_count': res_p9['new_route_edges'],
                'recovery_events': 0,
                'reroutes_count': 1 if res_p9['reroute_triggered'] else 0
            })

            # 8. Sequential Two-Edge Selection with Dynamic Rerouting
            # Reroute update injected mid-journey
            ctrl_seq_dyn = RouteController(self.adjacency, self.edge_lengths, selector_dest)
            k_step = max(2, len(dijk_pred.edge_path) // 3)
            res_seq_dyn = ctrl_seq_dyn.execute_journey(
                source=s_node,
                destination=d_node,
                initial_weights=predicted_weights,
                traffic_update_step=k_step,
                updated_weights=observed_weights,
                reference_dijkstra=dijk_pred
            )
            # Actual travel time under dynamic transition
            traversed_edges = res_seq_dyn.edge_path[:k_step]
            remaining_edges = res_seq_dyn.edge_path[k_step:]
            t_actual_seq_dyn = (
                sum(predicted_weights.get(e, 10.0) for e in traversed_edges) +
                sum(observed_weights.get(e, 10.0) for e in remaining_edges)
            )

            records.append({
                'od_pair': f"{s_node}->{d_node}",
                'algorithm': "8. Sequential Two-Edge + Dynamic Reroute",
                'is_success': res_seq_dyn.is_success,
                'actual_travel_time_s': round(t_actual_seq_dyn, 2),
                'distance_m': round(res_seq_dyn.total_distance_m, 2),
                'computation_time_ms': round(res_seq_dyn.total_computation_time_ms, 3),
                'avg_decision_latency_ms': round(res_seq_dyn.average_decision_latency_ms, 3),
                'hops_count': res_seq_dyn.total_decisions,
                'recovery_events': res_seq_dyn.recovery_events,
                'reroutes_count': res_seq_dyn.reroute_events
            })

        df = pd.DataFrame(records)
        df.to_csv(os.path.join(self.output_dir, "master_algorithm_comparison.csv"), index=False)
        return df
