"""Build the candidate Bhubaneswar road graph.

The dataset has NO endpoint/geometry fields. It does have, per segment:
  osmid (list of OSM way ids), length_m, road_type, centroid lat/lon.
That combination is the signature of an OSMnx *simplified* edge (u, v, key).
We therefore recover real endpoints by matching every segment to an edge of the
OSM drive network downloaded with OSMnx (external source, clearly labelled).
No endpoints are invented from centroids.

Match rule (per segment):
  candidate edges = edges whose osmid set == segment osmid set
                    (fallback: edges sharing >=1 osmid)
  accept best candidate if |length diff| <= max(2 m, 2%) and centroid/midpoint
  distance <= 25 m. All parallel/opposite edges satisfying the rule are kept
  (two-way roads -> both directions match, direction of TomTom reading ambiguous).

Outputs:
  data/external/bhubaneswar_drive.graphml          (cached OSM download)
  data/interim/segment_edge_match.csv              (segment -> OSM edge(s))
  data/interim/G_seg.graphml                       (graph of traffic segments only)
  outputs/phase1/metrics/graph_build.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import networkx as nx

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.config import PROJECT_ROOT, INTERIM_DIR, METRIC_DIR  # noqa: E402

EXT_DIR = PROJECT_ROOT / "data" / "external"
EXT_DIR.mkdir(parents=True, exist_ok=True)
OSM_GRAPHML = EXT_DIR / "bhubaneswar_drive.graphml"
BUFFER_DEG = 0.02  # ~2 km so boundary edges are not truncated


def _ssl_setup():
    """Corporate/AV TLS interception breaks certifi; use the Windows trust store."""
    try:
        import truststore
        truststore.inject_into_ssl()
        return "truststore"
    except Exception:
        return "default"


def load_osm(meta):
    import osmnx as ox
    if OSM_GRAPHML.exists():
        return ox.load_graphml(OSM_GRAPHML), "cache"
    mode = _ssl_setup()
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(EXT_DIR / "osmnx_cache")
    ox.settings.requests_timeout = 300
    bbox = (meta["lon"].min() - BUFFER_DEG, meta["lat"].min() - BUFFER_DEG,
            meta["lon"].max() + BUFFER_DEG, meta["lat"].max() + BUFFER_DEG)
    G = ox.graph_from_bbox(bbox, network_type="drive", simplify=True, retain_all=True,
                           truncate_by_edge=True)
    ox.save_graphml(G, OSM_GRAPHML)
    return G, f"download({mode})"


def _osm_set(v):
    if isinstance(v, list):
        return frozenset(int(x) for x in v)
    if isinstance(v, str) and v.startswith("["):
        return frozenset(int(x) for x in v.strip("[]").split(","))
    return frozenset([int(v)])


def edge_table(G):
    import osmnx as ox
    gdf = ox.graph_to_gdfs(G, nodes=False, edges=True, fill_edge_geometry=True).reset_index()
    gdf["osm_set"] = gdf["osmid"].map(_osm_set)
    geom = gdf.geometry
    gdf["cx"] = geom.centroid.x; gdf["cy"] = geom.centroid.y
    mid = geom.interpolate(0.5, normalized=True)
    gdf["mx"] = mid.x; gdf["my"] = mid.y
    return gdf


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = p2 - p1; dl = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def match(meta, E):
    by_set = {}
    by_way = {}
    for i, s in enumerate(E["osm_set"]):
        by_set.setdefault(s, []).append(i)
        for w in s:
            by_way.setdefault(w, []).append(i)
    rows = []
    for sid, r in meta.iterrows():
        sset = frozenset(int(x) for x in str(r["osmid_key"]).split("|"))
        cand = by_set.get(sset)
        how = "exact_osmid_set"
        if not cand:
            cand = sorted({i for w in sset for i in by_way.get(w, [])}); how = "partial_osmid"
        if not cand:
            rows.append(dict(segment_id=sid, matched=False, how="no_osm_way")); continue
        C = E.iloc[cand]
        d_c = haversine_m(r["lat"], r["lon"], C["cy"].values, C["cx"].values)
        d_m = haversine_m(r["lat"], r["lon"], C["my"].values, C["mx"].values)
        dist = np.minimum(d_c, d_m)
        dlen = np.abs(C["length"].values - r["length_m"])
        tol = np.maximum(2.0, 0.02 * r["length_m"])
        ok = (dlen <= tol) & (dist <= 25)
        if ok.any():
            for j in np.where(ok)[0]:
                e = C.iloc[j]
                rows.append(dict(segment_id=sid, matched=True, how=how, u=int(e["u"]), v=int(e["v"]),
                                 key=int(e["key"]), osm_len=float(e["length"]), len_diff=float(dlen[j]),
                                 centroid_dist=float(dist[j]), oneway=bool(e.get("oneway", False)),
                                 highway=str(e["highway"]), n_ok=int(ok.sum())))
        else:
            j = int(np.argmin(dist + dlen))
            rows.append(dict(segment_id=sid, matched=False, how=how + "_tolerance_fail",
                             len_diff=float(dlen[j]), centroid_dist=float(dist[j])))
    return pd.DataFrame(rows)


def build_segment_graph(meta, M, G_osm):
    """G_seg: nodes = OSM junction nodes that are endpoints of traffic segments,
    edges = traffic segments (directed per OSM). If a segment matched both
    directions of a two-way road, both directed edges are added and flagged."""
    Gs = nx.MultiDiGraph()
    for (sid, grp) in M[M["matched"]].groupby("segment_id"):
        r = meta.loc[sid]
        for _, m in grp.iterrows():
            Gs.add_edge(m["u"], m["v"], key=f"{sid}", segment_id=int(sid), length=float(m["osm_len"]),
                        road_type=r["road_type"], oneway=bool(m["oneway"]),
                        dir_ambiguous=bool(len(grp) > 1))
    for n in Gs.nodes:
        Gs.nodes[n]["x"] = float(G_osm.nodes[n]["x"]); Gs.nodes[n]["y"] = float(G_osm.nodes[n]["y"])
    return Gs


def main():
    meta = pd.read_csv(INTERIM_DIR / "segment_metadata.csv", index_col=0)
    G_osm, src = load_osm(meta)
    E = edge_table(G_osm)
    M = match(meta, E)
    M.to_csv(INTERIM_DIR / "segment_edge_match.csv", index=False)
    seg_ok = M.groupby("segment_id")["matched"].any()
    n_dir = M[M["matched"]].groupby("segment_id").size()
    Gs = build_segment_graph(meta, M, G_osm)
    nx.write_graphml(Gs, INTERIM_DIR / "G_seg.graphml")

    # physical (undirected) distinct edges covered by the 700 segments
    phys = M[M["matched"]].apply(lambda r: tuple(sorted((r["u"], r["v"]))) + (r["osm_len"].round(1),), axis=1)
    info = {
        "osm_source": src,
        "osm_nodes": G_osm.number_of_nodes(), "osm_edges": G_osm.number_of_edges(),
        "segments_matched": int(seg_ok.sum()), "segments_unmatched": int((~seg_ok).sum()),
        "match_how": M.drop_duplicates("segment_id")["how"].value_counts().to_dict(),
        "segments_matching_1_directed_edge": int((n_dir == 1).sum()),
        "segments_matching_2plus_directed_edges": int((n_dir >= 2).sum()),
        "len_diff_m_summary": M.loc[M["matched"], "len_diff"].describe().to_dict(),
        "centroid_dist_m_summary": M.loc[M["matched"], "centroid_dist"].describe().to_dict(),
        "distinct_physical_edges_covered": int(phys.nunique()),
        "segments_sharing_physical_edge": int(phys.duplicated(keep=False).sum()),
        "G_seg_nodes": Gs.number_of_nodes(), "G_seg_directed_edges": Gs.number_of_edges(),
        "unmatched_examples": M[~M["matched"]].head(10).to_dict(orient="records"),
    }
    (METRIC_DIR / "graph_build.json").write_text(json.dumps(info, indent=2, default=str))
    print(json.dumps(info, indent=1, default=str))


if __name__ == "__main__":
    main()
