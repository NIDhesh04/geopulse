# GeoPulse Phase 2A — Real-World Two-Edge Routing Validation

**Evaluation date:** 22 November 2026  
**Network:** Bhubaneswar OSM directed MultiDiGraph  
**Evaluation:** 10 fixed origin-destination pairs; stored predicted traffic at 2026-01-15 14:00 UTC  
**Status:** Improvements to cycle handling are verified, but Sequential Two-Edge Selection is not reliable as a standalone end-to-end router yet.

## Executive findings

The original finite 1,000-second visited-node penalty could still select or force a successor on the route already taken. On the canonical trip, a destination-aware choice entered a one-exit corridor whose only next edge returned to an earlier node. The cycle guard then replaced the proposed route with a Dijkstra path.

I added strict active-path successor avoidance in RouteController. It turns a choice with no unvisited successor into an explicit loop trap and invokes the separately counted safety fallback. This removed cycle-breaker recoveries in the controlled run and reduced actual repeated-node arrivals. Compared with the same evaluator using the legacy soft penalty, mean trip time fell by 7.1% to 17.2% across strategies, and end-to-end completion rose to 100% for all five Two-Edge variants.

That does not establish standalone reliability. Under the strict configuration, only 0–3 of 10 trips per strategy reached the destination without Dijkstra or backtracking. Dijkstra supplied 67–88% of the final route steps. The result is a more predictable safety path with less cycling; most successful routes still depend on Dijkstra.

I also tested local branch backtracking without Dijkstra. Lookahead completed 8 of 10 trips under a 10× shortest-path hop cap, but averaged 3,586 seconds versus the 980-second Dijkstra reference and used 627 backtracking steps across the 10 trips. That mode remains opt-in and is not the default.

## 1. Implementation traced

The Phase 1 complete report and cleanup manifest were reread before the source inspection. The primary routing path is CandidateGenerator → TwoEdgeSelector → RouteController. The Pygame simulator calls the selector directly and does not use RouteController recovery.

At each RouteController step:

1. CandidateGenerator constructs outgoing directed edges using the exact (from node, to node, lane key) tuple and active travel-time weights. If there are more than two eligible edges, its configured policy ranks them and passes two to the decision strategy.
2. Immediate reversal to the previous node is pruned when there is another outgoing neighbor. This pruning is by neighbor node, so it excludes every parallel lane to that neighbor.
3. The decision strategy compares the pair. Greedy compares immediate edge time. Destination-Aware compares edge time plus straight-line remaining time. Lookahead evaluates a bounded forward search. Adaptive switches its pair comparison to Lookahead when the minimum candidate speed is below 25 km/h; otherwise it uses Destination-Aware.
4. The controller advances one edge and repeats. The strategy is local; it does not guarantee the globally shortest path.

Lookahead in this evaluation uses depth 2 and up to four branches per search level. For out-degree above two, Adaptive currently forms its candidate pair with Destination-Aware ranking before its pair-level congestion switch. Thus its Lookahead branch cannot reconsider candidates already omitted by candidate generation.

In the legacy behavior, visited nodes receive a finite 1,000-second penalty. A fixed penalty is not a hard loop constraint, and a single eligible outgoing edge is forced regardless of its visited status. The controller’s cycle guard is applied after candidate selection. It allows a repeat until the visit threshold is met, then switches to Dijkstra recovery.

The updated RouteController enables strict active-path loop avoidance by default. TwoEdgeSelector keeps that option off by default for direct callers such as Pygame; RouteController sets it explicitly. Historical experiment outputs were not overwritten. Local backtracking can be enabled separately and keeps per-node rejected edges so it does not immediately retry a failed branch.

## 2. Reproducible evaluation inputs

The benchmark script is scripts/run_phase2a_real_network_evaluation.py. It loads:

- data/raw/osm/bhubaneswar_drive.graphml: 18,260 nodes and 46,679 directed edges.
- data/processed/traffic_to_osm_mapping_final.parquet.
- results/phase7_predictions.parquet: 700 prediction rows for 700 distinct traffic segments at 2026-01-15 14:00 UTC after hourly rounding.
- results/phase8_od_pairs.csv: fixed O-D IDs 0 through 9.

The prediction slice uses predicted_speed, never actual_speed. GraphWeightManager creates one common predicted-cost dictionary for every algorithm in each run. The reported 690 dynamically weighted directed edges and SHA-256 hashes are recorded in results/phase2a_20261122_final/run_metadata.json. Static edge speeds are at most 50 km/h; mapped dynamic speeds are clipped to 3–120 km/h.

| O-D ID | Source → destination | Straight-line distance |
|---:|---|---:|
| 0 | 3722327026 → 2443921849 | 8.215 km |
| 1 | 2283167591 → 293464723 | 3.408 km |
| 2 | 3727013594 → 2392383587 | 11.495 km |
| 3 | 8144958910 → 5875519688 | 4.456 km |
| 4 | 8167025447 → 8166852655 | 4.832 km |
| 5 | 3725763498 → 293464962 | 7.774 km |
| 6 | 2841381812 → 8182316367 | 2.525 km |
| 7 | 8124118501 → 293464897 | 3.202 km |
| 8 | 3725657841 → 6986305647 | 4.957 km |
| 9 | 3725560599 → 2443937252 | 10.701 km |

The legacy and strict runs use the same graph, mapping, prediction timestamp, O-D pairs, candidate heuristic setting, strategy depth, and hop multiplier. Only strict active-path loop avoidance differs. The final CSV has 60 rows: 10 O-D pairs × Dijkstra, the four requested Two-Edge strategies, and one additional safe-heuristic comparison.

## 3. Results

Dijkstra reached all 10 destinations. Its mean predicted-cost travel time was 980.48 seconds, mean distance 8,214 m, and mean path length 67.1 directed edges.

The “legacy” column reproduces the finite-penalty behavior with the same current harness, using --legacy-soft-loop-penalty. “Strict” means strict loop avoidance plus the measured Dijkstra safety recovery. “Two-Edge only” means the destination was reached with zero Dijkstra fallback steps and zero backtracking steps.

| Strategy | Legacy journey success | Strict journey success | Two-Edge-only success: legacy → strict | Mean travel time: legacy → strict | Paired mean change | Dijkstra fallback steps: legacy → strict | Strict fallback share of route steps |
|---|---:|---:|---:|---:|---:|---:|---:|
| Greedy Two-Edge | 9/10 | 10/10 | 0/10 → 0/10 | 1,359.55 → 1,130.84 s | −14.88% | 689 → 707 | 86.43% |
| Destination-Aware, 25 km/h | 10/10 | 10/10 | 3/10 → 2/10 | 1,203.09 → 1,100.20 s | −7.13% | 529 → 531 | 67.90% |
| Lookahead, depth 2 | 8/10 | 10/10 | 3/10 → 3/10 | 1,497.67 → 1,154.29 s | −17.24% | 545 → 597 | 67.23% |
| Adaptive | 9/10 | 10/10 | 3/10 → 2/10 | 1,407.85 → 1,169.67 s | −13.39% | 514 → 614 | 71.90% |
| Destination-Aware, safe h=120 km/h | 8/10 | 10/10 | 0/10 → 0/10 | 1,336.26 → 1,131.61 s | −14.92% | 609 → 712 | 87.58% |

The paired change is the mean per-O-D percentage change from legacy to strict; it is not computed by dividing the two aggregate means. Although strict mode lowered trip time for every strategy, fallback-step counts rose for four strategies and were nearly unchanged for Destination-Aware. Strict mode therefore reduces the cost of detours and repeated visits, but does not reduce dependence on the safety router.

In strict mode, the number of loop traps across the 10 trips was 10 Greedy, 8 Destination-Aware, 7 Lookahead, 8 Adaptive, and 10 safe-heuristic. These are reported separately from actual cycle recoveries, which were zero because the selector blocked a visited-only move before it became a repeated arrival. The corresponding Dijkstra fallback steps are visible in both the table and per-trip CSV; fallback steps never count toward Two-Edge-only success.

Strict-mode mean intersection comparisons were 8.8 Greedy, 21.8 Destination-Aware, 25.9 Lookahead, 21.0 Adaptive, and 8.1 for the 120 km/h heuristic. Mean full selector latency per intersection comparison ranged from 0.031 to 0.052 ms; this includes candidate generation and pair evaluation. Mean overall route execution was about 22–29 ms per trip on this machine. Timing is environment-dependent.

The final evaluation artifacts are:

- Root deliverable: GEOPULSE_PHASE2A_BENCHMARK_RESULTS.csv.
- Detailed comparison: results/phase2a_20261122_final/summary_metrics.csv.
- Per-trip metrics and success definitions: results/phase2a_20261122_final/journey_results.csv.
- Loop-trap and failure rows: results/phase2a_20261122_final/failure_analysis.csv.
- Candidate-by-candidate trace: results/phase2a_20261122_final/decision_trace.csv.
- Input hashes and evaluation configuration: results/phase2a_20261122_final/run_metadata.json.
- Visualization: results/phase2a_20261122_final/figures/routing_comparison.png.
- Matched legacy baseline: results/phase2a_20261122_legacy_baseline/.

## 4. Why the real-network route cycled

On the canonical O-D 3722327026 → 2443921849, the legacy Destination-Aware trace reaches node 8164124150 at step 15. It compares:

- 8164124150 → 8164124149: edge 13.55 s, remaining estimate 1,162.57 s, total 1,176.1 s; target not yet visited.
- 8164124150 → 6956618513: edge 12.00 s, remaining estimate 1,153.63 s, plus the 1,000-second visited penalty; total 2,165.6 s.

It selects 8164124149. That node has one outgoing edge, back to 8164124150, so the next step is forced into a node already on the path. The locally cheaper estimate misses that the first branch is a short return corridor. This trace is saved in the legacy decision_trace.csv.

This demonstrates the local/global mismatch: the selected edge minimizes the current score, but the score does not represent future reachability. The 1,000-second penalty can rank a visited destination poorly, but it cannot detect a one-exit corridor that returns to an ancestor. Forced continuations do not compare alternatives. The depth-2 Lookahead sees only a short horizon and prunes to at most four immediate-cost branches, so deeper traps can remain hidden.

Strict active-path avoidance makes a repeated successor ineligible. If every eligible successor has already been visited, CandidateGenerator returns a loop trap; RouteController then records a separate Dijkstra recovery. This prevents the selector from cycling through the same nodes, while leaving the decision and recovery path clearly attributable.

Lane keys are preserved for costs, selected edges, and Dijkstra references. Reverse-edge recovery searches all directed reverse lane keys before synthesizing a physical backtrack. Candidate reversal pruning itself is by neighbor node, not lane key; no lane-key mismatch was observed in this fixed O-D set.

## 5. Destination heuristic

The existing 25 km/h straight-line estimate is not admissible under the active speed model. An admissible travel-time lower bound must not exceed the cost of any route. The shortest road length is at least the Haversine distance, but a 25 km/h divisor overestimates travel time whenever an edge is faster than 25 km/h. Dynamic mapped speeds may reach 120 km/h.

Using 120 km/h makes straight-line distance divided by speed a lower bound under this repository’s configured edge limits. The safe-heuristic variant was evaluated without changing the 25 km/h historical semantics. It completed 0/10 trips without Dijkstra, used 712 Dijkstra fallback steps, and had an 87.58% fallback share. The standard 25 km/h Destination-Aware run completed 2/10 without Dijkstra and used 531 fallback steps. The weaker admissible bound was less useful empirically on this set. It is recorded as an alternative, not silently substituted for historical scores.

## 6. Local backtracking experiment

I tested an opt-in controller mode that rejects a failed directed transition at its branch point, physically backs up along a real reverse lane where available, and retries the next local choice. This mode does not use Dijkstra when it reaches its decision cap. The comparison used the same O-D set and weights, with a hop cap of 10 times the Dijkstra path length.

| Strategy | Completed without Dijkstra | Mean travel time | Backtracking steps across 10 trips |
|---|---:|---:|---:|
| Greedy | 0/10 | 7,468.59 s | 2,674 |
| Destination-Aware, 25 km/h | 5/10 | 5,209.28 s | 1,511 |
| Lookahead, depth 2 | 8/10 | 3,585.74 s | 627 |
| Adaptive | 8/10 | 4,460.91 s | 1,064 |
| Destination-Aware, safe h=120 km/h | 0/10 | 6,611.84 s | 2,544 |

The Dijkstra reference mean was 980.48 seconds. Local backtracking improves completion without Dijkstra for Lookahead on this set, but it performs a large route search by physically revisiting many nodes and incurs much higher travel time. It remains an explicit experiment option, not the default behavior or a claimed performance improvement.

## 7. Code changes and regressions covered

- CandidateGenerator now supports strict exclusion of active-path successors and previously rejected directed edges.
- TwoEdgeSelector exposes loop-avoidance behavior as a setting. Its direct-call default remains the legacy soft behavior; RouteController enables strict avoidance by default.
- RouteController has an opt-in local backtracking retry that tracks failed edges by branch and clears a branch’s failures when that branch is abandoned. It defaults off because the real-network ablation showed excessive detours.
- The 25 km/h heuristic documentation no longer calls it admissible. No default heuristic value or historical experiment output was changed.
- New tests cover the finite-penalty failure, the non-admissible 25 km/h estimate, loop-avoidance scoping, and branch retry without Dijkstra.

The adaptive candidate-pool behavior, depth-2 horizon, loop-prone one-exit corridors, and low Two-Edge-only completion remain open research issues. This run covers one stored prediction timestamp and 10 selected O-D pairs; it is not evidence of performance across all times or the full OSM network.

## 8. Verification and exact commands

Final evaluation, strict loop handling:

    .\.venv\Scripts\python.exe -B scripts/run_phase2a_real_network_evaluation.py --output-dir results/phase2a_20261122_final

Matched legacy soft-penalty baseline:

    .\.venv\Scripts\python.exe -B scripts/run_phase2a_real_network_evaluation.py --output-dir results/phase2a_20261122_legacy_baseline --legacy-soft-loop-penalty

Local backtracking ablation:

    .\.venv\Scripts\python.exe -B scripts/run_phase2a_real_network_evaluation.py --output-dir results/phase2a_20261122_local_backtracking_ablation --local-backtracking --max-hops-multiplier 10

Routing regressions:

    .\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider tests/test_two_edge_routing.py

Full suite:

    .\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider tests

Final full-suite result: 73 passed. Python syntax compilation in memory covered 64 files. The real-network evaluation was rerun after the routing changes. Historical Phase 7–11 and Two-Edge experiment files were not overwritten. No commit or push was performed.

