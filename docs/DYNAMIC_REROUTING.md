# GeoPulse: Dynamic Rerouting Engine
## Mid-Journey Traffic Ingestion & Closed-Loop Threshold-Gated Detour Directives

**Document:** `docs/DYNAMIC_REROUTING.md`  
**System:** GeoPulse Major Project  
**Author:** GeoPulse Architecture & Core Engineering  
**Version:** 2.0  
**Status:** Approved & Implemented  

---

## 1. Introduction

Urban traffic conditions are inherently non-stationary. Road networks experience sudden congestion spikes, peak-hour bottlenecks, and incident-related delays while vehicles are in transit. An intelligent transportation system cannot rely exclusively on open-loop pre-trip route planning.

The **GeoPulse Dynamic Rerouting Engine** implements a closed-loop operating paradigm:

$$\text{Predict} \longrightarrow \text{Plan} \longrightarrow \text{Drive} \longrightarrow \text{Observe} \longrightarrow \text{Compare} \longrightarrow \text{Re-route}$$

This document explains the dynamic rerouting architecture, its integration with sequential two-edge decision-making, the dual-threshold hysteresis policy, and route continuity guarantees.

---

## 2. Dynamic Rerouting Architecture

The dynamic rerouting system bridges the simulated Edge Server, the traffic sensor stream, and the vehicle client:

```
               [Live Arterial Sensor Telemetry]
                              │
                              ▼
               ┌──────────────────────────────┐
               │    TrafficUpdateMessage      │
               │  v_obs(e) for 700 corridors  │
               └──────────────┬───────────────┘
                              │
                              ▼
               ┌──────────────────────────────┐
               │       Edge Server            │
               │ • Rebuilds dynamic weights   │
               │ • Locates vehicle position u │
               └──────────────┬───────────────┘
                              │
               ┌──────────────┴───────────────┐
               │   Route Degradation Check    │
               │ T_remain(Current) vs T*(Alt) │
               └──────────────┬───────────────┘
                              │
            Does Saving Satisfy Dual Threshold?
             (ΔT >= 10.0s AND ΔT% >= 3.0%)
                              │
              ┌───────────────┴───────────────┐
             YES                             NO
              │                               │
              ▼                               ▼
     ┌────────────────────────┐      ┌────────────────────────┐
     │  RouteUpdateMessage    │      │  Suppression Directive │
     │  Dynamic Detour R1     │      │  Stay on Current Plan  │
     └────────┬───────────────┘      └────────────────────────┘
              │
              ▼
     ┌────────────────────────┐
     │  Vehicle Client        │
     │  Splices R1 at Node u  │
     │  Resumes Sequential    │
     │  Two-Edge Navigation   │
     └────────────────────────┘
```

---

## 3. Degradation Detection & Dual-Threshold Policy

### 3.1 The Flaw of Naive Rerouting
In unconstrained rerouting systems, any minuscule travel-time improvement (e.g. saving $0.5\text{ seconds}$ on a $15\text{ minute}$ trip) triggers a route update. This causes:
- **Route Chattering (Ping-Pong Effect):** Continuous switching between parallel corridors.
- **Driver Distraction & Friction:** Erratic turns and recalculation confusion.
- **Negative Rerouting Rate:** When traffic fluctuates rapidly, minor detours often end up taking longer than staying on the original route.

### 3.2 GeoPulse Dual-Threshold Hysteresis Policy
GeoPulse enforces an experimentally proven **dual-gate threshold policy** (established in Phase 10 ablation across 800 controlled runs):

$$\Delta T = T_{\text{remain}}(\text{Current Path} \mid v_{\text{obs}}) - T^*(\text{Current Node} \to \text{Dest} \mid v_{\text{obs}}) \ge \tau_{\text{abs}}$$

$$\Delta T\% = \frac{\Delta T}{T_{\text{remain}}(\text{Current Path} \mid v_{\text{obs}})} \times 100\% \ge \tau_{\text{rel}}$$

- **Default Parameters:**
  - $\tau_{\text{abs}} = 10.0\text{ seconds}$ (Absolute delay gate)
  - $\tau_{\text{rel}} = 3.0\%$ (Relative percentage gate)

### 3.3 Theoretical & Empirical Properties
1. **$100\%$ Beneficial Rerouting Guarantee:** Across all 800 evaluation scenarios in Phase 10, the dual-threshold policy yielded a **$100\%$ beneficial reroute rate** (0 detrimental reroutes).
2. **Noise Suppression:** Suppresses minor sensor jitters, signal delays, and micro-perturbations.
3. **Significant Travel-Time Savings:** In canonical peak congestion (OD #0), rerouting saves **$84.90\text{ seconds}$** ($6.60\%$ overall journey saving, $9.23\%$ remaining-leg saving).

---

## 4. Vehicle Position Continuity & Safety Guarantees

Dynamic rerouting in GeoPulse adheres strictly to physical continuity principles:

### 1. No Teleportation / No Source Reset
- When a reroute is triggered, the vehicle **never** restarts from its original origin.
- The detour path $R_1$ is computed strictly with source equal to the vehicle's **exact current node** $u = n_{\text{current}}$.

### 2. Preserved Completed Segments
- The traversed path history $P_{\text{traversed}} = [e_0, e_1, \dots, e_{k-1}]$ is frozen and permanently recorded in the journey log.
- Total executed journey trajectory becomes:
  $$P_{\text{executed}} = P_{\text{traversed}} \cup P_{\text{detour}}$$

### 3. Smooth Continuation Under Sequential Two-Edge Selection
- When rerouting occurs during sequential routing, the vehicle updates its remaining destination heuristic guidance and edge weights.
- Sequential two-edge selection continues seamlessly from node $u$, evaluating candidates $u \to v_A$ and $u \to v_B$ under the newly active weights.
