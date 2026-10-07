# Phase 11B: Interactive GeoPulse Demonstration Dashboard
## Live Closed-Loop Pipeline Visualization & Defense Guide

---

## 1. Purpose

The **GeoPulse Interactive Demonstration Dashboard** is a lightweight, real-time graphical application engineered on top of the validated Phase 7–11 core engines. Its primary purpose is to allow faculty advisors, thesis committee evaluators, and students to **execute, inspect, and interact with the actual GeoPulse pipeline live** rather than relying solely on static command-line outputs or pre-generated publication plots.

### Core Principle
This dashboard is a **visual interface to the genuine GeoPulse computational engine**, not a static mockup. Every interaction executes:
```text
Real Historical Traffic Data
          ↓
Real LightGBM ML Speed Forecasting
          ↓
Real Scratch-Built Dijkstra Shortest Path Solver
          ↓
Real Discrete Kinematic Vehicle Traversal Telemetry
          ↓
Real Sensor Stream Degradation Evaluation & Dual Thresholds
          ↓
Real Dynamic Detour Recomputation & Reroute Directive
          ↓
Real Travel-Time Savings & Counterfactual Verification
```

---

## 2. System Architecture

The dashboard visualizes the 3-tier distributed intelligent transportation system (ITS) simulated in Phase 11:

```text
┌─────────────────────────────────────────────────────────────┐
│                 INTERACTIVE DASHBOARD UI                    │
│      Streamlit • OSM Road Network Maps • Telemetry Scrubber │
└──────────────────────────────┬──────────────────────────────┘
                               │ User Triggers & Scrubber
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                 GEOPULSE BACKEND ENGINE                     │
│  src/dashboard/backend.py • src/dashboard/visualization.py  │
└──────┬───────────────────────┼───────────────────────┬──────┘
       │                       │                       │
       ▼                       ▼                       ▼
┌──────────────┐       ┌──────────────┐        ┌──────────────┐
│  CLOUD TIER  │       │  EDGE SERVER │        │ VEHICLE TIER │
│  LightGBM    │──────▶│ Custom       │───────▶│ Kinematic    │
│  25 Features │Model  │ Dijkstra     │Route   │ Traversal    │
│  Regional    │Brdcst │ Degradation  │Update  │ Waypoint     │
│  Broadcast   │       │ Dual Gates   │        │ Telemetry    │
└──────────────┘       └──────────────┘        └──────────────┘
```

1. **Cloud Component (`CloudModelService`)**: Hosts the validated LightGBM 25-feature regressor (`models/speed_predictor.joblib`), generating +1-hour predictive speed broadcasts across all 700 monitored regional links.
2. **Regional Edge Server (`EdgeServer`)**: Synthesizes predictive dynamic road weights, manages vehicle navigation sessions, solves shortest paths via our custom min-heap Dijkstra, ingests traffic updates, and evaluates the dual operational gates ($\Delta T \ge 10\text{ s}$ AND $\Delta T\% \ge 3\%$).
3. **Connected Vehicle Client (`Vehicle`)**: Discretely advances link-by-link through physical road segments, emits periodic `POSITION_UPDATE` telemetry, ingests `ROUTE_UPDATE` directives, and executes dynamic detours mid-journey.

---

## 3. How to Launch Locally

Ensure your Python virtual environment is activated, then execute:

```powershell
# From the repository root:
.venv\Scripts\streamlit run scripts/run_phase11_dashboard.py
```

Or on Linux/macOS:
```bash
./.venv/bin/streamlit run scripts/run_phase11_dashboard.py
```

The application opens automatically in your web browser at:
```text
http://localhost:8501
```

---

## 4. Scenario Catalog & Modes

The dashboard provides two operational demonstration modes:

### Mode A — Guided Demo (Default)
- **Profile**: Canonical Evening Peak Scenario (OD #0: Khandagiri Square $\to$ Rasulgarh Square).
- **Date & Departure**: Jan 15, 2026 at 19:30:00 IST (Severe evening commute peak).
- **Update Timestamp**: 20:30:00 IST at Decision Node `3320289784` (Link #15, ~20% along corridor).
- **Behavior**: Downstream bottleneck collapses segment speeds. Dual gates are breached ($\Delta T = 84.9\text{ s} \ge 10\text{ s}$, $\Delta T\% = 9.23\% \ge 3\%$). The Edge Server recomputes the optimal alternative via custom Dijkstra, saving **84.91 seconds (1.42 minutes, +6.60% improvement)**.
- **Validation**: Automatically verifies parity against canonical Phase 11 artifacts (`results/phase11/demo_results.json`).

### Mode B — Explore Scenarios
Allows faculty and examiners to test the system across **20 reproducible benchmark scenarios** spanning diverse operational conditions:
- **Evening Peak (Scenarios 0–7)**: High congestion across NH16 and arterial corridors; triggers beneficial dynamic rerouting ($\Delta T = 84.9\text{ s}$, $+5.43\%$ to $+6.60\%$).
- **Morning Peak (Scenarios 8–11)**: Traffic flows close to predictive expectations; degradation remains below gates; dynamic rerouting is **properly suppressed** (Saving = $0.0\text{ s}$, $0.0\%$ churn).
- **Midday Nominal Flow (Scenarios 12–15)**: Stable arterial flow; rerouting suppressed.
- **Off-Peak Free Flow (Scenarios 16–19)**: Late-night free flow conditions; routes maintained.

---

## 5. 60-Second Professor Demonstration Script

Follow this script during thesis defenses, committee presentations, or faculty reviews:

| Time | Action | What to Point Out & Explain |
|:---|:---|:---|
| **0:00 – 0:15** | Open dashboard and leave on **Mode A (Guided Demo)**. Click **`▶ RUN GEOPULSE`**. | *"Notice the live progress indicator executing our actual LightGBM model and custom Dijkstra algorithm. In less than 2 seconds, it synthesizes dynamic weights and plans initial route R0 across 74 directed road segments in Bhubaneswar."* |
| **0:15 – 0:30** | Direct attention to the **Route Map** and the **Architecture Status strip**. | *"Here is the physical OpenStreetMap geometry. The Cloud tier has broadcasted speed predictions, the Edge Server computed route R0 (blue line), and the connected vehicle departs Khandagiri Square."* |
| **0:30 – 0:45** | Click **`⚡ Traffic Update`** (or drag slider to **Step 15**). | *"At 20:30 IST, real-time sensor telemetry reports severe downstream congestion (observed speed drops below predicted speed). The Edge Server audits the remaining path and detects that an alternative bypass saves 84.9 seconds (9.23% relative)."* |
| **0:45 – 0:55** | Highlight the **Dual Thresholds** and **Route Map bypass**. | *"Because this exceeds our validated gates ($\Delta T \ge 10\text{s}$ and $\Delta T\% \ge 3\%$), the Edge Server dispatches a ROUTE_UPDATE. Notice the map: the vehicle abandons the red dashed congested corridor and seamlessly switches to the emerald green dynamic bypass."* |
| **0:55 – 1:10** | Click **`🏁 Destination`** and review the **Final Outcome Table**. | *"The vehicle reaches Rasulgarh Square in 20.04 minutes instead of 21.45 minutes. GeoPulse saved 1.42 minutes (84.91 seconds), a +6.60% journey improvement. Crucially, the system did not guess—this result is the exact mathematical counterfactual under real observed sensor data."* |
| **1:10 – 1:20** | Switch to **Mode B**, select **Scenario #8 (Morning Peak)**, and click Run. | *"When traffic flows normally in Morning Peak, $\Delta T$ stays below 10 seconds. GeoPulse suppresses rerouting to prevent unnecessary route flapping. This proves the system is robust and selective."* |

---

## 6. Metrics Reference Guide

| Metric | Subsystem | Scientific Definition |
|:---|:---|:---|
| **Predicted Speed** | Cloud (LightGBM) | Spatial mean of predicted segment velocities ($v_{\text{pred}}$ in km/h) forecasted 1 hour ahead. |
| **Observed Speed** | Edge (Sensors) | Ground-truth segment velocities ($v_{\text{obs}}$ in km/h) captured at update timestamp $t_1$. |
| **Prediction Error** | ML Pipeline | Mean absolute percentage error between forecast and ground truth on the corridor. |
| **Initial Route ETA** | Edge (Dijkstra) | Estimated trip duration at departure under LightGBM predicted weights ($T_0$). |
| **Remaining Path ETA** | Edge (Dijkstra) | Travel time required to traverse the remainder of initial route R0 under observed congestion. |
| **Alternative Bypass ETA** | Edge (Dijkstra) | Travel time required to reach destination from current node via scratch-built Dijkstra under observed weights. |
| **$\Delta T$ (Absolute Saving)** | Edge Decision Gate | Absolute travel-time differential: $T_{\text{remain, current}} - T_{\text{remain, optimal}}$ (in seconds). |
| **$\Delta T\%$ (Relative Saving)** | Edge Decision Gate | Relative improvement percentage: $\frac{\Delta T}{T_{\text{remain, current}}} \times 100\%$. |
| **Dual Gate Verdict** | Operational Policy | Boolean decision: `TRIGGER DYNAMIC REROUTE` if $\Delta T \ge 10\text{ s}$ AND $\Delta T\% \ge 3\%$; else `MAINTAIN ROUTE`. |
| **Spatial Route Overlap** | Navigation | Jaccard edge set overlap ($\frac{|E_0 \cap E_1|}{|E_0 \cup E_1|}$) quantifying trajectory divergence. |
| **Software Execution Time** | Prototype Benchmarks | Measured local CPU wall-clock computation latency in milliseconds for each algorithmic block. |

---

## 7. Results Export & Persistence

Every interactive run automatically exports its complete artifacts to disk:
```text
results/dashboard_runs/demo_result_scenario_<ID>_<TIMESTAMP>.json
results/dashboard_runs/demo_timeline_scenario_<ID>_<TIMESTAMP>.csv
```

Users can also download results directly from the UI using the **`📥 Download Run Results (JSON)`** and **`📥 Download Timeline (CSV)`** buttons.

> **Integrity Guarantee**: Dashboard exports never overwrite or mutate canonical Phase 11 baseline files (`results/phase11/demo_results.json`, `demo_timeline.csv`, etc.).

---

## 8. Limitations & Scope

1. **Software-Based Architecture Simulation**: The Cloud $\to$ Edge Server $\to$ Vehicle topology is logically simulated within Python processes using strictly typed dataclass message contracts. It is not deployed on physically separated embedded edge nodes (e.g., Raspberry Pi clusters or cellular MEC servers).
2. **Local Measured Execution Times**: Execution times reported in the expandable latency inspector reflect prototype software runtime on the local machine (Intel/AMD x86_64 CPU), not over-the-air cellular network propagation latency (5G NR V2X / C-V2X latency).
3. **Discrete 1-Hour Traffic Updates**: Real-time traffic updates occur on 1-hour resolution snapshots corresponding to the structured traffic dataset (`traffic_structured_v1.parquet`).
4. **Graph Road Coverage**: Road geometries and topologies are bounded by the validated Bhubaneswar OpenStreetMap drive network (`bhubaneswar_drive.graphml`).
