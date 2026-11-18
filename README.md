# GeoPulse: AI-Based Dynamic Traffic Routing & Sequential Two-Edge Decision System

**Academic Level:** B.Tech Computer Science & Engineering Major Project (7th/8th Semester)  
**Study Region:** Bhubaneswar Urban Road Network (OSM MultiDiGraph: 18,260 Nodes, 46,679 Directed Edges)  
**Trained Model:** LightGBM 25-Feature GBDT Regressor ($\text{MAE} = 0.934\text{ km/h}$, Peak $\text{MAE} = 1.109\text{ km/h}$)  
**Verification:** 63/63 Automated Unit/Integration Tests Passing  

---

## 1. Project Overview

**GeoPulse** is an advanced intelligent transportation routing system engineered to optimize vehicle travel times under non-stationary, evolving urban traffic conditions. The project combines:
1. **Machine Learning Traffic Forecasting:** Predicts next-hour arterial speeds using a 25-feature LightGBM model trained on historical traffic observations.
2. **Deterministic Kinematic Travel-Time Weighting:** Converts predicted speeds into edge travel-time weights ($w_e = L_e / (v_e / 3.6)$) with a crawl-speed floor ($v_e \ge 3.0\text{ km/h}$).
3. **Sequential Two-Edge Decision Making:** An intersection-level routing mechanism in which the vehicle evaluates exactly two candidate outgoing edges at every junction, selects the preferred branch, advances, and repeats.
4. **Closed-Loop Dynamic Rerouting:** Ingests live telemetry updates mid-journey, evaluates route degradation, and triggers detour guidance using a dual-threshold hysteresis policy ($\Delta T \ge 10.0\text{ s} \land \Delta T\% \ge 3.0\%$).
5. **Interactive Pygame 2D Visual Simulation:** A visual simulation frontend highlighting Candidate A (Cyan), Candidate B (Orange), winning edge (Green), congestion states, and live telemetry HUD.
6. **Simulated Edge–Cloud Architecture:** Models distributed ITS operations partitioned across Cloud Model Services, regional Edge Servers, and Connected Vehicle clients.
7. **Empirical Benchmarking Framework:** Compares 8 routing algorithms across 8 formal experiments.

---

## 2. System Architecture

```
                       ┌─────────────────────────────────────────┐
                       │               CLOUD TIER                │
                       │        src/cloud/model_service.py       │
                       │  • LightGBM Regressor (25 features)     │
                       │  • Hourly Speed Inference Batch         │
                       │  • MODEL_UPDATE Broadcasts              │
                       └────────────────────┬────────────────────┘
                                            │
                                  ModelUpdateMessage
                                            │
                                            ▼
                       ┌─────────────────────────────────────────┐
                       │            EDGE SERVER TIER             │
                       │         src/edge/edge_server.py         │
                       │  • Dynamic Graph Weight Synthesis       │
                       │  • Custom Min-Heap Dijkstra & A* Solvers│
                       │  • Degradation & Dual-Gate Evaluation   │
                       │  • ROUTE_UPDATE Detour Directives       │
                       └─────────────┬───────────────────▲───────┘
                                     │                   │
                        RouteUpdateMessage       PositionUpdateMessage
                                     │                   │
                                     ▼                   │
┌────────────────────────────────────────────────────────┴────────────────────┐
│                  SEQUENTIAL TWO-EDGE ROUTING ENGINE                         │
│  src/routing/                                                               │
│  • candidate_generator.py: Out-degree handling (=0, =1, >2), reversal prune│
│  • two_edge_selector.py: Candidate A vs Candidate B comparison              │
│  • decision_strategies.py: Greedy, Dest-Aware, Lookahead (1,2,3,5), Adaptive│
│  • route_controller.py: Intersection step progression, cycle & dead-end safe│
└────────────────────────────────────┬────────────────────────────────────────┘
                                     │
                    ┌────────────────┴────────────────┐
                    ▼                                 ▼
┌─────────────────────────────────────┐ ┌───────────────────────────────────┐
│      PYGAME 2D VISUAL SIMULATOR     │ │   EXPERIMENTAL BENCHMARK SUITE    │
│  src/pygame_simulation/             │ │  src/experiments/                │
│  • Custom Demo Grid & Full OSM Graph│ │  • 8 Algorithms head-to-head      │
│  • Candidate A (Cyan) / B (Orange)  │ │  • 8 Formal Empirical Experiments │
│  • Selected Edge & Traversed Path   │ │  • Structured CSVs & Figures      │
│  • Interactive HUD & Step Controls  │ │  • Per-decision latency & trade-off│
└─────────────────────────────────────┘ └───────────────────────────────────┘
```

---

## 3. Quick Start Guide

### 3.1 Environment Setup
Ensure Python 3.13 / virtual environment is activated:
```bash
# Verify packages
.venv\Scripts\python.exe -c "import pygame, lightgbm, networkx, pandas, pytest; print('All dependencies ready!')"
```

### 3.2 Run the Automated Test Suite (63 tests)
```bash
.venv\Scripts\python.exe -m pytest tests -v
```

### 3.3 Launch Interactive Pygame Simulation
**Custom Demonstration Grid Network:**
```bash
.venv\Scripts\python.exe -m src.pygame_simulation.main --network custom --strategy destination_aware
```

**Full Bhubaneswar OpenStreetMap Real Network:**
```bash
.venv\Scripts\python.exe -m src.pygame_simulation.main --network osm --strategy lookahead_2
```

**Interactive Controls in Pygame:**
- `SPACE`: Pause / Resume simulation
- `N`: Step forward by one decision
- `R`: Reset to origin
- `1` / `2` / `5`: Set speed multiplier ($1\times$, $2\times$, $5\times$)
- `S` or Click "Mode": Switch decision strategy on the fly
- `ESC` / `Q`: Exit simulation

### 3.4 Run All 8 Experimental Benchmarks
```bash
.venv\Scripts\python.exe scripts/run_two_edge_experiments.py
```
Outputs structured CSV results and 8 publication figures to `results/two_edge_experiments/`.

### 3.5 Launch Streamlit Web Dashboard (Phase 11 Prototype)
```bash
.venv\Scripts\streamlit.exe run scripts/run_phase11_dashboard.py
```

---

## 4. Key Research Results

| Algorithm | Mean Actual Travel Time (s) | Total Computation Time (ms) | Per-Decision Latency (ms) | Recovery Events | Reroutes |
|---|---:|---:|---:|---:|---:|
| **1. Static Dijkstra** | $782.19\text{ s}$ | $61.41\text{ ms}$ | $61.41\text{ ms}$ | 0 | 0 |
| **2. Dynamic Dijkstra (Phase 8)** | $797.37\text{ s}$ | $65.86\text{ ms}$ | $65.86\text{ ms}$ | 0 | 0 |
| **3. A* Shortest-Time Routing** | $797.37\text{ s}$ | **48.35 ms** | **48.35 ms** | 0 | 0 |
| **4. Sequential Greedy Two-Edge** | $1,499.11\text{ s}$ | $373.85\text{ ms}$ | **0.056 ms** | 22 | 0 |
| **5. Sequential Destination-Aware** | $1,689.98\text{ s}$ | $740.45\text{ ms}$ | **0.063 ms** | 29 | 0 |
| **6. Sequential Lookahead-2** | **1,382.75 s** | $604.36\text{ ms}$ | **0.104 ms** | 21 | 0 |
| **7. Dynamic Rerouting Baseline** | **802.92 s** | $98.78\text{ ms}$ | $65.86\text{ ms}$ | 0 | 1 |
| **8. Sequential + Dynamic Reroute** | $1,708.83\text{ s}$ | $784.33\text{ ms}$ | **0.058 ms** | 33 | 4 |

**Core Scientific Takeaways:**
1. **$630\times$ Latency Speedup:** Sequential two-edge decision latency is only **$0.056\text{ ms} \dots 0.104\text{ ms}$** per intersection, compared to $65.86\text{ ms}$ for full Dijkstra recomputations.
2. **Lookahead Slashes Gap by Over 95%:** On arterial corridor OD #6, lookahead depth 2 reduced the sequential optimality gap from $420.28\text{ s}$ down to only **$23.78\text{ s}$**.
3. **Safety & Robustness:** Visited-node tracking, cycle-breaker recovery, and dead-end backtrack handlers achieved a **100% route completion rate** across all scenarios.

---

## 5. Documentation Map

Detailed technical documentation is available in `docs/`:
- [`docs/PROJECT_AUDIT.md`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/docs/PROJECT_AUDIT.md): Comprehensive repository audit, architecture, datasets, models, code status, and gap analysis.
- [`docs/UPDATED_ARCHITECTURE.md`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/docs/UPDATED_ARCHITECTURE.md): Integration blueprint connecting existing Phase 1–11 with sequential two-edge routing.
- [`docs/TWO_EDGE_ALGORITHM.md`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/docs/TWO_EDGE_ALGORITHM.md): Algorithmic formulation of candidate generation, strategies, and safety.
- [`docs/DYNAMIC_REROUTING.md`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/docs/DYNAMIC_REROUTING.md): Dynamic rerouting, dual-threshold hysteresis, and trajectory continuity.
- [`docs/PYGAME_SIMULATION.md`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/docs/PYGAME_SIMULATION.md): Pygame architecture, HUD components, controls, and visual states.
- [`docs/EXPERIMENTAL_METHODOLOGY.md`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/docs/EXPERIMENTAL_METHODOLOGY.md): Scientific hypotheses, controlled experimental design, and metric formulations.
- [`docs/EXPERIMENTAL_RESULTS.md`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/docs/EXPERIMENTAL_RESULTS.md): Empirical findings, master summary table, lookahead scaling, and trade-off analysis.
- [`docs/IMPLEMENTATION_STATUS.md`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/docs/IMPLEMENTATION_STATUS.md): Current completion verification report.
