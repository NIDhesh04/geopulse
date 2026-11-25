"""Synchronized three-strategy simulation adapter around Phase 4's TemporalJourneyEngine.

Runs Static Dijkstra, Dynamic Dijkstra, and GeoPulse Two-Edge Selection against
the exact same graph, origin/destination pair, prediction frames, and realized
speed stream. Predicted speeds guide routing decisions at intersections;
realized speeds integrate vehicle movement along active links across time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

import networkx as nx
import pandas as pd

from src.experiments.temporal_journey import Edge, RouteTraceCounter, STRATEGIES, TemporalJourneyEngine
from src.pygame_simulation.scenario_manager import ScenarioManager
from src.routing.dijkstra import DijkstraResult
from src.routing.traffic_weights import GraphWeightManager
from src.simulation.vehicle import Vehicle
from src.traffic.replay import HistoricalTrafficReplay, TrafficReplayFrame


PROJECT_ROOT = Path(__file__).resolve().parents[2]

STRATEGY_LABELS: Dict[str, str] = {
    "static_dijkstra": "Static Dijkstra",
    "dynamic_dijkstra": "Dynamic Dijkstra",
    "geopulse_two_edge": "GeoPulse Two-Edge",
}


@dataclass
class TemporalScenarioBundle:
    """Self-contained scenario inputs for synchronized 3-strategy replay."""

    scenario_id: str
    title: str
    network_type: str  # "custom" | "osm"
    weight_manager: GraphWeightManager
    replay_frames: List[TrafficReplayFrame]
    node_coords: Dict[str, Tuple[float, float]]
    origin: str
    destination: str
    departure_timestamp: str
    default_sim_seconds_per_real_second: float
    highlight_nodes: Set[str] = field(default_factory=set)
    congested_note: str = ""
    edge_geometries: Dict[Edge, List[Tuple[float, float]]] = field(default_factory=dict)
    edge_highways: Dict[Edge, str] = field(default_factory=dict)
    edge_names: Dict[Edge, str] = field(default_factory=dict)
    dynamic_edges: Set[Edge] = field(default_factory=set)


def _clean_highway_tag(value: Any) -> str:
    if value is None:
        return "unclassified"
    text = str(value).strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1].split(",")[0].strip().strip("'\"")
    text = text.lower()
    for base in ("trunk", "primary", "secondary", "tertiary", "residential", "living_street", "unclassified"):
        if base in text:
            return base
    return text or "unclassified"


def _clean_name_tag(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    if text.startswith("[") and text.endswith("]"):
        parts = [p.strip().strip("'\"") for p in text[1:-1].split(",") if p.strip()]
        text = parts[0] if parts else ""
    return text


def _parse_wkt_linestring_latlon(
    wkt_text: Any,
    u_pt: Optional[Tuple[float, float]],
    v_pt: Optional[Tuple[float, float]],
) -> Optional[List[Tuple[float, float]]]:
    """Parse WKT LINESTRING(lon lat, ...) into [(lat, lon), ...] oriented u -> v."""
    if not wkt_text or not isinstance(wkt_text, str):
        return None
    stripped = wkt_text.strip()
    if not stripped.upper().startswith("LINESTRING"):
        return None
    lpar = stripped.find("(")
    rpar = stripped.rfind(")")
    if lpar == -1 or rpar <= lpar + 1:
        return None
    pts: List[Tuple[float, float]] = []
    for token in stripped[lpar + 1 : rpar].split(","):
        coords = token.strip().split()
        if len(coords) >= 2:
            try:
                lon = float(coords[0])
                lat = float(coords[1])
                pts.append((lat, lon))
            except ValueError:
                return None
    if len(pts) < 2:
        return None
    if u_pt is not None and v_pt is not None:
        d_fwd = abs(pts[0][0] - u_pt[0]) + abs(pts[0][1] - u_pt[1]) + abs(pts[-1][0] - v_pt[0]) + abs(pts[-1][1] - v_pt[1])
        d_rev = abs(pts[0][0] - v_pt[0]) + abs(pts[0][1] - v_pt[1]) + abs(pts[-1][0] - u_pt[0]) + abs(pts[-1][1] - u_pt[1])
        if d_rev < d_fwd:
            pts.reverse()
    return pts


def build_custom_temporal_bundle(congestion_level: str = "congested") -> TemporalScenarioBundle:
    """Build a TemporalJourneyEngine-backed bundle from the existing custom network."""
    base = ScenarioManager.create_custom_network_scenario(congestion_level=congestion_level)

    graph = nx.MultiDiGraph()
    for node_id, (x, y) in base.node_coords.items():
        graph.add_node(node_id, x=float(x), y=float(y))

    mapping_rows: List[Dict[str, Any]] = []
    segment_initial_speeds: Dict[int, float] = {}
    segment_updated_speeds: Dict[int, float] = {}
    for seg_id, ((u, v, key), length_m) in enumerate(sorted(base.edge_lengths.items()), start=1):
        graph.add_edge(u, v, key=key, length=float(length_m), highway="primary")
        mapping_rows.append(
            {
                "traffic_segment_id": seg_id,
                "u": str(u),
                "v": str(v),
                "key": int(key),
                "routing_eligibility": "DYNAMIC",
            }
        )
        init_spd = float(base.initial_speeds[(u, v, key)])
        upd_spd = float((base.updated_speeds or base.initial_speeds)[(u, v, key)])
        segment_initial_speeds[seg_id] = init_spd
        segment_updated_speeds[seg_id] = upd_spd

    mapping_df = pd.DataFrame(mapping_rows)
    weight_manager = GraphWeightManager(graph, mapping_df)

    # Frame 0 (origin 08:00Z -> valid [09:00Z, 10:00Z)): pre-incident flow.
    # Predicted speeds and realized speeds are stored separately so predictions
    # guide routing while realized speeds govern vehicle motion.
    # Frame 1 (origin 09:00Z -> valid [10:00Z, 11:00Z)): incident on ('2','4',0).
    # Forecast speed drops to 9.0 km/h while realized speed drops to 8.0 km/h.
    rows: List[Dict[str, Any]] = []
    for seg_id in sorted(segment_initial_speeds):
        init_pred = segment_initial_speeds[seg_id]
        init_real = max(3.0, init_pred - (1.0 if seg_id % 2 == 1 else 0.0))
        rows.append(
            {
                "timestamp": "2026-01-15T08:00:00Z",
                "traffic_segment_id": seg_id,
                "predicted_speed": init_pred,
                "actual_speed": init_real,
            }
        )

        upd_real = segment_updated_speeds[seg_id]
        # Distinct predicted forecast for incident link while preserving updated bottleneck
        if congestion_level == "congested" and upd_real < init_pred:
            upd_pred = upd_real + 1.0
        else:
            upd_pred = upd_real
            upd_real = max(3.0, upd_real - (1.0 if seg_id % 2 == 1 else 0.0))
        rows.append(
            {
                "timestamp": "2026-01-15T09:00:00Z",
                "traffic_segment_id": seg_id,
                "predicted_speed": upd_pred,
                "actual_speed": upd_real,
            }
        )

    replay = HistoricalTrafficReplay(pd.DataFrame(rows))
    frames = [replay.get_frame(ts) for ts in replay.available_timestamps]

    edge_geometries: Dict[Edge, List[Tuple[float, float]]] = {}
    edge_highways: Dict[Edge, str] = {}
    edge_names: Dict[Edge, str] = {}
    for u, v, key in weight_manager.edge_lengths:
        if u in base.node_coords and v in base.node_coords:
            edge_geometries[(u, v, key)] = [base.node_coords[u], base.node_coords[v]]
        edge_highways[(u, v, key)] = "primary" if u in ("1", "2", "4") and v in ("2", "4", "6") else "secondary"
        edge_names[(u, v, key)] = f"Link {u}-{v}"

    return TemporalScenarioBundle(
        scenario_id=base.scenario_id,
        title="Custom Urban Dual-Corridor Grid (Synchronized 3-Strategy Comparison)",
        network_type="custom",
        weight_manager=weight_manager,
        replay_frames=frames,
        node_coords=dict(base.node_coords),
        origin=base.source_node,
        destination=base.destination_node,
        # Depart 5 seconds before 10:00:00Z update becomes valid so all three vehicles
        # commit to initial route on 0->1 and receive update at intersection 1.
        departure_timestamp="2026-01-15T09:59:55Z",
        default_sim_seconds_per_real_second=8.0,
        congested_note="Update @ +5s: Corridor 2->4 degrades to 8.0 km/h",
        edge_geometries=edge_geometries,
        edge_highways=edge_highways,
        edge_names=edge_names,
        dynamic_edges=set(weight_manager.dynamic_edge_segments.keys()),
    )


def build_osm_temporal_bundle(
    od_id: int = 0,
    departure_timestamp: str = "2026-01-15T15:59:00Z",
    graph_path: str = "data/raw/osm/bhubaneswar_drive.graphml",
    mapping_path: str = "data/processed/traffic_to_osm_mapping_final.parquet",
    predictions_path: str = "results/phase7_predictions.parquet",
    od_pairs_path: str = "results/phase8_od_pairs.csv",
) -> TemporalScenarioBundle:
    """Load real Bhubaneswar OSM graph + saved Phase 7 replay frames for one OD pair."""
    g_path = (PROJECT_ROOT / graph_path).resolve()
    m_path = (PROJECT_ROOT / mapping_path).resolve()
    p_path = (PROJECT_ROOT / predictions_path).resolve()
    o_path = (PROJECT_ROOT / od_pairs_path).resolve()

    G = nx.read_graphml(g_path)
    mapping_df = pd.read_parquet(m_path)
    weight_manager = GraphWeightManager(G, mapping_df)
    replay = HistoricalTrafficReplay(p_path)
    frames = [replay.get_frame(ts) for ts in replay.available_timestamps]

    od_df = pd.read_csv(o_path, dtype={"source_node": str, "destination_node": str})
    match = od_df[od_df["od_id"] == int(od_id)]
    if match.empty:
        raise ValueError(f"OD id {od_id} not found in {o_path}")
    row = match.iloc[0]

    def _clean_node_id(val: Any) -> str:
        text = str(val).strip()
        if text.endswith(".0") and text[:-2].lstrip("-").isdigit():
            text = text[:-2]
        return text

    origin = _clean_node_id(row["source_node"])
    destination = _clean_node_id(row["destination_node"])

    node_coords: Dict[str, Tuple[float, float]] = {}
    for n, d in G.nodes(data=True):
        node_coords[str(n)] = (float(d.get("y", 0.0)), float(d.get("x", 0.0)))

    edge_geometries: Dict[Edge, List[Tuple[float, float]]] = {}
    edge_highways: Dict[Edge, str] = {}
    edge_names: Dict[Edge, str] = {}
    for u_raw, v_raw, key, data in G.edges(keys=True, data=True):
        edge = (str(u_raw), str(v_raw), key)
        u_pt = node_coords.get(edge[0])
        v_pt = node_coords.get(edge[1])
        parsed = _parse_wkt_linestring_latlon(data.get("geometry"), u_pt, v_pt)
        if parsed is not None:
            edge_geometries[edge] = parsed
        elif u_pt is not None and v_pt is not None:
            edge_geometries[edge] = [u_pt, v_pt]
        edge_highways[edge] = _clean_highway_tag(data.get("highway"))
        edge_names[edge] = _clean_name_tag(data.get("name"))

    return TemporalScenarioBundle(
        scenario_id=f"osm_od_{od_id}",
        title=f"Bhubaneswar OSM Network (OD #{od_id}: {origin} -> {destination})",
        network_type="osm",
        weight_manager=weight_manager,
        replay_frames=frames,
        node_coords=node_coords,
        origin=origin,
        destination=destination,
        departure_timestamp=departure_timestamp,
        default_sim_seconds_per_real_second=60.0,
        congested_note="Hourly Phase 7 forecast + realized speed stream",
        edge_geometries=edge_geometries,
        edge_highways=edge_highways,
        edge_names=edge_names,
        dynamic_edges=set(weight_manager.dynamic_edge_segments.keys()),
    )


@dataclass
class StrategyAgentState:
    """Runtime execution state for one routing strategy on the shared clock."""

    strategy: str
    display_name: str
    origin: str
    destination: str
    vehicle: Vehicle
    route_trace: RouteTraceCounter
    current_time: pd.Timestamp
    current_node: str
    visited: Set[str]
    planned_edges: List[Edge]
    fixed_route_edges: List[Edge]
    fixed_cursor: int = 0
    last_prediction_index: Optional[int] = None

    # Active segment kinematics
    active_edge: Optional[Edge] = None
    active_edge_length_m: float = 0.0
    active_edge_traversed_m: float = 0.0
    active_edge_remaining_m: float = 0.0
    active_edge_realized_speed_kmh: float = 0.0

    # Metrics aligned with TemporalJourneyResult
    intersection_decisions: int = 0
    two_edge_alternative_selections: int = 0
    prediction_updates_applied: int = 0
    dijkstra_reroutes: int = 0
    dijkstra_fallback_steps: int = 0

    # UI telemetry
    status_label: str = "READY"
    decision_reason: str = "Initializing departure route..."
    candidate_a: Optional[Edge] = None
    score_a: Optional[float] = None
    pred_time_a: Optional[float] = None
    tail_cost_a: Optional[float] = None
    candidate_b: Optional[Edge] = None
    score_b: Optional[float] = None
    pred_time_b: Optional[float] = None
    tail_cost_b: Optional[float] = None
    selected_candidate_slot: str = "A"
    last_update_applied_node: Optional[str] = None
    last_update_applied_time: Optional[str] = None

    arrived: bool = False
    failed: bool = False
    failure_reason: str = ""

    @property
    def next_junction(self) -> str:
        if self.active_edge is not None and not self.arrived:
            return str(self.active_edge[1])
        return str(self.current_node)

    @property
    def edge_progress(self) -> float:
        if self.active_edge is None or self.active_edge_length_m <= 0.0:
            return 0.0
        return max(0.0, min(1.0, self.active_edge_traversed_m / self.active_edge_length_m))

    @property
    def elapsed_time_s(self) -> float:
        return float(self.vehicle.elapsed_travel_time_s)

    @property
    def distance_m(self) -> float:
        return float(self.vehicle.accumulated_distance_m)

    @property
    def traversed_edges(self) -> List[Edge]:
        return list(self.vehicle.temporal_traversed_edges)


class ThreeStrategySimulation:
    """Synchronized three-panel temporal simulation built atop TemporalJourneyEngine."""

    def __init__(self, bundle: TemporalScenarioBundle):
        self.bundle = bundle
        self.engine = TemporalJourneyEngine(bundle.weight_manager, bundle.replay_frames)
        self.departure_time = self.engine._timestamp(bundle.departure_timestamp)
        self.base_sim_sec_per_real_sec = float(bundle.default_sim_seconds_per_real_second)
        self.speed_multiplier: float = 1.0
        self.is_paused: bool = False
        self.agents: Dict[str, StrategyAgentState] = {}
        self.sim_time: pd.Timestamp = self.departure_time
        self.sim_elapsed_s: float = 0.0
        self.active_frame_index: int = 0
        self.initial_frame_index: int = 0
        self.reset()

    def reset(self) -> None:
        """Reset all three routing strategies to the shared origin and departure clock."""
        self.sim_time = self.departure_time
        self.sim_elapsed_s = 0.0
        self.initial_frame_index = self.engine._frame_index_at(self.departure_time)
        self.active_frame_index = self.initial_frame_index
        init_weights = self.engine._prediction_weights(self.initial_frame_index)
        init_route: DijkstraResult = self.engine._route(
            self.bundle.origin, self.bundle.destination, init_weights
        )

        self.agents = {}
        for strategy in STRATEGIES:
            vehicle = Vehicle(
                vehicle_id=f"sim_{strategy}",
                origin=self.bundle.origin,
                destination=self.bundle.destination,
                departure_time=self.departure_time.isoformat(),
            )
            route_trace = RouteTraceCounter(self.bundle.origin)
            state = StrategyAgentState(
                strategy=strategy,
                display_name=STRATEGY_LABELS[strategy],
                origin=self.bundle.origin,
                destination=self.bundle.destination,
                vehicle=vehicle,
                route_trace=route_trace,
                current_time=self.departure_time,
                current_node=self.bundle.origin,
                visited={self.bundle.origin},
                planned_edges=list(init_route.edge_path) if init_route.is_reached else [],
                fixed_route_edges=list(init_route.edge_path) if init_route.is_reached else [],
                last_prediction_index=self.initial_frame_index,
            )

            if not init_route.is_reached:
                state.failed = True
                state.failure_reason = "destination_unreachable_at_departure"
                state.status_label = "UNREACHABLE"
            elif self.bundle.origin == self.bundle.destination:
                vehicle.begin_temporal_journey(
                    [self.bundle.origin], [], self.departure_time.isoformat()
                )
                vehicle.finish_temporal_journey(self.departure_time.isoformat())
                state.arrived = True
                state.status_label = "ARRIVED"
                state.decision_reason = "Origin equals destination."
            else:
                vehicle.begin_temporal_journey(
                    list(init_route.node_path),
                    list(init_route.edge_path),
                    self.departure_time.isoformat(),
                )
                self._choose_next_edge(state)

            self.agents[strategy] = state

    @property
    def all_finished(self) -> bool:
        return all(agent.arrived or agent.failed for agent in self.agents.values())

    @property
    def update_became_valid(self) -> bool:
        return self.active_frame_index != self.initial_frame_index

    def current_realized_speeds(self) -> Dict[Edge, float]:
        """Realized road speeds at the shared simulation clock (for traffic layer coloring)."""
        idx = self.engine._frame_index_at(min(self.sim_time, self.engine.final_valid_until - pd.Timedelta(microseconds=1)))
        return self.engine._realized_speeds_for(idx)

    def current_predicted_speeds(self) -> Dict[Edge, float]:
        """Predicted speeds at the shared simulation clock."""
        idx = self.engine._frame_index_at(min(self.sim_time, self.engine.final_valid_until - pd.Timedelta(microseconds=1)))
        _, pred_speeds, _ = self.bundle.weight_manager.build_scenario_weights(
            self.engine.frames[idx].predicted_speeds
        )
        return pred_speeds

    def _choose_next_edge(self, state: StrategyAgentState) -> None:
        """Select the next edge at state.current_node using only predicted weights."""
        if state.arrived or state.failed:
            return
        if state.current_node == state.destination:
            state.vehicle.finish_temporal_journey(state.current_time.isoformat())
            state.active_edge = None
            state.arrived = True
            state.status_label = "ARRIVED"
            state.decision_reason = f"Reached destination in {state.elapsed_time_s:.1f}s."
            return

        try:
            frame_index = self.engine._frame_index_at(state.current_time)
            weights = self.engine._prediction_weights(frame_index)
        except ValueError as exc:
            state.failed = True
            state.failure_reason = f"realized_traffic_unavailable:{exc}"
            state.status_label = "HORIZON END"
            return

        selected_edge: Optional[Edge] = None
        fallback_step = False
        current = state.current_node
        destination = state.destination

        if state.strategy == "static_dijkstra":
            if state.fixed_cursor >= len(state.fixed_route_edges):
                state.failed = True
                state.failure_reason = "fixed_route_exhausted_before_destination"
                state.status_label = "FAILED"
                return
            selected_edge = state.fixed_route_edges[state.fixed_cursor]
            state.fixed_cursor += 1
            state.candidate_a = selected_edge
            state.candidate_b = None
            state.score_a = float(weights.get(selected_edge, 0.0))
            state.pred_time_a = state.score_a
            state.tail_cost_a = None
            state.score_b = None
            state.pred_time_b = None
            state.tail_cost_b = None
            state.selected_candidate_slot = "A"
            state.status_label = f"FIXED {selected_edge[0]}->{selected_edge[1]}"
            state.decision_reason = f"Fixed initial Dijkstra plan ({selected_edge[0]}->{selected_edge[1]})."

        elif state.strategy == "dynamic_dijkstra":
            rerouted_here = False
            if frame_index != state.last_prediction_index:
                reroute = self.engine._route(current, destination, weights, state.visited)
                state.prediction_updates_applied += 1
                state.last_update_applied_node = current
                state.last_update_applied_time = state.current_time.strftime("%H:%M:%S UTC")
                old_edges = list(state.planned_edges)
                if not reroute.is_reached:
                    reroute = self.engine._route(current, destination, weights)
                if not reroute.is_reached or not reroute.edge_path:
                    state.failed = True
                    state.failure_reason = "destination_unreachable_after_traffic_update"
                    state.status_label = "FAILED"
                    return
                state.planned_edges = list(reroute.edge_path)
                state.last_prediction_index = frame_index
                if state.planned_edges != old_edges:
                    state.dijkstra_reroutes += 1
                    rerouted_here = True
                route_nodes = self.engine._nodes_for_edges(current, state.planned_edges)
                state.vehicle.set_temporal_plan(
                    route_nodes,
                    state.planned_edges,
                    state.current_time.isoformat(),
                    "Dynamic Dijkstra recomputed at intersection after traffic update",
                )
            if not state.planned_edges:
                state.failed = True
                state.failure_reason = "dynamic_route_exhausted_before_destination"
                state.status_label = "FAILED"
                return
            selected_edge = state.planned_edges.pop(0)
            state.candidate_a = selected_edge
            state.candidate_b = None
            state.score_a = float(weights.get(selected_edge, 0.0))
            state.pred_time_a = state.score_a
            state.tail_cost_a = None
            state.score_b = None
            state.pred_time_b = None
            state.tail_cost_b = None
            state.selected_candidate_slot = "A"
            if rerouted_here:
                state.status_label = f"REROUTED -> {selected_edge[1]}"
                state.decision_reason = f"Traffic update applied at {current}: rerouted via {selected_edge[0]}->{selected_edge[1]}."
            else:
                state.status_label = f"MOVING {selected_edge[0]}->{selected_edge[1]}"
                state.decision_reason = f"Follow dynamic Dijkstra plan along {selected_edge[0]}->{selected_edge[1]}."

        else:
            if frame_index != state.last_prediction_index:
                state.prediction_updates_applied += 1
                state.last_prediction_index = frame_index
                state.last_update_applied_node = current
                state.last_update_applied_time = state.current_time.strftime("%H:%M:%S UTC")
            selected_edge, new_plan, choice, forced, is_decision = self.engine._two_edge_choice(
                current, destination, state.planned_edges, weights, state.visited
            )
            if selected_edge is None:
                fallback = self.engine._route(current, destination, weights, state.visited)
                if not fallback.is_reached or not fallback.edge_path:
                    fallback = self.engine._route(current, destination, weights)
                if not fallback.is_reached or not fallback.edge_path:
                    state.failed = True
                    state.failure_reason = "no_reachable_two_edge_candidate_or_fallback"
                    state.status_label = "FAILED"
                    return
                selected_edge = fallback.edge_path[0]
                new_plan = list(fallback.edge_path)
                fallback_step = True
                state.dijkstra_fallback_steps += 1
                state.candidate_a = selected_edge
                state.candidate_b = None
                state.score_a = float(fallback.total_cost)
                state.pred_time_a = float(weights.get(selected_edge, 0.0))
                state.tail_cost_a = max(0.0, state.score_a - state.pred_time_a)
                state.score_b = None
                state.pred_time_b = None
                state.tail_cost_b = None
                state.selected_candidate_slot = "A"
                state.status_label = f"FALLBACK {selected_edge[0]}->{selected_edge[1]}"
                state.decision_reason = "Safety Dijkstra fallback from dead end."
            else:
                cand_a = choice.get("candidate_a")
                cand_b = choice.get("candidate_b")
                state.candidate_a = cand_a
                state.candidate_b = cand_b
                state.score_a = choice.get("score_a")
                state.score_b = choice.get("score_b")
                state.pred_time_a = float(weights[cand_a]) if (cand_a and cand_a in weights) else None
                state.tail_cost_a = (
                    max(0.0, float(state.score_a) - float(state.pred_time_a))
                    if state.score_a is not None and state.pred_time_a is not None
                    else None
                )
                state.pred_time_b = float(weights[cand_b]) if (cand_b and cand_b in weights) else None
                state.tail_cost_b = (
                    max(0.0, float(state.score_b) - float(state.pred_time_b))
                    if state.score_b is not None and state.pred_time_b is not None
                    else None
                )
                if is_decision:
                    state.intersection_decisions += 1
                    if selected_edge == cand_b:
                        state.two_edge_alternative_selections += 1
                        state.selected_candidate_slot = "B"
                        state.status_label = f"2-EDGE ALT -> {selected_edge[1]}"
                        state.decision_reason = (
                            f"Alternative edge {cand_b[0]}->{cand_b[1]} ({state.score_b:.1f}s) "
                            f"beats planned {cand_a[0]}->{cand_a[1]} ({state.score_a:.1f}s)."
                        )
                    else:
                        state.selected_candidate_slot = "A"
                        state.status_label = f"2-EDGE A -> {selected_edge[1]}"
                        state.decision_reason = (
                            f"Planned edge {cand_a[0]}->{cand_a[1]} ({state.score_a:.1f}s) "
                            f"beats alternative {cand_b[0]}->{cand_b[1]} ({state.score_b:.1f}s)."
                        )
                else:
                    state.selected_candidate_slot = "A"
                    state.status_label = f"FORCED -> {selected_edge[1]}"
                    state.decision_reason = (
                        f"Forced single reachable corridor {selected_edge[0]}->{selected_edge[1]} "
                        f"(total predicted cost {state.score_a:.1f}s)."
                    )
            state.planned_edges = list(new_plan)
            route_nodes = self.engine._nodes_for_edges(current, state.planned_edges)
            state.vehicle.set_temporal_plan(
                route_nodes,
                state.planned_edges,
                state.current_time.isoformat(),
                state.decision_reason,
            )

        if selected_edge is None or str(selected_edge[0]) != current:
            state.failed = True
            state.failure_reason = f"invalid_selected_edge:{selected_edge!r}"
            state.status_label = "FAILED"
            return

        edge_length = float(self.bundle.weight_manager.edge_lengths[selected_edge])
        realized_speed = float(self.engine._realized_speeds_for(frame_index)[selected_edge])
        state.active_edge = selected_edge
        state.active_edge_length_m = edge_length
        state.active_edge_traversed_m = 0.0
        state.active_edge_remaining_m = edge_length
        state.active_edge_realized_speed_kmh = realized_speed
        state._current_edge_elapsed_s = 0.0  # track exact realized edge duration

    def _advance_agent(self, state: StrategyAgentState, sim_dt_s: float) -> None:
        """Advance one strategy vehicle across sim_dt_s realized seconds."""
        if state.arrived or state.failed or sim_dt_s <= 0.0:
            return

        remaining_dt = float(sim_dt_s)
        edge_elapsed = getattr(state, "_current_edge_elapsed_s", 0.0)
        clock_elapsed = getattr(
            state,
            "_clock_elapsed_s",
            (state.current_time - self.departure_time).total_seconds(),
        )

        # Quantization-safe loop threshold slightly above 1 nanosecond (pd.Timestamp precision).
        while remaining_dt > 1e-8 and not state.arrived and not state.failed:
            edge = state.active_edge
            if edge is None:
                self._choose_next_edge(state)
                edge_elapsed = getattr(state, "_current_edge_elapsed_s", 0.0)
                if state.active_edge is None:
                    break
                edge = state.active_edge

            try:
                frame_index = self.engine._frame_index_at(state.current_time)
                speed_kmh = float(self.engine._realized_speeds_for(frame_index)[edge])
            except (RuntimeError, ValueError) as exc:
                state.failed = True
                state.failure_reason = f"realized_traffic_unavailable:{exc}"
                state.status_label = "HORIZON END"
                break

            speed_mps = speed_kmh / 3.6
            if speed_mps <= 0.0:
                state.failed = True
                state.failure_reason = f"invalid_realized_speed:{edge!r}"
                state.status_label = "FAILED"
                break

            state.active_edge_realized_speed_kmh = speed_kmh
            boundary = (
                self.engine.valid_times[frame_index + 1]
                if frame_index + 1 < len(self.engine.valid_times)
                else self.engine.final_valid_until
            )
            boundary_elapsed = (boundary - self.departure_time).total_seconds()
            available_s = boundary_elapsed - clock_elapsed
            if available_s <= 1e-9:
                clock_elapsed = boundary_elapsed
                state._clock_elapsed_s = clock_elapsed
                state.current_time = boundary
                continue

            step_dt = min(remaining_dt, available_s)
            possible_m = speed_mps * step_dt

            if state.active_edge_remaining_m <= possible_m + 1e-9:
                used_dt = min(step_dt, state.active_edge_remaining_m / speed_mps)
                edge_elapsed += used_dt
                clock_elapsed += used_dt
                state._clock_elapsed_s = clock_elapsed
                if abs(clock_elapsed - boundary_elapsed) <= 1e-9 or clock_elapsed >= boundary_elapsed:
                    clock_elapsed = boundary_elapsed
                    state._clock_elapsed_s = clock_elapsed
                    state.current_time = boundary
                else:
                    state.current_time = self.departure_time + pd.to_timedelta(
                        round(clock_elapsed * 1_000_000_000), unit="ns"
                    )
                state.active_edge_traversed_m = state.active_edge_length_m
                state.active_edge_remaining_m = 0.0

                # Commit realized link traversal identically to TemporalJourneyEngine
                state.vehicle.record_realized_edge_traversal(
                    edge,
                    max(edge_elapsed, 1e-9),
                    state.active_edge_length_m,
                    state.current_time.isoformat(),
                )
                state.route_trace.record(edge)
                next_node = str(edge[1])
                state.visited.add(next_node)
                state.current_node = next_node
                if (
                    state.strategy == "geopulse_two_edge"
                    and state.planned_edges
                    and state.planned_edges[0] == edge
                ):
                    state.planned_edges.pop(0)

                remaining_dt = max(0.0, remaining_dt - used_dt)
                state._current_edge_elapsed_s = 0.0
                self._choose_next_edge(state)
                edge_elapsed = getattr(state, "_current_edge_elapsed_s", 0.0)
            else:
                state.active_edge_traversed_m += possible_m
                state.active_edge_remaining_m -= possible_m
                edge_elapsed += step_dt
                state._current_edge_elapsed_s = edge_elapsed
                clock_elapsed += step_dt
                state._clock_elapsed_s = clock_elapsed
                if remaining_dt >= available_s - 1e-12 or clock_elapsed >= boundary_elapsed - 1e-9:
                    clock_elapsed = boundary_elapsed
                    state._clock_elapsed_s = clock_elapsed
                    state.current_time = boundary
                else:
                    state.current_time = self.departure_time + pd.to_timedelta(
                        round(clock_elapsed * 1_000_000_000), unit="ns"
                    )
                remaining_dt = max(0.0, remaining_dt - step_dt)

    def update(self, real_dt_s: float) -> None:
        """Advance the synchronized simulation clock by real wall-clock dt."""
        if self.is_paused or self.all_finished or real_dt_s <= 0.0:
            return
        sim_dt_s = float(real_dt_s) * self.base_sim_sec_per_real_sec * self.speed_multiplier
        self.step_sim(sim_dt_s)

    def step_sim(self, sim_dt_s: float) -> None:
        """Advance all three vehicles synchronously by an explicit number of sim seconds."""
        if self.all_finished or sim_dt_s <= 0.0:
            return

        # Compute actual max advance needed so global sim_elapsed_s stops cleanly when all finish
        pre_done = self.all_finished
        for strategy in STRATEGIES:
            self._advance_agent(self.agents[strategy], sim_dt_s)

        if not pre_done:
            # If all three have arrived/failed, lock clock to latest completion timestamp
            if self.all_finished:
                latest_t = max(agent.current_time for agent in self.agents.values())
                self.sim_time = latest_t
                self.sim_elapsed_s = max(0.0, (latest_t - self.departure_time).total_seconds())
            else:
                self.sim_time += pd.to_timedelta(sim_dt_s, unit="s")
                self.sim_elapsed_s += sim_dt_s

        probe_time = min(self.sim_time, self.engine.final_valid_until - pd.Timedelta(microseconds=1))
        self.active_frame_index = self.engine._frame_index_at(probe_time)

    def live_elapsed_s(self, strategy: str) -> float:
        """Return live elapsed time including mid-edge progress for smooth HUD counters."""
        agent = self.agents[strategy]
        in_flight = getattr(agent, "_current_edge_elapsed_s", 0.0) if not (agent.arrived or agent.failed) else 0.0
        return float(agent.elapsed_time_s + in_flight)

    def live_distance_m(self, strategy: str) -> float:
        """Return live accumulated distance including mid-edge progress."""
        agent = self.agents[strategy]
        in_flight = agent.active_edge_traversed_m if (agent.active_edge and not (agent.arrived or agent.failed)) else 0.0
        return float(agent.distance_m + in_flight)

    def get_comparison_rows(self) -> List[Dict[str, Any]]:
        """Return live or final comparison metrics across all three strategies."""
        static_agent = self.agents["static_dijkstra"]
        static_time = (
            self.live_elapsed_s("static_dijkstra")
            if (static_agent.arrived and not static_agent.failed)
            else None
        )

        rows: List[Dict[str, Any]] = []
        for strategy in STRATEGIES:
            agent = self.agents[strategy]
            t_s = self.live_elapsed_s(strategy)
            d_m = self.live_distance_m(strategy)
            saved_s: Optional[float] = None
            saved_pct: Optional[float] = None
            if (
                static_time is not None
                and static_time > 0.0
                and agent.arrived
                and not agent.failed
                and strategy != "static_dijkstra"
            ):
                saved_s = static_time - t_s
                saved_pct = (saved_s / static_time) * 100.0

            rows.append(
                {
                    "strategy": strategy,
                    "label": agent.display_name,
                    "status": agent.status_label,
                    "arrived": agent.arrived,
                    "failed": agent.failed,
                    "elapsed_time_s": t_s,
                    "distance_m": d_m,
                    "saved_vs_static_s": saved_s,
                    "saved_vs_static_pct": saved_pct,
                    "edges_traversed": len(agent.traversed_edges),
                    "updates_applied": agent.prediction_updates_applied,
                    "reroutes": agent.dijkstra_reroutes,
                    "two_edge_decisions": agent.intersection_decisions,
                    "two_edge_alt_selections": agent.two_edge_alternative_selections,
                    "fallback_steps": agent.dijkstra_fallback_steps,
                    "backtracking_events": agent.route_trace.backtracking_events,
                }
            )
        return rows
