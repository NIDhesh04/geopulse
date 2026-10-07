# Phase 9: Dynamic Rerouting Replay & End-to-End System Demonstration

**Project:** GeoPulse — AI-Based Dynamic Traffic Routing System  
**Academic Level:** 7th Semester B.Tech Major Project  
**Author:** Pair Programming Team (GeoPulse Engineering)  
**Study Region:** Bhubaneswar Urban Network (OSM MultiDiGraph: 18,260 Nodes, 46,679 Directed Edges)  
**Historical Period:** January 15–17, 2026 (Real Chronological Test Observations)

---

## 1. Objective

Phase 8 established that offline routing guided by ML speed forecasts performs near the empirical current-traffic oracle (recovering 99.4% of oracle efficiency and outperforming naive static limits by 16.5%). However, real-world transport systems operate under dynamic, non-stationary conditions: traffic evolves mid-journey, accidents or sudden bottlenecks occur, and static or purely open-loop routes degrade over time.

The objective of **Phase 9** is to implement and empirically demonstrate the complete closed-loop operating paradigm of GeoPulse:

$$\text{Predict} \longrightarrow \text{Plan} \longrightarrow \text{Drive} \longrightarrow \text{Observe} \longrightarrow \text{Compare} \longrightarrow \text{Re-route}$$

Specifically, Phase 9:
1. Implements a lightweight, time-progressive historical replay engine ([`src/routing/dynamic_rerouter.py`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/src/routing/dynamic_rerouter.py)) that simulates vehicle progress along physical road links without synthetic data artifacts.
2. Formulates an automated route degradation detection and threshold-gated rerouting trigger policy.
3. Computes counterfactual journey outcomes: **Strategy A (No Rerouting)** vs. **Strategy B (GeoPulse Dynamic Rerouting)**.
4. Selects a reproducible, high-congestion **Main Demonstration Scenario** (OD #0, Evening Peak) and runs a rigorous 20-scenario multi-period benchmark.
5. Generates 10 defense-grade visual analytics figures ([`results/phase9/figures/`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase9/figures)) and an interactive terminal replay demo ([`src/demo/phase9_demo.py`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/src/demo/phase9_demo.py)).

---

## 2. Predict $\to$ Plan $\to$ Observe $\to$ Compare $\to$ Re-route Architecture

The system operates across five coordinated functional stages:

```
  [t0: Planning Epoch]
           │
           ▼
┌───────────────────────┐
│ ML Speed Prediction   │ ◄── LightGBM model forecasts next-hour corridor speeds v_pred(e)
└──────────┬────────────┘
           │
           ▼
┌───────────────────────┐
│ Custom Dijkstra R0    │ ◄── Synthesizes edge weights w_pred(e) = length / v_pred; computes initial route R0
└──────────┬────────────┘
           │
           ▼
  [Vehicle Traversal: t0 -> t1]
           │
           ▼
┌───────────────────────┐
│ In-Transit Telemetry  │ ◄── Vehicle reaches Decision Node n_dec after traversing k segments of R0
└──────────┬────────────┘
           │
  [t1: Observation Epoch]
           │
           ▼
┌───────────────────────┐
│ Traffic State Update  │ ◄── Real-time sensor telemetry v_obs(e) received from arterial network
└──────────┬────────────┘
           │
           ▼
┌───────────────────────┐
│ Degradation Evaluator │ ◄── Compares T_remain(R0 | v_obs) vs. T*(n_dec -> dest | v_obs)
└──────────┬────────────┘
           │
     Is Saving >= Threshold? (ΔT >= 10s AND ΔT/T >= 3%)
      ┌────┴────┐
     NO        YES
      │         │
      ▼         ▼
┌──────────┐ ┌───────────────────────────┐
│ Stay on  │ │ Custom Dijkstra Rerouting │ ◄── Solves new optimal subpath R1 from n_dec
│ Path R0  │ └─────────────┬─────────────┘
└──────────┘               │
                           ▼
             ┌───────────────────────────┐
             │ Merge Trajectory:         │
             │ Traversed(R0) + R1        │
             └───────────────────────────┘
```

---

## 3. Replay Methodology

To ensure physical realism without requiring a complex microscopic vehicular simulator (e.g. SUMO), Phase 9 adopts a **link-based discrete-event kinematic replay**:

1. **Spatial Representation:** The Bhubaneswar OSM directed graph $G = (V, E)$ represents all road links with exact geodesic lengths $L_e$, road classifications, and directional connectivity.
2. **Temporal Discretization:** The replay advances over historical hourly observation windows ($t_0 \to t_1$), corresponding to real traffic telemetry timestamps recorded during the Phase 7 test period (January 15–17, 2026).
3. **Link Accumulation:**
   For each directed edge $e = (u, v, key)$ traversed during epoch $t$, travel time is evaluated as:
   $$\tau(e, t) = \frac{L_e}{v(e, t)}$$
   where $v(e, t)$ is the effective speed under the active traffic weight policy (dynamic sensor speeds with static speed limit fallback).
4. **Decision Boundary:** At intermediate decision nodes along the route (e.g. 20%–40% into the planned journey), the replay pauses the vehicle, ingests the incoming $t_1$ observation state, and evaluates downstream conditions.

This represents a clean **historical replay approximation** that is mathematically tractable, reproducible, and reflective of urban intelligent transportation system (ITS) deployments.

---

## 4. Initial Route Selection ($t_0$)

At timestamp $t_0$, the system possesses:
- Historical feature lags and calendar embeddings (hour of day, day of week, peak flag).
- The Phase 7 trained LightGBM model ($\text{MAE} = 4.79\text{ km/h}, R^2 = 0.817$).
- Baseline static road network attributes (OSM length, speed limits).

**Zero Data Leakage Guarantee:**  
Crucially, **no future observed traffic from timestamp $t_1$ is accessible during initial planning**. The edge weights $w_{\text{pred}}(e)$ are constructed strictly using:
$$w_{\text{pred}}(e) = \frac{L_e}{\hat{v}_{t_1}(e)}$$
Custom min-heap Dijkstra is executed from Origin to Destination on $G$ with weights $w_{\text{pred}}$, returning the planned route sequence:
$$R_0 = [e_1, e_2, \dots, e_m]$$

---

## 5. Real-Time Traffic Observation ($t_1$)

As the vehicle progresses along $R_0$, it traverses the initial prefix of edges:
$$R_{\text{traversed}} = [e_1, e_2, \dots, e_k]$$
Upon arriving at node $u_{k+1}$ (the **Decision Node**), new arterial sensor observations from epoch $t_1$ arrive.

In the real urban environment, traffic conditions diverge from forecasts due to:
- localized queue spillbacks,
- sudden pedestrian surges or intersection impedance,
- stochastic variance in commuter arrival rates.

The remaining untraversed portion of the initial route is:
$$R_{\text{remain}} = [e_{k+1}, e_{k+2}, \dots, e_m]$$
Its actual remaining travel time under the newly observed traffic field $v_{\text{obs}}(t_1)$ is evaluated as:
$$T_{\text{remain}}(R_0 \mid v_{\text{obs}}) = \sum_{e \in R_{\text{remain}}} \frac{L_e}{v_{\text{obs}}(e, t_1)}$$

---

## 6. Route Degradation Detection

To determine if the vehicle is trapped in an unexpected bottleneck, the system queries the optimal path available from the vehicle's current position $u_{k+1}$ to Destination under the new observed field $v_{\text{obs}}(t_1)$:
$$R_1^* = \text{Dijkstra}\left(G, \text{source}=u_{k+1}, \text{dest}=\text{Destination}, \text{weights}=w_{\text{obs}}(t_1)\right)$$
with optimal remaining travel time:
$$T^*(u_{k+1} \to \text{dest} \mid v_{\text{obs}}) = \sum_{e \in R_1^*} \frac{L_e}{v_{\text{obs}}(e, t_1)}$$

The **Route Degradation** (potential saving) is defined as:
$$\Delta T = T_{\text{remain}}(R_0 \mid v_{\text{obs}}) - T^*(u_{k+1} \to \text{dest} \mid v_{\text{obs}})$$
$$\Delta T_{\%} = \frac{\Delta T}{T_{\text{remain}}(R_0 \mid v_{\text{obs}})} \times 100\%$$

---

## 7. Rerouting Threshold Policy

A naive reactive router that switches paths for sub-second differences creates **route thrashing** (erratic driver guidance, GPS confusion, and network destabilization).

GeoPulse enforces a **dual-gate hysteresis threshold**:
1. **Absolute Threshold:** $\Delta T \ge \theta_{\text{abs}} = 10.0\text{ seconds}$
2. **Relative Threshold:** $\Delta T_{\%} \ge \theta_{\text{rel}} = 3.0\%$

**Decision Rule:**
$$\text{Trigger Reroute} \iff (\Delta T \ge 10.0\text{ s}) \land (\Delta T_{\%} \ge 3.0\%)$$

If either condition fails, the system logs the event as sub-threshold and instructs the vehicle to maintain its current trajectory.

---

## 8. Custom Dijkstra Rerouting

When the threshold is satisfied:
1. The custom min-heap Dijkstra algorithm computes the exact optimal bypass corridor $R_1^*$ from $u_{k+1}$ to Destination using updated observed weights $w_{\text{obs}}(e, t_1)$.
2. The dynamic rerouted journey trajectory $R_{\text{dyn}}$ is synthesized by concatenating:
   $$R_{\text{dyn}} = R_{\text{traversed}} \mathbin{\Vert} R_1^*$$
3. Structural divergence metrics are logged:
   - **Path Overlap (Jaccard Index):**
     $$\text{Overlap}(R_0, R_{\text{dyn}}) = \frac{|E(R_0) \cap E(R_{\text{dyn}})|}{|E(R_0) \cup E(R_{\text{dyn}})|}$$
   - **Changed Link Count:** Count of unique edges in $R_1^*$ not present in $R_{\text{remain}}$.

---

## 9. Counterfactual No-Reroute Comparison

To rigorously demonstrate the value of dynamic intelligence, Phase 9 formulates a formal **counterfactual evaluation**:

- **Strategy A (No Rerouting — Baseline):**  
  The vehicle stubbornly follows the initial ML-predicted route $R_0$ to completion, absorbing all unanticipated downstream delays under observed traffic $v_{\text{obs}}(t_1)$:
  $$T_A = T_{\text{traversed}}(R_0 \mid v_{t_0}) + T_{\text{remain}}(R_0 \mid v_{\text{obs}, t_1})$$

- **Strategy B (GeoPulse Dynamic Reroute):**  
  The vehicle traverses the prefix under $v_{t_0}$, switches to $R_1^*$ at the decision node upon detecting degradation, and completes the bypass:
  $$T_B = T_{\text{traversed}}(R_0 \mid v_{t_0}) + T^*(u_{k+1} \to \text{dest} \mid v_{\text{obs}, t_1})$$

- **Net Time Saved:**
  $$\Delta T_{\text{saved}} = T_A - T_B$$
- **Percentage Efficiency Gain:**
  $$\eta = \frac{T_A - T_B}{T_A} \times 100\%$$

---

## 10. Main Demonstration Scenario Results

The candidate search script ranked 221 candidate journeys across the test period (January 15–17, 2026). **Scenario #0** was deterministically selected as the primary demonstration trip:

### Scenario Metadata
- **Origin-Destination Pair:** OD #0 (Origin: Node `3722327026`, Destination: Node `2443921849`)
- **Corridor Distance:** $10.98\text{ km}$ across central Bhubaneswar
- **Temporal Context:** Evening Commuter Peak (Planning: 19:30 IST / 14:00 UTC; Telemetry Update: 20:30 IST / 15:00 UTC)
- **Decision Point:** Link #15 (Node `3320289784`), representing approximately 20% into the journey.

### Numerical Results

| Metric | Strategy A (No Reroute) | Strategy B (GeoPulse Dynamic) | Impact / Difference |
|---|---|---|---|
| **Total Journey Duration** | **$1,287.06\text{ s}$** ($21.45\text{ min}$) | **$1,202.15\text{ s}$** ($20.04\text{ min}$) | **$-84.91\text{ s}$** ($-1.42\text{ min}$) |
| **Travel Time Improvement** | Baseline ($0.0\%$) | **$+6.60\%$** | **$+6.60\%$ faster** |
| **Route Distance** | $10,981.64\text{ m}$ ($10.98\text{ km}$) | $10,984.73\text{ m}$ ($10.98\text{ km}$) | $+3.09\text{ m}$ ($+0.03\%$) |
| **Total Road Segments** | 74 links | 46 links (cleaner bypass) | $-28\text{ links}$ |
| **Decision Trigger Reason** | N/A | Degradation $\Delta T = 84.9\text{ s}$ ($9.2\%$) | Exceeds $10\text{s} / 3\%$ gates |
| **Spatial Route Overlap** | $100\%$ | $60.0\%$ | Diverges onto major parallel bypass |

### Physical Interpretation of Route Degradation
Figure 5 illustrates the physical mechanism behind the reroute:
- At planning time ($t_0 = 19:30\text{ IST}$), the downstream corridor segment had a free-flow design speed of $50.0\text{ km/h}$ and an ML predicted speed of $31.7\text{ km/h}$.
- By the time the vehicle arrived at the decision node ($t_1 = 20:30\text{ IST}$), observed traffic on this segment plummeted to **$14.0\text{ km/h}$** due to peak evening congestion.
- Continuing straight on $R_0$ would have incurred substantial queuing delay. GeoPulse dynamically detected this speed collapse, searched for an alternative, and redirected the vehicle onto an open arterial bypass that added only $3\text{ meters}$ in physical distance while bypassing the congested segment completely, saving $1.42\text{ minutes}$.

---

## 11. Multi-Scenario Benchmark Results

To evaluate system consistency, a structured benchmark of **20 distinct replay scenarios** was evaluated across all four operational diurnal periods:
- **Morning Peak** (09:30 $\to$ 10:30 IST)
- **Midday Flow** (13:30 $\to$ 14:30 IST)
- **Evening Peak** (19:30 $\to$ 20:30 IST)
- **Off-Peak Night** (22:30 $\to$ 23:30 IST)

### Benchmark Summary Statistics

| Benchmark Metric | Measured Empirical Value |
|---|---|
| **Total Evaluated Scenarios** | 20 journeys |
| **Reroute Trigger Frequency** | **$40.0\%$** (8 out of 20 scenarios) |
| **No-Reroute Frequency** | **$60.0\%$** (12 out of 20 scenarios) |
| **Beneficial Reroute Rate** | **$100.0\%$** (8 / 8 triggered trips saved time) |
| **False / Detrimental Reroute Rate** | **$0.0\%$** (0 / 8 triggered trips lost time) |
| **Mean Time Saved (When Triggered)** | **$84.90\text{ seconds}$** ($1.42\text{ min}$) |
| **Mean Percentage Gain (When Triggered)**| **$+5.88\%$** |
| **Overall Mean Saving (All 20 Trips)** | **$33.96\text{ seconds}$** |
| **Overall Mean Gain (All 20 Trips)** | **$+2.35\%$** |
| **Average Route Overlap Across Fleet**| **$87.75\%$** |

### Insights from Multi-Period Analysis
1. **Peak Period Responsiveness:** Dynamic rerouting was triggered predominantly during the Evening Peak (18:30–20:30 IST), where rapid arterial congestion fluctuations occur.
2. **Off-Peak and Morning Stability:** In 60% of cases, the initial ML route remained optimal or the difference was sub-threshold (e.g. Scenario 12 showed an $8.7\text{s} / 0.7\%$ potential saving, which was correctly suppressed by the $3\%$ relative threshold).
3. **Absence of Negative Rerouting:** Because Dijkstra recomputes paths with true observed link costs, no vehicle was diverted into a worse route.

---

## 12. Visualizations Summary

All figures were rendered at **300 DPI** and saved in [`results/phase9/figures/`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase9/figures):

1. **`01_dynamic_rerouting_map.png`**: High-resolution geographical plot of the Bhubaneswar OSM road network depicting the initial trajectory, abandoned congested corridor, and dynamic bypass.
2. **`02_rerouting_timeline.png`**: Chronological milestone timeline tracking travel-time expectations across the 4-stage lifecycle.
3. **`03_before_after_travel_time.png`**: Direct bar chart contrasting Strategy A ($21.45\text{ min}$) vs. Strategy B ($20.04\text{ min}$).
4. **`04_route_change_analysis.png`**: Comparative breakdown of segment counts, bypass length, and route overlap.
5. **`05_traffic_evolution.png`**: Bottleneck telemetry audit tracking speed decline ($50.0 \to 31.7 \to 14.0\text{ km/h}$).
6. **`06_rerouting_benefit_distribution.png`**: Histogram and KDE of travel time savings across triggered trips.
7. **`07_reroute_frequency.png`**: Fleet-wide distribution of reroute triggers ($40\%$ triggered, $60\%$ suppressed).
8. **`08_prediction_vs_observation.png`**: Corridor-level scatter plot comparing forecasted speeds vs. telemetry observations.
9. **`09_cumulative_journey_comparison.png`**: Step-by-step cumulative travel time curves illustrating trajectory separation at Step 15.
10. **`10_dynamic_routing_summary.png`**: Executive defense infographic presenting the complete closed-loop architecture.

Complete visual annotations and descriptions are available in [`docs/phase9_visualizations.md`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/docs/phase9_visualizations.md).

---

## 13. System Limitations

While Phase 9 establishes an end-to-end working prototype, several limitations should be noted for future work:

1. **Discrete Temporal Granularity:** Historical observations update at 1-hour intervals. In a live production system, GPS telemetry and sensor feeds would stream at 1- to 5-minute intervals.
2. **Link-Based Kinematic Approximation:** The replay model evaluates travel time as link length divided by link speed. It does not model microscopic vehicle-vehicle interactions, signal timing phases, or lane-changing friction.
3. **Static Downstream Assumptions Post-Reroute:** When evaluating $R_1^*$, downstream unmonitored links utilize OSM static speed limits as established in Phase 8's weight policy.
4. **Single-Vehicle Perspective:** The simulation does not simulate network-level equilibrium (e.g. redirecting 1,000 vehicles to the same bypass corridor causing secondary congestion).

---

## 14. Scientific Interpretation & Conclusion

The core intellectual contribution of GeoPulse is **not** an assertion that machine learning can foresee all future traffic states with perfect accuracy. Rather, it is the integration of **predictive foresight** with **reactive adaptation**:

1. **Predictive Planning ($t_0$)** provides a far superior initial routing baseline than static speed limits, avoiding historically congested corridors before departure.
2. **Reactive Dynamic Rerouting ($t_1$)** acts as a resilient safety net, detecting stochastic departures from the ML forecast and deflecting vehicles away from evolving bottlenecks.

By coupling custom Dijkstra with an empirical degradation trigger, GeoPulse achieves a **6.60% travel-time reduction (84.9 seconds)** on the main demonstration commute while maintaining strict decision stability (suppressing false reroutes on 60% of standard journeys). This validates Phase 9 as a complete, defense-ready academic prototype.
