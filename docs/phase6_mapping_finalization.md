# Phase 6: Final Traffic-to-OSM Mapping Validation & Routing Finalization

**Project:** GeoPulse — AI-Based Dynamic Traffic Routing System  
**Phase:** 6 — Mapping Finalization & Routing Policy  
**Status:** `PHASE 6 COMPLETE`  
**Execution Timestamp:** 2026-10-07 15:37:00 IST (UTC+05:30)  

---

## 1. What Was Validated
A targeted audit of the 109 risky segments identified in Phase 5:
- 99 MEDIUM-confidence mappings (assessing direction ambiguity and competing candidates).
- 8 LOW-confidence mappings (evaluating length mismatch and spatial distortion).
- 92 direction-ambiguous segments on two-way undivided roads.
- 43 repeated directed-edge assignments (analyzing Jan 4–17 time series correlation, MAE, and distribution similarity across 86 segments).

---

## 2. Final Counts by Mapping Status

| `mapping_status` | Description | Count | Percentage |
|---|---|---:|---:|
| **MAPPED** | High/medium certainty mapping to directed OSM edge | **599** | 85.57% |
| **AMBIGUOUS** | Valid physical alignment, but bidirectional or candidate margin small | **100** | 14.29% |
| **UNRESOLVED** | Severe physical mismatch; candidate unrepresentative | **1** | 0.14% |
| **Total** | | **700** | **100.0%** |

*Note: Segment 308 is classified as UNRESOLVED due to a >1,400 m length discrepancy.*

---

## 3. Final Counts by Confidence

| `confidence` | Criteria Summary | Count | Percentage |
|---|---|---:|---:|
| **HIGH** | Exact length match, distance $\le 50\text{ m}$, margin $\ge 0.08$, clear direction | **593** | 84.71% |
| **MEDIUM** | Solid physical match, but bidirectional street or moderate margin | **99** | 14.14% |
| **LOW** | Plausible candidate, but elevated length error or distance $> 85\text{ m}$ | **8** | 1.14% |
| **Total** | | **700** | **100.0%** |

---

## 4. Final Counts by Routing Eligibility

| `routing_eligibility` | Dynamic Routing Action | Count | Percentage |
|---|---|---:|---:|
| **DYNAMIC** | Unambiguous one-way or dominant edge; receives predicted speed $\hat{v}(t+1)$ | **599** | 85.57% |
| **DYNAMIC_BIDIRECTIONAL** | Two-way street; observed/predicted speed applied symmetrically to both $(u \to v)$ and $(v \to u)$ | **92** | 13.14% |
| **STATIC_FALLBACK** | Mapping uncertainty exceeds threshold; edge uses OSM speed hierarchy baseline | **9** | 1.29% |
| **Total** | | **700** | **100.0%** |

---

## 5. Number of Risky Cases Accepted / Rejected
Out of 109 risky segments evaluated:
- **Accepted as DYNAMIC:** **8 segments** (6 medium oneway segments + 2 resolved junction segments).
- **Accepted as DYNAMIC_BIDIRECTIONAL:** **92 segments** (two-way roads with exact length match and sub-meter distance).
- **Rejected to STATIC_FALLBACK:** **9 segments** (8 low-confidence segments: 13, 59, 132, 154, 308, 427, 493, 696, plus conflicting segment 11).

---

## 6. Duplicate-Edge Validation Result
For the 43 directed OSM edges mapped to twin sensor IDs:
- **41 Duplicate Groups (82 segments):** **Validated as genuine twin sensors** (mean time-series correlation: **0.9703**, median correlation: **0.9999**, median MAE: **0.0031 km/h**; 39 pairs have $>95\%$ identical readings). Both sensors are dynamic-eligible, and their predicted speeds are averaged during edge cost assignment.
- **2 Duplicate Groups (4 segments: [59, 132] and [11, 308]):** **Rejected as non-duplicates** (represent unequal sub-slices or disparate junction branches). All 4 segments cleanly fall back to `STATIC_FALLBACK`.

---

## 7. Direction Policy
1. One-way carriageways (`oneway = True`) receive `DYNAMIC`.
2. Two-way streets (`oneway = False`) where sensor measures general corridor flow receive `DYNAMIC_BIDIRECTIONAL`, applying the dynamic speed symmetrically to both directed edges in Dijkstra's graph.
3. Segments with conflicting orientation or excessive spatial error revert to `STATIC_FALLBACK`.

---

## 8. Final Routing-Weight Policy
Travel time for edge $e = (u, v, k)$ is computed strictly as:
$$w_e = \frac{\text{length\_m}_e}{v_e / 3.6}$$
- For the 657 dynamic edges: $v_e = \hat{v}_e(t+1)$ from the ML model.
- For all 46,022 unmonitored OSM edges: $v_e = v_{0, \text{highway}}$ (OSM speed baseline).
- Minimum crawl speed guardrail: $v_e \ge 3.0\text{ km/h}$.
- Stored `currentTravelTime` and `freeFlowTravelTime` columns are permanently banned from routing calculations.

---

## 9. Remaining Known Limitations
1. **Network Fragmentation:** Mapped edges form 221 disconnected arterial fragments; routing must execute on the full 46,679-edge OSM network.
2. **Two-Way Symmetric Assumption:** 92 bidirectional segments assume symmetric speeds in opposite directions, reflecting prevailing congestion on undivided roads.
3. **Short Temporal Window:** Traffic predictions cover an 13.4-day continuous baseline, suitable for prototype proof-of-concept.

---

## 10. Exact Files Produced
- Final Parquet Mapping: [`data/processed/traffic_to_osm_mapping_final.parquet`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/data/processed/traffic_to_osm_mapping_final.parquet)
- Final CSV Mapping: [`data/processed/traffic_to_osm_mapping_final.csv`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/data/processed/traffic_to_osm_mapping_final.csv)
- Routing Weight Policy Document: [`docs/routing_weight_policy.md`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/docs/routing_weight_policy.md)
- Phase 6 Report: [`docs/phase6_mapping_finalization.md`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/docs/phase6_mapping_finalization.md)
