# Phase 11: Edge-Cloud System Architecture Specification

**Project:** GeoPulse — AI-Based Dynamic Traffic Routing System  
**Academic Level:** 7th Semester B.Tech Major Project  
**Author:** Pair Programming Team (GeoPulse Engineering)  
**Artifact Directory:** [`results/phase11/`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase11)  
**Figure Reference:** [`03_edge_cloud_architecture.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase11/figures/03_edge_cloud_architecture.png)

---

## 1. System Architecture Overview

GeoPulse logically separates computation across three distinct operational tiers to balance predictive intelligence with real-time reactive responsiveness:

```text
                  CLOUD TIER
        ┌─────────────────────────┐
        │ Historical Traffic Data │
        │ Feature Engineering     │
        │ LightGBM GBDT Regressor │
        │ Model Management        │
        └────────────┬────────────┘
                     │
              MODEL_UPDATE
                     ↓
              EDGE SERVER TIER
        ┌─────────────────────────┐
        │ Traffic Sensor Ingestion│
        │ Dynamic Edge Weights    │
        │ Custom Dijkstra Solver  │
        │ Degradation Evaluator   │
        │ Session State Tracker   │
        └────────────┬────────────┘
                     │
               ROUTE_UPDATE
                     ↓
             VEHICLE CLIENT TIER
        ┌─────────────────────────┐
        │ Kinematic Path Progress │
        │ Subpath Navigation      │
        │ Real-Time Telemetry     │
        └────────────┬────────────┘
                     │
              POSITION_UPDATE
                     │
                     └────────────→ EDGE SERVER
```

---

## 2. Component Responsibilities

### Tier 1: Cloud Component (`src/cloud/model_service.py`)
- **Scope:** Heavy, batch-oriented historical computation.
- **Responsibilities:**
  - Ingests and archives historical sensor telemetry streams ($30,800$ test records, $700$ corridors).
  - Maintains feature extraction pipelines (cyclical calendar embeddings, autoregressive speed lags, rolling aggregates).
  - Manages training lifecycle of LightGBM regressor (`models/speed_predictor.joblib`, 25 features, $\text{MAE} = 0.934\text{ km/h}$).
  - Generates periodic batch next-hour traffic forecasts and broadcasts them downstream.
- **Independence:** Does **not** participate in the vehicle's high-frequency closed-loop routing or rerouting evaluations.

### Tier 2: Logical Edge Server (`src/edge/edge_server.py`)
- **Scope:** Latency-sensitive, geographically localized operations for active urban corridors.
- **Responsibilities:**
  - Maintains road network graph topology ($18,260$ nodes, $46,679$ directed edges) and localized weight representations.
  - Ingests incoming sensor feeds (`TrafficUpdateMessage`) and dynamically synthesizes edge travel times ($w_e = L_e / v_e$).
  - Tracks active vehicle sessions (`PositionUpdateMessage`), preserving current node positions and traversed route history.
  - Executes scratch-built min-heap Dijkstra algorithm to compute initial departure plans and evaluate detour alternatives.
  - Monitors route degradation ($\Delta T$, $\Delta T\%$) and enforces dual-threshold gating ($\Delta T \ge 10\text{s} \land \Delta T\% \ge 3\%$).
  - Dispatches `RouteUpdateMessage` directives directly to vehicles.

### Tier 3: Connected Vehicle Client (`src/simulation/vehicle.py`)
- **Scope:** Mobile navigation client executing route traversal.
- **Responsibilities:**
  - Ingests initial route directives $R_0$ from the Edge Server.
  - Navigates road links according to physical kinematic constraints ($t = L_e / v_e$).
  - Emits periodic `PositionUpdateMessage` telemetry at intersection boundaries.
  - Listens for asynchronous `RouteUpdateMessage` signals; seamlessly splices dynamic bypass corridors into remaining route plans upon receiving a detour directive.

---

## 3. Inter-Component Message Protocols

All inter-tier communication is structured via typed Python message schemas (`src/edge/messages.py`):

### 1. `MODEL_UPDATE` (Cloud $\longrightarrow$ Edge Server)
Broadcast when new forecast horizons or model updates become available:
```python
ModelUpdateMessage(
    model_version="LightGBM-v1.0 (Iteration 112)",
    feature_metadata={...},
    prediction_timestamp="2026-01-15 14:00:00+00:00",
    predicted_speeds={0: 31.7, 1: 34.2, ...},  # 700 monitored links
    total_segments=700
)
```

### 2. `TRAFFIC_UPDATE` (Sensor Stream $\longrightarrow$ Edge Server)
Pushed by arterial sensor ingestion streams when fresh telemetry arrives:
```python
TrafficUpdateMessage(
    timestamp="2026-01-15 20:30:00+05:30",
    observed_speeds={0: 14.0, 1: 22.5, ...},
    sensor_count=700
)
```

### 3. `POSITION_UPDATE` (Vehicle $\longrightarrow$ Edge Server)
Emitted by connected vehicles reporting real-time road progress:
```python
PositionUpdateMessage(
    vehicle_id="veh_001",
    current_node="3320289784",
    current_edge=("2283167656", "3320289784", 0),
    edge_index=15,
    progress_pct=20.3,
    elapsed_time_s=367.0,
    timestamp="2026-01-15 20:00:00+05:30"
)
```

### 4. `ROUTE_UPDATE` (Edge Server $\longrightarrow$ Vehicle)
Dispatched to vehicle clients upon initial route planning or dynamic detour:
```python
RouteUpdateMessage(
    vehicle_id="veh_001",
    node_path=[...],
    edge_path=[...],
    total_cost_s=1202.15,
    is_reroute=True,
    saving_s=84.90,
    saving_pct=9.23,
    reason="Degradation detected: Alternative saves 84.9s (9.2%), exceeding gates (10.0s / 3.0%)."
)
```

---

## 4. Dynamic Degradation & Rerouting Policy

Upon ingesting fresh sensor telemetry at epoch $t_1$, the Edge Server audits the remaining path of every active vehicle session:

1. **Remaining Route Evaluation:**
   $$T_{\text{remain}}(R_0 \mid v_{\text{obs}}) = \sum_{e \in R_{\text{remain}}} \frac{L_e}{v_{\text{obs}}(e, t_1)}$$

2. **Optimal Alternative Computation:**
   Custom Dijkstra recomputes the global optimal subpath from the vehicle's current node $u_{\text{curr}}$ to the destination:
   $$R_1^* = \text{Dijkstra}\left(G, \text{source}=u_{\text{curr}}, \text{dest}=\text{Destination}, \text{weights}=w_{\text{obs}}\right)$$
   $$T^*(u_{\text{curr}} \to \text{dest} \mid v_{\text{obs}}) = \sum_{e \in R_1^*} \frac{L_e}{v_{\text{obs}}(e, t_1)}$$

3. **Degradation Detection:**
   $$\Delta T = T_{\text{remain}}(R_0 \mid v_{\text{obs}}) - T^*(u_{\text{curr}} \to \text{dest} \mid v_{\text{obs}})$$
   $$\Delta T\% = \frac{\Delta T}{T_{\text{remain}}(R_0 \mid v_{\text{obs}})} \times 100\%$$

4. **Dual-Threshold Hysteresis Rule:**
   $$\text{Trigger Reroute} \iff (\Delta T \ge 10.0\text{ seconds}) \land (\Delta T\% \ge 3.0\%)$$

If both conditions are met, the Edge Server compiles $R_{\text{dyn}} = R_{\text{traversed}} \mathbin{\Vert} R_1^*$ and issues a `ROUTE_UPDATE (REROUTE)` signal. Otherwise, the current route is maintained, preventing path thrashing.

---

## 5. Architectural Motivation: Why Edge-Cloud?

In intelligent transportation networks, placing routing computation at the Edge rather than the Cloud provides critical operational advantages:
1. **Low-Latency Decision Loop:** Finding a detour around an emerging accident or queue spillback must happen within sub-second timescales before the vehicle passes the divert junction. The Edge Server executes Dijkstra and degradation audits in under **$20.4\text{ ms}$**.
2. **Bandwidth Economy:** Transmitting raw, high-frequency vehicular GPS coordinates across cellular backhauls to a distant cloud datacenter generates severe network congestion. Local Edge Servers aggregate localized telemetry and exchange compact routing directives.
3. **Resilience to WAN Partitions:** In the event of cloud connectivity disruptions, local Edge Servers continue routing and rerouting vehicles using cached weights and local road network topologies.

---

## 6. Prototype vs. Real-World Deployment Distinction

> [!IMPORTANT]
> **Scientific Integrity Declaration:**
> The current GeoPulse Phase 11 prototype **simulates** the logical separation between Cloud, Edge Server, and Vehicle using modular Python components on the host workstation.
>
> - **Software Modules:** The Cloud service, Edge Server, and Vehicle simulator execute as modular objects in the local development environment.
> - **Execution Timings:** All reported latencies (e.g. $20.33\text{ ms}$ Dijkstra runtime, $1.03\text{ ms}$ prediction packaging) represent **prototype software execution runtimes on host hardware**, not physical embedded edge hardware benchmarks.
> - **Scope Boundary:** Physical embedded edge hardware deployment (e.g., NVIDIA Jetson, Raspberry Pi compute nodes), cellular networking (4G/5G V2X), and wireless packet latency measurements are outside the current project scope and are designated for future production deployment.
