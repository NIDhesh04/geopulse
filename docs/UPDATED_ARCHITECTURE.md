# GeoPulse: Updated System Architecture
## ML-Based Traffic Prediction with Sequential Two-Edge Selection and Dynamic Rerouting

**Document:** `docs/UPDATED_ARCHITECTURE.md`  
**System:** GeoPulse Major Project  
**Author:** GeoPulse Architecture & Core Engineering  
**Version:** 2.0 (Sequential Routing & Pygame Extension)  
**Status:** Approved for Implementation  

---

## 1. System Overview & Core Philosophy

The updated GeoPulse architecture preserves the complete existing software foundation (OSM road network, LightGBM speed forecasting, kinematic edge travel times, custom min-heap Dijkstra, and dual-threshold rerouting) while introducing a **sequential decision-making routing paradigm**.

In conventional routing (e.g. global Dijkstra or A*), a centralized algorithm solves an entire end-to-end path in advance. Under the **Sequential Two-Edge Decision Paradigm**, the vehicle acts as an active agent navigating step-by-step through the network:
1. At each intersection node, the vehicle identifies two candidate outgoing edges.
2. The vehicle evaluates both candidates using travel-time costs, traffic predictions, and destination estimates.
3. The preferred edge is selected, and the vehicle advances to the next node.
4. When downstream traffic conditions evolve, the vehicle triggers dynamic rerouting to evaluate continuation subpaths.
5. Cycle prevention, dead-end recovery, and heuristic lookahead ensure safe and robust arrival at the destination.

---

## 2. Integrated System Architecture

The following diagram illustrates how the existing GeoPulse components integrate with the new sequential routing and visual simulation modules:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          CLOUD TIER (PRESERVED)                             │
│  src/cloud/model_service.py                                                 │
│  • LightGBM Regressor (models/speed_predictor.joblib, 25 features)          │
│  • Hourly traffic speed forecasts for 700 monitored corridors               │
│  • MODEL_UPDATE broadcast generator                                         │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ ModelUpdateMessage
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       EDGE SERVER TIER (EXTENDED)                           │
│  src/edge/edge_server.py & src/routing/traffic_weights.py                   │
│  • GraphWeightManager: OSM topology + Dynamic edge weights                  │
│  • Edge travel time: w_e = L_e / (v_e / 3.6), speed floor >= 3.0 km/h        │
│  • Global Dijkstra Reference & Heuristic Cache (src/routing/dijkstra.py)    │
│  • Real-time sensor stream ingest & degradation detection                   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Traffic & Initial Route Directives
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                   NEW SEQUENTIAL ROUTING ENGINE LAYER                       │
│  src/routing/                                                               │
│                                                                             │
│  ┌────────────────────────┐         ┌────────────────────────────────────┐  │
│  │  Candidate Generator   │ ──────▶ │       Two-Edge Selector            │  │
│  │ candidate_generator.py │         │       two_edge_selector.py         │  │
│  │ • Out-degree analysis  │         │ • Edge cost evaluation             │  │
│  │ • Reversal pruning     │         │ • Decision scoring & comparison    │  │
│  │ • Candidate strategies │         │ • Winner selection (A vs B)        │  │
│  └────────────────────────┘         └─────────────────┬──────────────────┘  │
│                                                       │                     │
│  ┌────────────────────────┐                           ▼                     │
│  │  Decision Strategies   │ ◀─────────────────────────┘                     │
│  │ decision_strategies.py │                                                 │
│  │ • Greedy Selection     │                                                 │
│  │ • Destination-Aware    │                                                 │
│  │ • Lookahead (1,2,3,5)  │                                                 │
│  │ • Adaptive Selection   │                                                 │
│  └────────────────────────┘                                                 │
│               │                                                             │
│               ▼                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                         Route Controller                              │  │
│  │                       route_controller.py                             │  │
│  │ • Step-by-step intersection progression                               │  │
│  │ • Route safety: cycle detection, loop prevention, max-hop limit       │  │
│  │ • Dead-end recovery (Dijkstra fallback)                               │  │
│  │ • Dynamic rerouting integration (dual-threshold policy)               │  │
│  │ • Metrics recording (latency, hop count, time, distance, regret)      │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                      ┌────────────────┴────────────────┐
                      ▼                                 ▼
┌───────────────────────────────────────┐ ┌───────────────────────────────────┐
│       PYGAME VISUAL SIMULATION        │ │      EXPERIMENTAL BENCHMARK       │
│  src/pygame_simulation/               │ │  src/experiments/                │
│  • renderer.py: Canvas & road network │ │  • Experiments 1 to 8             │
│  • vehicle_sprite.py: Kinematic car   │ │  • Baseline comparisons:          │
│  • ui_components.py: Candidate HUD    │ │    - Static Dijkstra              │
│  • simulation_controller.py: Controls │ │    - Dynamic Dijkstra             │
│  • Custom graph & OSM graph support   │ │    - A* Shortest Path             │
│                                       │ │    - Sequential Two-Edge          │
│                                       │ │    - Sequential + Dynamic Reroute │
└───────────────────────────────────────┘ └───────────────────────────────────┘
```

---

## 3. End-to-End Operational Lifecycle (18-Stage Flow)

1. **Load Road Network:** Load the Bhubaneswar OSM `MultiDiGraph` (18,260 nodes, 46,679 edges) and spatial mapping table via `GraphWeightManager`.
2. **Load ML Model:** Centralized `CloudModelService` loads serialized 25-feature LightGBM model and feature metadata.
3. **Predict Traffic Speeds:** Cloud generates next-hour speed forecasts $\hat{v}_e(t+1)$ across all monitored road segments.
4. **Synthesize Edge Travel Times:** Convert predicted speeds into edge travel-time weights:
   $$w_e = \frac{L_e}{v_e / 3.6}, \quad v_e = \max(v_e, 3.0\text{ km/h})$$
5. **Select Origin and Destination:** Specify origin node $S$ and destination node $D$.
6. **Generate Initial Reference Route:** Compute the initial predicted reference route $R_0$ using custom min-heap Dijkstra.
7. **Initialize Vehicle Simulation:** Place the vehicle at origin node $S$, initializing journey timer, distance counter, and visited node set.
8. **Generate Candidate Outgoing Edges:** At current intersection node $u$:
   - If out-degree $= 0$: trigger dead-end recovery.
   - If out-degree $= 1$: forced continuation on the single valid edge.
   - If out-degree $\ge 2$: identify eligible edges (excluding immediate reversal to previous node unless no other path exists) and select exactly **two candidate edges**: Candidate A and Candidate B.
9. **Evaluate Candidate Edges:** Evaluate Candidates A and B using the configured decision strategy (e.g. immediate cost, destination distance heuristic, or multi-step lookahead).
10. **Select Preferred Edge:** Compute decision score and pick the winning edge $e^* = (u, v^*, k^*)$.
11. **Move Vehicle:** Advance vehicle along selected edge $e^*$, accumulating actual travel time and distance.
12. **Update Position & History:** Record node $v^*$ into visited history and cycle detection structures.
13. **Detect Updated Traffic Conditions:** Ingest incoming real-time sensor updates $v_{\text{obs}}(t)$ representing emerging congestion bottlenecks.
14. **Recalculate Continuation Costs:** Check remaining travel-time cost under updated traffic.
15. **Evaluate Dynamic Rerouting:** Compare current path vs alternative continuation. If travel-time saving satisfies dual threshold ($\Delta T \ge 10.0\text{ s} \land \Delta T\% \ge 3.0\%$), flag reroute benefit.
16. **Apply Continuation Detour:** If beneficial, update destination guidance or target path from current node $v^*$.
17. **Iterate Until Destination:** Repeat steps 8–16 until destination $D$ is reached or target condition met.
18. **Record & Evaluate Journey:** Export complete trajectory, step-by-step candidate logs, execution latencies, and optimality gap metrics.

---

## 4. Component Design: Candidate Generator (`src/routing/candidate_generator.py`)

### 4.1 Eligibility Criteria
Given current node $u$, previous node $p$, and destination $D$:
- **Valid Outgoing Edges:** All directed edges $(u, v, k) \in E(G)$ originating at $u$.
- **Reversal Suppression:** If an outgoing edge leads back to $p$ (i.e. $v == p$), it is filtered out unless it is the only physical exit from $u$ (cul-de-sac).
- **Visited Cycle Penalty:** Edges leading to nodes already visited in the current journey receive a loop penalty or are ranked below unvisited candidates.

### 4.2 Candidate Selection Policies (when out-degree $> 2$)
To produce exactly two candidates $\{e_A, e_B\}$ from $m > 2$ eligible edges:
- **Strategy A (Random):** Uniformly sample two distinct edges at random.
- **Strategy B (Lowest Immediate Cost):** Sort eligible edges by immediate traversal travel time $w_e$; pick the two lowest-cost edges.
- **Strategy C (Destination-Aware):** Sort eligible edges by $w_e + h(v, D)$ where $h(v, D)$ is the estimated remaining travel time to $D$ (Euclidean distance divided by maximum network speed, or Dijkstra static heuristic); pick top two.
- **Strategy D (Lookahead-Based):** Evaluate consequences of each branch to depth $k$; pick top two branches with lowest cumulative lookahead cost.

### 4.3 Corner Cases
- **Out-degree $= 1$:** Return single edge as forced continuation. Selector bypasses comparison and selects this edge directly without fabricating a dummy edge.
- **Out-degree $= 0$ (Dead-end):** Return empty candidate list, triggering `RouteController` recovery fallback.

---

## 5. Component Design: Decision Strategies (`src/routing/decision_strategies.py`)

All decision strategies implement a uniform abstract base class:

```python
class BaseDecisionStrategy(ABC):
    @abstractmethod
    def evaluate_candidates(
        self,
        candidate_a: CandidateEdge,
        candidate_b: CandidateEdge,
        current_node: str,
        destination: str,
        context: RoutingContext
    ) -> DecisionResult:
        pass
```

### Strategy 1: Greedy Selection
Evaluates only the immediate edge traversal cost:
$$\text{Score}(e) = w_e = \frac{L_e}{v_e / 3.6}$$
Select candidate with $\min(\text{Score}(e_A), \text{Score}(e_B))$.

### Strategy 2: Destination-Aware Selection
Evaluates immediate edge cost combined with an admissible remaining-distance heuristic to the destination:
$$\text{Score}(e) = w_e + \alpha \cdot \frac{d_{\text{haversine}}(v, D)}{v_{\text{freeflow}}}$$
where $\alpha \ge 1.0$ controls destination attraction.

### Strategy 3: Limited-Lookahead Selection
Performs a $k$-depth tree search ($k \in \{1, 2, 3, 5\}$) evaluating the best possible subpath originating from candidate $e_A$ vs candidate $e_B$:
$$\text{Score}(e) = w_e + \min_{P \in \text{Paths}(v, \text{depth}=k-1)} \left( \sum_{e' \in P} w_{e'} + h(\text{end}(P), D) \right)$$

### Strategy 4: Adaptive Selection
Dynamically switches strategies based on local graph topology and traffic state:
- When remaining distance is large and road is arterial: uses Destination-Aware.
- When local congestion index on candidate edges exceeds threshold: switches to Lookahead ($k=3$) to navigate complex urban detours.

---

## 6. Route Safety, Cycle Prevention & Failure Handling

Sequential local routing in directed graphs can suffer from:
1. **Cycles ($A \to B \to A$):** Handled via:
   - Visited node set $V_{\text{visited}}$.
   - Immediate parent exclusion.
   - Cycle detection: if a node has been visited more than $M_{\text{max\_visits}}$ times (default 2), penalize candidate heavily.
2. **Dead-ends:** If candidate generator returns 0 candidates:
   - Trigger **Recovery Subpath Solver**: compute custom Dijkstra from current node $u$ to destination $D$. If graph is disconnected from $u$, backtrack to last intersection with unvisited branches.
3. **Maximum Hop Threshold:** If hop count exceeds $3 \times \text{hops}(R_0)$, invoke recovery solver to prevent infinite oscillation.
4. **Missing Predictions Fallback:** If an edge has no dynamic sensor mapping or prediction, fall back strictly to OSM road hierarchy static speed limit (as defined in [`docs/routing_weight_policy.md`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/docs/routing_weight_policy.md)).

---

## 7. Dynamic Rerouting Integration

The existing dual-threshold rerouting engine is integrated seamlessly into the sequential loop:
- When real-time traffic updates arrive at timestamp $t_1$, updated speeds are ingested into `GraphWeightManager`.
- The vehicle's active position (current node $u$) is preserved.
- The remaining expected travel time on the current route plan is compared against a newly computed optimal continuation.
- If savings exceed the dual threshold:
  $$\Delta T \ge 10.0\text{ s} \quad \text{AND} \quad \Delta T\% \ge 3.0\%$$
  a reroute directive is issued, updating the vehicle's target corridor while sequential two-edge selection continues uninterrupted from the vehicle's exact current location.

---

## 8. Pygame Visual Simulation Architecture (`src/pygame_simulation/`)

The visual simulation is engineered as a decoupled frontend:

```
src/pygame_simulation/
├── __init__.py
├── main.py                  # Entrypoint with CLI arguments (--network, --strategy, --fps)
├── simulation_controller.py # Simulation loop, step execution, time pacing, state machine
├── renderer.py              # Pygame canvas manager, coordinate transforms, anti-aliasing
├── road_renderer.py         # Road segment drawing, traffic heat colors, intersection nodes
├── vehicle_sprite.py        # Smooth kinematic interpolation, car icon, heading rotation
├── ui_components.py         # Side panel HUD: Candidate A/B speeds, costs, scores, journey stats
└── scenario_manager.py      # Scenario loader (custom toy graph & Bhubaneswar OSM network)
```

### Visual Behaviors at Intersections:
- **Decision Pause / Slowdown:** Vehicle pauses briefly at intersection nodes to visually highlight Candidates A and B in distinct colors (e.g. Cyan and Amber).
- **HUD Telemetry:** Candidate cards display road name, length, predicted speed, travel time, and decision score.
- **Selected Edge Animation:** Winning edge flashes Green, and the vehicle animates smoothly along the link.
- **Traffic Congestion Overlay:** Road links change color dynamically from green ($>35\text{ km/h}$) to yellow ($20–35\text{ km/h}$) to red ($<20\text{ km/h}$).

---

## 9. Experimental Benchmark Suite (`src/experiments/`)

The framework compares 8 algorithms across 8 formal experiments:

### Evaluated Algorithms:
1. Static Shortest-Time Dijkstra
2. Traffic-Aware Dynamic Dijkstra (Existing GeoPulse Phase 8)
3. A* Shortest-Time Routing (with admissible Euclidean / Haversine heuristic)
4. Sequential Greedy Two-Edge Selection
5. Sequential Destination-Aware Two-Edge Selection
6. Sequential Limited-Lookahead Two-Edge Selection (Depths 1, 2, 3, 5)
7. Existing Dynamic Rerouting Baseline (Phase 9)
8. Sequential Two-Edge Selection with Dynamic Rerouting

### Formal Experiments:
- **Exp 1 (Candidate Generation):** Random vs Lowest Immediate Cost vs Destination-Aware vs Lookahead candidates.
- **Exp 2 (Decision Strategy):** Greedy vs Destination-Aware vs Lookahead vs Adaptive.
- **Exp 3 (Lookahead Depth):** Depths $k \in \{1, 2, 3, 5\}$: travel time vs per-decision latency trade-off.
- **Exp 4 (Dynamic Traffic Scenarios):** Normal, Moderate, Severe congestion, and Sudden Bottleneck.
- **Exp 5 (Threshold Sensitivity):** Dual thresholds $\Delta T \in \{5, 10, 20, 30\}\text{ s}$, $\Delta T\% \in \{1, 3, 5, 10\}\%$.
- **Exp 6 (Diurnal & Multi-OD Journeys):** 20 canonical OD journeys across Morning, Midday, Evening, and Off-Peak.
- **Exp 7 (Network Scalability):** Toy graph ($10$ nodes) vs Sub-network ($500$ nodes) vs Full Bhubaneswar OSM network ($18,260$ nodes).
- **Exp 8 (Robustness & Safety):** Dead-ends, cyclic topologies, missing predictions, road closures, and recovery rate.
