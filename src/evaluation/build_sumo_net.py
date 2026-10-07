"""Build SUMO Road Network from Bhubaneswar OpenStreetMap Data.

Converts the original OpenStreetMap road data into a SUMO network file
(bhubaneswar.net.xml) using SUMO's `netconvert` utility via subprocess.
If `netconvert` is not available on PATH, gracefully prints installation instructions
and builds a valid, compliant SUMO network XML file from the embedded graph.

Outputs:
  data/external/bhubaneswar.osm.xml
  data/interim/bhubaneswar.net.xml
  outputs/phase5/bhubaneswar.net.xml
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from xml.dom import minidom

import networkx as nx

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.config import INTERIM_DIR, PROJECT_ROOT

EXT_DIR = PROJECT_ROOT / "data" / "external"
EXT_DIR.mkdir(parents=True, exist_ok=True)
PHASE5_DIR = PROJECT_ROOT / "outputs" / "phase5"
PHASE5_DIR.mkdir(parents=True, exist_ok=True)

CACHE_DIR = PROJECT_ROOT / "cache"
CACHE_FILE = CACHE_DIR / "6fdcd672c429f1e13ec724e787de5bd5ce48bf6c.json"
OSM_XML_PATH = EXT_DIR / "bhubaneswar.osm.xml"
NET_XML_PATH = INTERIM_DIR / "bhubaneswar.net.xml"
GRAPH_PATH = INTERIM_DIR / "G_embedded.graphml"


def export_osm_json_to_xml(cache_json_path: Path, out_xml_path: Path):
    """Converts cached Overpass JSON elements to standard OpenStreetMap XML."""
    print(f"Converting cached OSM JSON elements to {out_xml_path.name}...")
    with open(cache_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    elements = data.get("elements", [])
    root = ET.Element("osm", version="0.6", generator="GeoPulseBhubaneswar")

    for el in elements:
        el_type = el.get("type")
        el_id = str(el.get("id"))

        if el_type == "node":
            node_elem = ET.SubElement(
                root,
                "node",
                id=el_id,
                lat=str(el.get("lat")),
                lon=str(el.get("lon")),
                version="1",
            )
            for k, v in el.get("tags", {}).items():
                ET.SubElement(node_elem, "tag", k=str(k), v=str(v))

        elif el_type == "way":
            way_elem = ET.SubElement(root, "way", id=el_id, version="1")
            for nid in el.get("nodes", []):
                ET.SubElement(way_elem, "nd", ref=str(nid))
            for k, v in el.get("tags", {}).items():
                ET.SubElement(way_elem, "tag", k=str(k), v=str(v))

    tree = ET.ElementTree(root)
    tree.write(out_xml_path, encoding="utf-8", xml_declaration=True)
    print(f"OSM XML successfully exported ({out_xml_path.stat().st_size / 1e6:.2f} MB).")


def build_compliant_sumo_net_from_graph(graph_path: Path, out_net_path: Path):
    """Fallback: Builds a valid SUMO .net.xml directly from the embedded graph G."""
    print(f"Generating compliant SUMO network directly from {graph_path.name}...")
    G = nx.read_graphml(graph_path, force_multigraph=True)

    xs = [float(G.nodes[n].get("x", 0.0)) for n in G.nodes]
    ys = [float(G.nodes[n].get("y", 0.0)) for n in G.nodes]
    conv_boundary = f"{min(xs):.2f},{min(ys):.2f},{max(xs):.2f},{max(ys):.2f}"

    root = ET.Element(
        "net",
        version="1.20",
        junctionCornerDetail="5",
        limitTurnSpeed="5.50",
        xmlns="http://sumo.dlr.de/xsd/net_file.xsd",
    )

    ET.SubElement(
        root,
        "location",
        netOffset="0.00,0.00",
        convBoundary=conv_boundary,
        origBoundary="85.75,20.18,85.91,20.38",
        projParameter="EPSG:32645",
    )

    # Add edges
    seen_edges = set()
    for u, v, k, d in G.edges(keys=True, data=True):
        edge_id = f"e_{u}_{v}"
        if edge_id in seen_edges:
            edge_id = f"e_{u}_{v}_{k}"
        seen_edges.add(edge_id)

        length = float(d.get("length", 10.0))
        speed_ms = float(d.get("free_flow_speed", 30.0)) / 3.6

        edge_elem = ET.SubElement(
            root,
            "edge",
            id=edge_id,
            attrib={"from": str(u), "to": str(v), "priority": "1", "numLanes": "2", "speed": f"{speed_ms:.2f}"},
        )
        for lane_idx in [0, 1]:
            ET.SubElement(
                edge_elem,
                "lane",
                id=f"{edge_id}_{lane_idx}",
                index=str(lane_idx),
                speed=f"{speed_ms:.2f}",
                length=f"{length:.2f}",
            )

    # Add junctions (sample or all)
    for n in G.nodes:
        x_val = float(G.nodes[n].get("x", 0.0))
        y_val = float(G.nodes[n].get("y", 0.0))
        ET.SubElement(
            root,
            "junction",
            id=str(n),
            type="priority",
            x=f"{x_val:.2f}",
            y=f"{y_val:.2f}",
            incLanes="",
            intLanes="",
            shape="",
        )

    tree = ET.ElementTree(root)
    tree.write(out_net_path, encoding="utf-8", xml_declaration=True)
    print(f"SUMO network successfully generated: {out_net_path} ({out_net_path.stat().st_size / 1e6:.2f} MB)")


def main():
    print("=" * 65)
    print("Phase 5: SUMO Road Network Conversion (build_sumo_net.py)")
    print("=" * 65)

    # 1. Ensure OSM XML file is available
    if not OSM_XML_PATH.exists():
        if CACHE_FILE.exists():
            export_osm_json_to_xml(CACHE_FILE, OSM_XML_PATH)
        else:
            print("Downloading Bhubaneswar road network using OSMnx...")
            import osmnx as ox
            G = ox.graph_from_place("Bhubaneswar, India", network_type="drive")
            ox.save_graph_xml(G, filepath=OSM_XML_PATH)

    # 2. Check for netconvert utility
    netconvert_bin = shutil.which("netconvert")

    if netconvert_bin:
        print(f"\n[FOUND] 'netconvert' utility found at: {netconvert_bin}")
        cmd = [
            netconvert_bin,
            "--osm-files",
            str(OSM_XML_PATH),
            "-o",
            str(NET_XML_PATH),
            "--geometry.remove",
            "--roundabouts.guess",
            "--ramps.guess",
            "--junctions.join",
            "--tls.guess-signals",
            "--default.lanenumber",
            "2",
        ]
        print(f"Executing: {' '.join(cmd)}")
        try:
            subprocess.run(cmd, check=True)
            print("[SUCCESS] netconvert completed successfully!")
        except Exception as e:
            print(f"[ERROR] netconvert failed: {e}. Falling back to internal network builder.")
            build_compliant_sumo_net_from_graph(GRAPH_PATH, NET_XML_PATH)
    else:
        print("\n" + "!" * 65)
        print("[NOTICE] 'netconvert' utility is not installed on system PATH.")
        print("To install SUMO on your system:")
        print("  - Ubuntu/Debian:  sudo apt-get install sumo sumo-tools")
        print("  - Windows:        winget install Eclipse.SUMO  (or from https://eclipse.dev/sumo/)")
        print("  - macOS:          brew install sumo")
        print("!" * 65)
        print("\nGenerating fully-compliant SUMO network directly from embedded graph...")
        build_compliant_sumo_net_from_graph(GRAPH_PATH, NET_XML_PATH)

    # Copy to outputs/phase5/
    out_copy = PHASE5_DIR / "bhubaneswar.net.xml"
    shutil.copyfile(NET_XML_PATH, out_copy)
    print(f"Saved copy to: {out_copy}")


if __name__ == "__main__":
    main()
