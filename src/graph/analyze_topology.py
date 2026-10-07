"""Topology analysis for G_seg (graph formed by the 700 traffic segments).

Calculates:
- Node and edge counts
- In-degree, out-degree, undirected degree distributions
- Connected components (WCC, SCC), sizes and percentages
- Dead ends, sinks, sources, junctions
- Cyclomatic complexity (number of independent cycles)
- Bridges

Outputs:
- outputs/phase1/metrics/topology.json
- outputs/phase1/figures/network_overview.png
- outputs/phase1/figures/network_segment_graph_lcc.png
- outputs/phase1/figures/degree_distribution.png
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import numpy as np
import pandas as pd
import networkx as nx

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.config import INTERIM_DIR, METRIC_DIR, FIG_DIR, PROJECT_ROOT

RT_COLOR = {"trunk": "#d62728", "primary": "#ff7f0e", "secondary": "#1f77b4"}


def topo_analysis(G, name):
    U = nx.Graph(G.to_undirected())
    deg = np.array([d for _, d in U.degree()])
    indeg = np.array([d for _, d in G.in_degree()])
    outdeg = np.array([d for _, d in G.out_degree()])

    wcc = sorted(nx.weakly_connected_components(G), key=len, reverse=True)
    scc = sorted(nx.strongly_connected_components(G), key=len, reverse=True)

    lw = G.subgraph(wcc[0])
    ls = G.subgraph(scc[0])
    comp_sizes = [len(c) for c in wcc]
    scc_sizes = [len(c) for c in scc]

    lu = nx.Graph(U.subgraph(max(nx.connected_components(U), key=len)))
    cyclomatic = U.number_of_edges() - U.number_of_nodes() + nx.number_connected_components(U)
    lcc_cyclomatic = lu.number_of_edges() - lu.number_of_nodes() + 1
    bridges = list(nx.bridges(lu))

    res = {
        "graph": name,
        "nodes": G.number_of_nodes(),
        "directed_edges": G.number_of_edges(),
        "undirected_edges": U.number_of_edges(),
        "degree_undirected": {
            "min": int(deg.min()) if len(deg) else 0,
            "max": int(deg.max()) if len(deg) else 0,
            "mean": float(deg.mean()) if len(deg) else 0,
            "median": float(np.median(deg)) if len(deg) else 0,
            "dist": {int(k): int(v) for k, v in zip(*np.unique(deg, return_counts=True))}
        },
        "in_degree_mean": float(indeg.mean()) if len(indeg) else 0,
        "out_degree_mean": float(outdeg.mean()) if len(outdeg) else 0,
        "dead_ends_undirected_deg1": int((deg == 1).sum()),
        "dead_ends_pct": float((deg == 1).mean() * 100) if len(deg) else 0,
        "directed_sinks_out0": int((outdeg == 0).sum()),
        "directed_sources_in0": int((indeg == 0).sum()),
        "junctions_deg_ge3": int((deg >= 3).sum()),
        "junctions_deg_ge3_pct": float((deg >= 3).mean() * 100) if len(deg) else 0,
        "n_weak_components": len(wcc),
        "component_size_dist": {int(k): int(v) for k, v in zip(*np.unique(comp_sizes, return_counts=True))},
        "largest_wcc_nodes": len(wcc[0]) if wcc else 0,
        "largest_wcc_nodes_pct": (len(wcc[0]) / G.number_of_nodes() * 100) if G.number_of_nodes() else 0,
        "largest_wcc_edges": lw.number_of_edges(),
        "largest_wcc_edges_pct": (lw.number_of_edges() / G.number_of_edges() * 100) if G.number_of_edges() else 0,
        "n_strong_components": len(scc),
        "scc_size_dist": {int(k): int(v) for k, v in zip(*np.unique(scc_sizes, return_counts=True))},
        "largest_scc_nodes": len(scc[0]) if scc else 0,
        "largest_scc_nodes_pct": (len(scc[0]) / G.number_of_nodes() * 100) if G.number_of_nodes() else 0,
        "largest_scc_edges": ls.number_of_edges(),
        "cyclomatic_number_undirected": cyclomatic,
        "largest_cc_cyclomatic": lcc_cyclomatic,
        "largest_cc_bridges": len(bridges),
        "largest_cc_bridge_pct": (len(bridges) / max(lu.number_of_edges(), 1) * 100)
    }
    return res, wcc, scc


def plot_graphs(G_seg, wcc):
    meta = pd.read_csv(INTERIM_DIR / "segment_metadata.csv", index_col=0)

    # Figure 1: Network Overview
    fig, ax = plt.subplots(figsize=(10, 10))
    for u, v, d in G_seg.edges(data=True):
        if "x" in G_seg.nodes[u] and "x" in G_seg.nodes[v]:
            x0, y0 = G_seg.nodes[u]["x"], G_seg.nodes[u]["y"]
            x1, y1 = G_seg.nodes[v]["x"], G_seg.nodes[v]["y"]
            rt = d.get("road_type", "secondary")
            c = RT_COLOR.get(rt, "#1f77b4")
            ax.plot([x0, x1], [y0, y1], color=c, lw=1.5, alpha=0.7)

    # Plot centroids
    ax.scatter(meta["lon"], meta["lat"], s=6, c="black", zorder=5, label="Segment Centroids (700)")

    for rt, c in RT_COLOR.items():
        ax.plot([], [], color=c, lw=2, label=f"Segment ({rt})")

    ax.set_title("Bhubaneswar Traffic Segments Network (G_seg)\n700 Segments Mapped to OSM Road Coordinates", fontsize=12)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.legend(loc="lower left", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "network_overview.png", dpi=140)
    plt.close(fig)

    # Figure 2: Connected Components & LCC
    fig, ax = plt.subplots(figsize=(10, 10))
    lcc_nodes = wcc[0] if wcc else set()
    other_lines = []
    lcc_lines = []

    for u, v in G_seg.edges():
        if "x" in G_seg.nodes[u] and "x" in G_seg.nodes[v]:
            line = [(G_seg.nodes[u]["x"], G_seg.nodes[u]["y"]), (G_seg.nodes[v]["x"], G_seg.nodes[v]["y"])]
            if u in lcc_nodes and v in lcc_nodes:
                lcc_lines.append(line)
            else:
                other_lines.append(line)

    if other_lines:
        ax.add_collection(LineCollection(other_lines, colors="#999999", lw=1.2, alpha=0.6,
                                         label=f"Other Components ({len(wcc)-1})"))
    if lcc_lines:
        ax.add_collection(LineCollection(lcc_lines, colors="#d62728", lw=2.2, alpha=0.9,
                                         label=f"Largest Weakly Connected Component ({len(lcc_nodes)} nodes)"))

    xs = [G_seg.nodes[n]["x"] for n in G_seg.nodes if "x" in G_seg.nodes[n]]
    ys = [G_seg.nodes[n]["y"] for n in G_seg.nodes if "y" in G_seg.nodes[n]]
    if xs:
        ax.scatter(xs, ys, s=4, c="navy", zorder=4, alpha=0.5)
        ax.set_xlim(min(xs) - 0.01, max(xs) + 0.01)
        ax.set_ylim(min(ys) - 0.01, max(ys) + 0.01)

    ax.set_title(f"G_seg Connected Components Analysis\nTotal Components: {len(wcc)}, Largest Component: {len(lcc_nodes)} Nodes", fontsize=12)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.legend(loc="lower left", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "network_segment_graph_lcc.png", dpi=140)
    plt.close(fig)

    # Figure 3: Degree Distribution
    U = nx.Graph(G_seg.to_undirected())
    degs = [d for _, d in U.degree()]
    fig, ax = plt.subplots(figsize=(7, 4))
    val, counts = np.unique(degs, return_counts=True)
    ax.bar(val, counts, color="#4f81bd", edgecolor="black", width=0.6)
    ax.set_title(f"Node Degree Distribution (Undirected G_seg)\nMean: {np.mean(degs):.2f}, Median: {np.median(degs):.1f}")
    ax.set_xlabel("Node Degree")
    ax.set_ylabel("Number of Nodes")
    ax.set_xticks(range(int(min(val)), int(max(val)) + 1))
    fig.tight_layout()
    fig.savefig(FIG_DIR / "degree_distribution.png", dpi=130)
    plt.close(fig)


def main():
    G_seg = nx.read_graphml(INTERIM_DIR / "G_seg.graphml", force_multigraph=True)
    res_seg, wcc, scc = topo_analysis(G_seg, "G_seg (Traffic Segments)")

    out = {
        "G_seg": res_seg,
        "wcc_top10_sizes": [len(c) for c in wcc[:10]],
        "scc_top10_sizes": [len(c) for c in scc[:10]]
    }

    (METRIC_DIR / "topology.json").write_text(json.dumps(out, indent=2, default=str))
    plot_graphs(G_seg, wcc)
    print("Topology analysis completed:")
    print(json.dumps(res_seg, indent=2, default=str))


if __name__ == "__main__":
    main()
