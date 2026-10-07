# GeoPulse: Dynamic & Fallback Edge Weight Routing Policy

**Document Status:** FINAL ROUTING POLICY  
**Author:** GeoPulse Engineering Core  
**Applicability:** Offline Evaluation, Historical Replay, & Real-Time Dijkstra Engine  

---

## 1. Physical Principle & Edge Cost Formulation

The core routing cost for every directed edge $e = (u, v, k)$ in the road network graph $G = (V, E)$ is the **traversal travel time in seconds** ($w_e$):

$$w_e = \frac{\text{length\_m}_e}{v_e / 3.6}$$

where:
- $\text{length\_m}_e$ is the physical metric length of the edge derived from OpenStreetMap geometry.
- $v_e$ is the traversal speed in **km/h**.
- The factor $3.6$ converts speed from $\text{km/h}$ to $\text{m/s}$.

> [!CAUTION]
> **Strict Prohibition on Raw Travel-Time Columns:**  
> The columns `currentTravelTime` and `freeFlowTravelTime` from the TomTom data feed must **never** be used as edge routing costs. The Phase 1 audit demonstrated that these fields fail physical kinematics by massive margins (MAE > 1,400 seconds, relative error > 9,000%, and negative correlation against $d/v$). All edge costs must be computed deterministically via kinematics.

---

## 2. Dynamic vs. Static Fallback Routing Hierarchy

The GeoPulse routing engine operates over the **entire 46,679-edge Bhubaneswar road graph** (`data/raw/osm/bhubaneswar_drive.graphml`) using a 2-tier edge hierarchy:

```
┌────────────────────────────────────────────────────────┐
│             OSM Directed Edge e = (u, v, k)            │
└──────────────────────────┬─────────────────────────────┘
                           │
             Is edge mapped to an eligible
               dynamic traffic segment?
                           │
             ┌─────────────┴─────────────┐
            YES                          NO
             │                           │
  ┌───────────────────────┐   ┌───────────────────────┐
  │     DYNAMIC TIER      │   │  STATIC FALLBACK TIER │
  │   (657 unique edges)  │   │ (46,022 unmonitored)  │
  ├───────────────────────┤   ├───────────────────────┤
  │ Speed derived from    │   │ Speed derived from    │
  │ ML prediction model   │   │ OSM road hierarchy    │
  │ v_pred(t+1) or replay │   │ baseline free-flow v0 │
  └───────────────────────┘   └───────────────────────┘
```

### Tier 1 — Dynamic Traffic Edges ($n = 657$ Unique Edges)
Edges assigned `routing_eligibility = 'DYNAMIC'` or `'DYNAMIC_BIDIRECTIONAL'` in [`data/processed/traffic_to_osm_mapping_final.parquet`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/data/processed/traffic_to_osm_mapping_final.parquet):
- **Predictive Mode:** Traversal speed $v_e(t+1)$ is supplied by the next-hour machine learning model:
  $$w_e(t+1) = \frac{\text{length\_m}_e}{\hat{v}_e(t+1) / 3.6}$$
- **Replay / Live Mode:** Observed traffic speed $v_e(t)$ from sensor streams.
- **Dynamic Bidirectional Policy:** For the 92 two-way street segments (`DYNAMIC_BIDIRECTIONAL`), the prevailing sensor speed is applied symmetrically to both $(u \to v)$ and $(v \to u)$ in the graph.
- **Repeated Edge Aggregation:** For the 41 validated twin-sensor pairs, the effective dynamic speed is the arithmetic mean of both sensor predictions:
  $$\hat{v}_e(t+1) = \frac{\hat{v}_{s_1}(t+1) + \hat{v}_{s_2}(t+1)}{2}$$

### Tier 2 — Static Fallback Edges ($n = 46,022$ Edges)
Edges not monitored by dynamic sensors or segments assigned `routing_eligibility = 'STATIC_FALLBACK'`:
- Traversal speed defaults to the OSM road hierarchy baseline:

| OSM Highway Classification | Default Baseline Speed ($v_0$) |
|---|---:|
| `motorway` / `trunk` / `trunk_link` | $50.0\text{ km/h}$ |
| `primary` / `primary_link` | $40.0\text{ km/h}$ |
| `secondary` / `secondary_link` | $30.0\text{ km/h}$ |
| `tertiary` / `tertiary_link` | $25.0\text{ km/h}$ |
| `residential` / `living_street` / `unclassified` | $20.0\text{ km/h}$ |
| All other drivable ways | $15.0\text{ km/h}$ |

---

## 3. Dijkstra Cost Guardrails

To preserve scientific correctness and algorithmic stability during pathfinding:
1. **Speed Bounding:** Speeds must be strictly positive:
   $$v_e = \max(v_e, 3.0\text{ km/h})$$
   A minimum crawl speed of $3\text{ km/h}$ prevents zero-division and infinite costs during gridlock simulation.
2. **Deterministic Fallback:** If any dynamic prediction fails at runtime (e.g. missing input features), the routing engine automatically reverts to the Tier 2 static baseline without throwing an unhandled exception.
3. **Additive Graph Weights:** In Dijkstra's algorithm, path cost is the sum of edge traversal times:
   $$T(\pi) = \sum_{e \in \pi} w_e$$
   ensuring that routes minimize total expected trip time across the city.
