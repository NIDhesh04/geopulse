# GeoPulse: Comprehensive System Audit & Repository Assessment
**Project Title:** GeoPulse — AI-Based Dynamic Traffic Routing System  
**Academic Level:** 7th Semester B.Tech Major Project (Computer Science & Engineering)  
**Audit Date:** November 2026 (Updated for Sequential Two-Edge Decision & Pygame Extension)  
**Auditor:** GeoPulse Core Engineering & Architecture Team  
**Evaluation Baseline:** Clean Git Working Tree, 45/45 Unit/Integration Tests Passing  

---

## 1. Executive Summary

This audit establishes the rigorous technical foundation of the **GeoPulse** repository prior to implementing the updated research direction: **ML-Based Traffic Prediction with Sequential Two-Edge Selection and Dynamic Rerouting for Minimum Travel-Time Optimization**.

The existing GeoPulse project represents an extensive, highly engineered software system spanning 11 developmental phases (Phases 1 through 11). It features:
1. Real-world urban OpenStreetMap (OSM) drive topology modeling (Bhubaneswar, Odisha).
2. Physical sensor-to-directed-edge spatial mapping with strict routing eligibility tiers.
3. High-accuracy next-hour speed prediction via a 25-feature LightGBM Gradient Boosted Decision Tree (GBDT).
4. Pure Python min-heap Dijkstra shortest-path engine with deterministic kinematic travel-time costs.
5. Closed-loop dynamic rerouting engine with dual-threshold hysteresis ($\Delta T \ge 10.0\text{ s} \land \Delta T\% \ge 3.0\%$).
6. Simulated 3-tier distributed Edge–Cloud intelligent transportation architecture (`CloudModelService`, `EdgeServer`, `Vehicle`).
7. Interactive Streamlit dashboard and publication-grade visual diagnostics.

All existing 45 unit and integration tests across 5 test suites pass deterministically in 17.18s without regressions. This audit documents every subsystem, identifies architectural gaps relative to the professor-directed sequential two-edge routing approach, specifies components to retain, extend, or replace, and establishes safety guardrails.

---

## 2. Existing System Architecture

The existing GeoPulse system operates as a **3-tier hierarchical closed loop**:

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
                       │  • Session State Management             │
                       │  • Scratch Min-Heap Dijkstra Solver     │
                       │  • Degradation & Dual-Gate Evaluation   │
                       │  • ROUTE_UPDATE Detour Directives       │
                       └─────────────┬───────────────────▲───────┘
                                     │                   │
                        RouteUpdateMessage       PositionUpdateMessage
                                     │                   │
                                     ▼                   │
                       ┌─────────────────────────────────┴───────┐
                       │           VEHICLE CLIENT TIER           │
                       │        src/simulation/vehicle.py        │
                       │  • Link-by-Link Kinematic Traversal     │
                       │  • Telemetry Emitting (POSITION_UPDATE) │
                       │  • Mid-Journey Reroute Splicing         │
                       │  • Accumulated Trip Travel Time Metrics │
                       └─────────────────────────────────────────┘
```

### Operational Closed-Loop Flow:
1. **PREDICT ($t_0$):** `CloudModelService` predicts speeds across 700 monitored corridors for $t_0+1\text{h}$ and transmits `ModelUpdateMessage` to `EdgeServer`.
2. **PLAN ($t_0$):** `EdgeServer` combines predicted speeds with static baseline speeds for unmonitored links into kinematic travel times $w_e = L_e / (v_e / 3.6)$, solving initial route $R_0$ via `custom_dijkstra()`.
3. **DRIVE ($t_0 \to t_1$):** `Vehicle` navigates link-by-link along $R_0$, emitting `PositionUpdateMessage` telemetry.
4. **OBSERVE ($t_1$):** Vehicle reaches decision waypoint; `TrafficUpdateMessage` delivers live sensor observations showing downstream congestion spikes.
5. **DETECT ($t_1$):** `EdgeServer` evaluates remaining travel time on $R_0$ vs. freshly computed detour $R_1^*$ under current observed weights.
6. **REROUTE ($t_1$):** If absolute saving $\ge 10.0\text{ s}$ AND relative saving $\ge 3.0\%$, `EdgeServer` dispatches `RouteUpdateMessage`.
7. **SAVE TIME:** Vehicle adopts subpath $R_1$, completing the journey with measurably lower travel time.

---

## 3. Inventory of Existing Code Modules

| Subsystem / Path | Key Files | Primary Responsibilities | Status | Reuse Strategy |
|---|---|---|---|---|
| **Graph & Weights** | [`src/routing/traffic_weights.py`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/src/routing/traffic_weights.py) | Graph topology indexing, static speed categorization (15-50 km/h), physical kinematic travel time $t = L/(v/3.6)$, speed floor $\ge 3.0$ km/h, twin-sensor aggregation, dynamic weights generation. | Fully functional | **Retain as-is**; core dependency for all travel-time and candidate cost calculations. |
| **Shortest Path Solver** | [`src/routing/dijkstra.py`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/src/routing/dijkstra.py) | Pure Python min-heap Dijkstra solver. Supports directed `MultiDiGraph`, parallel edges, early target termination, node/edge reconstruction. | Fully functional | **Retain as-is**; baseline comparison, initial route generation, heuristic lookahead reference, and safety recovery solver. |
| **Route Evaluation** | [`src/routing/route_evaluator.py`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/src/routing/route_evaluator.py) | Edge Jaccard overlap, trip metric aggregations, route comparison helpers. | Fully functional | **Retain as-is**; used across evaluation benchmarks. |
| **Dynamic Rerouting** | [`src/routing/dynamic_rerouter.py`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/src/routing/dynamic_rerouter.py) | `DynamicRerouter` class for initial planning, link progression, degradation evaluation, dual-threshold check, and counterfactual trip comparison. | Fully functional | **Retain and extend**; integrate with two-edge routing decisions. |
| **Cloud Model Service** | [`src/cloud/model_service.py`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/src/cloud/model_service.py) | Model artifact loading (`joblib`), metadata serialization, batch hourly speed inference broadcast generator (`ModelUpdateMessage`). | Fully functional | **Retain as-is**; provides predictions to sequential routing and dynamic rerouting. |
| **Edge Server** | [`src/edge/edge_server.py`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/src/edge/edge_server.py) | Regional session tracker, dynamic weight synthesizer, initial and reroute Dijkstra solver, event logging. | Fully functional | **Retain and extend** to support sequential two-edge route dispatching. |
| **Edge-Cloud Messages** | [`src/edge/messages.py`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/src/edge/messages.py) | Strongly typed dataclasses: `ModelUpdateMessage`, `TrafficUpdateMessage`, `PositionUpdateMessage`, `RouteUpdateMessage`, `ArchitectureEvent`. | Fully functional | **Retain as-is**; extend if candidate edge metadata is dispatched over messages. |
| **Vehicle Simulation** | [`src/simulation/vehicle.py`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/src/simulation/vehicle.py) | Discrete link-by-link kinematic movement simulation, telemetry emission, detour splicing, history tracking. | Fully functional | **Extend** to support step-by-step sequential edge decisions at intersections. |
| **Phase 10 Ablation** | `src/phase10/*.py` | Routing strategy ablation (Static, Persistence, Historical, LightGBM, Oracle), threshold sensitivity grid, robustness across diurnal periods/route lengths/congestion tertiles. | Fully functional | **Retain as-is**; provides reference benchmarks and statistical test methodologies. |
| **Streamlit Dashboard** | `src/dashboard/*.py`, `scripts/run_phase11_dashboard.py` | Full interactive web dashboard with Matplotlib and Pydeck visualizations, scenario catalog, session state scrubber. | Fully functional | **Retain as-is**; exists alongside the new Pygame simulation. |
| **Offline Audits** | `src/audit_*.py` | Data exploration scripts from Phase 1-5. | Completed archive | **Retain as historical reference**. |

---

## 4. Datasets & Road Networks

### 4.1 Road Network Graph: Bhubaneswar, Odisha
- **File:** [`data/raw/osm/bhubaneswar_drive.graphml`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/data/raw/osm/bhubaneswar_drive.graphml)
- **Graph Type:** OpenStreetMap `MultiDiGraph` (directed graph with potential parallel edges).
- **Nodes:** $18,260$ spatial intersection nodes.
  - Node attributes: `osmid`, `x` (longitude), `y` (latitude), `street_count`.
- **Directed Edges:** $46,679$ physical directed links.
  - Edge attributes: `u`, `v`, `key`, `osmid`, `name`, `highway`, `oneway`, `length` (metric length in meters), `geometry` (WKT LineString).
- **Strongly Connected Component (SCC):** Largest SCC contains $18,172$ nodes ($99.52\%$ of network), guaranteeing high origin-destination reachability.
- **Legacy Unused Graph:** `datasets/jaipur_osm/jaipur_graph.graphml` (retained from initial exploration; not used in production).

### 4.2 Sensor Mapping Table
- **File:** [`data/processed/traffic_to_osm_mapping_final.parquet`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/data/processed/traffic_to_osm_mapping_final.parquet)
- **Rows:** $700$ sensor corridor mapping entries.
- **Key Columns:**
  - `traffic_segment_id` (int): Unique sensor identifier ($0 \dots 699$).
  - `u`, `v`, `key`: Directed OSM graph edge endpoints.
  - `confidence` (str): Mapping quality (`HIGH`, `MEDIUM`, `LOW`).
  - `routing_eligibility` (str):
    - `DYNAMIC` ($n = 565$): Applied directly to edge $(u, v, key)$.
    - `DYNAMIC_BIDIRECTIONAL` ($n = 92$): Applied symmetrically to both $(u \to v)$ and $(v \to u)$ on undivided streets.
    - `STATIC_FALLBACK` ($n = 43$): Ambiguous or low-confidence mappings forced to static road hierarchy speed limits.

### 4.3 Traffic Speeds Dataset
- **File:** [`datasets/traffic_structured_v1.parquet`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/datasets/traffic_structured_v1.parquet)
- **Volume:** $275,800$ rows ($700$ segments $\times$ $394$ hourly epochs from 2026-01-01 to 2026-01-17).
- **Completeness:** Over the clean evaluation window (2026-01-04 to 2026-01-17, 322 consecutive hours), completeness is $99.9996\%$ ($225,399 / 225,400$ cells observed).
- **Ground-Truth Speeds:** $1.0\text{ km/h} \dots 54.0\text{ km/h}$ (mean $33.14\text{ km/h}$, median $32.0\text{ km/h}$).

---

## 5. Machine Learning Model & Predictions

### 5.1 Model Specifications
- **Framework:** LightGBM Regressor (`LGBMRegressor`).
- **Artifact:** [`models/speed_predictor.joblib`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/models/speed_predictor.joblib)
- **Metadata:** [`models/feature_metadata.json`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/models/feature_metadata.json)
- **Input Features ($n = 25$):**
  - *Temporal (7):* `hour`, `day_of_week`, `is_weekend`, `sin_hour`, `cos_hour`, `sin_dow`, `cos_dow`
  - *Lag speeds (6):* `speed_lag_1h`, `speed_lag_2h`, `speed_lag_3h`, `speed_lag_6h`, `speed_lag_12h`, `speed_lag_24h`
  - *Rolling statistics (5):* `rolling_mean_3h`, `rolling_mean_6h`, `rolling_mean_24h`, `rolling_std_6h`, `rolling_std_24h`
  - *Traffic & Road attributes (7):* `currentSpeed`, `freeFlowSpeed`, `speed_ratio`, `length_m`, `road_type_code`, `conf_code`, `hist_speed`
- **Chronological Data Splits:**
  - Training: $142,799$ samples ($70\%$, 2026-01-05 to 2026-01-13)
  - Validation: $30,800$ samples ($15\%$, 2026-01-13 to 2026-01-15)
  - Testing: $30,800$ samples ($15\%$, 2026-01-15 to 2026-01-17)
- **Speed Clamping Guardrails:** Strictly constrained to $[3.0, 120.0]\text{ km/h}$.

### 5.2 Model Performance Metrics

| Slice / Condition | Persistence Baseline MAE | Historical Baseline MAE | LightGBM Regressor MAE | LightGBM RMSE | LightGBM $R^2$ |
|---|---:|---:|---:|---:|---:|
| **Overall Test Set ($n=30,800$)** | $1.210\text{ km/h}$ | $0.835\text{ km/h}$ | **$0.934\text{ km/h}$** | $1.601\text{ km/h}$ | $0.9679$ |
| **Peak Congestion ($n=6,300$)** | $2.234\text{ km/h}$ | $1.350\text{ km/h}$ | **$1.109\text{ km/h}$** | **$1.745\text{ km/h}$** | **$0.9593$** |
| **Off-Peak ($n=24,500$)** | $0.947\text{ km/h}$ | $0.703\text{ km/h}$ | $0.889\text{ km/h}$ | $1.561\text{ km/h}$ | $0.9698$ |

*Observation on Metrics Consistency:*  
In overall data, the historical mean baseline achieves slightly lower MAE ($0.835$ vs $0.934$) due to $67.7\%$ free-flow ceiling stability during night/off-peak hours. However, during critical peak congestion hours, LightGBM outperforms Historical Baseline by **$17.8\%$ lower MAE** and Persistence by **$50.4\%$ lower MAE**.

---

## 6. Existing Routing & Dynamic Rerouting Logic

### 6.1 Edge Travel Time Formulation
Travel time $w_e$ in seconds for directed edge $e = (u, v, k)$ of length $L_e$ (meters) and speed $v_e$ (km/h) is computed as:
$$w_e = \frac{L_e}{v_e / 3.6}$$
- Minimum crawl speed guardrail: $v_e = \max(v_e, 3.0\text{ km/h})$.
- Speed floor prevents division by zero or infinite edge weights during simulated traffic gridlock.

### 6.2 Existing Dijkstra Routing (Phase 8)
- Min-heap priority queue implementation in [`src/routing/dijkstra.py`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/src/routing/dijkstra.py).
- Edge weights indexed by `(u, v, key)`.
- Reconstructs both `node_path` ($[u_0, u_1, \dots, u_m]$) and `edge_path` ($[(u_0, u_1, k_0), \dots]$).
- Citywide benchmark results ($n = 800$ OD-timestamp runs):
  - Static Baseline: Mean travel time $1,066.81\text{ s}$ ($17.78\text{ min}$).
  - ML-Predicted Dynamic: Mean travel time $1,063.08\text{ s}$ ($17.72\text{ min}$, win rate vs static $34.62\%$, peak win rate $45.60\%$).
  - Current-Optimal Oracle: Mean travel time $1,060.75\text{ s}$ ($17.68\text{ min}$). Mean oracle regret for ML routing is only $2.33\text{ s}$ ($0.17\%$).

### 6.3 Existing Dynamic Rerouting Engine (Phase 9 & 10)
- Defined in [`src/routing/dynamic_rerouter.py`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/src/routing/dynamic_rerouter.py).
- Evaluates candidate detour at intermediate decision waypoint node $n_{\text{dec}}$ when traffic update arrives at $t_1$.
- Dual-threshold gating policy:
  $$\Delta T = T_{\text{remain}}(R_0 \mid v_{\text{obs}}) - T^*(n_{\text{dec}} \to \text{dest} \mid v_{\text{obs}}) \ge 10.0\text{ s}$$
  $$\Delta T\% = \frac{\Delta T}{T_{\text{remain}}(R_0 \mid v_{\text{obs}})} \times 100\% \ge 3.0\%$$
- Canonical demo scenario (OD #0, Evening Peak):
  - No-Reroute travel time: $1,287.05\text{ s}$.
  - Dynamic Reroute travel time: $1,202.15\text{ s}$.
  - Direct time saved: **$84.90\text{ s}$** ($6.60\%$ overall journey saving; $9.23\%$ remaining-leg saving).

---

## 7. Status of Existing Tests

All 45 existing unit and integration tests execute successfully:

| Test Suite | Tests | Status | Execution Time | Coverage Scope |
|---|---:|:---:|---:|---|
| [`tests/test_phase8_routing.py`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/tests/test_phase8_routing.py) | 8 | PASSED | $0.4\text{ s}$ | Custom Dijkstra (diamond graph, source=dest, unreachable, parallel edges), kinematic calculation, crawl speed clamping, dynamic edge preference, zero data leakage. |
| [`tests/test_phase9_rerouting.py`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/tests/test_phase9_rerouting.py) | 7 | PASSED | $0.5\text{ s}$ | Threshold gating (below/above threshold), congestion deflection, counterfactual validation, non-retroactivity, zero leakage in initial plan, OD preservation. |
| [`tests/test_phase10_ablation.py`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/tests/test_phase10_ablation.py) | 8 | PASSED | $0.6\text{ s}$ | Schema integrity, strategy travel-time ordering, non-negative oracle regret, policy monotonicity, 100% beneficial reroutes under dual threshold, leakage audit pass, figure persistence. |
| [`tests/test_phase11_dashboard.py`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/tests/test_phase11_dashboard.py) | 16 | PASSED | $6.2\text{ s}$ | Dashboard imports/loaders, scenario catalog, numerical parity with Phase 9, reroute/no-reroute branches, metric completeness, dynamic computation verification, visualization checks, session state lifecycle. |
| [`tests/test_phase11_integration.py`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/tests/test_phase11_integration.py) | 6 | PASSED | $9.5\text{ s}$ | Cloud model service lifecycle, edge server initial routing, threshold gating, vehicle simulation link advancement, end-to-end numerical parity, figure/table generation. |
| **Total** | **45** | **ALL PASSED** | **17.18 s** | Comprehensive regression baseline confirmed. |

---

## 8. Gap Analysis & Proposed Architectural Transition

### 8.1 What is Missing for the Professor-Directed Objective?
1. **No Sequential Two-Edge Decision Engine:** The current system uses Dijkstra to compute an entire global path from start to end (or from decision node to destination). It does not perform localized two-edge candidate generation, edge comparison, and step-by-step sequential selection at each intersection.
2. **No Candidate Generation Module:** Missing logic to evaluate out-degree at intersections, prune prohibited/reversal edges, handle $>2$ or $<2$ outgoing branches, and select two candidate edges according to candidate-generation strategies (Random, Lowest Immediate Cost, Destination-Aware, Limited Lookahead).
3. **No Local Decision Strategies Interface:** Missing modular strategy implementations (Greedy, Destination-Aware, Lookahead depths 1, 2, 3, 5, Adaptive) operating behind a polymorphic selector interface.
4. **No Route Safety & Failure Protection Layer:** Sequential local decisions risk cyclic loops ($A \to B \to A \to B$), dead ends (zero outgoing edges), or disconnected graph deadlocks. The repository lacks loop detection, visited-node tracking, max-hop bounding, and Dijkstra-backed recovery fallbacks.
5. **No Pygame Visual Simulation:** Visualization is currently restricted to static Matplotlib PNGs and a Streamlit web app. Pygame is missing completely (`pygame` library is not yet installed in `.venv`). There is no interactive 2D animated desktop simulation highlighting candidate edges A & B, selected edge, vehicle movement, live telemetry, and interactive controls (play, pause, step, scenario switch).
6. **No Multi-Algorithm Experimental Benchmark Suite:** Existing Phase 8 & 10 experiments compared global Dijkstra strategies (Static, Persistence, Historical, LightGBM, Oracle). They do not benchmark the sequential two-edge selection strategies against global Dijkstra, A*, or evaluate candidate-generation heuristics, lookahead depths, and sequential rerouting.

### 8.2 Component Disposition Table

| Component | Status | Disposition | Detailed Rationale |
|---|---|---|---|
| `data/raw/osm/bhubaneswar_drive.graphml` | Working | **Retain** | Official spatial road network (18,260 nodes, 46,679 edges). |
| `data/processed/traffic_to_osm_mapping_final.parquet` | Working | **Retain** | Validated sensor-to-edge mapping with confidence tiers. |
| `datasets/traffic_structured_v1.parquet` | Working | **Retain** | Canonical observed traffic speed dataset. |
| `models/speed_predictor.joblib` & metadata | Working | **Retain** | Validated 25-feature LightGBM model; reuse without retraining. |
| `src/routing/traffic_weights.py` | Working | **Retain** | Computes kinematic edge travel times, crawl-speed floors, and dynamic scenario weights. |
| `src/routing/dijkstra.py` | Working | **Retain & Reuse** | Retain as reference oracle, global baseline, lookahead heuristic provider, and recovery fallback. |
| `src/routing/candidate_generator.py` | Missing | **Create New** | Generates eligible candidate outgoing edges at intersections; enforces out-degree handling ($=1$, $=2$, $>2$, dead-ends). |
| `src/routing/two_edge_selector.py` | Missing | **Create New** | Evaluates two candidate edges, calculates decision scores, and selects preferred branch. |
| `src/routing/decision_strategies.py` | Missing | **Create New** | Polymorphic decision strategies: Greedy, Destination-Aware, Lookahead ($k \in \{1,2,3,5\}$), Adaptive. |
| `src/routing/route_controller.py` | Missing | **Create New** | Orchestrates sequential journey from source to destination, manages route safety, cycle breaking, and dynamic reroute events. |
| `src/routing/dynamic_rerouter.py` | Working | **Extend** | Adapt to support sequential reroute triggers mid-journey. |
| `src/simulation/vehicle.py` | Working | **Extend** | Add support for sequential intersection stepping and candidate edge inspection. |
| `src/pygame_simulation/` | Missing | **Create New** | Complete visual simulation: custom test graph + OSM road network, candidate edge highlighting, live HUD, playback controls. |
| `src/experiments/` & `scripts/run_two_edge_experiments.py` | Missing | **Create New** | Multi-algorithm experimental framework (Experiments 1–8, CSV exports, plots, metrics). |
| `src/dashboard/` & Streamlit app | Working | **Retain** | Preserve existing web dashboard for backward compatibility. |

---

## 9. Identified Risks & Technical Limitations

1. **Local Optima & Cycle Trapping in Sequential Routing:** Pure greedy local edge selection can readily become trapped in cyclic loops or dead-ends if uninformed by destination distance. A robust visited-node tracker, cycle detector, and fallback recovery mechanism are mandatory.
2. **Computational Overhead of High-Depth Lookahead on Large Graphs:** Branching factor at intersections can cause exponential expansion at depth $\ge 5$ if naive tree search is executed. Lookahead must prune paths efficiently or leverage cached heuristic estimates.
3. **Pygame Headless / Environment Execution:** In headless test runner or CI environments, Pygame requires dummy video driver settings (`os.environ["SDL_VIDEODRIVER"] = "dummy"`). The simulation must support both interactive display mode and headless validation mode.
4. **Dependency Availability:** `pygame` is not yet installed in `.venv`. Must be installed cleanly without perturbing existing packages.
5. **Parity with Reference Dijkstra:** A sequential local decision policy constrained to 2 outgoing candidates cannot mathematically guarantee global shortest-path optimality under static weights. The study must honestly measure and document the optimality gap and investigate trade-offs between decision speed, local flexibility, and travel time under dynamic traffic.
