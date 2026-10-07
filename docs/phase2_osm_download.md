# Phase 2: Bhubaneswar OSM Road Graph Download & Verification Report

**Project:** GeoPulse — AI-Based Dynamic Traffic Routing System  
**Phase:** 2 — OSM Driving Road Graph Download and Verification  
**Status:** `PHASE 2 COMPLETE`  
**Execution Timestamp:** 2026-10-07 14:59:00 IST (UTC+05:30)  
**Environment:** Python 3.13.9 | OSMnx 2.1.1 | NetworkX 3.4.2  

---

## 1. Provenance and Acquisition Details

The road network was acquired strictly replicating the query and parameters established in the project notebook [`notebooks/bhubaneshwar_dataset.ipynb`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/notebooks/bhubaneshwar_dataset.ipynb).

- **Place Query:** `"Bhubaneswar, Odisha, India"`
- **Network Type:** `"drive"` (drivable public road network)
- **Graph Simplification:** `simplify=True` (collapses intermediate geometry nodes into single edges)
- **Retain All:** `retain_all=False` (default: retains only connected drivable components)
- **Coordinate Reference System (CRS):** `EPSG:4326` (WGS84 latitude/longitude)
- **Output Destination:** [`data/raw/osm/bhubaneswar_drive.graphml`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/data/raw/osm/bhubaneswar_drive.graphml)
- **File Size:** `18,569,800` bytes (17.71 MB)
- **File SHA-256 Checksum:** `7d363f7109fea13b426c3d76d34b1bb9bf58654704fe07c132f7cbcb101d8cf8`

---

## 2. Graph Topological Verification

The downloaded graph was loaded and verified as a directed multi-graph:

| Parameter | Observed Value | Expected Reference | Match Status |
|---|---|---|---|
| **Graph Class** | `networkx.classes.multidigraph.MultiDiGraph` | `MultiDiGraph` | Identical |
| **Node Count ($|V|$)** | **18,260** | 18,260 | **Exact Match** |
| **Directed Edge Count ($|E|$)** | **46,679** | 46,679 | **Exact Match** |
| **Weakly Connected Components** | **1** | 1 | Complete global reachability |
| **Largest Weak Component Nodes** | **18,260** (100.0%) | 18,260 | Entire graph is weakly connected |
| **Strongly Connected Components** | **15** | 15 | Expected for real directed road networks |
| **Largest Strong Component Nodes** | **18,230** (99.84%) | 18,230 | 99.84% mutually reachable |

### Note on Exact Match
The node count (18,260) and edge count (46,679) match the previous project audit and notebook summary **exactly**. Because the original OSM response cache was preserved in `notebooks/cache/`, OSMnx re-instantiated the exact spatial topology originally used for the project, eliminating any temporal drift or discrepancies caused by later OpenStreetMap edits.

---

## 3. Geographic Bounds and City Verification

The spatial envelope of the graph was compared against the spatial envelope of the 700 TomTom road segments in `traffic_structured_v1.parquet`:

| Metric | OSM Graph Bounds | Traffic Dataset Bounds | Coverage Verification |
|---|---|---|---|
| **Minimum Latitude** | $20.2092303^\circ\text{ N}$ | $20.2116180^\circ\text{ N}$ | **True** (OSM extends 265 m south of traffic data) |
| **Maximum Latitude** | $20.3646262^\circ\text{ N}$ | $20.3639312^\circ\text{ N}$ | **True** (OSM extends 77 m north of traffic data) |
| **Minimum Longitude** | $85.7545274^\circ\text{ E}$ | $85.7803800^\circ\text{ E}$ | **True** (OSM extends 2.7 km west of traffic data) |
| **Maximum Longitude** | $85.8977276^\circ\text{ E}$ | $85.8892710^\circ\text{ E}$ | **True** (OSM extends 880 m east of traffic data) |

**Conclusion:** The graph completely encloses the entire spatial envelope of the Bhubaneswar traffic dataset with adequate boundary padding. City verification is **confirmed positive**.

---

## 4. Edge Attributes Audit

To verify suitability for subsequent Dijkstra routing and dynamic edge weight assignment:

- **Edges with Length (`length`):** 46,679 / 46,679 (**100.0%** have physical distance in meters).
- **Edges with Highway Classification (`highway`):** 46,679 / 46,679 (**100.0%** have road classification, including `primary`, `secondary`, `trunk`, `tertiary`, `residential`, and associated links).
- **Edges with Explicit Geometry (`geometry` LineString):** 20,194 / 46,679 (curved road segments possess high-resolution intermediate coordinates; straight edges inherit linear geometry directly from $u \to v$ node endpoint coordinates).

---

## 5. Next Recommended Step

Proceed to Phase 3: Map the 700 TomTom traffic segments to their corresponding directed OSM edges in `data/raw/osm/bhubaneswar_drive.graphml` using OSM IDs, heading orientation, and conservative spatial projection.
