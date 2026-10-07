"""Download OSM ways and nodes for Bhubaneswar.

Strategy:
1. Primary: Download the exact OSM ways and node coordinates for all 344 OSM ways
   referenced by the 700 segments using the official OpenStreetMap API (api.openstreetmap.org).
2. Major network: Download Bhubaneswar major roads (trunk, primary, secondary) using
   Overpass API with rotating endpoints, custom headers, and fallback.
"""
import ast
import json
import math
import sys
import time
from pathlib import Path
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.config import INTERIM_DIR, PROJECT_ROOT

EXT_DIR = PROJECT_ROOT / "data" / "external"
EXT_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENT = "BhubaneswarTrafficResearch/1.0 (academic research project; contact: student@geopulse.edu)"
HEADERS = {"User-Agent": USER_AGENT}


def haversine_dist(lat1, lon1, lat2, lon2):
    R = 6371000.0  # meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
    return 2.0 * R * math.asin(math.sqrt(a))


def fetch_osm_ways_and_nodes(way_ids):
    ways_cache_file = EXT_DIR / "osm_ways.json"
    nodes_cache_file = EXT_DIR / "osm_nodes.json"

    ways_data = {}
    if ways_cache_file.exists():
        ways_data = json.loads(ways_cache_file.read_text(encoding="utf-8"))
    
    needed_ways = [w for w in way_ids if str(w) not in ways_data]
    if needed_ways:
        print(f"Fetching {len(needed_ways)} ways from OSM API...")
        # Batch size up to 150
        batch_size = 100
        for i in range(0, len(needed_ways), batch_size):
            batch = needed_ways[i:i + batch_size]
            url = f"https://api.openstreetmap.org/api/0.6/ways.json?ways={','.join(map(str, batch))}"
            resp = requests.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 200:
                for el in resp.json().get("elements", []):
                    ways_data[str(el["id"])] = el
            else:
                print(f"Warning: batch {i} status {resp.status_code}")
            time.sleep(0.5)
        ways_cache_file.write_text(json.dumps(ways_data), encoding="utf-8")

    # Collect all node IDs needed
    needed_node_ids = set()
    for w in way_ids:
        w_el = ways_data.get(str(w))
        if w_el and "nodes" in w_el:
            needed_node_ids.update(w_el["nodes"])

    nodes_data = {}
    if nodes_cache_file.exists():
        nodes_data = json.loads(nodes_cache_file.read_text(encoding="utf-8"))

    needed_nodes = [nid for nid in needed_node_ids if str(nid) not in nodes_data]
    if needed_nodes:
        print(f"Fetching {len(needed_nodes)} nodes from OSM API...")
        batch_size = 200
        for i in range(0, len(needed_nodes), batch_size):
            batch = needed_nodes[i:i + batch_size]
            url = f"https://api.openstreetmap.org/api/0.6/nodes.json?nodes={','.join(map(str, batch))}"
            resp = requests.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 200:
                for el in resp.json().get("elements", []):
                    nodes_data[str(el["id"])] = {"lat": el["lat"], "lon": el["lon"]}
            else:
                print(f"Warning: nodes batch {i} status {resp.status_code}")
            time.sleep(0.3)
        nodes_cache_file.write_text(json.dumps(nodes_data), encoding="utf-8")

    return ways_data, nodes_data


def fetch_major_network_overpass(bbox):
    cache_file = EXT_DIR / "bhubaneswar_major_osm.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    query = f"""[out:json][timeout:60];
(
  way["highway"~"^(motorway|trunk|primary|secondary|tertiary)"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
);
out body;
>;
out skel qt;
"""
    endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass.private.coffee/api/interpreter"
    ]
    for ep in endpoints:
        try:
            print(f"Trying Overpass endpoint: {ep}")
            resp = requests.post(ep, data={"data": query}, headers=HEADERS, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                cache_file.write_text(json.dumps(data), encoding="utf-8")
                print(f"Successfully downloaded {len(data.get('elements', []))} elements from Overpass")
                return data
            else:
                print(f"Endpoint {ep} returned HTTP {resp.status_code}")
        except Exception as e:
            print(f"Endpoint {ep} error: {e}")

    print("Warning: Overpass download failed. Major network will be constructed from segment ways.")
    return None


def main():
    import pandas as pd
    meta = pd.read_csv(INTERIM_DIR / "segment_metadata.csv", index_col=0)
    all_ways = set()
    for osmid_key in meta["osmid_key"].dropna():
        for wid in str(osmid_key).split("|"):
            all_ways.add(int(wid))

    print(f"Identified {len(all_ways)} unique OSM ways in segment metadata.")
    ways, nodes = fetch_osm_ways_and_nodes(sorted(all_ways))
    print(f"Successfully cached {len(ways)} ways and {len(nodes)} nodes.")

    bbox = (meta["lat"].min() - 0.03, meta["lon"].min() - 0.03,
            meta["lat"].max() + 0.03, meta["lon"].max() + 0.03)
    fetch_major_network_overpass(bbox)


if __name__ == "__main__":
    main()
