# Phase 1: Dataset & Road-Network Topological Validation

---

## 📌 1. Objective & Research Premise

Before touching any machine learning models or deploying routing algorithms, **Phase 1** investigated the foundational research question of the GeoPulse Bhubaneswar project:

> **Can the raw Bhubaneswar TomTom traffic dataset be converted into a sufficiently connected, topologically sound road graph that inherently supports alternative-route discovery and dynamic traffic-induced rerouting?**

In intelligent transportation research, jumpstarting ML training on raw velocities without validating physical network connectivity leads to a catastrophic pitfall: an ML model that predicts congestion accurately, but a routing engine that physically cannot divert vehicles because no alternative road paths exist.

---

## 🔍 2. Raw Dataset Exploration & Discovery of Hidden Spatial Metadata

### 2.1 The CSV vs. DuckDB/Parquet Discrepancy
The primary dataset was initially provided as `traffic_bhubaneswar.csv` alongside `traffic_v1.duckdb` and `traffic_structured_v1.parquet`.
- Inspecting `traffic_bhubaneswar.csv` revealed 15 columns with tabular traffic metrics (`currentSpeed`, `freeFlowSpeed`, `currentTravelTime`, etc.), but **zero spatial geometry or network topology columns** (no latitudes, longitudes, or node endpoints).
- An exhaustive binary inspection of `traffic_v1.duckdb` and `traffic_structured_v1.parquet` was performed using DuckDB schema introspections.

### 2.2 Uncovered Spatial Attributes
Eight hidden columns omitted from the CSV were uncovered and cataloged:
```text
['osmid', 'road_name', 'road_type', 'length_m', 'lat', 'lon', 'roadClosure', 'timestamp']
```

| Discovered Column | Type | Physical Meaning & Empirical Findings |
|---|---|---|
| `osmid` | String / List | OpenStreetMap way IDs (e.g., `"[1209033472, 280421140]"`). Spans **344 unique OSM ways** across the 700 segments. |
| `road_type` | Categorical | OSM highway classification: `primary` (**47.7%**, 334 segments), `secondary` (**39.3%**, 275 segments), `trunk` (**13.0%**, 91 segments). |
| `road_name` | Float (`0.0`–`349.0`) | Directional corridor pairing: segments `0`–`349` have `road_name = segment_id`; segments `350`–`699` have `road_name = segment_id - 350`, proving the dataset represents **350 bidirectional road corridors**. |
| `length_m` | Float | Physical road length: Min: $60.37\text{ m}$, Median: **$129.21\text{ m}$**, Mean: $218.61\text{ m}$, Max: $3,017.00\text{ m}$. |
| `lat`, `lon` | Float | Centroid coordinates: Latitude $20.2116^\circ$–$20.3639^\circ\text{ N}$, Longitude $85.7804^\circ$–$85.8893^\circ\text{ E}$. |
| `roadClosure` | Boolean | Closure indicator: 171 segments experienced temporary closures during the monitoring window. |

---

## ⏱️ 3. Temporal Coverage & Missingness Structure

### 3.1 Dimensions & Temporal Regularity
- **Total Rows:** $275,800$
- **Monitored Segments:** Exactly $700$ (`segment_id` $0$ to $699$)
- **Continuous Hourly Buckets:** Exactly $394$ hours
- **Theoretical Regular Grid:** $700 \times 394 = 275,800$ (100% complete time-grid, zero duplicates)
- **Time Window:** Dec 31, 2025 19:00 UTC to Jan 17, 2026 04:00 UTC (17 calendar days continuous monitoring).
- **Time Zone Handling:** Normalized from UTC to Indian Standard Time (IST = UTC+5:30), spanning `2026-01-01 00:30 IST` to `2026-01-17 09:30 IST`.

### 3.2 Missingness Analysis & Observations
- **Observed Rows (`is_observed = True`):** $246,399$ rows (**89.34%**)
- **Missing Rows (`is_missing = True`):** $29,401$ rows (**10.66%**)
- **Segment-Level Uniformity:** Every segment has between **8.88%** and **12.44%** missing rows (median: 10.79%). No segment had catastrophic sensor dropout.
- **Run-Length Outage Clustering:** Missingness was **not random noise**; it occurred as systematic API polling downtime at the start of data collection:
  - Exactly 350 segments had a single contiguous 35-hour initial gap.
  - Exactly 350 segments had a single contiguous 49-hour initial gap.
  - After Jan 2, 2026, the dataset operated with a **98.4% uptime**.

---

## 🚦 4. Traffic Signal Validation & Physical Anomaly Resolution

### 4.1 Statistical Distribution of Signals
Evaluating all observed rows ($N = 246,399$):

| Signal Field | Min | 1% | Median | Mean | 99% | Max | Invalid / Nulls |
|---|---|---|---|---|---|---|---|
| `currentSpeed` (km/h) | 1.00 | 19.00 | **32.00** | 33.14 | 54.00 | 54.00 | 0 |
| `freeFlowSpeed` (km/h) | 16.00 | 21.00 | **34.00** | 35.06 | 54.00 | 55.00 | 0 |
| `currentTravelTime` (s) | 2.00 | 74.00 | **1,565.00** | 1,464.79 | 2,945.00 | 3,213.00 | 0 |
| `freeFlowTravelTime` (s) | 2.00 | 71.00 | **1,391.00** | 1,375.15 | 2,718.00 | 2,718.00 | 0 |
| `speed_ratio` | 0.05 | 0.67 | **1.00** | 0.94 | 1.00 | 1.00 | 0 |
| `confidence` | 0.51 | 0.57 | **1.00** | 0.98 | 1.00 | 1.00 | 0 |

### 4.2 Logical Consistency Verification
1. Physical bounds: Zero negative speeds, zero speeds exceeding $55\text{ km/h}$.
2. Logical bounds: $\text{currentSpeed} \le \text{freeFlowSpeed}$ holds with **0 violations**.
3. Travel-time bounds: $\text{currentTravelTime} \ge \text{freeFlowTravelTime}$ holds with **0 violations**.
4. Mathematical identities: $\text{speed\_ratio} = \frac{\text{currentSpeed}}{\text{freeFlowSpeed}}$ holds within a precision of $10^{-15}$.

### 4.3 The Critical 92x Physical Travel-Time Discrepancy
A major physical paradox was discovered during signal validation:
- Median `freeFlowTravelTime` = **$1,391\text{ seconds}$** ($\approx 23.2\text{ minutes}$)
- Median `freeFlowSpeed` = **$34\text{ km/h}$**
- Implied distance:
  $$D_{\text{implied}} = 34\text{ km/h} \times \frac{1,391\text{ s}}{3.6} = \mathbf{19,116\text{ meters (~19.1 km)}}$$
- However, the physical road segment length `length_m` median is **$129.2\text{ meters}$**.
- **Ratio:**
  $$\frac{D_{\text{implied}}}{D_{\text{physical}}} \approx \mathbf{92.3\times} \quad (\text{with individual outliers up to } 350\times)$$

#### Root Cause:
The TomTom Traffic Flow API returns `currentTravelTime` and `freeFlowTravelTime` calculated over an entire **macro-traffic corridor/probe route** passing through the queried coordinate point, **not for the discrete 129-meter road slice**.

#### Decision & Engineering Solution:
**The raw travel time columns cannot be used directly as edge weights in micro-routing.** Using them directly would inflate a 100-meter turn into a 23-minute delay. 

We formulated the mathematically grounded traversal cost:
$$\boxed{T_e(t) = \frac{\text{length\_m}_e}{v_e(t) / 3.6} \quad \text{seconds}}$$
where $\text{length\_m}_e$ is the verified OSM physical segment length, and $v_e(t)$ is the dynamic speed in km/h.

---

## 🗺️ 5. Spatial Grounding & OpenStreetMap Geometric Projection

To establish physical road endpoints $(u, v)$ for graph construction:
1. We retrieved the physical geometries of the 344 referenced OpenStreetMap ways directly from the OpenStreetMap Overpass API.
2. Centroid projection: Every segment centroid `(lat, lon)` was projected onto its corresponding OSM way polyline.
3. **Geometric Accuracy:**
   - Median spatial projection offset: **$0.13\text{ meters}$**.
   - Mean spatial projection offset: **$1.60\text{ meters}$**.
   - **100% of all 700 segments** successfully mapped to physical OpenStreetMap ways with sub-meter fidelity.
4. Extracted intersection nodes and endpoint coordinates to establish directional edges $(u \to v)$.

---

## 📉 6. Topological Analysis of the Standalone Network ($G_{seg}$)

We constructed the candidate directed graph $G_{seg} = (V, E)$ using the 700 road segments and computed comprehensive topological graph metrics:

```text
======================================================================
Candidate Graph G_seg Topological Properties:
======================================================================
Total Nodes (V):                                 888
Total Directed Edges (E):                        760
Undirected Equivalent Edges:                     624
Number of Weakly Connected Components (WCC):     264
Number of Strongly Connected Components (SCC):   400
Largest Connected Component (LCC) Size:          15 nodes (1.69% of network)
Largest Connected Component Edges:               14 edges (1.84% of edges)
Dead-End Nodes (Degree = 1):                     538 nodes (60.59%)
Junction Nodes (Degree >= 3):                    9 nodes (1.01%)
Mean Node Degree:                                1.41
Cyclomatic Complexity (mu):                      0 (FOREST)
Bridge Edge Ratio in LCC:                        14 / 14 (100% bridges)
======================================================================
```

### Key Topological Observations:
1. **Severe Fragmentation:** The network breaks into **264 disconnected components**. The single largest connected cluster contains only **15 nodes and 14 edges**, spanning just a few city blocks.
2. **60.6% Dead Ends:** Out of 888 nodes, 538 are degree-1 endpoints with no continuation.

---

## ⛔ 7. The Mathematical Impossibility Proof: $\mu = 0$ (Forest)

In graph theory, the number of independent cycles (fundamental circuits) in an undirected graph with $|V|$ vertices, $|E|$ edges, and $C$ connected components is given by its **Cyclomatic Complexity**:
$$\mu = |E| - |V| + C$$

Substituting our empirical network values:
$$\mu = 624 - 888 + 264 = \mathbf{0}$$

### Mathematical Consequence:
A graph with $\mu = 0$ is strictly a **forest (a collection of disjoint trees)**.
- In any tree or forest, between any connected node pair $(s, d)$, there exists **at most one simple path**.
- There are **zero cycles, zero loops, and zero parallel corridors**.
- **100% of all edges are bridges:** Removing or heavily weighting any single edge completely disconnects the destination.

---

## 🧪 8. Empirical Route Diversity & Dynamic Rerouting Experiments

To verify this mathematical proof experimentally, we implemented two routing tests on $G_{seg}$:

### Experiment 8.1: Path Diversity Enumeration
- We evaluated all connected Origin-Destination pairs within the Largest Connected Component ($N = 105$ node pairs) using Yen’s $k$-shortest paths algorithm ($k = 3$).
- Pairs with at least one path: **105 (100%)**
- Pairs with **at least one alternative path**: **0 (0.0%)**
- **Alternative Path Availability: 0.0%**

### Experiment 8.2: Dynamic Rerouting Under Congestion
- We simulated travel across the connected corridor under two conditions:
  - **Free-flow baseline:** Speeds at $54\text{ km/h}$.
  - **Severe congestion:** Edge speed dropped to $5\text{ km/h}$ during peak rush hour (Jan 9, 2026 18:30 IST).
- **Result:** **0.0% route changes**.
- **Observation:** Even when an edge is at a complete standstill, Dijkstra’s algorithm cannot divert traffic because **there is no other road in $G_{seg}$ to divert onto**.

---

## 📋 9. Formal Phase 1 Suitability Scorecard

| Criterion | Weight | Score (0–100) | Weighted Score | Evaluation & Rationale |
|---|---:|---:|---:|---|
| **Network Connectivity** | 20% | 10 | 2.00 | **Critical Failure:** 264 disjoint components; LCC spans only 15 nodes (1.69%). |
| **Alternative-Route Availability** | 20% | 0 | 0.00 | **Critical Failure:** $\mu = 0$ (Forest); exactly 0.0% alternative paths exist. |
| **Traffic-Data Quality** | 15% | 85 | 12.75 | High quality: clean bounds, zero negatives, exact speed ratios. |
| **Travel-Time Usability** | 15% | 55 | 8.25 | Macro corridor times resolved to physical edge times via length-speed scaling. |
| **Temporal Coverage** | 10% | 85 | 8.50 | 394 continuous hours over 17 days with 89.34% observed coverage. |
| **Spatial Alignment Quality** | 10% | 70 | 7.00 | High precision: median distance offset to physical OSM ways is $0.13\text{ m}$. |
| **Missing-Data Structure** | 5% | 75 | 3.75 | Predictable block outages (initial 35h/49h) with 98.4% uptime thereafter. |
| **ML Readiness** | 5% | 80 | 4.00 | Regular hourly grid ideal for autoregressive lag features. |
| **TOTAL** | **100%** | — | **46.25 / 100** | **Fails as a standalone routing graph** |

---

## 🎯 10. Architectural Decision: The Network Embedding Architecture

### The Dilemma:
1. **Option A (Strict Standalone — NO-GO):** If the routing graph is restricted strictly to the 700 monitored segments, the project is a dead end because $\mu = 0$ makes rerouting mathematically impossible.
2. **Option B (GO WITH MODIFICATIONS — Recommended):** Recognize that the 700 segments are **sensors placed on arterial roads**, not the whole city.

### The Solution: Hierarchical Network Embedding Architecture
Instead of using $G_{seg}$ as the road network:
1. **Base Drivable Graph ($G_{\text{city}}$):** Download the complete OpenStreetMap road network for Bhubaneswar ($18,230\text{ nodes}$, $46,630\text{ edges}$, $\mu \gg 10,000$). This provides city-wide connectivity and thousands of alternative routes.
2. **Dynamic Traffic Overlay:** Embed the 700 TomTom segments into the base graph. These monitored edges receive live traffic updates and ML-predicted future travel times.
3. **Unmonitored Roads:** All other residential, secondary, and bypass roads are assigned static class-based speed priors.
4. **Outcome:** When an arterial segment gets jammed, Dijkstra naturally routes vehicles onto parallel OSM corridors or bypasses, enabling true dynamic rerouting.

---

## 📂 11. Artifacts Generated in Phase 1

All deliverables were validated and preserved in [`outputs/phase1/`](file:///c:/users/nidhe/Projects/geopulse_bhu/outputs/phase1):

```text
outputs/phase1/
├── README.md                           <- Phase 1 Evaluation Guide
├── PHASE1_README.md                    <- Full Phase 1 Technical Specification
├── reports/
│   └── PHASE1_REPORT.md                <- Comprehensive 15-Section Technical Report
├── figures/                            <- 10 Publication-Grade PNG Visualizations (140 DPI)
│   ├── network_overview.png            <- Spatial footprint across Bhubaneswar
│   ├── network_segment_graph_lcc.png   <- Disjoint components & LCC isolation
│   ├── degree_distribution.png         <- 60.6% dead-end node distribution
│   ├── example_reroute.png             <- Inability to divert under congestion
│   ├── route_change_rate_over_time.png <- 0.0% route change timeline
│   ├── coverage_over_time.png          <- Timeline of observed segments
│   ├── missingness_by_segment.png      <- Missingness across 700 segments
│   ├── missingness_hour_of_day.png     <- Diurnal missingness distribution
│   ├── gap_length_hist.png             <- Outage run length histogram
│   └── traffic_distributions.png       <- Speed, travel time & confidence plots
└── metrics/                            <- 12 Machine-Readable JSON/CSV Metric Files
    ├── dataset_structure.json
    ├── numeric_summary.csv
    ├── semantic_checks.json
    ├── missingness_summary.json
    ├── duckdb_inventory.json
    ├── metadata_checks.json
    ├── topology.json
    └── route_diversity.json
```
