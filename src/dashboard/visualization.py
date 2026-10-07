"""
GeoPulse Phase 11B: Interactive Dashboard Visualizations Engine

Generates geographically accurate maps and timelines using the true OSM graph:
- High-resolution Matplotlib route geometry maps with vehicle scrubber puck
- Interactive Pydeck 3D/2D GIS layers for pan/zoom/tilt exploration
- Visual milestone journey timelines
- Architecture tier status cards
"""

import os
from typing import Dict, List, Tuple, Any, Optional
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import networkx as nx
from shapely import wkt
import pydeck as pdk


# Professional styling tokens
COLOR_BASE_ROAD = '#cbd5e1'
COLOR_TRAVERSED = '#0284c7'       # Ocean Blue
COLOR_CONGESTED = '#ef4444'       # Crimson Red
COLOR_REROUTE = '#10b981'         # Emerald Green
COLOR_ORIGIN = '#2563eb'          # Royal Blue
COLOR_DESTINATION = '#059669'     # Forest Green
COLOR_DECISION = '#f59e0b'        # Amber Orange
COLOR_VEHICLE = '#e11d48'         # Bright Rose Puck


def _extract_edge_coords(G: nx.MultiDiGraph, u: str, v: str, k: int = 0) -> List[Tuple[float, float]]:
    """Extracts (lon, lat) list for an edge from geometry WKT or node coordinates."""
    data = G.get_edge_data(u, v, k, default={})
    if 'geometry' in data:
        try:
            geom = wkt.loads(data['geometry'])
            return list(geom.coords)
        except Exception:
            pass
    u_d = G.nodes.get(u, {})
    v_d = G.nodes.get(v, {})
    x1 = float(u_d.get('x', u_d.get('lon', 0.0)))
    y1 = float(u_d.get('y', u_d.get('lat', 0.0)))
    x2 = float(v_d.get('x', v_d.get('lon', 0.0)))
    y2 = float(v_d.get('y', v_d.get('lat', 0.0)))
    return [(x1, y1), (x2, y2)]


def render_route_map_matplotlib(
    G: nx.MultiDiGraph,
    run_result: Dict[str, Any],
    current_step: Optional[int] = None,
    dark_mode: bool = False
) -> plt.Figure:
    """
    Renders the geographically accurate Bhubaneswar road network and dynamic routing state.

    Parameters
    ----------
    G : nx.MultiDiGraph
        Bhubaneswar OSM graph.
    run_result : Dict[str, Any]
        Output dictionary from run_geopulse_pipeline.
    current_step : Optional[int]
        Playback scrubber step (0 to total route edges). If None, shows full final route.
    dark_mode : bool
        If True, applies sleek dark-mode styling.
    """
    initial_edges = run_result['initial_route_edges']
    final_edges = run_result['final_route_edges']
    decision_step = run_result['decision_step']
    source_node = run_result['origin_node']
    dest_node = run_result['destination_node']
    decision_node = run_result['decision_node']
    reroute_triggered = run_result['reroute_triggered']

    active_route_edges = final_edges if (reroute_triggered and (current_step is None or current_step >= decision_step)) else initial_edges
    active_route_nodes = run_result['final_route_nodes'] if (reroute_triggered and (current_step is None or current_step >= decision_step)) else run_result['initial_route_nodes']

    total_steps = len(active_route_edges)
    step = total_steps if current_step is None else min(max(0, current_step), total_steps)

    # Figure theme colors
    bg_color = '#0f172a' if dark_mode else '#ffffff'
    net_color = '#334155' if dark_mode else '#e2e8f0'
    text_color = '#f8fafc' if dark_mode else '#0f172a'
    spine_color = '#475569' if dark_mode else '#cbd5e1'

    fig, ax = plt.subplots(figsize=(11, 8.5), facecolor=bg_color)
    ax.set_facecolor(bg_color)

    # Determine geographic bounding box with padding
    all_nodes = [source_node, dest_node, decision_node]
    for e in initial_edges + final_edges:
        all_nodes.extend([e[0], e[1]])
    all_nodes = list(set(all_nodes))

    lons = [float(G.nodes[n].get('x', G.nodes[n].get('lon', 0.0))) for n in all_nodes if n in G.nodes]
    lats = [float(G.nodes[n].get('y', G.nodes[n].get('lat', 0.0))) for n in all_nodes if n in G.nodes]

    pad = 0.009
    min_lon, max_lon = min(lons) - pad, max(lons) + pad
    min_lat, max_lat = min(lats) - pad, max(lats) + pad

    # 1. Background physical road network
    for u, v, k, d in G.edges(keys=True, data=True):
        coords = _extract_edge_coords(G, u, v, k)
        xs, ys = zip(*coords)
        if min_lon <= min(xs) <= max_lon and min_lat <= min(ys) <= max_lat:
            ax.plot(xs, ys, color=net_color, linewidth=0.75, alpha=0.65, zorder=1)

    # 2. Abandoned congested corridor (Red dashed) if rerouted
    if reroute_triggered:
        abandoned_edges = initial_edges[decision_step:]
        first_aband = True
        for e in abandoned_edges:
            coords = _extract_edge_coords(G, e[0], e[1], e[2] if len(e) > 2 else 0)
            xs, ys = zip(*coords)
            ax.plot(xs, ys, color=COLOR_CONGESTED, linewidth=3.5, linestyle='--', alpha=0.9, zorder=3,
                    label='Observed Congestion (Abandoned Corridor)' if first_aband else "")
            first_aband = False

    # 3. Dynamic Reroute Bypass (Green solid)
    if reroute_triggered:
        reroute_bypass_edges = final_edges[decision_step:]
        first_reroute = True
        for e in reroute_bypass_edges:
            coords = _extract_edge_coords(G, e[0], e[1], e[2] if len(e) > 2 else 0)
            xs, ys = zip(*coords)
            ax.plot(xs, ys, color=COLOR_REROUTE, linewidth=3.8, alpha=0.95, zorder=4,
                    label='GeoPulse Dynamic Bypass' if first_reroute else "")
            first_reroute = False
    else:
        # Initial predicted route when not rerouted
        first_init = True
        for e in initial_edges:
            coords = _extract_edge_coords(G, e[0], e[1], e[2] if len(e) > 2 else 0)
            xs, ys = zip(*coords)
            ax.plot(xs, ys, color='#64748b', linewidth=3.5, alpha=0.7, zorder=3,
                    label='Initial Predicted Route (Maintained)' if first_init else "")
            first_init = False

    # 4. Traversed Path up to current_step (Blue solid)
    traversed_edges = active_route_edges[:step]
    first_trav = True
    for e in traversed_edges:
        coords = _extract_edge_coords(G, e[0], e[1], e[2] if len(e) > 2 else 0)
        xs, ys = zip(*coords)
        ax.plot(xs, ys, color=COLOR_TRAVERSED, linewidth=4.5, zorder=5,
                label=f'Traversed Path (Step 0→{step})' if first_trav else "")
        first_trav = False

    # 5. Milestone Node Markers
    src_pt = (float(G.nodes[source_node].get('x', G.nodes[source_node].get('lon'))),
              float(G.nodes[source_node].get('y', G.nodes[source_node].get('lat'))))
    dst_pt = (float(G.nodes[dest_node].get('x', G.nodes[dest_node].get('lon'))),
              float(G.nodes[dest_node].get('y', G.nodes[dest_node].get('lat'))))
    dec_pt = (float(G.nodes[decision_node].get('x', G.nodes[decision_node].get('lon'))),
              float(G.nodes[decision_node].get('y', G.nodes[decision_node].get('lat'))))

    ax.scatter(*src_pt, color=COLOR_ORIGIN, s=260, edgecolors='white', linewidth=2.0, zorder=8,
               label=f"Origin: {run_result['origin_name']}")
    ax.scatter(*dst_pt, color=COLOR_DESTINATION, s=260, marker='s', edgecolors='white', linewidth=2.0, zorder=8,
               label=f"Destination: {run_result['destination_name']}")
    ax.scatter(*dec_pt, color=COLOR_DECISION, s=340, marker='*', edgecolors='black', linewidth=1.8, zorder=9,
               label=f"Decision Point (Step {decision_step})")

    # 6. Current Vehicle Position Marker
    if step < len(active_route_nodes):
        curr_veh_node = active_route_nodes[step]
    else:
        curr_veh_node = active_route_nodes[-1]

    veh_pt = (float(G.nodes[curr_veh_node].get('x', G.nodes[curr_veh_node].get('lon'))),
              float(G.nodes[curr_veh_node].get('y', G.nodes[curr_veh_node].get('lat'))))

    # Glow ring + Puck marker
    ax.scatter(*veh_pt, color=COLOR_VEHICLE, s=500, alpha=0.35, zorder=10)
    ax.scatter(*veh_pt, color=COLOR_VEHICLE, s=220, edgecolors='white', linewidth=2.5, zorder=11,
               label=f'Vehicle Position (Step {step}/{total_steps})')

    # Formatting
    ax.set_xlim(min_lon, max_lon)
    ax.set_ylim(min_lat, max_lat)
    ax.set_xlabel('Longitude (°E)', color=text_color, fontweight='bold', fontsize=10)
    ax.set_ylabel('Latitude (°N)', color=text_color, fontweight='bold', fontsize=10)
    ax.tick_params(colors=text_color, labelsize=9)
    for spine in ax.spines.values():
        spine.set_color(spine_color)

    title_str = (
        f"Bhubaneswar Road Network — Scenario #{run_result['scenario_id']} ({run_result['period']})\n"
        f"Kinematic Progress: Step {step}/{total_steps} ({round((step/total_steps)*100 if total_steps else 0, 1)}%)"
    )
    ax.set_title(title_str, fontsize=12, fontweight='bold', color=text_color, pad=12)

    legend = ax.legend(loc='lower right', frameon=True, facecolor=bg_color, edgecolor=spine_color,
                       fontsize=9, labelcolor=text_color)
    legend.get_frame().set_alpha(0.92)

    plt.tight_layout()
    return fig


def create_pydeck_map(
    G: nx.MultiDiGraph,
    run_result: Dict[str, Any],
    current_step: Optional[int] = None
) -> pdk.Deck:
    """
    Builds an interactive Pydeck Map with Deck.GL PathLayer and ScatterplotLayer.
    """
    initial_edges = run_result['initial_route_edges']
    final_edges = run_result['final_route_edges']
    decision_step = run_result['decision_step']
    source_node = run_result['origin_node']
    dest_node = run_result['destination_node']
    decision_node = run_result['decision_node']
    reroute_triggered = run_result['reroute_triggered']

    active_route_edges = final_edges if (reroute_triggered and (current_step is None or current_step >= decision_step)) else initial_edges
    active_route_nodes = run_result['final_route_nodes'] if (reroute_triggered and (current_step is None or current_step >= decision_step)) else run_result['initial_route_nodes']

    total_steps = len(active_route_edges)
    step = total_steps if current_step is None else min(max(0, current_step), total_steps)

    path_data = []

    # 1. Abandoned Congested Section (Red)
    if reroute_triggered:
        for e in initial_edges[decision_step:]:
            coords = _extract_edge_coords(G, e[0], e[1], e[2] if len(e) > 2 else 0)
            path_data.append({
                'path': [[lon, lat] for lon, lat in coords],
                'color': [239, 68, 68, 220],
                'width': 6,
                'name': 'Observed Congestion (Abandoned Corridor)'
            })

    # 2. Dynamic Reroute Bypass (Green)
    if reroute_triggered:
        for e in final_edges[decision_step:]:
            coords = _extract_edge_coords(G, e[0], e[1], e[2] if len(e) > 2 else 0)
            path_data.append({
                'path': [[lon, lat] for lon, lat in coords],
                'color': [16, 185, 129, 230],
                'width': 7,
                'name': 'GeoPulse Dynamic Bypass'
            })
    else:
        for e in initial_edges:
            coords = _extract_edge_coords(G, e[0], e[1], e[2] if len(e) > 2 else 0)
            path_data.append({
                'path': [[lon, lat] for lon, lat in coords],
                'color': [100, 116, 139, 180],
                'width': 6,
                'name': 'Initial Predicted Route (Maintained)'
            })

    # 3. Traversed Path (Blue)
    for e in active_route_edges[:step]:
        coords = _extract_edge_coords(G, e[0], e[1], e[2] if len(e) > 2 else 0)
        path_data.append({
            'path': [[lon, lat] for lon, lat in coords],
            'color': [2, 132, 199, 255],
            'width': 8,
            'name': 'Traversed Path'
        })

    # Milestone points
    src_pt = [float(G.nodes[source_node].get('x', G.nodes[source_node].get('lon'))),
              float(G.nodes[source_node].get('y', G.nodes[source_node].get('lat')))]
    dst_pt = [float(G.nodes[dest_node].get('x', G.nodes[dest_node].get('lon'))),
              float(G.nodes[dest_node].get('y', G.nodes[dest_node].get('lat')))]
    dec_pt = [float(G.nodes[decision_node].get('x', G.nodes[decision_node].get('lon'))),
              float(G.nodes[decision_node].get('y', G.nodes[decision_node].get('lat')))]

    curr_node = active_route_nodes[min(step, len(active_route_nodes) - 1)]
    veh_pt = [float(G.nodes[curr_node].get('x', G.nodes[curr_node].get('lon'))),
              float(G.nodes[curr_node].get('y', G.nodes[curr_node].get('lat')))]

    point_data = [
        {'position': src_pt, 'color': [37, 99, 235], 'radius': 80, 'name': f"Origin: {run_result['origin_name']}"},
        {'position': dst_pt, 'color': [5, 150, 105], 'radius': 80, 'name': f"Destination: {run_result['destination_name']}"},
        {'position': dec_pt, 'color': [245, 158, 11], 'radius': 90, 'name': 'Decision Point (Traffic Update)'},
        {'position': veh_pt, 'color': [225, 29, 72], 'radius': 110, 'name': f"Connected Vehicle (Step {step}/{total_steps})"}
    ]

    path_layer = pdk.Layer(
        "PathLayer",
        data=path_data,
        get_path="path",
        get_color="color",
        get_width="width",
        width_scale=2,
        width_min_pixels=3,
        pickable=True
    )

    point_layer = pdk.Layer(
        "ScatterplotLayer",
        data=point_data,
        get_position="position",
        get_color="color",
        get_radius="radius",
        radius_min_pixels=6,
        radius_max_pixels=15,
        pickable=True
    )

    view_state = pdk.ViewState(
        latitude=dec_pt[1],
        longitude=dec_pt[0],
        zoom=13.0,
        pitch=25,
        bearing=0
    )

    deck = pdk.Deck(
        layers=[path_layer, point_layer],
        initial_view_state=view_state,
        tooltip={"text": "{name}"},
        map_style="carto-positron"
    )
    return deck


def render_journey_timeline_figure(run_result: Dict[str, Any]) -> plt.Figure:
    """
    Renders an elegant chronological journey milestone timeline figure.
    """
    timeline = run_result.get('timeline', [])
    decision_step = run_result['decision_step']
    reroute_triggered = run_result['reroute_triggered']

    milestones = [
        ("PLAN", "LightGBM Speed Prediction Broadcast & Initial Dijkstra Route R0 Computed", '#0284c7'),
        ("DEPART", f"Vehicle Departed Origin: {run_result['origin_name']} ({run_result['departure_timestamp'][:16]})", '#2563eb'),
        ("DRIVE", f"Kinematic Traversal: Link-by-link navigation up to Decision Node #{decision_step}", '#0284c7'),
        ("TRAFFIC UPDATE", f"Sensor Ingestion at {run_result['observation_timestamp'][:16]} (700 Regional Links)", '#f59e0b')
    ]

    if reroute_triggered:
        milestones.extend([
            ("DEGRADATION DETECTED", f"Downstream Bottleneck: Delta T = {run_result['delta_T_s']:.1f}s, Delta T% = {run_result['delta_T_pct']:.1f}%", '#ef4444'),
            ("DIJKSTRA REROUTE", f"Custom Dijkstra Solved in {run_result['execution_times_ms']['edge_reroute_dijkstra_ms']:.2f} ms", '#8b5cf6'),
            ("NEW ROUTE", f"Vehicle Switched to Dynamic Bypass ({run_result['final_route_edges_count']} segments)", '#10b981')
        ])
    else:
        milestones.extend([
            ("DEGRADATION AUDIT", f"Degradation Below Gates (Delta T = {run_result['delta_T_s']:.1f}s < 10s)", '#64748b'),
            ("ROUTE CONFIRMED", "Reroute Suppressed: Initial Route R0 Maintained", '#10b981')
        ])

    milestones.append(("DESTINATION", f"Arrived at Destination: {run_result['destination_name']} (Total Time: {run_result['dynamic_reroute_total_time_s']/60:.2f} min)", '#059669'))

    n = len(milestones)
    fig, ax = plt.subplots(figsize=(10, 4.2), facecolor='white')
    ax.set_facecolor('white')

    y_pos = list(range(n - 1, -1, -1))
    ax.plot([0.5] * n, y_pos, color='#cbd5e1', linewidth=3.0, zorder=1)

    for i, (title, desc, color) in enumerate(milestones):
        y = y_pos[i]
        ax.scatter(0.5, y, color=color, s=260, edgecolors='black', linewidth=1.5, zorder=3)
        ax.text(0.58, y + 0.12, title, fontsize=11, fontweight='bold', color=color, va='center')
        ax.text(0.58, y - 0.18, desc, fontsize=9, color='#334155', va='center')

    ax.set_xlim(0.4, 2.5)
    ax.set_ylim(-0.8, n - 0.2)
    ax.axis('off')
    plt.tight_layout()
    return fig


def get_step_simulation_status(run_result: Dict[str, Any], step: int) -> Dict[str, Any]:
    """
    Returns rich telemetry status for a given simulation playback step.
    """
    decision_step = run_result['decision_step']
    reroute_triggered = run_result['reroute_triggered']
    initial_edges = run_result['initial_route_edges']
    final_edges = run_result['final_route_edges']

    active_edges = final_edges if (reroute_triggered and step >= decision_step) else initial_edges
    total_steps = len(active_edges)
    step = min(max(0, step), total_steps)

    progress_pct = (step / total_steps) * 100.0 if total_steps > 0 else 0.0

    if step == 0:
        stage = "DEPARTURE"
        status_banner = "🚀 TRIP COMMENCED — Navigating Initial Predictive Route R0"
        alert_level = "info"
        edge_desc = f"Origin: {run_result['origin_name']} -> Destination: {run_result['destination_name']}"
    elif step < decision_step:
        stage = "NORMAL_TRAVERSAL"
        status_banner = f"🚙 EN ROUTE — Segment {step}/{total_steps} (Traffic nominal under ML predictions)"
        alert_level = "info"
        edge_desc = f"Traversing planned corridor link #{step}"
    elif step == decision_step:
        if reroute_triggered:
            stage = "DECISION_REROUTE"
            status_banner = (
                f"⚠ CONGESTION DETECTED! Real-time traffic update arrived.\n"
                f"Downstream bottleneck crossed gates: ΔT = {run_result['delta_T_s']:.1f}s (≥10s) & ΔT% = {run_result['delta_T_pct']:.1f}% (≥3%).\n"
                f"✓ ROUTE_UPDATE issued by Edge Server: Switching to Dynamic Bypass!"
            )
            alert_level = "warning"
        else:
            stage = "DECISION_CONFIRMED"
            status_banner = (
                f"ℹ TRAFFIC UPDATE RECEIVED — Regional traffic ingested.\n"
                f"Degradation ΔT = {run_result['delta_T_s']:.1f}s is below operational gates.\n"
                f"✓ Initial route R0 confirmed and maintained."
            )
            alert_level = "success"
        edge_desc = f"Decision Node {run_result['decision_node']} (Traffic Update Timestamp {run_result['observation_timestamp'][:16]})"
    elif step < total_steps:
        if reroute_triggered:
            stage = "BYPASS_TRAVERSAL"
            status_banner = f"🟢 DYNAMIC BYPASS ACTIVE — Segment {step}/{total_steps} (Avoiding downstream congestion)"
            alert_level = "success"
        else:
            stage = "NORMAL_TRAVERSAL"
            status_banner = f"🚙 EN ROUTE — Segment {step}/{total_steps} (Continuing on planned route)"
            alert_level = "info"
        edge_desc = f"Navigating link #{step} towards destination"
    else:
        stage = "ARRIVED"
        status_banner = f"🏁 ARRIVED AT DESTINATION — {run_result['destination_name']}"
        alert_level = "success"
        edge_desc = f"Completed all {total_steps} segments."

    return {
        'step': step,
        'total_steps': total_steps,
        'progress_pct': round(progress_pct, 1),
        'stage': stage,
        'status_banner': status_banner,
        'alert_level': alert_level,
        'edge_desc': edge_desc
    }
