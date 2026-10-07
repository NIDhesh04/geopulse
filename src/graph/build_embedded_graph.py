"""City-Scale Embedded Road Graph Construction for GeoPulse Bhubaneswar.

Extracts the entire drivable OpenStreetMap graph for Bhubaneswar, extracts the largest
strongly connected component, projects to EPSG:32645 (metric UTM zone 45N), and embeds the
700 monitored TomTom segments as dynamic edge-weight providers.

Outputs:
  data/interim/G_embedded.graphml
"""
import sys
from pathlib import Path

import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
import pyproj

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.config import INTERIM_DIR, PROJECT_ROOT

# Ensure cache is used
ox.settings.use_cache = True
ox.settings.requests_timeout = 300
ox.settings.user_agent = "GeoPulseResearch/1.0 (academic research; contact: research@geopulse.bhu)"

# Baseline speeds for unmonitored road classes (in km/h)
CLASS_SPEEDS = {
    "motorway": 60.0,
    "motorway_link": 45.0,
    "trunk": 55.0,
    "trunk_link": 40.0,
    "primary": 50.0,
    "primary_link": 35.0,
    "secondary": 40.0,
    "secondary_link": 30.0,
    "tertiary": 35.0,
    "tertiary_link": 25.0,
    "residential": 30.0,
    "living_street": 20.0,
    "service": 20.0,
    "unclassified": 30.0,
}
DEFAULT_SPEED = 30.0


def parse_highway(val):
    if isinstance(val, list):
        return val[0]
    return str(val)


def main():
    print("=" * 60)
    print("Step 1: Downloading / Loading Bhubaneswar drive network...")
    print("=" * 60)
    G = ox.graph_from_place("Bhubaneswar, India", network_type="drive", simplify=True)
    print(f"Raw graph: {len(G)} nodes, {G.number_of_edges()} edges")

    print("\nStep 2: Extracting largest strongly connected component (SCC)...")
    scc = max(nx.strongly_connected_components(G), key=len)
    G_scc = G.subgraph(scc).copy()
    print(f"SCC graph: {len(G_scc)} nodes, {G_scc.number_of_edges()} edges")

    print("\nStep 3: Projecting graph to EPSG:32645 (metric CRS)...")
    G_proj = ox.project_graph(G_scc, to_crs="EPSG:32645")

    print("\nStep 4: Loading monitored segments metadata...")
    endpoints = pd.read_csv(INTERIM_DIR / "segment_endpoints.csv", index_col=0)
    meta = pd.read_csv(INTERIM_DIR / "segment_metadata.csv", index_col=0)

    # Project segment centroids to EPSG:32645
    transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32645", always_xy=True)
    xs, ys = transformer.transform(meta["lon"].values, meta["lat"].values)
    meta["x_proj"] = xs
    meta["y_proj"] = ys

    print("\nStep 5: Matching 700 segments to unique edges in G_proj...")
    assigned_edges = {}  # sid -> (u, v, k)
    used_edges = set()

    # Pass 1: Direct endpoint matching
    for sid in meta.index:
        r = endpoints.loc[sid]
        u, v = r.get("u"), r.get("v")
        if pd.notna(u) and pd.notna(v):
            u, v = int(u), int(v)
            # Try forward edge
            if G_proj.has_edge(u, v):
                for k in G_proj[u][v]:
                    if (u, v, k) not in used_edges:
                        assigned_edges[sid] = (u, v, k)
                        used_edges.add((u, v, k))
                        break
            # Try reverse edge if still unassigned
            if sid not in assigned_edges and G_proj.has_edge(v, u):
                for k in G_proj[v][u]:
                    if (v, u, k) not in used_edges:
                        assigned_edges[sid] = (v, u, k)
                        used_edges.add((v, u, k))
                        break

    print(f"Pass 1 (direct endpoints): {len(assigned_edges)} / {len(meta)}")

    # Pass 2: Spatial snapping for unassigned segments
    unassigned = [s for s in meta.index if s not in assigned_edges]
    if unassigned:
        print(f"Pass 2: Snapping {len(unassigned)} remaining segments via spatial nearest edges...")
        pts_x = meta.loc[unassigned, "x_proj"].values
        pts_y = meta.loc[unassigned, "y_proj"].values
        near_edges = ox.nearest_edges(G_proj, pts_x, pts_y)
        for sid, (u, v, k) in zip(unassigned, near_edges):
            if (u, v, k) not in used_edges:
                assigned_edges[sid] = (u, v, k)
                used_edges.add((u, v, k))
            elif G_proj.has_edge(v, u):
                # Try reverse
                for k2 in G_proj[v][u]:
                    if (v, u, k2) not in used_edges:
                        assigned_edges[sid] = (v, u, k2)
                        used_edges.add((v, u, k2))
                        break
            if sid not in assigned_edges:
                # Search immediate successors
                found = False
                for nbr in [u, v]:
                    for succ in G_proj.successors(nbr):
                        for k3 in G_proj[nbr][succ]:
                            if (nbr, succ, k3) not in used_edges:
                                assigned_edges[sid] = (nbr, succ, k3)
                                used_edges.add((nbr, succ, k3))
                                found = True
                                break
                        if found:
                            break
                    if found:
                        break

    assert len(assigned_edges) == 700, f"Expected 700 assigned edges, got {len(assigned_edges)}"
    assert len(used_edges) == 700, f"Expected 700 unique edges, got {len(used_edges)}"
    print(f"Successfully mapped all {len(assigned_edges)} segments to unique edges.")

    # Create mapping from (u, v, k) -> sid
    edge_to_sid = {edge: sid for sid, edge in assigned_edges.items()}

    print("\nStep 6: Annotating all edges with attributes...")
    monitored_count = 0
    unmonitored_count = 0

    for u, v, k, d in G_proj.edges(keys=True, data=True):
        edge_key = (u, v, k)
        length = float(d.get("length", 10.0))

        if edge_key in edge_to_sid:
            sid = int(edge_to_sid[edge_key])
            ff_speed = float(meta.loc[sid, "ffs"]) if "ffs" in meta.columns else 35.0
            ff_speed = max(ff_speed, 1.0)  # enforce minimum speed floor
            ff_time = length / (ff_speed / 3.6)

            d["is_monitored"] = True
            d["segment_id"] = sid
            d["free_flow_speed"] = ff_speed
            d["free_flow_time"] = ff_time
            d["road_type"] = str(meta.loc[sid, "road_type"])
            monitored_count += 1
        else:
            hw = parse_highway(d.get("highway", "residential"))
            base_speed = CLASS_SPEEDS.get(hw, DEFAULT_SPEED)
            base_speed = max(base_speed, 1.0)
            base_time = length / (base_speed / 3.6)

            d["is_monitored"] = False
            d["segment_id"] = -1
            d["free_flow_speed"] = base_speed
            d["free_flow_time"] = base_time
            d["road_type"] = hw
            unmonitored_count += 1

    # Ensure all edge, node, and graph attributes are GraphML-compatible primitives
    for u, v, k, d in G_proj.edges(keys=True, data=True):
        if "geometry" in d:
            del d["geometry"]
        for attr, val in list(d.items()):
            if not isinstance(val, (int, float, str, bool)):
                d[attr] = str(val)

    for n, nd in G_proj.nodes(data=True):
        for attr, val in list(nd.items()):
            if isinstance(val, (list, tuple, set, dict)):
                nd[attr] = str(val)

    for attr, val in list(G_proj.graph.items()):
        if not isinstance(val, (int, float, str, bool)):
            G_proj.graph[attr] = str(val)

    out_path = INTERIM_DIR / "G_embedded.graphml"
    print(f"\nStep 7: Saving combined graph to {out_path}...")
    nx.write_graphml(G_proj, out_path)
    print(f"G_embedded.graphml successfully saved! File size: {out_path.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
