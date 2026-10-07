"""Generate SUMO Route XML File from Phase 4 Benchmark Paths.

Maps Python node paths to SUMO edge IDs, creates valid route definitions,
and writes vehicle trip configurations with standard passenger car physics.

Outputs:
  data/interim/benchmark.rou.xml
  outputs/phase5/benchmark.rou.xml
"""
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET

import networkx as nx
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.config import INTERIM_DIR, PROJECT_ROOT
from src.routing.dynamic_simulator import VehicleSimulation

PHASE5_DIR = PROJECT_ROOT / "outputs" / "phase5"
PHASE5_DIR.mkdir(parents=True, exist_ok=True)

GRAPH_PATH = INTERIM_DIR / "G_embedded.graphml"
MODEL_PATH = PROJECT_ROOT / "outputs" / "phase3" / "xgb_speed_model.json"
FEAT_PATH = INTERIM_DIR / "ml_features.parquet"
ROU_XML_PATH = INTERIM_DIR / "benchmark.rou.xml"


def nodes_to_sumo_edges(G: nx.MultiDiGraph, path_nodes: list) -> list:
    """Converts a node path [n1, n2, n3...] into SUMO edge IDs [e_n1_n2, e_n2_n3...]."""
    edge_ids = []
    for i in range(len(path_nodes) - 1):
        u = str(path_nodes[i])
        v = str(path_nodes[i + 1])
        edge_id = f"e_{u}_{v}"
        edge_ids.append(edge_id)
    return edge_ids


def main():
    print("=" * 65)
    print("Phase 5: Generating SUMO Routes (generate_sumo_routes.py)")
    print("=" * 65)

    print("Step 1: Initializing VehicleSimulation environment...")
    G = nx.read_graphml(GRAPH_PATH, force_multigraph=True)
    sim = VehicleSimulation(
        G=G,
        model_path=MODEL_PATH,
        features_path=FEAT_PATH,
        epsilon=45.0,
        alpha=0.0,
        beta=1.0,
    )

    # Use a benchmark pair from Phase 4 (OD_03: 8065163006 -> 4714739238)
    source = "8065163006"
    target = "4714739238"
    departure_time = pd.Timestamp("2026-01-14 13:00:00+00:00")

    print(f"\nStep 2: Computing paths for OD corridor: {source} -> {target}...")
    res_static = sim.run_static_baseline(source, target, departure_time)
    res_pred = sim.run_predictive_preplanned(source, target, departure_time)
    res_dyn = sim.run_dynamic_edge_rerouting(source, target, departure_time)

    edges_static = nodes_to_sumo_edges(G, res_static["path"])
    edges_pred = nodes_to_sumo_edges(G, res_pred["path"])
    edges_dyn = nodes_to_sumo_edges(G, res_dyn["path"])

    print(f"  - Static Route:     {len(edges_static)} edges, {res_static['total_distance_meters']/1000:.2f} km")
    print(f"  - Predictive Route: {len(edges_pred)} edges, {res_pred['total_distance_meters']/1000:.2f} km")
    print(f"  - Dynamic Route:    {len(edges_dyn)} edges, {res_dyn['total_distance_meters']/1000:.2f} km")

    print("\nStep 3: Building SUMO routes XML document...")
    root = ET.Element(
        "routes",
        xmlns="http://sumo.dlr.de/xsd/routes_file.xsd",
    )

    # Standard passenger vehicle type
    ET.SubElement(
        root,
        "vType",
        id="car",
        accel="2.6",
        decel="4.5",
        sigma="0.5",
        length="4.5",
        minGap="2.5",
        maxSpeed="33.33",  # 120 km/h max speed
    )

    # Routes
    ET.SubElement(root, "route", id="route_static", edges=" ".join(edges_static))
    ET.SubElement(root, "route", id="route_predictive", edges=" ".join(edges_pred))
    ET.SubElement(root, "route", id="route_dynamic", edges=" ".join(edges_dyn))

    # Vehicles departing at t=0
    ET.SubElement(root, "vehicle", id="veh_static", type="car", route="route_static", depart="0")
    ET.SubElement(root, "vehicle", id="veh_predictive", type="car", route="route_predictive", depart="0")
    ET.SubElement(root, "vehicle", id="veh_dynamic", type="car", route="route_dynamic", depart="0")

    tree = ET.ElementTree(root)
    tree.write(ROU_XML_PATH, encoding="utf-8", xml_declaration=True)
    print(f"SUMO route file generated: {ROU_XML_PATH} ({ROU_XML_PATH.stat().st_size / 1e3:.1f} KB)")

    # Copy to outputs/phase5/
    out_copy = PHASE5_DIR / "benchmark.rou.xml"
    shutil.copyfile(ROU_XML_PATH, out_copy)
    print(f"Saved copy to: {out_copy}")


if __name__ == "__main__":
    main()
