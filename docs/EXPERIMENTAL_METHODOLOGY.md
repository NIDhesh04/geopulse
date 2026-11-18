# GeoPulse: Experimental Methodology & Scientific Design
## Controlled Evaluation Framework for Sequential Two-Edge Decision & Dynamic Rerouting

**Document:** `docs/EXPERIMENTAL_METHODOLOGY.md`  
**System:** GeoPulse Major Project  
**Author:** GeoPulse Architecture & Core Engineering  
**Version:** 1.0  
**Status:** Approved  

---

## 1. Research Objectives & Hypotheses

The central scientific objective of this investigation is:
> **To evaluate the trade-offs between computational decision latency, local candidate restrictions, changing traffic conditions, and total journey travel time under sequential two-edge decision-making compared to global shortest-path benchmarks.**

### Core Hypotheses:
1. **$H_1$ (Computational Efficiency):** Localized sequential two-edge selection reduces per-decision computation time by orders of magnitude relative to global Dijkstra or A* recomputations on large urban networks.
2. **$H_2$ (Candidate Generation Impact):** Destination-aware and lookahead candidate filtering significantly reduces the optimality gap relative to random or naive greedy candidate selection.
3. **$H_3$ (Lookahead Diminishing Returns):** Increasing lookahead depth $k$ yields diminishing marginal travel-time reductions beyond $k=2$, while incurring exponential growth in expansion latency.
4. **$H_4$ (Dynamic Robustness):** When unexpected downstream bottlenecks occur mid-journey, sequential two-edge routing with dynamic rerouting prevents vehicles from driving blindly into severe congestion.

---

## 2. Compared Routing Algorithms ($n = 8$)

All algorithms are evaluated using identical graph topologies, edge lengths, metric units, crawl-speed floors, and ground-truth traffic states:

1. **Static Shortest-Time Dijkstra (`Static Dijkstra`):**
   - Pure Python min-heap Dijkstra solver on static OSM road hierarchy baseline speeds ($15\text{--}50\text{ km/h}$).
   - Represents conventional un-telemetered GPS navigation.
2. **Traffic-Aware Dynamic Dijkstra (`Dynamic Dijkstra (Phase 8)`):**
   - Pure Python min-heap Dijkstra solver using LightGBM next-hour speed forecasts.
   - Evaluated under actual observed speeds with zero data leakage.
3. **A* Shortest-Time Routing (`A* Routing`):**
   - Pure Python A* solver with admissible straight-line travel-time heuristic:
     $$f(n) = g(n) + h(n), \quad h(n) = \frac{d_{\text{haversine}}(n, D)}{v_{\text{max}}}$$
   - Exact mathematical equivalent to Dijkstra in solution quality, with reduced state expansion.
4. **Sequential Greedy Two-Edge (`Sequential Greedy`):**
   - Evaluates two lowest immediate cost candidates at each intersection:
     $$\text{Score}(e) = w_e = \frac{L_e}{v_e / 3.6}$$
5. **Sequential Destination-Aware Two-Edge (`Sequential Destination-Aware`):**
   - Balances immediate travel time with destination heuristic:
     $$\text{Score}(e) = w_e + h(v, D)$$
6. **Sequential Lookahead-2 Two-Edge (`Sequential Lookahead-2`):**
   - Evaluates forward consequences to depth $k=2$ using bounded search.
7. **Existing Dynamic Rerouting Baseline (`Phase 9 Dynamic Rerouting`):**
   - Phase 9 historical replay simulation with dual-threshold gating ($\Delta T \ge 10.0\text{ s} \land \Delta T\% \ge 3.0\%$) triggered at decision waypoint.
8. **Sequential Two-Edge with Dynamic Rerouting (`Sequential + Dynamic Reroute`):**
   - Step-by-step sequential selection with live traffic updates ingested mid-journey and threshold-gated continuation adjustments.

---

## 3. The 8 Formal Experiments

| Exp # | Experiment Title | Tested Configurations / Independent Variables | Primary Evaluated Metrics |
|---|---|---|---|
| **Exp 1** | **Candidate Generation Strategies** | Random, Lowest Immediate Cost, Destination-Aware, Lookahead-2 | Optimality gap vs Dijkstra, trip travel time, distance, recovery events. |
| **Exp 2** | **Decision Strategies** | Greedy, Destination-Aware, Lookahead-2, Adaptive | Travel time, distance, decision hops, recovery frequency, execution latency. |
| **Exp 3** | **Lookahead Depth Scaling** | Depths $k \in \{1, 2, 3, 5\}$ | Travel time vs. per-decision latency trade-off curve, branch expansion counts. |
| **Exp 4** | **Dynamic Traffic Scenarios** | Normal, Moderate Congestion (+30% delay), Severe Congestion (+100% delay), Sudden Bottleneck (+250% collapse) | Congestion delay absorption, detour effectiveness, reroute triggers. |
| **Exp 5** | **Rerouting Threshold Sensitivity** | Absolute $\Delta T \in \{5, 10, 20, 30\}\text{ s}$ $\times$ Relative $\Delta T\% \in \{1, 3, 5, 10\}\%$ | Reroute event frequency, noise suppression, total travel time. |
| **Exp 6** | **Multi-OD Diurnal Journeys** | Canonical OD pairs across Morning Peak, Midday, Evening Peak, Off-Peak | Generalizability across varying corridor lengths (2.5 km to 11.5 km). |
| **Exp 7** | **Network Scalability** | Custom Demo Grid (11 nodes) vs Subgraph (500 nodes) vs Full Bhubaneswar OSM Graph (18,260 nodes) | Graph construction time, query latency, memory consumption. |
| **Exp 8** | **Robustness & Recovery Safeguards** | Dead-ends, cyclic topologies, missing predictions, road closures | Route completion rate, recovery invocations, cycle avoidance. |

---

## 4. Evaluation Metrics Definition

For every trip from source $S$ to destination $D$:
1. **Actual Total Travel Time ($T_{\text{actual}}$):**
   $$T_{\text{actual}} = \sum_{e \in P_{\text{executed}}} \frac{L_e}{v_{\text{observed}}(e) / 3.6} \quad (\text{seconds})$$
2. **Total Distance Travelled ($D_{\text{total}}$):**
   $$D_{\text{total}} = \sum_{e \in P_{\text{executed}}} L_e \quad (\text{meters})$$
3. **Optimality Gap Against Global Dijkstra ($\Delta T_{\text{opt}}$):**
   $$\Delta T_{\text{opt}} = \max(T_{\text{actual}} - T_{\text{Dijkstra}}, 0.0), \quad \Delta T\%_{\text{opt}} = \frac{\Delta T_{\text{opt}}}{T_{\text{Dijkstra}}} \times 100\%$$
4. **Per-Decision Computation Latency ($t_{\text{decision}}$):**
   Wall-clock time in milliseconds to evaluate candidates and select the winning edge at a single intersection.
5. **Total End-to-End Computation Time ($t_{\text{comp}}$):**
   Total time in milliseconds to compute all decisions for the complete journey.
6. **Recovery Events Count ($N_{\text{recovery}}$):**
   Number of emergency loop-breaking or dead-end backtrack recovery invocations.
7. **Reroute Events Count ($N_{\text{reroute}}$):**
   Number of times mid-journey traffic updates triggered a beneficial subpath update.
8. **Route Completion Rate ($R_{\text{complete}}$):**
   Percentage of trips that safely reached destination $D$ without infinite cycling or failure ($100\%$ target).
