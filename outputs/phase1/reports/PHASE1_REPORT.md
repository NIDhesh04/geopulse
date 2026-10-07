# Phase 1 Technical Report: Bhubaneswar Traffic Dataset & Road Network Validation

**Project:** Intelligent Transportation & Dynamic Route Planning (GeoPulse Bhubaneswar)  
**Author:** AI Research & Engineering Agent  
**Date:** October 7, 2026  
**Status:** Complete  

---

## Executive Summary

| Item | Result |
|---|---|
| **Dataset** | Bhubaneswar Traffic Flow Dataset (`traffic_bhubaneswar.csv`, DuckDB, Parquet) |
| **Segments** | 700 unique segments (indices `0` to `699`) |
| **Time Range** | Dec 31, 2025 19:00 UTC → Jan 17, 2026 04:00 UTC (394 hourly timestamps, 17 days) |
| **Observed Coverage** | 89.34% observed (246,399 rows), 10.66% explicit missing grid (29,401 rows) |
| **Physical Graph ($G_{seg}$)** | 888 nodes, 760 directed edges |
| **Weakly Connected Components** | 264 disconnected components |
| **Largest Component Size** | 15 nodes (1.69% of the network), 14 edges (1.84%) |
| **Dead-End Nodes (Degree = 1)** | 538 nodes (60.59% of all nodes) |
| **Cyclomatic Complexity ($\mu$)** | **0** (Forest: zero cycles across the entire network) |
| **Alternative-Route Availability** | **0.0%** (Exactly 0 alternative simple paths exist between any OD pair) |
| **Traffic-Dependent Route Changes** | **0.0%** (Congestion cannot divert traffic because no alternative paths exist) |
| **Formal Suitability Score** | **46.25 / 100** |
| **Final Recommendation** | **GO WITH MODIFICATIONS (Conditional) / NO-GO (Strict Standalone)** |

---

## 1. Dataset Overview & Dimensions

The dataset represents hourly traffic observations across Bhubaneswar, Odisha, India collected via the TomTom Traffic Flow API.

- **Total Rows:** 275,800
- **Total Columns:** 15 in CSV, 17 in Parquet/DuckDB
- **Unique Road Segments:** 700 (`segment_id` 0 to 699)
- **Unique Hourly Buckets:** 394 continuous hours
- **Theoretical Grid Size:** $700 \times 394 = 275,800$ (100% regular grid, 0 duplicate segment-hour rows)
- **Time Zone:** Timestamps stored in UTC (`hour`), covering Indian Standard Time (IST = UTC+5:30) from `2026-01-01 00:30 IST` to `2026-01-17 09:30 IST`.
- **Primary Signals:** `currentSpeed`, `freeFlowSpeed`, `currentTravelTime`, `freeFlowTravelTime`, `confidence`, `speed_ratio`, `congestion_level`, `is_congested`, `is_observed`, `is_missing`.

---

## 2. DuckDB & Parquet Schema Findings

Inspection of `traffic_v1.duckdb` and `traffic_structured_v1.parquet` revealed **8 critical spatial columns omitted from `traffic_bhubaneswar.csv`**:

```text
Columns in DuckDB/Parquet but missing from CSV:
['osmid', 'road_name', 'road_type', 'length_m', 'lat', 'lon', 'roadClosure', 'timestamp']
```

### Static Road Metadata Inventory
- `osmid`: OpenStreetMap way ID(s) stored as string representations of integers or lists (e.g. `"[1209033472, 280421140, 1317533102]"`). There are **344 unique OSM way IDs** across all 700 segments.
- `road_type`: OSM highway classification:
  - `primary`: 334 segments (47.7%)
  - `secondary`: 275 segments (39.3%)
  - `trunk`: 91 segments (13.0%)
- `road_name`: Contains float values `0.0` to `349.0`. Segments 0–349 have `road_name = segment_id`, while segments 350–699 have `road_name = segment_id - 350`. This proves the dataset was generated from **350 base road links**.
- `length_m`: Physical length of the segment in meters (min: 60.37m, median: 129.21m, mean: 218.61m, max: 3,017.00m).
- `lat`, `lon`: Centroid coordinates of the segment (bounding box: lat 20.2116° to 20.3639° N, lon 85.7804° to 85.8893° E).
- `roadClosure`: Boolean flag indicating road closures (171 segments had temporary closures recorded).

---

## 3. Temporal Coverage & Missingness Analysis

### Temporal Regularity
The dataset spans exactly 394 continuous hours without any missing time buckets. Every single segment contains exactly 394 rows in the grid.

### Missingness Distribution
- **Observed Rows (`is_observed = True`):** 246,399 (89.34%)
- **Missing Rows (`is_missing = True`):** 29,401 (10.66%)
- `is_observed == ~is_missing` holds 100% consistently across all 275,800 rows.

### Segment-Level Missingness
- Every segment has between 8.88% and 12.44% missing rows (median: 10.79%).
- No segments have catastrophic (>20%) missingness.
- Segments 0–349 have ~8.88% missingness; segments 350–699 have ~12.44% missingness.

### Temporal Structure of Missingness
- Out of 394 hours, **344 hours are 100% fully observed** across all 700 segments.
- **35 hours have 100% missing data** (systemic API polling outages, concentrated on Dec 31 – Jan 1).
- Missingness occurs in **long consecutive runs** rather than random point noise:
  - Exactly 350 segments experienced a single 35-hour initial gap.
  - Exactly 350 segments experienced a single 49-hour initial gap.
  - After Jan 2, 2026, the dataset has an observed uptime exceeding 98%.

---

## 4. Traffic Signal & Semantic Validation

Validation of observed rows (`is_observed = True`, $N = 246,399$):

| Field | Min | 1% | Median | Mean | 99% | Max | Invalid / Nulls |
|---|---|---|---|---|---|---|---|
| `currentSpeed` (km/h) | 1.0 | 19.0 | 32.0 | 33.14 | 54.0 | 54.0 | 0 |
| `freeFlowSpeed` (km/h) | 16.0 | 21.0 | 34.0 | 35.06 | 54.0 | 55.0 | 0 |
| `currentTravelTime` (s) | 2.0 | 74.0 | 1,565.0 | 1,464.79 | 2,945.0 | 3,213.0 | 0 |
| `freeFlowTravelTime` (s) | 2.0 | 71.0 | 1,391.0 | 1,375.15 | 2,718.0 | 2,718.0 | 0 |
| `speed_ratio` | 0.053 | 0.667 | 1.000 | 0.944 | 1.000 | 1.000 | 0 |
| `confidence` | 0.505 | 0.574 | 1.000 | 0.977 | 1.000 | 1.000 | 0 |

### Logical Consistency Checks
- `currentSpeed <= 0`: 0 violations.
- `currentSpeed > freeFlowSpeed`: 0 violations.
- `currentTravelTime < freeFlowTravelTime`: 0 violations.
- `speed_ratio == currentSpeed / freeFlowSpeed`: Holds exactly (max absolute difference $< 10^{-15}$).
- `speed_ratio > 1.0` or `< 0.0`: 0 violations.

### Travel Time Semantics: Critical Discrepancy Identified
A critical physical discovery was uncovered regarding `currentTravelTime` and `freeFlowTravelTime`:
- In the dataset, median `freeFlowTravelTime` is **1,391 seconds (~23.2 minutes)**, and median `freeFlowSpeed` is **34 km/h**.
- Implied distance: $34 \text{ km/h} \times 1391 \text{ s} / 3.6 = \mathbf{19,116\text{ meters (~19.1 km)}}$!
- However, the physical road segment length `length_m` has a median of **129.2 meters**!
- Ratio: $\frac{\text{TomTom Implied Length}}{\text{Physical Segment Length}} \approx \mathbf{92.3\times}$ (range up to $350\times$).

**Root Cause:**
The TomTom Traffic Flow API returns speed and travel time for a macro-level traffic corridor or probe route passing through the queried coordinate, **NOT for the isolated 129-meter road slice**.
Therefore:
1. `currentSpeed` and `freeFlowSpeed` represent the true local velocity (km/h) on that corridor.
2. The raw `currentTravelTime` and `freeFlowTravelTime` columns **CANNOT be used directly as edge weights** for micro-routing.
3. **Correct Edge Travel Time Formulation:**
   $$T_e(t) = \frac{\text{length\_m}_e}{v_e(t) / 3.6} \quad \text{seconds}$$
   where $v_e(t)$ is `currentSpeed` at hour $t$ (or `freeFlowSpeed` under free-flow).

---

## 5. Segment-to-Physical Road Mapping & Graph Construction

### Spatial Verification
Using the 344 OSM way IDs from the static metadata, we retrieved the exact node geometries directly from OpenStreetMap:
- Distance from every segment centroid `(lat, lon)` to its OSM way polyline: **Median = 0.13 meters, Mean = 1.60 meters**.
- 100% of the 700 segments physically lie on OpenStreetMap ways.

### Candidate Graph Construction ($G_{seg}$)
We constructed the directed graph $G_{seg} = (V, E)$ directly from the physical road segments:
- **Total Segments Matched:** 700 / 700 (100%)
- **Total Nodes:** 888 nodes (intersections and segment endpoints)
- **Total Directed Edges:** 760 edges (624 undirected segments)
- **Median Length Match Error:** 0.00019 meters

---

## 6. Graph Topology Analysis: The Fundamental Blocker

Evaluating the candidate road graph $G_{seg}$ yielded decisive empirical results:

```text
Topology Metrics for G_seg:
=========================================
Total Nodes:                     888
Total Directed Edges:            760
Undirected Edges:                624
Number of Weakly Connected Components: 264
Largest Component Size:          15 nodes (1.69% of all nodes)
Largest Component Edges:         14 edges (1.84% of all edges)
Dead-End Nodes (Degree = 1):     538 nodes (60.59%)
Junctions (Degree >= 3):         9 nodes (1.01%)
Mean Node Degree:                1.41
Cyclomatic Complexity (mu):      0 (FOREST)
Largest CC Bridges:              14 / 14 edges (100% bridges)
```

### Topological Diagnosis
1. **Extreme Fragmentation:** The 700 segments are shattered into **264 disconnected components**. The single largest connected cluster contains only **15 nodes and 14 edges**.
2. **Zero Cycles ($\mu = 0$):** Cyclomatic complexity $\mu = |E| - |V| + C = 624 - 888 + 264 = 0$. Mathematically, $G_{seg}$ is a **forest** consisting of isolated tree branches and linear corridor fragments.
3. **100% Bridge Edges:** Every single edge in the largest component is a bridge. There are zero closed loops or alternative branches.

---

## 7. Alternative-Route & Traffic-Dependent Routing Experiments

### Experiment 1: Simple Path Diversity on $G_{seg}$
- Origin-Destination (OD) pairs tested across all connected node pairs in the largest component ($N = 105$ pairs):
  - Pairs with a valid path: 105 (100%)
  - Pairs with **at least one alternative simple path**: **0 (0.0%)**
  - Alternative path availability: **0.0%**

### Experiment 2: Dynamic Rerouting Under Congestion
We evaluated routing decisions between the Free-Flow baseline (Scenario A) and the most congested hours (Scenarios B & C, e.g., Jan 9, 2026 13:00 UTC):
- **Route Change Rate:** **0.0%**
- **Reason:** In a tree graph with $\mu = 0$, the unique path between node $u$ and node $v$ is the *only* path that exists. Even when an edge experiences severe congestion (speed dropping from 54 km/h to 10 km/h), Dijkstra's algorithm cannot divert around it because **there is no alternative road in the graph**.

---

## 8. Dataset Suitability Scorecard

| Criterion | Weight | Score (0–100) | Weighted Score | Evaluation |
|---|---:|---:|---:|---|
| **Network connectivity** | 20% | 10 | 2.00 | **Critical Failure:** 264 components; largest component is only 1.69% of nodes. |
| **Alternative-route availability** | 20% | 0 | 0.00 | **Critical Failure:** Cyclomatic complexity = 0; exactly 0.0% alternative paths. |
| **Traffic-data quality** | 15% | 85 | 12.75 | High quality; zero negatives, speeds logically bounded, speed ratio exact. |
| **Travel-time availability** | 15% | 55 | 8.25 | Speeds valid; macro travel time must be converted to edge travel time. |
| **Temporal coverage** | 10% | 85 | 8.50 | 394 continuous hours over 17 days on a regular grid. |
| **Map/topology quality** | 10% | 70 | 7.00 | Segments precisely match OSM coordinates (median offset 0.13m). |
| **Missing-data quality** | 5% | 75 | 3.75 | 89.3% observed; missingness concentrated in 35-hour initial block outages. |
| **ML suitability** | 5% | 80 | 4.00 | High temporal continuity suitable for LSTM / GNN congestion forecasting. |
| **TOTAL** | **100%** | — | **46.25 / 100** | **Unsuitable as a standalone routing graph** |

---

## 9. Critical Blockers vs. Possible Workarounds

### Critical Blockers for a Standalone Graph
1. **Lack of Alternative Paths:** A dynamic rerouting system requires alternative routes that can become optimal when the primary path is congested. On $G_{seg}$, alternative routes do not exist.
2. **Network Disconnection:** 264 separate components prevent city-wide travel between arbitrary origins and destinations.

### The Viable Workaround: "Network Embedding"
If the research project adopts an **Embedded Sensor Architecture**:
- **Base Graph ($G_{city}$):** Download the complete OpenStreetMap road graph of Bhubaneswar (which has full connectivity and thousands of alternative routes).
- **Traffic Overlay:** The 700 TomTom segments provide real-time dynamic traffic observations and ML predictions on key arterials.
- **Unmonitored Roads:** Connecting secondary/tertiary roads in OSM are assigned static free-flow speeds.
- In this architecture, dynamic rerouting functions effectively because congestion on an arterial segment will cause Dijkstra to divert vehicles onto adjacent OSM roads.

---

## 10. Explicit Recommendation

### Decision: **GO WITH MODIFICATIONS** (or **NO-GO** under strict standalone constraints)

1. **Choose "GO WITH MODIFICATIONS" IF:**
   The professor agrees that routing occurs on the **complete Bhubaneswar OSM road graph**, with the 700 segments functioning as dynamic traffic sensor links.
2. **Choose "NO-GO" IF:**
   The project strictly demands that the routing graph consist *exclusively* of the observed traffic segments without external road network embedding. In that case, the system must revert to Delhi or a fully connected sensor network.
