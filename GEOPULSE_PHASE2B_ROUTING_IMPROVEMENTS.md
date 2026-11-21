# GeoPulse Phase 2B — Sequential Two-Edge Routing Improvements

**Evaluation date:** 22 November 2026 · **Network:** Bhubaneswar OSM directed MultiDiGraph
**Result:** Deeper bounded lookahead materially reduced Dijkstra fallback on held-out O-D pairs and times. It raised standalone completion, with a measured latency and travel-time trade-off. The algorithm is not yet a replacement for Dijkstra on this network.

## Findings

The Phase 2A traces exposed two candidate-selection limits.

1. When there are more than two outgoing edges, Adaptive previously ranked its pair with Destination-Aware scores before deciding whether to use Lookahead. A Lookahead-favored edge could therefore be omitted. The selector now supplies a pair containing the best Destination-Aware candidate and the best Lookahead candidate. The pair still contains at most two outgoing directed edges, and Adaptive still makes the route decision between those two.
2. Limited Lookahead ranked branches at each future node only by immediate edge time. A slower edge with better destination progress could be pruned by the branch cap. The new bounded reachability experiment supports immediate-cost, destination-potential, and onward-connectivity branch rankings, and marks a branch nonviable if all explored paths terminate or can only return to an active-path node.

The Adaptive candidate-pool defect is fixed and covered by tests. On the Phase 2B data, its corrected pair changed only 2 of 148 matched high-degree decisions in the screening set and 74 of 1,502 in validation; selected successors changed 0 and 3 times respectively. Route metrics consequently stayed nearly the same. This confirms the implementation defect, while showing that it was not the main cause of fallback on these journeys.

The strongest measured change came from configuring the existing bounded Lookahead strategy at depth 5 with four branches per level. On the 60 held-out O-D/time scenarios, standalone Two-Edge completion rose from 13/60 (21.7%) at depth 2 to 31/60 (51.7%). Dijkstra fallback steps fell from 3,463 to 2,087, and fallback share fell from 53.1% to 28.5%. Mean travel time was 3.0% higher than depth 2 on paired cases; mean intersection-decision latency was about 3.2 times higher. Dijkstra remained faster on mean travel time.

## Implementation changes

- `src/routing/candidate_generator.py` adds three explicit two-candidate policies for ablation: fastest plus destination progress, destination plus Lookahead, and Adaptive’s diverse pair. Each decision still compares no more than two immediate outgoing edges.
- `src/routing/two_edge_selector.py` selects the diverse pair policy by default for Adaptive, while retaining explicit policy overrides for matched experiments.
- `src/routing/lookahead.py` adds `BoundedReachabilityEvaluator`. It explores a capped tree, excludes nodes on the supplied visited path, records viable frontiers and expansions, and can order branches by immediate cost, destination estimate, or the count of onward unvisited successors. It does not call Dijkstra or search the full graph.
- `src/routing/decision_strategies.py` adds `BoundedReachabilityDecisionStrategy`, which first prefers a candidate with a bounded viable continuation, then compares estimated travel cost.
- `scripts/run_phase2b_routing_experiments.py` reproduces screening and holdout evaluations, emits per-journey metrics, failure analysis, decision traces, input hashes, summaries, and figures.
- `tests/test_two_edge_routing.py` adds four regressions for Adaptive candidate-pool coverage/default selection, bounded detection of a one-exit return corridor, and destination-aware ordering under a branch limit.

The historical Phase 2A report, CSV, and result directories were not overwritten. Dijkstra fallback remains enabled for the application and is counted separately. A journey counts as **Two-Edge-only success** only if it reached its destination with zero Dijkstra fallback steps and zero backtracking steps. Local backtracking completion is reported in its separate field.

## Evaluation design

The evaluation uses the same Bhubaneswar GraphML graph, traffic mapping, predicted edge-weight dictionary per scenario, and directed lane keys for every algorithm in that scenario. The graph contains 18,260 nodes and 46,679 directed edges. The stored prediction dataset has 700 traffic-segment rows at each tested time; these map to 690 dynamically weighted directed edges. Input SHA-256 hashes are in each run’s `run_metadata.json`.

The screening set uses Phase 2A O-D IDs 0–9 at **2026-01-15 14:00 UTC**. It ran 28 configurations: Dijkstra, the Phase 2A strategies, lookahead depth/branching sweeps, reachability and candidate-pair ablations, and three local-backtracking combinations.

The holdout set uses 20 additional reproducible O-D pairs, IDs 10–29, at **08:00, 14:00, and 20:00 UTC** on 15 January 2026. That gives 60 scenarios per configuration and tests three of the 44 stored hourly prediction times. Six configurations were compared in validation: Dijkstra, Destination-Aware, depth-2 Lookahead, both Adaptive candidate-pool modes, and depth-5 Lookahead.

The primary timing fields are per journey. Mean and p95 decision latency are calculated over intersection selector calls and include candidate generation plus pair evaluation. Execution time covers the RouteController journey, including safety recovery when used. Timings are machine-dependent.

## Phase 2A O-D screening results

This table compares selected ablations on the exact Phase 2A O-D set and timestamp. Fallback share is Dijkstra fallback steps divided by total route steps. `Two-Edge-only` excludes both Dijkstra fallback and backtracking.

| Configuration | Journey success | Two-Edge-only | Mean time / distance | Dijkstra fallback steps / share | Backtrack steps | Repeats / loop traps | Mean intersections | Mean / p95 decision latency | Mean execution |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Dijkstra | 10/10 | — | 980.48 s / 8,214 m | 0 / 0% | 0 | 0 / 0 | 0 | — | 63.24 ms |
| Destination-Aware, 25 km/h | 10/10 | 2/10 | 1,100.20 s / 8,944 m | 531 / 67.90% | 0 | 2.4 / 8 | 21.8 | 0.105 / 0.153 ms | 71.43 ms |
| Lookahead, depth 2, branches 4 | 10/10 | 3/10 | 1,154.29 s / 9,164 m | 597 / 67.23% | 0 | 5.0 / 7 | 25.9 | 0.147 / 0.277 ms | 76.12 ms |
| Adaptive, Phase 2A pool | 10/10 | 2/10 | 1,169.67 s / 9,346 m | 614 / 71.90% | 0 | 5.1 / 8 | 21.0 | 0.156 / 0.270 ms | 79.66 ms |
| Adaptive, diverse pair | 10/10 | 2/10 | 1,169.67 s / 9,346 m | 614 / 71.90% | 0 | 5.1 / 8 | 21.0 | 0.162 / 0.315 ms | 79.41 ms |
| Lookahead, depth 5, branches 4 | 9/10 | 4/10 | 1,514.44 s / 10,993 m | 301 / 22.79% | 0 | 7.1 / 6 | 88.6 | 0.507 / 1.075 ms | 91.97 ms |
| Bounded Reachability, depth 3, branches 4 | 10/10 | 0/10 | 1,447.73 s / 10,825 m | 600 / 49.02% | 0 | 6.1 / 10 | 53.9 | 0.424 / 0.705 ms | 111.29 ms |
| Lookahead depth 2 + local backtracking | 8/10 | 3/10 | 3,585.74 s / 22,967 m | 0 / 0% | 627 | 84.1 / 627 | 187.5 | 0.180 / 0.351 ms | 983.74 ms |
| Lookahead depth 5 + local backtracking | 6/10 | 4/10 | 3,361.82 s / 21,120 m | 0 / 0% | 713 | 115.6 / 713 | 196.7 | 0.648 / 1.454 ms | 1,175.27 ms |

The depth sweep showed a consistent cost curve. Lookahead depth 1 produced the same route choices as Destination-Aware on this set. Depth 2 achieved 3/10 Two-Edge-only success. Depth 3 remained at 3/10 and reduced fallback steps from 597 to 537. Depth 5 with two branches achieved 3/10 and 301 fallback steps; four branches achieved 4/10 and 301 fallback steps. Depth 5 raised mean decision latency from roughly 0.15 ms at depth 2 to 0.43–0.51 ms, depending on branching. Branch limits of 2 and 4 produced identical results at depths 1 and 2 for these O-D pairs.

All ten tested Bounded Reachability configurations had zero Two-Edge-only completions. Depth-3 variants required 600 fallback steps and depth-5 variants required 560, at substantially higher decision latency. The fastest-plus-progress candidate pair reduced mean time for one reachability variant but increased fallback steps; it did not improve standalone completion. These local reachability policies are not recommended from this evidence.

Local backtracking eliminated Dijkstra steps but introduced hundreds of reverse steps, high repeat counts, long travel times, and hop-cap failures. Depth-2 backtracking reached 8/10 end to end; depth-5 reached 6/10. It is not a better general configuration on this network.

## Holdout results: 20 O-D pairs × 3 prediction times

| Configuration | Journey success | Two-Edge-only | Mean time / distance | Dijkstra fallback steps / share | Backtrack steps | Repeats / loop traps | Mean intersections | Mean / p95 decision latency | Mean execution |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Dijkstra | 60/60 | — | 1,039.33 s / 9,403 m | 0 / 0% | 0 | 0 / 0 | 0 | — | 97.05 ms |
| Destination-Aware, 25 km/h | 60/60 | 5/60 (8.3%) | 1,216.95 s / 10,450 m | 3,867 / 64.2% | 0 | 3.05 / 55 | 31.97 | 0.103 / 0.194 ms | 92.09 ms |
| Lookahead, depth 2, branches 4 | 58/60 | 13/60 (21.7%) | 1,347.19 s / 11,123 m | 3,463 / 53.1% | 0 | 4.12 / 47 | 44.65 | 0.152 / 0.283 ms | 84.03 ms |
| Adaptive, Phase 2A pool | 60/60 | 10/60 (16.7%) | 1,403.19 s / 11,597 m | 3,837 / 56.9% | 0 | 5.93 / 50 | 41.65 | 0.143 / 0.260 ms | 87.96 ms |
| Adaptive, diverse pair | 60/60 | 10/60 (16.7%) | 1,403.08 s / 11,597 m | 3,837 / 56.9% | 0 | 5.93 / 50 | 41.65 | 0.149 / 0.292 ms | 87.59 ms |
| Lookahead, depth 5, branches 4 | 60/60 | 31/60 (51.7%) | 1,387.13 s / 10,893 m | 2,087 / 28.5% | 0 | 3.35 / 29 | 78.43 | 0.482 / 1.001 ms | 87.07 ms |

Compared with depth 2 on the same 60 O-D/time scenarios, depth 5:

- Increased Two-Edge-only completion by 18 journeys, from 21.7% to 51.7%.
- Reduced Dijkstra fallback steps by 1,376 (39.7%) and fallback share from 53.1% to 28.5%.
- Reduced mean repeated-node visits from 4.12 to 3.35 and loop traps from 47 to 29.
- Reduced mean distance by about 230 m, but increased paired mean travel time by 3.0% (about 40 seconds).
- Increased mean intersection latency from 0.152 ms to 0.482 ms and mean per-journey p95 latency from 0.283 ms to 1.001 ms.

Depth 5 still averaged 1,387 seconds, about 33% above Dijkstra’s 1,039 seconds, and its decision latency was higher than depth 2. The result supports it as a fallback-reduction profile where latency is acceptable; it does not establish better travel time than Dijkstra.

### Remaining failure pattern

Strict active-path avoidance prevented cycle-breaker recoveries in these runs, but it did not keep every Two-Edge prefix out of a corridor that later returns to the path. On the holdout set, depth-2 Lookahead produced 47 loop traps; 31 occurred at nodes with one outgoing edge. Depth-5 reduced this to 29 traps, of which 20 were at one-exit nodes. The search can therefore prefer a locally promising branch whose forced continuation lies beyond the bounded horizon or outside the retained branches. The controller then uses its separately counted Dijkstra safety recovery. One Phase 2A-set depth-5 trip also exceeded its hop cap after detours and fallback. The decision traces record each trap node, degree, preceding choices, and fallback path.

## Interpretation and recommendation

**Recommended Two-Edge configuration for the next application experiment:** strict active-path loop avoidance with standard Limited Lookahead at **depth 5, branch limit 4**, no local backtracking by default, and measured Dijkstra fallback retained as the safety path. It had the highest standalone completion in screening and holdout, and it cut fallback use on the holdout set. Keep it configurable because its decisions cost more and it remains slower than Dijkstra on mean route time.

Adaptive’s corrected candidate pair is the right implementation of its declared strategy, but it did not improve routing metrics enough to recommend Adaptive over Lookahead. Bounded Reachability and local backtracking should remain experimental options; their tested variants did not outperform the recommended depth-5 profile on standalone completion and fallback use.

The algorithm is **partly working independently**, with 31/60 holdout trips completed without any fallback at depth 5. It still needed Dijkstra on 29/60 holdout journeys, used more decision work than depth 2, and averaged a longer trip time than Dijkstra. The sample covers 30 O-D pairs and three prediction times from one day; broader O-D/time validation is still needed before changing a product default.

**Next recommended research step:** evaluate a bounded forced-corridor check that follows only one-exit transitions until it reaches a decision point, destination, active-path return, or a strict edge cap. The next benchmark should measure whether this catches the remaining one-exit traps more cheaply than depth-5 expansion, with the same O-D/time holdout separation.

## Artifacts and exact commands

- Per-journey comparison: `GEOPULSE_PHASE2B_BENCHMARK_RESULTS.csv` (640 rows, including screening and holdout stages).
- Screening output and decision traces: `results/phase2b_20261122_screen_v2/`.
- Holdout output and decision traces: `results/phase2b_20261122_validation/`.
- Cross-stage summaries: `results/phase2b_20261122_cross_stage_summary.csv`.
- Cross-stage failure rows: `results/phase2b_20261122_cross_stage_failure_analysis.csv`.
- The versioned directories each contain `journey_results.csv`, `summary_metrics.csv`, `failure_analysis.csv`, `decision_trace.csv`, `run_metadata.json`, and comparison figures.

Screening command:

    .\.venv\Scripts\python.exe -B scripts/run_phase2b_routing_experiments.py --stage screen --output-dir results/phase2b_20261122_screen_v2

Holdout command:

    .\.venv\Scripts\python.exe -B scripts/run_phase2b_routing_experiments.py --stage validate --selected-config "Lookahead Two-Edge (depth=5, branches=4)" --output-dir results/phase2b_20261122_validation

Routing regressions:

    .\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider tests/test_two_edge_routing.py

Full suite:

    .\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider tests

Final full-suite result: **77 passed in 76.48s**. In-memory syntax compilation covered 65 Python files, and `git diff --check` found no whitespace errors. No commit or push was made.
