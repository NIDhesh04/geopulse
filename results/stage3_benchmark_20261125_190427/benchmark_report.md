# GeoPulse Stage 3 — Large-Scale Temporal Benchmark Report

- **Experiment ID:** `stage3_benchmark_20261125_190427`
- **Execution Timestamp (UTC):** `2026-11-25T19:04:27.680568+00:00`
- **Git Commit:** `038df6d74f5123c1dace6deb8bf2b750db3d3c82`
- **Random Seed:** `42`
- **Reproduction Command:** `python scripts/run_stage3_benchmark.py --max-pairs 50 --max-departures 5 --seed 42`

## 1. Executive Summary

This benchmark evaluates **Static Dijkstra**, **Dynamic Dijkstra**, and **GeoPulse (Sequential Two-Edge Selection)** across **50 OD pairs** × **5 departure timestamps** = **250 paired scenarios** (**750 journey executions**) on the real Bhubaneswar OSM drive network (`18,260` nodes, `46,679` directed edges).

- **GeoPulse vs Static Dijkstra:** 17 wins / 3 losses / 230 ties (250 paired; mean improvement: 0.0374%).
- **GeoPulse vs Dynamic Dijkstra:** 0 wins / 0 losses / 250 ties (250 paired; mean improvement: 0.0000%).
- **Dynamic Dijkstra vs Static Dijkstra:** 17 wins / 3 losses / 230 ties (250 paired; mean improvement: 0.0374%).

## 2. Research Objective

Determine under strictly controlled, paired experimental conditions whether GeoPulse's intersection-level sequential two-edge selection reduces realized journey travel time compared with fixed-route Static Dijkstra and update-triggered full-recomputation Dynamic Dijkstra when navigating dynamic predicted traffic and realized observed road speeds.

## 3. Experimental Setup

- Identical directed graph, edge lengths, static fallback speeds, and dynamic traffic mapping per scenario.
- Identical origin node, destination node, and UTC departure timestamp across all three strategies.
- Identical Phase 7 hourly predicted-speed frames (for routing choices) and realized observed-speed timeline (for physical movement).
- Tie definition: `|baseline_time - test_time| <= max(1.0s, 0.1% of baseline_time)`.

## 4. Dataset and Graph Description

- **Graph File:** `data/raw/osm/bhubaneswar_drive.graphml`
- **Nodes / Directed Edges:** 46,679 directed edges across 18,260 nodes (largest SCC: 18,230 nodes).
- **Dynamic Mapping:** `data/processed/traffic_to_osm_mapping_final.parquet` maps **690** directed edges (**1.48%** of network edges).
- **Prediction & Realized Stream:** `results/phase7_predictions.parquet` (44 hourly frames; origin `2026-01-15T08:00:00+00:00` -> `2026-01-17T03:00:00+00:00`; target-valid `2026-01-15T09:00:00+00:00` -> `2026-01-17T04:00:00+00:00`, final realized boundary `2026-01-17T05:00:00+00:00`).

## 5. OD Selection Methodology

Candidate nodes were sampled deterministically (`seed=42`) across both dynamically monitored intersections and general SCC intersections, using single-source Dijkstra trees to verify directed reachability and stratify OD pairs across all distance bins (short `<5 km`, medium `5–15 km`, long `>=15 km`) and route-specific dynamic coverage bins (low `<30%`, medium `30–70%`, high `>=70%`).

**Selected OD Distribution:**

- Distance bins: {'long': 18, 'medium': 17, 'short': 15}
- Coverage bins: {'high': 17, 'low': 17, 'medium': 16}

## 6. Temporal Validity and Horizon Handling

- Each prediction frame (`origin_timestamp`) becomes valid at `target_valid_timestamp = origin_timestamp + 1h` and remains active over `[target_valid_timestamp, next_hour)`.
- `predicted_speed` guides routing decisions only; `actual_speed` (aligned observed `currentSpeed` at the target hour) drives vehicle physics and integrates across hour boundaries.
- Traffic prediction updates affect route choices only at the next reached intersection after `target_valid_timestamp`.
- Journeys reaching `final_valid_until` without arriving terminate immediately as incomplete (`realized_traffic_unavailable`).

**Selected Departure Timestamps (UTC / IST):**

- `2026-01-15T09:58:00+00:00` (2026-01-15 15:28 IST — Afternoon)
- `2026-01-15T11:58:00+00:00` (2026-01-15 17:28 IST — Evening Peak)
- `2026-01-15T16:58:00+00:00` (2026-01-15 22:28 IST — Off-Peak Night)
- `2026-01-16T02:58:00+00:00` (2026-01-16 08:28 IST — Morning Peak)
- `2026-01-16T06:58:00+00:00` (2026-01-16 12:28 IST — Midday)

## 7. Strategy Definitions

1. **Static Dijkstra (`static_dijkstra`):** Computes one shortest path at departure using departure-frame predicted speeds and never reroutes.
2. **Dynamic Dijkstra (`dynamic_dijkstra`):** Recomputes full shortest path from the current node whenever arriving at an intersection after a new hourly forecast becomes valid.
3. **GeoPulse Two-Edge (`geopulse_two_edge`):** At every intersection, evaluates Candidate A (planned next edge) vs Candidate B (best destination-reachable alternative) using `predicted_edge_time + exact Dijkstra remaining tail cost`, switching when strictly beneficial while preserving loop avoidance and Dijkstra safety fallbacks.

## 8. Evaluation Metrics

Journey-level instrumentation records completion status, realized travel time (s), actual distance (m), traffic updates applied, route changes, two-edge decisions, alternative selections, forced single-edge decisions, Dijkstra safety fallbacks, backtracking events, repeated-node visits, loop traps, incomplete decisions, decision latencies (mean/P95/max ms), wall execution time, and actually traversed dynamic edge coverage (%).

## 9. Overall Results

| Strategy | Completed / Total | Completion % | Mean Time (s) | Median Time (s) | P95 Time (s) | Std Time (s) | Mean Dist (m) | Mean Traversed Cov (%) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `static_dijkstra` | 250/250 | 100.00% | 1102.0921 | 1075.038 | 1999.6492 | 649.0732 | 9982.8785 | 44.3233 |
| `dynamic_dijkstra` | 250/250 | 100.00% | 1101.7419 | 1075.038 | 1999.6492 | 649.1171 | 9990.2663 | 43.9596 |
| `geopulse_two_edge` | 250/250 | 100.00% | 1101.7419 | 1075.038 | 1999.6492 | 649.1171 | 9990.2663 | 43.9596 |

## 10. Paired Head-to-Head Comparison

| Comparison | Paired | Wins | Losses | Ties | Win % | Mean Diff (s) | Mean Impr (%) | Median Impr (%) | Primary Test | p-value |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|
| `geopulse_two_edge_vs_static_dijkstra` | 250 | 17 | 3 | 230 | 6.80% | 0.3502 | 0.0374 | 0.0 | Wilcoxon Signed-Rank Test | 0.035974 |
| `geopulse_two_edge_vs_dynamic_dijkstra` | 250 | 0 | 0 | 250 | 0.00% | 0.0 | 0.0 | 0.0 | Identical Outcomes (Zero Variance) | 1.0 |
| `dynamic_dijkstra_vs_static_dijkstra` | 250 | 17 | 3 | 230 | 6.80% | 0.3502 | 0.0374 | 0.0 | Wilcoxon Signed-Rank Test | 0.035974 |

## 11. Coverage-Wise Results

| Coverage Bin | Scenarios | Static Mean (s) | Dynamic Mean (s) | GeoPulse Mean (s) | GP vs Static (W/L/T, Impr%) | GP vs Dynamic (W/L/T, Impr%) |
|---|---:|---:|---:|---:|---|---|
| `low` | 85 | 1282.61 | 1282.29 | 1282.29 | 3/0/82 (0.021%) | 0/0/85 (0.000%) |
| `medium` | 80 | 1175.23 | 1175.41 | 1175.41 | 2/2/76 (-0.009%) | 0/0/80 (0.000%) |
| `high` | 85 | 852.74 | 851.85 | 851.85 | 12/1/72 (0.097%) | 0/0/85 (0.000%) |

## 12. Journey-Length-Wise Results

| Distance Bin | Scenarios | Static Mean (s) | Dynamic Mean (s) | GeoPulse Mean (s) | GP vs Static (W/L/T, Impr%) | GP vs Dynamic (W/L/T, Impr%) |
|---|---:|---:|---:|---:|---|---|
| `short` | 75 | 341.71 | 341.69 | 341.69 | 1/0/74 (0.004%) | 0/0/75 (0.000%) |
| `medium` | 85 | 1068.48 | 1067.79 | 1067.79 | 8/3/74 (0.087%) | 0/0/85 (0.000%) |
| `long` | 90 | 1767.49 | 1767.19 | 1767.19 | 8/0/82 (0.019%) | 0/0/90 (0.000%) |

## 13. Failure and Fallback Analysis

- **Incomplete Journeys:** `0` across all strategy executions (100% completion rate).

- **GeoPulse Two-Edge-Only Completions:** 250 / 250
- **Total Two-Edge Decisions:** 13540
- **Total Alternative Selections:** 20
- **Total Forced Single-Edge Continuations:** 4114
- **Total Route Changes:** 20
- **Total Dijkstra Safety Fallbacks:** 0
- **Total Backtracking Events:** 0
- **Total Repeated-Node Visits:** 0
- **Total Loop Traps:** 0

## 14. Computational Overhead

- **`static_dijkstra`:** mean wall execution = `0.0416s` (P95 `0.1421s`), mean decision latency = `nan ms`, two-edge mean latency = `nan ms`.
- **`dynamic_dijkstra`:** mean wall execution = `0.0736s` (P95 `0.2318s`), mean decision latency = `0.4843 ms`, two-edge mean latency = `nan ms`.
- **`geopulse_two_edge`:** mean wall execution = `1.8289s` (P95 `4.9911s`), mean decision latency = `17.5532 ms`, two-edge mean latency = `22.4145 ms`.

## 15. Limitations

1. **Sparse Sensor Coverage:** Dynamic speed mapping covers only **690/46679 (1.48%)** of directed OSM edges; all remaining road links use static highway speeds.
2. **Limited Forecast Horizon:** Phase 7 predictions span **44 hours** (Jan 15–17, 2026), preventing multi-week seasonal evaluation.
3. **Hourly Update Granularity:** Traffic forecasts update once per hour, so urban trips typically cross at most one forecast transition unless departed right before the hourly boundary.
4. **No Microscopic Queueing:** Travel times integrate realized link speeds without intersection signal delays or turning penalties.

## 16. Conclusion

This Stage 3 benchmark measured realized journey travel times under identical graph, OD, prediction, and actual-speed conditions. Against Static Dijkstra, GeoPulse achieved **17 wins, 3 losses, and 230 ties** (mean improvement `0.0374%`, p=`0.035974`). Against Dynamic Dijkstra, GeoPulse achieved **0 wins, 0 losses, and 250 ties** (mean improvement `0.0000%`, p=`1.0`).

Because GeoPulse evaluates predicted edge time plus the exact remaining Dijkstra tail cost using the same hourly forecast tensor as Dynamic Dijkstra, its realized routes closely match Dynamic Dijkstra when forecasts update once per hour—providing identical or near-identical travel times with higher per-intersection decision compute overhead.
