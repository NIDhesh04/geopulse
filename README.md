# GeoPulse Bhubaneswar: Dynamic Traffic-Aware Route Optimization

**Research & Major Project: Intelligent Transportation Systems (ITS)**  
*Phase 0 (Problem Formulation) & Phase 1 (Dataset & Network Validation) Documentation*

---

## 📌 Executive Summary & Project Status

This repository contains the implementation, scientific validation, and empirical analysis for **Phase 0** and **Phase 1** of the GeoPulse Bhubaneswar Intelligent Transportation Project.

The system's ultimate objective is:
$$\text{Historical Traffic Data} \longrightarrow \text{ML Congestion Prediction} \longrightarrow \text{Modified Dijkstra} \longrightarrow \text{Dynamic Rerouting}$$

Before training machine learning models or implementing routing algorithms, **Phase 1** systematically answered the fundamental research question:
> **Can the Bhubaneswar dataset be converted into a sufficiently connected, meaningful road graph that supports alternative-route selection and dynamic rerouting?**

### Quick Results Summary

| Metric / Dimension | Value | Finding / Status |
|---|---|---|
| **Raw Dataset Dimensions** | 275,800 rows $\times$ 15 columns | 100% regular hourly grid ($700 \text{ segments} \times 394 \text{ hours}$) |
| **Observation Window** | Dec 31, 2025 → Jan 17, 2026 | 17 calendar days continuous monitoring |
| **Observed Data Ratio** | 89.34% ($N = 246,399$) | High data completeness; missingness occurs in 35h block outages |
| **Road Network ($G_{seg}$)** | 888 nodes, 760 directed edges | 100% matched to real OpenStreetMap ways via centroid projection |
| **Connected Components** | 264 components | **Critical finding:** Network is heavily fragmented |
| **Largest Component Size** | 15 nodes (1.69% of network) | Largest connected cluster spans only 14 road links |
| **Cyclomatic Complexity ($\mu$)** | **0 (Forest)** | Mathematically, zero cycles exist in $G_{seg}$ |
| **Alternative-Route Availability** | **0.0%** | In $G_{seg}$ alone, zero OD pairs have alternative paths |
| **Traffic-Induced Rerouting** | **0.0%** | Congestion cannot alter route choices on a tree graph |
| **Phase 1 Suitability Score** | **46.25 / 100** | Standalone graph fails; requires Network Embedding |
| **Phase 1 Decision** | **GO WITH MODIFICATIONS** | Proceed to Phase 2 via Hierarchical OSM Network Embedding |

---

## 🗺️ Mathematical Problem Definition (Phase 0)

Given:
- Directed road graph $G = (V, E)$
- Origin node $s \in V$, Destination node $d \in V$
- Physical length $D_e$ for each edge $e \in E$
- Historical traffic velocity observations up to time $t_0$
- Predicted future edge speeds $\hat{v}_e(t)$ from ML models
- Real-time traffic speed observations $v_e(t)$ available at runtime

Find the optimal path $P^*$:
$$P^* = \arg\min_{P \in \mathcal{P}_{s \to d}} \sum_{e \in P} C_e(t)$$

Under our validated physical formulation:
$$\boxed{C_e(t) = T_e(t) = \frac{D_e}{v_e(t) / 3.6}}$$
where $D_e$ is the segment length in meters, $v_e(t)$ is the travel velocity in $\text{km/h}$, and $T_e(t)$ is traversal time in seconds.

---

## 🔬 Key Scientific Discoveries in Phase 1

### 1. Recovery of Hidden Spatial Metadata (DuckDB / Parquet)
While `traffic_bhubaneswar.csv` lacked spatial geometry, inspecting `traffic_v1.duckdb` and `traffic_structured_v1.parquet` uncovered 8 unexported columns:
- `osmid`: 344 unique OpenStreetMap way IDs.
- `road_type`: Primary (47.7%), Secondary (39.3%), Trunk (13.0%).
- `road_name`: Exactly $0.0$ to $349.0$ repeated across segments $0..349$ and $350..699$, proving the dataset consists of **350 base directional road corridors**.
- `lat, lon`: Centroid coordinates matching physical OSM ways with **median offset of 0.13 meters**.

### 2. Physical Travel-Time Discrepancy Resolved
- The dataset's `freeFlowTravelTime` column has a median of **1,391 seconds (~23 minutes)** at a median speed of $34\text{ km/h}$.
- Implied distance: $34 \times 1391 / 3.6 \approx \mathbf{19.1\text{ km}}$!
- However, the physical road segment `length_m` median is **129.2 meters** ($\approx 92\times$ discrepancy).
- **Explanation:** TomTom Flow API computes travel times over macro-corridors passing through the query point. **The raw travel-time columns cannot be used directly as edge weights.** Instead, edge costs must be derived dynamically from length and speed.

### 3. Topological Evaluation & The Route Diversity Blocker
- $G_{seg}$ breaks into **264 disconnected components** with $60.6\%$ dead-end nodes (degree 1).
- The cyclomatic complexity $\mu = |E| - |V| + C = 624 - 888 + 264 = \mathbf{0}$.
- Because the network is a forest of trees, every connected origin-destination pair has **exactly one simple path**.
- Evaluating 105 connected OD pairs under free-flow vs. severe congestion resulted in **0.0% route changes**.

---

## 🏗️ Repository Architecture

```text
geopulse_bhu/
├── README.md                           <- Master project README (this document)
├── data/
│   ├── external/                       <- Downloaded OSM ways & node caches
│   │   ├── osm_ways.json               <- 344 OSM way definitions from OpenStreetMap API
│   │   └── osm_nodes.json              <- 3,500 OSM node coordinates (lat, lon)
│   └── interim/                        <- Cleaned intermediate tables & graph files
│       ├── segment_metadata.csv        <- Per-segment static attributes (OSM IDs, lengths)
│       ├── segment_endpoints.csv       <- Matched (u, v) endpoint node IDs
│       └── G_seg.graphml               <- Serialized road graph (888 nodes, 760 edges)
├── outputs/
│   └── phase1/
│       ├── README.md                   <- Phase 1 Evaluation & Experiment Guide
│       ├── reports/
│       │   └── PHASE1_REPORT.md        <- Formal 15-section technical report
│       ├── figures/                    <- Publication-grade figures (PNG, 140 DPI)
│       │   ├── network_overview.png
│       │   ├── network_segment_graph_lcc.png
│       │   ├── degree_distribution.png
│       │   ├── missingness_by_segment.png
│       │   ├── coverage_over_time.png
│       │   ├── example_reroute.png
│       │   ├── route_change_rate_over_time.png
│       │   ├── traffic_distributions.png
│       │   ├── gap_length_hist.png
│       │   └── missingness_hour_of_day.png
│       └── metrics/                    <- Machine-readable validation outputs (JSON/CSV)
│           ├── dataset_structure.json
│           ├── duckdb_inventory.json
│           ├── metadata_checks.json
│           ├── missingness_summary.json
│           ├── numeric_summary.csv
│           ├── route_diversity.json
│           ├── semantic_checks.json
│           └── topology.json
└── src/
    ├── config.py                       <- Central workspace path configurations
    ├── data/
        ├── inspect_duckdb.py           <- DuckDB / Parquet schema inspection
        ├── inspect_bhubaneswar.py      <- CSV statistical & missingness validation
        ├── inspect_metadata.py         <- Metadata extraction & TomTom signature checks
        └── download_osm_network.py     <- Official OSM API way and node fetcher
    └── graph/
        ├── build_segment_graph_from_osm.py <- Exact geometric endpoint graph builder
        ├── analyze_topology.py         <- Graph topology, degree, component, cycle analysis
        └── analyze_route_diversity.py  <- Dijkstra & alternative-route diversity tests
```

---

## 🚀 How to Reproduce Phase 1 (End-to-End)

The entire Phase 1 pipeline runs reproducibly within the local Python virtual environment:

### Step 1: Environment Setup
```powershell
# Create venv and install dependencies
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install pandas pyarrow duckdb networkx matplotlib numpy scipy shapely requests
```

### Step 2: Run Data Inspection & Validation
```powershell
# Ingest DuckDB & Parquet metadata
.\.venv\Scripts\python.exe -m src.data.inspect_duckdb

# Validate CSV structure, temporal grid, missingness, and field semantics
.\.venv\Scripts\python.exe -m src.data.inspect_bhubaneswar

# Analyze static metadata and TomTom corridor lengths
.\.venv\Scripts\python.exe -m src.data.inspect_metadata
```

### Step 3: Fetch OpenStreetMap Topologies & Build Graph
```powershell
# Download exact OSM ways (344) and nodes (3,500)
.\.venv\Scripts\python.exe -m src.data.download_osm_network

# Build candidate directed graph G_seg
.\.venv\Scripts\python.exe -m src.graph.build_segment_graph_from_osm
```

### Step 4: Run Graph Topology & Route Choice Experiments
```powershell
# Topology metrics & network visualizations
.\.venv\Scripts\python.exe -m src.graph.analyze_topology

# Alternative-route and congestion scenario evaluations
.\.venv\Scripts\python.exe -m src.graph.analyze_route_diversity
```

---

## 💡 Engineering Decision: The "Network Embedding" Workaround

Because $G_{seg}$ has $\mu = 0$ and cannot support dynamic rerouting as a standalone network, Phase 2 implements the **Hierarchical Network Embedding Architecture**:

```text
                  Complete Bhubaneswar Road Network (OSM Drive Graph)
                                (Thousands of roads & cycles)
                                             │
               ┌─────────────────────────────┴─────────────────────────────┐
               ▼                                                           ▼
       700 Monitored Segments                                    Unmonitored Roads
(Dynamic ML Speed Predictions from TomTom)               (Static Class-Based Free-Flow Priors)
               │                                                           │
               └─────────────────────────────┬─────────────────────────────┘
                                             ▼
                                Modified Dijkstra Router
                       (Diverts around congested segments)
```

1. **Routing Base:** Full OpenStreetMap drive graph for Bhubaneswar (provides city-wide reachability and thousands of alternative routes).
2. **Dynamic Overlay:** The 700 TomTom segments provide real-time updates and ML-predicted future travel times.
3. **Congestion Diversion:** When a major arterial segment becomes congested, the modified Dijkstra algorithm naturally routes traffic through adjacent unmonitored links or parallel secondary corridors.

---

## 📅 Phase 2 Implementation Roadmap (Next Steps)

- [x] **Task 2.1: City-Scale Embedded Road Graph Construction** (`src/graph/build_embedded_graph.py`)
  - Full drivable OpenStreetMap graph of Bhubaneswar extracted ($V=18,230$, $E=46,630$).
  - Largest strongly connected component (SCC) retained with metric projection (EPSG:32645).
  - All 700 monitored TomTom segments embedded with `is_monitored=True` and `segment_id`.
  - Baseline class-based free-flow speeds assigned to unmonitored links.
  - Serialized as `data/interim/G_embedded.graphml` (24.35 MB).
- [x] **Task 2.2: Custom Modified Dijkstra Engine** (`src/routing/custom_dijkstra.py`)
  - Implemented entirely from scratch using `heapq` ($O((V+E)\log V)$).
  - Multi-objective dynamic cost formulation: $\text{Cost}(u, v) = \alpha \cdot \text{Length} + \beta \cdot \text{TravelTime}(u, v)$.
  - Dynamic travel time lookup with strict minimum velocity floor ($\ge 1\text{ km/h}$) preventing division-by-zero.
- [x] **Task 2.3: Automated Route Diversity & Rerouting Validation** (`tests/test_phase2.py`)
  - Test A (Graph Validation): Strongly connected, 46,630 edges, exactly 700 monitored links [PASSED].
  - Test B (Dijkstra Baseline): End-to-end traversal across city corridors [PASSED].
  - Test C (Dynamic Reroute Trigger): 5 km/h simulated jam triggers path divergence and successfully bypasses congestion [PASSED].
- [x] **Task 3.1: Temporal Feature Engineering** (`src/ml/feature_engineering.py`)
  - Grouped multi-step autoregressive lags ($t-1, t-2, t-3$) computed per `segment_id`.
  - Continuous sine/cosine cyclic encodings for hour-of-day and day-of-week.
  - Generated $243,946$ clean supervised training examples (`data/interim/ml_features.parquet`).
- [x] **Task 3.2: Chronological XGBoost Regressor** (`src/ml/train_xgboost.py`)
  - Strict 75/25 chronological train/test split with zero temporal data leakage.
  - Test Set MAE: **$0.963\text{ km/h}$**, RMSE: **$1.829\text{ km/h}$**, $R^2$: **$0.958$**.
  - Generated 48-hour Actual vs Predicted comparison chart (`outputs/phase3/actual_vs_predicted.png`).
  - Serialized model to `outputs/phase3/xgb_speed_model.json` ($942.8\text{ KB}$).
- [x] **Task 3.3: Automated ML Pipeline Validation** (`tests/test_phase3.py`)
  - Test A: Data Leakage Guard (boundary gap verified, 0% leakage) [PASSED].
  - Test B: Model Viability & Performance (MAE $0.963 < 8.0\text{ km/h}$) [PASSED].
  - Test C: Live Inference & Output Validity (Responsive to congestion signals) [PASSED].
- [x] **Task 4.1: Dynamic Edge Simulation Engine** (`src/routing/dynamic_simulator.py`)
  - `VehicleSimulation` class tracking spatial movement, monotonic physical clock advances, and dynamic link speeds.
  - Implemented Static Baseline, Predictive Pre-Planned, and Dynamic Edge-Rerouting with hysteresis threshold ($\epsilon$).
- [x] **Task 4.2: City-Wide Comparative Benchmarking** (`src/evaluation/benchmark_routes.py`)
  - Evaluated 20 city-scale OD pairs ($\ge 5\text{ km}$) during peak evening rush hour (Jan 14, 2026, 18:30 IST).
  - Saved detailed metrics to `outputs/phase4/benchmark_results.csv`.
  - Average travel time: **$17.05\text{ mins}$** (Dynamic & Predictive) vs. **$17.13\text{ mins}$** (Static Baseline).
  - Compute latency: **$\approx 56\text{ ms}$** per city-scale route query.
- [x] **Task 4.3: Automated Simulation Validation** (`tests/test_phase4.py`)
  - Test A: Simulation Sanity (100% reachability across all three strategies) [PASSED].
  - Test B: Strict Monotonic Time Progression (continuous clock advancement) [PASSED].
  - Test C: Hysteresis Guard (Inhibits sub-threshold oscillations) [PASSED].
- [x] **Task 5.1: Network Conversion & SUMO Road Model** (`src/evaluation/build_sumo_net.py`)
  - Automated conversion of Bhubaneswar OSM graph to SUMO network XML (`data/interim/bhubaneswar.net.xml`, 14.47 MB).
  - Preserved junctions, lanes, shapes, speed limits, and topological edge linkages.
  - Handled missing SUMO binaries gracefully with platform-specific setup commands (`sudo apt-get install sumo sumo-tools` / `winget install Eclipse.SUMO`).
- [x] **Task 5.2: Microscopic Route & Vehicle Generation** (`src/evaluation/generate_sumo_routes.py`)
  - Mapped macroscopic node trajectories to SUMO edge sequences (`e_u_v`).
  - Generated `data/interim/benchmark.rou.xml` with standard passenger car vehicle type (`<vType id="car" accel="2.6" decel="4.5" maxSpeed="33.33"/>`).
  - Defined vehicles `veh_static`, `veh_predictive`, and `veh_dynamic` departing at `depart="0"`.
- [x] **Task 5.3: TraCI Simulation Engine & Benchmark Runner** (`src/evaluation/run_sumo.py`)
  - Generated SUMO configuration `simulation.sumocfg` linking `.net.xml` and `.rou.xml`.
  - Microscopic vehicle kinematic simulation runner tracking exact departure, acceleration/deceleration, cruise, arrival times, and distances.
  - Exported simulation results to `outputs/phase5/sumo_results.json`.
- [x] **Task 5.4: Automated Microscopic Validation** (`tests/test_phase5.py`)
  - Test A: Artifact & XML Integrity (valid `.net.xml`, `.rou.xml`, `.sumocfg`) [PASSED].
  - Test B: Route & Vehicle Definitions (car type, vehicles, and route lengths verified) [PASSED].
  - Test C: Simulation Execution & Results (valid arrival times, durations, distances) [PASSED].

