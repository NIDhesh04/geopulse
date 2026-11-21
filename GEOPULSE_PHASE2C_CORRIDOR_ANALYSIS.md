# GeoPulse Phase 2C — Capped Forced-Corridor Evaluation

**Evaluation date:** 22 November 2026  
**Road graph:** Bhubaneswar OSM directed `MultiDiGraph`  
**Decision:** Keep the corridor check as an opt-in experiment and diagnostic. Do not make it the routing default yet.

## What was evaluated

The new check starts with a proposed outgoing directed edge and follows successive one-exit choices. It stops at the destination, a node with multiple valid outgoing edge records, a dead end, a return to the active path, or its edge cap. Lane keys remain distinct, matching the selector's directed-edge choices. The reported corridor cost and length include the candidate edge and new corridor edges actually followed; an edge back to an active node is detected as a trap but is not traversed or added to those totals.

An edge-cap stop is recorded as `edge_cap` and is neither a dead end nor grounds for conservative rejection. Ranking prefers destination/junction evidence, then incomplete evidence, then proven dead ends or active-path returns. Conservative rejection removes only proven traps and only when another candidate remains.

The Phase 2B depth-5 profile was reproduced first. The same network, weights, seed, 30 O-D IDs (0–29), and three stored predictions (15 January 2026 at 08:00, 14:00, and 20:00 UTC) were then used for all paired comparisons. Each timestamp had 700 prediction rows mapped to 690 dynamically weighted directed edges. The graph has 18,260 nodes and 46,679 directed edges. Input hashes and scenario metadata are saved in both run metadata files.

The final comparison contains the Phase 2B depth-5 baseline, a matched Destination-Aware no-corridor control, the six Destination-Aware corridor variants (caps 5/10/20 × ranking/rejection), and the two depth-5 plus cap-10 variants. An independent Dijkstra reference was run for each O-D/time scenario.

**Success definitions:** journey completion means the controller reached the destination, including safety recovery. Two-Edge-only completion requires destination arrival with zero Dijkstra fallback steps and zero local backtracking steps. Fallback edges are counted separately and are never credited as Two-Edge decisions. No configuration used local backtracking.

## Baseline reproduction

The Phase 2C depth-5 baseline matched the Phase 2B validation on all 60 overlapping cases (O-D IDs 10–29 at the same three timestamps). Success, standalone success, time, distance, fallback steps, repeated visits, loop traps, intersection decisions, and route-step counts matched exactly. The check is in `results/phase2c_20261122_baseline/phase2b_reproduction_check.csv`.

Across the full 90-case set, depth-5 completed 83/90 journeys and 41/90 without fallback. It used 2,912 fallback steps (26.34% of route steps), averaged 1,401.55 seconds and 10,831.14 metres, and had 4.60 repeated-node visits and 47 loop traps per 90 journeys. Seven journeys stopped at the controller's maximum-hop limit.

## Overall results

Each configuration ran 90 journeys. “Fallback” is the total number of fallback route edges; its share is fallback edges divided by all route edges.

| Configuration | Journey completion | Two-Edge-only | Fallback steps / share | Mean time | Mean distance | Repeated visits | Loop traps | Mean execution / journey |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Dijkstra | 90/90 | — | 0 / 0% | 1,007.56 s | 8,991.32 m | 0.00 | 0 | 26.20 ms |
| Destination-Aware, no corridor | 90/90 | 11/90 (12.2%) | 5,264 / 64.23% | 1,167.46 s | 9,954.89 m | 2.89 | 79 | 25.39 ms |
| Destination-Aware + corridor, either policy, cap 5/10/20 | 90/90 | 19/90 (21.1%) | 5,192 / 53.31% | 1,365.81 s | 11,043.14 m | 5.78 | 71 | about 27.4–28.9 ms |
| Phase 2B depth-5 baseline | 83/90 | 41/90 (45.6%) | 2,912 / 26.34% | 1,401.55 s | 10,831.14 m | 4.60 | 47 | 23.12 ms |
| Depth-5 + corridor cap 10, either policy | 83/90 | 43/90 (47.8%) | 2,792 / 24.82% | 1,426.06 s | 10,971.46 m | 4.60 | 45 | about 30.5–30.8 ms |

The Destination-Aware corridor variants completed eight more journeys without fallback than their matched no-corridor control and used 72 fewer fallback steps. Their mean trip was 198.34 seconds longer and 1,088 metres longer. For depth 5, adding cap 10 yielded two additional Two-Edge-only completions and 120 fewer fallback steps, while increasing mean trip time by 24.51 seconds, mean distance by 140 metres, and mean execution time by about 7.3 ms per journey. It did not change the seven max-hop failures.

All Two-Edge configurations remained slower and longer on average than Dijkstra. These results do not show superiority over Dijkstra.

## Cap, policy, and cost findings

- The cap sweep did not exercise an incomplete corridor: **0 of 86,022** checks stopped at the cap. The longest observed assessment contained 7 edges. Thus caps 5, 10, and 20 produced identical selected-edge traces within each Destination-Aware policy. A larger cap did not improve routes in this sample.
- Ranking and conservative rejection had identical selected-edge traces and route outcomes for each base strategy here. Rejection reduced counted two-candidate intersections because a proven-trap candidate was removed, but it did not change the selected route. It did not reject an incomplete result; that rule is covered by a regression test.
- Of all assessments, 78,094 ended at a junction, 7,704 detected a return to the active path, 212 reached the destination, and 12 reached a dead end. These assessment counts repeat across configurations and are not unique network locations.
- Pooled corridor-check latency was about 0.0098–0.0102 ms mean and 0.0150–0.0171 ms p95 for Destination-Aware variants. For depth-5 plus cap 10, it was 0.0130–0.0138 ms mean and 0.0170–0.0178 ms p95. Timings are machine-specific.
- Pooled intersection-decision latency for depth 5 was 0.1166 ms mean / 0.2481 ms p95. With cap 10 it was 0.1807 / 0.3595 ms for ranking and 0.1971 / 0.3872 ms for conservative rejection. The timed traces include candidate generation and pair evaluation; the separately recorded corridor-check duration is not an added adjustment to that measurement.
- There were no cycle-recovery steps in these runs. The active-path guard instead produced loop traps that triggered safety fallback. In the depth-5 baseline, 35 of 47 loop traps were at one-exit nodes; depth-5 plus cap 10 had 27 of 45 there. The total trap count fell only from 47 to 45 because traps at other out-degrees increased.

The network has 185 nodes with multiple keyed directed edges to the same successor. The corridor checker treats these as separate outgoing edge choices, consistently with the Two-Edge selector and lane-keyed weights; it therefore stops at such a node as a junction. This is conservative for a node-only definition of a corridor and should be tested separately if topology is later collapsed by successor node.

## Recommendation and limits

The check identifies forced paths that return to the active path and slightly reduces fallback under the recommended depth-5 profile. The gain is small on this set: 2 more standalone completions out of 90 and 120 fewer fallback steps, alongside longer trips and more decision work. The cap sweep was not informative because no check reached its cap, and the two integration policies produced the same route outcomes.

Keep the implementation selectable for further experiments and diagnostics, but keep **strict active-path avoidance + depth-5 lookahead, branch limit 4, no local backtracking** as the routing profile for now, with Dijkstra safety fallback measured separately. Do not enable corridor ranking or rejection as a default based on these results.

The result covers one city graph, 30 reproducible O-D pairs, and three stored traffic timestamps. Seven depth-5 journeys hit the hop cap. The evaluation did not exercise an incomplete corridor, so it does not establish how a longer forced corridor should be handled. The next step is an independent set of longer trips and additional timestamps, ideally including networks with longer one-exit chains, while preserving the same strict success and fallback accounting.

## Artifacts

- `GEOPULSE_PHASE2C_BENCHMARK_RESULTS.csv`: 990 paired journey rows (90 Dijkstra + 90 depth-5 baseline + 810 comparison-control/variant rows).
- `results/phase2c_20261122_baseline/`: reproduced baseline and Dijkstra journey rows, summary, decision traces, metadata, and Phase 2B reproduction check.
- `results/phase2c_20261122_comparison_v4/`: comparison journey rows, all decision traces, 86,022 corridor assessments, summaries, failure and loop-trap analyses, latency tables, metadata, and visualization.
- `results/phase2c_20261122_comparison_v4/figures/corridor_comparison.png`: comparison chart.
- Earlier exploratory comparison outputs (`comparison`, `comparison_v2`, and `comparison_v3`) were preserved; the v4 directory is the final output with the matched control and complete analyses.

## Exact commands

```powershell
.\.venv\Scripts\python.exe -B scripts/run_phase2c_corridor_evaluation.py --stage baseline --output-dir results/phase2c_20261122_baseline
.\.venv\Scripts\python.exe -B scripts/run_phase2c_corridor_evaluation.py --stage compare --baseline-dir results/phase2c_20261122_baseline --output-dir results/phase2c_20261122_comparison_v4
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider tests
```

Verification completed with **82 tests passing**. No commit or push was made.
