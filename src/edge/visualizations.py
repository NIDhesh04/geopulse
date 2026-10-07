"""
GeoPulse Phase 11: End-to-End Visualizations & Architecture Diagram Engine

Generates 3 publication/defense-ready visual artifacts at 300 DPI:
  01_end_to_end_route.png          (Physical Bhubaneswar OSM road network map)
  02_end_to_end_timeline.png       (Chronological journey milestone timeline)
  03_edge_cloud_architecture.png   (Edge-Cloud architectural block diagram)
"""

import os
from typing import Dict, List, Tuple, Any
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import networkx as nx
from shapely import wkt

# Visual styling
plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.size'] = 11
plt.rcParams['axes.titlesize'] = 13
plt.rcParams['axes.labelsize'] = 11
plt.rcParams['figure.titlesize'] = 14


def _extract_edge_coords(G, u, v, k):
    data = G.get_edge_data(u, v, k, default={})
    if 'geometry' in data:
        try:
            geom = wkt.loads(data['geometry'])
            return list(geom.coords)
        except Exception:
            pass
    u_d = G.nodes[u]
    v_d = G.nodes[v]
    return [
        (float(u_d.get('x', u_d.get('lon', 0.0))), float(u_d.get('y', u_d.get('lat', 0.0)))),
        (float(v_d.get('x', v_d.get('lon', 0.0))), float(v_d.get('y', v_d.get('lat', 0.0))))
    ]


def generate_end_to_end_route_map(
    G: nx.MultiDiGraph,
    initial_edge_path: List[Tuple[str, str, int]],
    final_edge_path: List[Tuple[str, str, int]],
    decision_step: int,
    source_node: str,
    destination_node: str,
    decision_node: str,
    output_path: str
):
    """Figure 1: High-resolution physical road network geometry map."""
    fig, ax = plt.subplots(figsize=(12, 10))

    # Segment pathways
    traversed_edges = initial_edge_path[:decision_step]
    abandoned_edges = initial_edge_path[decision_step:]
    rerouted_edges = final_edge_path[decision_step:]

    # Bounding box
    all_nodes = [source_node, destination_node, decision_node]
    for e in initial_edge_path + final_edge_path:
        all_nodes.extend([e[0], e[1]])
    all_nodes = list(set(all_nodes))

    lons = [float(G.nodes[n].get('x', G.nodes[n].get('lon', 0.0))) for n in all_nodes]
    lats = [float(G.nodes[n].get('y', G.nodes[n].get('lat', 0.0))) for n in all_nodes]

    pad = 0.008
    min_lon, max_lon = min(lons) - pad, max(lons) + pad
    min_lat, max_lat = min(lats) - pad, max(lats) + pad

    # Background road network
    for u, v, k, d in G.edges(keys=True, data=True):
        coords = _extract_edge_coords(G, u, v, k)
        xs, ys = zip(*coords)
        if min_lon <= min(xs) <= max_lon and min_lat <= min(ys) <= max_lat:
            ax.plot(xs, ys, color='#e2e8f0', linewidth=0.6, alpha=0.7, zorder=1)

    # 1. Traversed prefix (Blue solid)
    first_trav = True
    for e in traversed_edges:
        coords = _extract_edge_coords(G, e[0], e[1], e[2])
        xs, ys = zip(*coords)
        ax.plot(xs, ys, color='#0d6efd', linewidth=4.0, zorder=4,
                label='Pre-Update Traversed Path' if first_trav else "")
        first_trav = False

    # 2. Abandoned congested corridor (Red dashed)
    first_aband = True
    for e in abandoned_edges:
        coords = _extract_edge_coords(G, e[0], e[1], e[2])
        xs, ys = zip(*coords)
        ax.plot(xs, ys, color='#dc3545', linewidth=3.5, linestyle='--', zorder=3,
                label='Abandoned Congested Corridor (R0)' if first_aband else "")
        first_aband = False

    # 3. Dynamic rerouted bypass (Green solid)
    first_reroute = True
    for e in rerouted_edges:
        coords = _extract_edge_coords(G, e[0], e[1], e[2])
        xs, ys = zip(*coords)
        ax.plot(xs, ys, color='#198754', linewidth=4.0, zorder=5,
                label='GeoPulse Dynamic Bypass (R1)' if first_reroute else "")
        first_reroute = False

    # Key node markers
    src_pt = (float(G.nodes[source_node].get('x', G.nodes[source_node].get('lon'))),
              float(G.nodes[source_node].get('y', G.nodes[source_node].get('lat'))))
    dst_pt = (float(G.nodes[destination_node].get('x', G.nodes[destination_node].get('lon'))),
              float(G.nodes[destination_node].get('y', G.nodes[destination_node].get('lat'))))
    dec_pt = (float(G.nodes[decision_node].get('x', G.nodes[decision_node].get('lon'))),
              float(G.nodes[decision_node].get('y', G.nodes[decision_node].get('lat'))))

    ax.scatter(*src_pt, color='#0d6efd', s=220, edgecolors='black', linewidth=1.5, zorder=6, label='Trip Origin (Departure)')
    ax.scatter(*dst_pt, color='#198754', s=220, marker='s', edgecolors='black', linewidth=1.5, zorder=6, label='Trip Destination')
    ax.scatter(*dec_pt, color='#fd7e14', s=260, marker='*', edgecolors='black', linewidth=1.5, zorder=7, label='Decision Node (Traffic Update at t1)')

    ax.annotate("Departure (19:30 IST)", xy=src_pt, xytext=(12, 12), textcoords="offset points",
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#0d6efd", lw=1.5), fontsize=10, fontweight='bold')
    ax.annotate("Destination", xy=dst_pt, xytext=(12, -18), textcoords="offset points",
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#198754", lw=1.5), fontsize=10, fontweight='bold')
    ax.annotate("REROUTE POINT\n(Bottleneck Detected)", xy=dec_pt, xytext=(-45, 25), textcoords="offset points",
                arrowprops=dict(arrowstyle="->", color="#fd7e14", lw=2.0),
                bbox=dict(boxstyle="round,pad=0.4", fc="#fff3cd", ec="#fd7e14", lw=1.5), fontsize=10, fontweight='bold')

    ax.set_xlim(min_lon, max_lon)
    ax.set_ylim(min_lat, max_lat)
    ax.set_title("Figure 1: End-to-End Dynamic Rerouting Demonstration (Bhubaneswar Road Network)\nTrip OD #0: Evening Commuter Peak (19:30 -> 20:30 IST)", fontsize=13, fontweight='bold', pad=15)
    ax.set_xlabel("Longitude (E)")
    ax.set_ylabel("Latitude (N)")
    ax.legend(loc='lower right', frameon=True, facecolor='white', framealpha=0.95, fontsize=10)

    # Info summary box
    summary_txt = (
        "Strategy A (No Reroute): 21.45 min (1287.1s)\n"
        "Strategy B (Dynamic Reroute): 20.04 min (1202.2s)\n"
        "Net Time Saved: +84.9 seconds (1.42 min)\n"
        "Travel-Time Improvement: +6.60%\n"
        "Decision Gate: ΔT = 84.9s (9.2%) >= [10s / 3%]"
    )
    ax.text(0.03, 0.96, summary_txt, transform=ax.transAxes, va='top', fontsize=10,
            bbox=dict(boxstyle="round,pad=0.5", fc="white", ec="#495057", lw=1.5, alpha=0.95))

    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()


def generate_end_to_end_timeline(demo_data: Dict[str, Any], output_path: str):
    """Figure 2: Milestone journey progression timeline."""
    fig, ax = plt.subplots(figsize=(13, 6))

    milestones = [
        ("Step 1: Planning (t0 = 19:30 IST)", "Cloud LightGBM forecasts next-hour speeds\nCustom Dijkstra selects R0 (74 links)\nETA: 21.45 min (1287.1s)", "#0d6efd", 1),
        ("Step 2: En Route Traversal", "Vehicle progresses links 1 -> 15 (20% of trip)\nTraversal time elapsed: 4.88 min (292.8s)\nApproaching Node 3320289784", "#20c997", 2),
        ("Step 3: Telemetry Arrival (t1 = 20:30 IST)", "Sensor feed detects downstream bottleneck\nLink speed plummets 31.7 -> 14.0 km/h\nRemaining R0 time swells to 994.2s", "#dc3545", 3),
        ("Step 4: Degradation Detection", "Edge Server probes alternative path R1\nOptimal bypass time: 909.3s\nΔT = 84.9s (9.2%) exceeds 10s / 3% gates", "#fd7e14", 4),
        ("Step 5: Dynamic Reroute & Arrival", "Edge Server dispatches ROUTE_UPDATE\nVehicle switches to open arterial bypass\nFinal Trip Time: 20.04 min (1202.2s)", "#198754", 5)
    ]

    for title, desc, clr, x in milestones:
        # Milestone node
        ax.scatter(x, 0, color=clr, s=500, zorder=4, edgecolors='black', linewidth=1.5)
        ax.text(x, 0, str(x), ha='center', va='center', color='white', fontweight='bold', fontsize=12, zorder=5)

        # Title
        ax.text(x, 0.45, title, ha='center', va='bottom', fontweight='bold', fontsize=11, color='#212529')

        # Description box
        ax.text(x, -0.45, desc, ha='center', va='top', fontsize=9.5,
                bbox=dict(boxstyle="round,pad=0.4", fc="white", ec=clr, lw=1.5))

    # Timeline connector
    ax.plot([0.5, 5.5], [0, 0], color='#adb5bd', linewidth=4, zorder=2)

    ax.set_xlim(0.3, 5.7)
    ax.set_ylim(-1.5, 1.3)
    ax.axis('off')

    ax.set_title("Figure 2: End-to-End GeoPulse Journey Lifecycle & Degradation Response Timeline", fontsize=13, fontweight='bold', pad=20)

    # Highlight box for savings
    sav_txt = f"Total Time Saved: +84.9 seconds (1.42 minutes)  |  Efficiency Gain: +6.60%  |  Status: SUCCESS"
    fig.text(0.5, 0.05, sav_txt, ha='center', fontsize=11, fontweight='bold',
             bbox=dict(boxstyle="round,pad=0.5", fc="#d1e7dd", ec="#198754", lw=2.0))

    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()


def generate_edge_cloud_architecture_diagram(
    exec_times: Dict[str, float],
    output_path: str
):
    """Figure 3: Publication-grade Edge-Cloud architectural block diagram."""
    fig, ax = plt.subplots(figsize=(14, 9))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis('off')

    # Color tokens
    cloud_bg, cloud_border = '#e0f2fe', '#0284c7'
    edge_bg, edge_border = '#fef3c7', '#d97706'
    veh_bg, veh_border = '#dcfce7', '#16a34a'

    # Box 1: CLOUD TIER
    box_cloud = patches.FancyBboxPatch((10, 68), 80, 26, boxstyle="round,pad=1.5", fc=cloud_bg, ec=cloud_border, lw=2.5)
    ax.add_patch(box_cloud)
    ax.text(14, 90, "CLOUD COMPONENT (Centralized Model Lifecycle)", fontsize=13, fontweight='bold', color='#0369a1')
    cloud_desc = (
        "• Historical Traffic Warehouse (30,800 test observations, 700 monitored corridors)\n"
        "• Feature Engineering Pipeline (Calendar embeddings, periodic encodings, speed lag arrays)\n"
        "• Trained LightGBM Regressor (25 features, MAE = 0.934 km/h, Iteration 112)\n"
        "• Batch Hourly Prediction Service -> Dispatches MODEL_UPDATE messages to regional edges"
    )
    ax.text(14, 73, cloud_desc, fontsize=10, color='#1e293b')

    # Arrow Cloud -> Edge
    ax.annotate(
        "MODEL_UPDATE: Next-Hour Speed Forecasts\n(Software Exec Time: 0.05 ms)",
        xy=(50, 62), xytext=(50, 68),
        ha='center', va='center', fontsize=9.5, fontweight='bold', color='#0369a1',
        arrowprops=dict(arrowstyle="->", color=cloud_border, lw=2.5)
    )

    # Box 2: EDGE SERVER TIER
    box_edge = patches.FancyBboxPatch((10, 32), 80, 30, boxstyle="round,pad=1.5", fc=edge_bg, ec=edge_border, lw=2.5)
    ax.add_patch(box_edge)
    ax.text(14, 58, "LOGICAL EDGE SERVER (Low-Latency Regional Control)", fontsize=13, fontweight='bold', color='#b45309')
    
    # Internal Edge tasks with execution times
    d_time = exec_times.get('dijkstra_exec_ms', 0.28)
    w_time = exec_times.get('weight_update_ms', 0.02)
    dec_time = exec_times.get('decision_exec_ms', 0.01)
    tot_time = exec_times.get('total_edge_decision_ms', 0.31)

    edge_desc = (
        "• Ingests Sensor Telemetry & Assembles Dynamic Graph Weights\n"
        f"• Scratch-Built Min-Heap Dijkstra Solver (Prototype Exec Time: {d_time:.3f} ms)\n"
        "• Active Vehicle Session & Telemetry Tracking (Node 3320289784, 20% progress)\n"
        f"• Real-Time Route Degradation Evaluator (ΔT = 84.9s, ΔT% = 9.2% >= [10s / 3%])\n"
        f"• Total Edge Rerouting Decision Latency: {tot_time:.3f} ms (sub-millisecond responsiveness)"
    )
    ax.text(14, 36, edge_desc, fontsize=10, color='#1e293b')

    # Bidirectional Arrows Edge <-> Vehicle
    ax.annotate(
        "ROUTE_UPDATE (Initial R0 & Dynamic Detour R1)",
        xy=(35, 26), xytext=(35, 32),
        ha='center', va='center', fontsize=9.5, fontweight='bold', color='#16a34a',
        arrowprops=dict(arrowstyle="->", color=edge_border, lw=2.5)
    )
    ax.annotate(
        "POSITION_UPDATE: Telemetry Stream",
        xy=(65, 32), xytext=(65, 26),
        ha='center', va='center', fontsize=9.5, fontweight='bold', color='#b45309',
        arrowprops=dict(arrowstyle="->", color=veh_border, lw=2.5)
    )

    # Box 3: VEHICLE / CLIENT TIER
    box_veh = patches.FancyBboxPatch((10, 4), 80, 22, boxstyle="round,pad=1.5", fc=veh_bg, ec=veh_border, lw=2.5)
    ax.add_patch(box_veh)
    ax.text(14, 21, "VEHICLE SIMULATOR (Connected Client)", fontsize=13, fontweight='bold', color='#15803d')
    veh_desc = (
        "• Ingests Route Directives from Edge Server (74 links initial -> 46 links rerouted)\n"
        "• Link-Based Kinematic Traversal: t = L / v (Step-by-step physical movement)\n"
        "• Emits Periodic Position Updates at Intersection Boundaries\n"
        "• Seamlessly Swaps Remaining Route Segments upon Receiving Reroute Signal"
    )
    ax.text(14, 7, veh_desc, fontsize=10, color='#1e293b')

    fig.suptitle("Figure 3: Simulated Edge-Cloud Architecture & Component Interactivity", fontsize=15, fontweight='bold', y=0.98)
    
    note_txt = (
        "Note: Software architecture simulation executing on host machine. "
        "Execution timings reflect prototype software runtimes, not physical embedded hardware latency."
    )
    fig.text(0.5, 0.01, note_txt, ha='center', fontsize=9, style='italic', color='#64748b')

    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()
