# Phase 2: Hierarchical Network Embedding & Custom Dijkstra Engine

---

## 📌 1. Objective & Research Premise

In **Phase 1**, mathematical analysis proved that the 700 monitored TomTom road segments formed a fragmented forest ($\mu = 0$) across 264 disconnected components, making dynamic rerouting impossible on the standalone segments alone.

**Phase 2** implemented the foundational architectural solution: **Hierarchical Network Embedding Architecture**.
Instead of forcing routing exclusively onto isolated sensor segments, we extracted the **complete drivable OpenStreetMap graph of Bhubaneswar**, extracted its largest strongly connected component (SCC), and embedded the 700 monitored TomTom segments into this city-scale network as dynamic edge-weight providers. We then built a custom Modified Dijkstra routing engine from scratch to navigate this multi-tier road network.

---

## 🏗️ 2. Architectural Blueprint

```text
                        Full Bhubaneswar Drivable OSM Graph (G_city)
                          (18,230 Nodes, 46,630 Directed Edges, mu >> 10,000)
                                            │
               ┌────────────────────────────┴────────────────────────────┐
               ▼                                                         ▼
       700 Monitored Segments                                   45,930 Unmonitored Roads
(Dynamic ML / TomTom Speed Overrides)                     (Class-Based Static Free-Flow Priors)
               │                                                         │
               └────────────────────────────┬────────────────────────────┘
                                            ▼
                           Custom Modified Dijkstra Router
                        Cost = alpha * Length + beta * TravelTime
                   (Dynamically diverts around congested arterial links)
```

---

## ⚙️ 3. Step-by-Step Implementation & Engineering Decisions

### Step 3.1: City-Scale Road Network Extraction
- **Tool / Methodology:** `osmnx.graph_from_place('Bhubaneswar, India', network_type='drive', simplify=True)`.
- **Observation:** The raw drivable network contains peripheral spurs, dead-end cul-de-sacs, and one-way entrance ramps that do not connect back into the urban road grid.
- **Decision:** Extract the **Largest Strongly Connected Component (SCC)**:
  ```python
  scc = max(nx.strongly_connected_components(G), key=len)
  G_scc = G.subgraph(scc).copy()
  ```
- **Rationale:** A strongly connected directed graph guarantees that every node $u$ has at least one valid path to every other node $v$, completely eliminating disconnected destination failures.
- **Topology Result:**
  - Nodes: **$18,230$**
  - Directed edges: **$46,630$**
  - Cyclomatic complexity: $\mu \gg 10,000$ (thousands of alternative loops and parallel corridors).

### Step 3.2: Metric Coordinate Projection (EPSG:32645 UTM Zone 45N)
- **Observation:** Geographic coordinates (WGS84 lat/lon degrees) cause Euclidean distortion when calculating edge lengths and physical distances in meters across Bhubaneswar.
- **Decision:** Project the entire graph to **EPSG:32645 (UTM Zone 45N)** using `pyproj`:
  ```python
  G_proj = ox.project_graph(G_scc, to_crs="EPSG:32645")
  ```
- **Outcome:** Every node and edge possesses metric $(x, y)$ coordinates in meters, enabling exact physical velocity and travel-time calculations.

### Step 3.3: Two-Pass Hierarchical Segment Embedding Algorithm
Mapping 700 arbitrary TomTom corridor coordinates to distinct edges in a 46,630-edge multigraph required a collision-free assignment algorithm:

1. **Pass 1 — Direct Endpoint Matching:**
   - Evaluated the $(u, v)$ endpoint IDs identified in Phase 1 (`segment_endpoints.csv`).
   - If an edge $(u, v)$ existed in $G_{\text{proj}}$, it was assigned to `segment_id`. If only the reverse edge $(v, u)$ existed, the reverse orientation was assigned.
   - **Pass 1 Result:** 688 of 700 segments matched directly.

2. **Pass 2 — Spatial Nearest-Edge Snapping with Successor Exploration:**
   - For the remaining 12 segments where topological simplification consolidated micro-nodes, projected segment centroids $(x_{\text{proj}}, y_{\text{proj}})$ were snapped to the nearest edge using `ox.nearest_edges`.
   - In case of edge collision with an already-assigned segment, explored immediate topological successors:
     ```python
     for succ in G_proj.successors(nbr):
         # assign to adjacent unassigned multi-edge key
     ```
- **Verification Assertion:**
  ```python
  assert len(assigned_edges) == 700
  assert len(used_edges) == 700  # 100% unique edge assignment
  ```
  **All 700 monitored segments mapped to unique physical edges in $G_{\text{proj}}$ with zero duplicate collisions.**

### Step 3.4: Multi-Tier Attribute Annotation & Velocity Priors
Every edge in the multigraph was tagged with uniform attributes:

1. **Monitored Edges ($N = 700$):**
   - `is_monitored = True`
   - `segment_id = sid` (0 to 699)
   - `free_flow_speed`: Extracted from metadata (median: $34.0\text{ km/h}$)
   - `free_flow_time`: $\frac{\text{length}}{v_{\text{ff}} / 3.6}\text{ seconds}$
   - Dynamic weight provider hook: At runtime, speeds update dynamically from real-time feeds or ML predictions.

2. **Unmonitored Roads ($N = 45,930$):**
   - `is_monitored = False`
   - `segment_id = -1`
   - Class-based physical free-flow speed hierarchy:
     | OSM Highway Classification | Assigned Free-Flow Speed ($v_0$) |
     |---|---|
     | `motorway` | $60.0\text{ km/h}$ |
     | `trunk` | $55.0\text{ km/h}$ |
     | `primary` | $50.0\text{ km/h}$ |
     | `secondary` | $40.0\text{ km/h}$ |
     | `tertiary` | $35.0\text{ km/h}$ |
     | `residential` / `unclassified` | $30.0\text{ km/h}$ |
     | `living_street` / `service` | $20.0\text{ km/h}$ |
     | `*_link` (connectors/ramps) | $25.0\text{ to } 45.0\text{ km/h}$ |

3. **Strict Minimum Speed Floor:**
   - Enforced $v \ge 1.0\text{ km/h}$ across all edges.
   - **Why:** Prevents division-by-zero or infinite traversal costs during complete standstill traffic jams.

### Step 3.5: GraphML Serialization Sanitation
- **Observation:** NetworkX `write_graphml` crashes when edge/node dictionaries contain complex Python types (e.g., Shapely geometries, lists of OSM IDs, or tuple objects).
- **Decision:** Implemented explicit attribute sanitization:
  - Removed raw `geometry` objects (retained metric node coordinates `x, y`).
  - Serialized all compound attributes into primitive strings, integers, or floats.
- **Output:** Serialized to `data/interim/G_embedded.graphml` (**$24.35\text{ MB}$**).

---

## 🚀 4. Custom Modified Dijkstra Routing Engine (`src/routing/custom_dijkstra.py`)

Rather than relying on black-box routing libraries, we implemented the routing engine from scratch using a min-heap priority queue (`heapq`).

### 4.1 Cost Formulation
The router optimizes a tunable multi-objective cost function:
$$\boxed{\text{Cost}(u, v) = \alpha \cdot \text{Length}(u, v) + \beta \cdot \text{TravelTime}(u, v)}$$
- **$\alpha = 0, \beta = 1$**: Pure Travel-Time Minimization (Fastest Route).
- **$\alpha = 1, \beta = 0$**: Pure Distance Minimization (Shortest Physical Route).
- **$\alpha = 1, \beta = 1$**: Balanced Cost Function.

### 4.2 Dynamic Traversal Time Calculation
When exploring edge $(u, v)$ with length $L$:
$$\text{TravelTime}(u, v) = \begin{cases}
\frac{L}{v_{\text{dynamic}}(sid) / 3.6} & \text{if } \text{is\_monitored} = \text{True and } sid \in \text{speeds} \\
\frac{L}{v_{\text{free\_flow}} / 3.6} & \text{otherwise}
\end{cases}$$

### 4.3 Multigraph Support
Because real-world road networks contain multi-edges between intersections (e.g., separate directional carriageways or express lanes), the engine iterates across all parallel edge keys:
```python
best_edge_cost = min(alpha * d["length"] + beta * travel_time for key, d in G[u][v].items())
```

---

## 🧪 5. Automated Validation & Rerouting Proof (`tests/test_phase2.py`)

We developed a 3-stage validation suite to verify the architecture:

### Test A: Graph Validation
- Asserts that `G_embedded.graphml` exists on disk.
- Confirms directed edge count exceeds 10,000 (**$46,630\text{ edges}$**).
- Verifies strong connectivity: `nx.is_strongly_connected(G) == True` (**$100\%$ reachability across all $18,230\text{ nodes}$**).
- Verifies exact sensor count: exactly **700 edges** have `is_monitored=True`.
- **Status: PASSED**

### Test B: Custom Dijkstra Baseline
- Evaluated end-to-end traversal across Bhubaneswar from Node `293452459` to Node `4613766153`.
- Router identified the optimal path sequence with positive, non-infinite cost in **$42\text{ ms}$**.
- **Status: PASSED**

### Test C: Dynamic Rerouting Trigger Under Congestion
- **Experiment:**
  1. Identified a monitored segment along the baseline path (e.g., arterial segment traversing an urban corridor).
  2. Injected a simulated severe congestion jam on that segment:
     $$\text{Speed} = 5.0\text{ km/h}$$
  3. Re-queried the Custom Dijkstra engine with the dynamic speed override.
- **Result:**
  - **Path Divergence:** The router immediately altered its trajectory:
    $$\text{Baseline Path} \neq \text{Rerouted Path}$$
  - **Congestion Avoidance:** The congested arterial segment was completely avoided; the router diverted the vehicle onto a parallel secondary OSM corridor.
- **Status: PASSED**

---

## 📊 6. Summary of Key Decisions & Observations in Phase 2

| Step / Component | Observation / Challenge | Decision & Engineering Action |
|---|---|---|
| **Road Network Scope** | Standalone segments had $\mu = 0$ and 264 components. | Extracted full Bhubaneswar OSM network ($18,230$ nodes, $46,630$ edges). |
| **Graph Reachability** | Raw OSM network has dead-end spurs and unidirectional cul-de-sacs. | Extracted Largest Strongly Connected Component (SCC) to guarantee 100% reachability. |
| **Distance Precision** | Lat/Lon degree coordinates cause distance distortion. | Projected entire network to metric UTM Zone 45N (EPSG:32645). |
| **Segment Collision** | Multiple segments share nearby nodes or corridors. | Built two-pass matching (endpoint mapping + spatial snapping) ensuring 700 unique edges. |
| **Unmonitored Edges** | 45,930 edges had no traffic sensor data. | Assigned class-based speed priors derived from physical highway classifications. |
| **Zero-Speed Hazard** | Jams ($0\text{ km/h}$) cause division-by-zero ($T_e \to \infty$). | Enforced universal minimum velocity floor $v_{\min} = 1.0\text{ km/h}$. |
| **GraphML Export** | Complex Python objects broke GraphML XML schema. | Stripped non-primitive attributes and sanitized metadata. |
| **Routing Flexibility** | Standard shortest path algorithms only consider distance. | Built custom Dijkstra with multi-objective $(\alpha \cdot D + \beta \cdot T)$ cost function. |
| **Dynamic Verification** | Rerouting feasibility needed empirical proof. | Injected $5.0\text{ km/h}$ jam; verified automated path diversion in automated test suite. |

---

## 📂 7. Phase 2 Deliverables & File Locations

- **Embedded Graph Builder:** [`src/graph/build_embedded_graph.py`](file:///c:/users/nidhe/Projects/geopulse_bhu/src/graph/build_embedded_graph.py)
- **Custom Dijkstra Router:** [`src/routing/custom_dijkstra.py`](file:///c:/users/nidhe/Projects/geopulse_bhu/src/routing/custom_dijkstra.py)
- **Serialized Embedded Graph:** `data/interim/G_embedded.graphml` (24.35 MB)
- **Automated Validation Suite:** [`tests/test_phase2.py`](file:///c:/users/nidhe/Projects/geopulse_bhu/tests/test_phase2.py)
