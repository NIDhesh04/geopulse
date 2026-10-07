# Phase 8: Implementation Notes & Architectural Decisions

**Project:** GeoPulse — AI-Based Dynamic Traffic Routing System  
**Component:** Phase 8 Custom Dynamic Routing Engine  
**Author:** GeoPulse Engineering Core  
**Timestamp:** 2026-10-07 16:15:00 IST (UTC+05:30)  

---

## 1. Files & Schemas Inspected

1. **Traffic Dataset:** [`datasets/traffic_structured_v1.parquet`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/datasets/traffic_structured_v1.parquet)
   - 246,399 observed hourly rows, 700 traffic segments.
2. **OSM Road Graph:** [`data/raw/osm/bhubaneswar_drive.graphml`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/data/raw/osm/bhubaneswar_drive.graphml)
   - 18,260 nodes, 46,679 directed edges. MultiDiGraph format.
   - Largest Strongly Connected Component (SCC): 18,230 nodes (99.84% of network).
3. **Traffic-to-OSM Mapping:** [`data/processed/traffic_to_osm_mapping_final.parquet`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/data/processed/traffic_to_osm_mapping_final.parquet)
   - 700 segment mappings.
   - `routing_eligibility`: 599 `DYNAMIC`, 92 `DYNAMIC_BIDIRECTIONAL`, 9 `STATIC_FALLBACK`.
   - Node identifiers `u` and `v` are 64-bit integers matching string node IDs in GraphML.
4. **Phase 7 Predictions:** [`results/phase7_predictions.parquet`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7_predictions.parquet)
   - 30,800 test predictions across 44 hourly timestamps from Jan 15 13:30 IST to Jan 17 08:30 IST.
   - Includes `actual_speed`, `predicted_speed`, `persistence_prediction`, `historical_prediction`.
5. **Routing Policy Specification:** [`docs/routing_weight_policy.md`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/docs/routing_weight_policy.md)
   - Travel time formula: $w_e = \frac{\text{length\_m}_e}{v_e / 3.6}$.
   - Raw `currentTravelTime` / `freeFlowTravelTime` strictly prohibited.
   - Speed guardrail: $v_e \ge 3.0\text{ km/h}$.
   - 2-tier hierarchy (Dynamic vs Static Fallback).

---

## 2. Core Routing Assumptions & Protocols

1. **Custom Dijkstra from Scratch:**
   - Standard shortest path libraries (`networkx.shortest_path`, `osmnx` routing) are **strictly bypassed**.
   - Min-heap priority queue (`heapq`) implementation with adjacency caching.
   - Parallel multi-edge relaxation selects minimum traversal cost between adjacent nodes.
2. **Deterministic Twin Sensor Aggregation:**
   - 41 validated twin pairs mapping to identical directed OSM edges receive arithmetic mean speed:
     $$v_e = \frac{v_{s_1} + v_{s_2}}{2}$$
   - Non-validated twin groups (segments [59, 132] and [11, 308]) remain on `STATIC_FALLBACK`.
3. **Bidirectional Two-Way Road Assignment:**
   - 92 `DYNAMIC_BIDIRECTIONAL` segments apply observed/predicted speeds symmetrically to $(u \to v)$ and $(v \to u)$ in the graph.
4. **Three Controlled Routing Scenarios:**
   - **Scenario A (Static Routing):** Fixed speed hierarchy by OSM road classification (50 km/h for trunk to 15 km/h for local).
   - **Scenario B (Current-Traffic Routing):** Oracle benchmark route selected using observed speeds $v(t)$.
   - **Scenario C (ML-Predicted Routing):** Route selected using Phase 7 predicted next-hour speeds $\hat{v}(t+1)$.
5. **No Data Leakage Guarantee:**
   - The ML route is chosen **strictly** using predicted edge weights. Ground-truth observed speeds are accessed only post-hoc to evaluate actual travel time incurred by each selected path.

---

## 3. Discovered Challenges & Mitigations

- **MultiDiGraph Edge Redundancy:** Multiple edges can exist between node $u$ and node $v$ with different keys and lengths.
  - *Mitigation:* The custom Dijkstra dynamically tracks the active key that achieves minimal traversal time, returning the precise sequence of directed edge triples `(u, v, key)`.
- **Reachability Across Network Subgraphs:** Dead-end nodes outside the main road component could cause disconnected path failures.
  - *Mitigation:* All 50 evaluation OD pairs are selected strictly from the 18,230-node Largest Strongly Connected Component (SCC).
- **Graph Performance:** Repeatedly reading GraphML is I/O intensive.
  - *Mitigation:* Graph topology, edge lengths, and static speeds are precomputed once into an indexed adjacency structure.

---

## 4. Final Architectural Decisions

- Module `src/routing/dijkstra.py`: Pure Python Dijkstra pathfinder.
- Module `src/routing/traffic_weights.py`: Deterministic dynamic/static edge weight builder.
- Module `src/routing/route_evaluator.py`: Standardized multi-scenario route evaluation harness.
- Test Suite `tests/test_phase8_routing.py`: Verifies Dijkstra correctness, kinematic weights, rerouting responsiveness, and zero leakage.
