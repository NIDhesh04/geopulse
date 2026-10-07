"""Construct the candidate road graph G_seg directly from OSM ways and nodes.

Every segment has:
- osmid_key: OSM way id(s)
- length_m: segment length in meters
- lat, lon: centroid coordinate
- road_type: road classification

Using the exact OSM geometry:
- If a segment spans the full way (or chain of ways): endpoints are way endpoints.
- If a segment is a subsegment of an OSM way: we project the centroid onto the
  way polyline to find its cumulative distance, and select the node span [u, v]
  matching length_m centered at that projection.

Outputs:
- data/interim/segment_endpoints.csv
- data/interim/G_seg.graphml
- outputs/phase1/metrics/graph_build.json
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import networkx as nx
from shapely.geometry import LineString, Point

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.config import INTERIM_DIR, METRIC_DIR, FIG_DIR, PROJECT_ROOT

EXT_DIR = PROJECT_ROOT / "data" / "external"


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2)**2
    return 2.0 * R * math.asin(math.sqrt(a))


def main():
    ways = json.load(open(EXT_DIR / "osm_ways.json", encoding="utf-8"))
    nodes = json.load(open(EXT_DIR / "osm_nodes.json", encoding="utf-8"))
    meta = pd.read_csv(INTERIM_DIR / "segment_metadata.csv", index_col=0)

    # Precompute node polyline and cumulative distances for every way
    way_geom = {}
    for wid_str, w in ways.items():
        wid = int(wid_str)
        nds = w.get("nodes", [])
        if len(nds) < 2:
            continue
        coords = []
        dists = [0.0]
        valid = True
        for i, nid in enumerate(nds):
            nd = nodes.get(str(nid))
            if not nd:
                valid = False
                break
            coords.append((nd["lon"], nd["lat"]))
            if i > 0:
                prev_nd = nodes[str(nds[i-1])]
                d = haversine_m(prev_nd["lat"], prev_nd["lon"], nd["lat"], nd["lon"])
                dists.append(dists[-1] + d)
        if valid and len(coords) >= 2:
            way_geom[wid] = {
                "nodes": nds,
                "coords": coords,
                "dists": dists,
                "total_len": dists[-1],
                "oneway": w.get("tags", {}).get("oneway", "no") in ("yes", "1", "true"),
                "highway": w.get("tags", {}).get("highway", "unclassified")
            }

    matched_records = []
    unmatched_count = 0

    for sid, r in meta.iterrows():
        wids = [int(x) for x in str(r["osmid_key"]).split("|")]
        # Filter available ways
        avail_wids = [w for w in wids if w in way_geom]
        if not avail_wids:
            unmatched_count += 1
            matched_records.append({
                "segment_id": sid, "matched": False, "u": None, "v": None,
                "length_diff": None, "oneway": False
            })
            continue

        target_len = float(r["length_m"])
        centroid_pt = Point(r["lon"], r["lat"])

        # Case 1: single way or chain of ways
        if len(avail_wids) == 1:
            wg = way_geom[avail_wids[0]]
            nds = wg["nodes"]
            dists = wg["dists"]
            tot_len = wg["total_len"]

            # If way total length matches target_len within 5% or 5m
            if abs(tot_len - target_len) <= max(5.0, 0.05 * target_len):
                u, v = nds[0], nds[-1]
                matched_records.append({
                    "segment_id": sid, "matched": True, "u": u, "v": v,
                    "actual_geom_len": tot_len, "length_diff": abs(tot_len - target_len),
                    "oneway": wg["oneway"], "highway": wg["highway"], "match_type": "full_way"
                })
            else:
                # Subsegment: project centroid onto polyline
                line = LineString(wg["coords"])
                # Normalized distance along polyline (0.0 to 1.0)
                norm_proj = line.project(centroid_pt, normalized=True)
                proj_dist_m = norm_proj * tot_len

                # Center the span [s0, s1] of length target_len
                half_len = target_len / 2.0
                s0 = max(0.0, proj_dist_m - half_len)
                s1 = min(tot_len, proj_dist_m + half_len)

                # Find closest nodes to s0 and s1
                idx0 = int(np.argmin([abs(d - s0) for d in dists]))
                idx1 = int(np.argmin([abs(d - s1) for d in dists]))
                if idx0 == idx1:
                    if idx1 < len(nds) - 1:
                        idx1 += 1
                    elif idx0 > 0:
                        idx0 -= 1

                u, v = nds[idx0], nds[idx1]
                actual_span_len = abs(dists[idx1] - dists[idx0])
                matched_records.append({
                    "segment_id": sid, "matched": True, "u": u, "v": v,
                    "actual_geom_len": actual_span_len, "length_diff": abs(actual_span_len - target_len),
                    "oneway": wg["oneway"], "highway": wg["highway"], "match_type": "subsegment"
                })
        else:
            # Multi-way chain
            tot_chain_len = sum(way_geom[w]["total_len"] for w in avail_wids)
            u = way_geom[avail_wids[0]]["nodes"][0]
            v = way_geom[avail_wids[-1]]["nodes"][-1]
            matched_records.append({
                "segment_id": sid, "matched": True, "u": u, "v": v,
                "actual_geom_len": tot_chain_len, "length_diff": abs(tot_chain_len - target_len),
                "oneway": way_geom[avail_wids[0]]["oneway"],
                "highway": way_geom[avail_wids[0]]["highway"],
                "match_type": "multi_way_chain"
            })

    df_match = pd.DataFrame(matched_records).set_index("segment_id")
    df_match.to_csv(INTERIM_DIR / "segment_endpoints.csv")

    # Build G_seg
    G_seg = nx.MultiDiGraph()
    for sid, r in meta.iterrows():
        m = df_match.loc[sid]
        if not m["matched"] or m["u"] is None or m["v"] is None:
            continue
        u, v = int(m["u"]), int(m["v"])
        if u == v:
            continue

        # Add forward edge
        G_seg.add_edge(u, v, key=f"{sid}_fwd", segment_id=int(sid),
                       length=float(r["length_m"]), road_type=str(r["road_type"]),
                       freeFlowSpeed=float(r["ffs"]), freeFlowTravelTime=float(r["fftt"]))
        # If road is bidirectional or direction is unconstrained, add reverse edge as candidate
        # Note: in TomTom/OSM, secondary and primary roads without explicit oneway are 2-way.
        if not m.get("oneway", False):
            G_seg.add_edge(v, u, key=f"{sid}_rev", segment_id=int(sid),
                           length=float(r["length_m"]), road_type=str(r["road_type"]),
                           freeFlowSpeed=float(r["ffs"]), freeFlowTravelTime=float(r["fftt"]))

    # Add node coordinates
    for n in G_seg.nodes():
        nd = nodes.get(str(n))
        if nd:
            G_seg.nodes[n]["x"] = float(nd["lon"])
            G_seg.nodes[n]["y"] = float(nd["lat"])

    nx.write_graphml(G_seg, INTERIM_DIR / "G_seg.graphml")

    info = {
        "total_segments": len(meta),
        "segments_matched": int(df_match["matched"].sum()),
        "full_way_matches": int((df_match["match_type"] == "full_way").sum()),
        "subsegment_matches": int((df_match["match_type"] == "subsegment").sum()),
        "multi_way_chain_matches": int((df_match["match_type"] == "multi_way_chain").sum()),
        "G_seg_nodes": G_seg.number_of_nodes(),
        "G_seg_directed_edges": G_seg.number_of_edges(),
        "length_diff_median_m": float(df_match["length_diff"].dropna().median()),
        "length_diff_p95_m": float(df_match["length_diff"].dropna().quantile(0.95)),
    }
    (METRIC_DIR / "graph_build.json").write_text(json.dumps(info, indent=2, default=str))
    print("Graph build completed successfully:")
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
