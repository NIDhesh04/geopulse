# GeoPulse Phase 4 — Temporal Journey Engine

**Evaluation date:** 2026-11-24  
**Scope:** Implement and evaluate time-varying journey simulation for Static Dijkstra, Dynamic Dijkstra, and Sequential Two-Edge Selection.

## Implementation

The engine keeps route choice and vehicle motion on separate inputs:

- Stored model predictions are converted to edge travel-time costs and used for routing decisions.
- Stored `actual_speed` labels drive vehicle motion. Edge traversal integrates distance across hourly observed-speed changes. If a traffic frame becomes valid while a vehicle is on an edge, route choice changes only after the vehicle reaches its next node.
- Each strategy starts with the same departure-time predicted-cost Dijkstra route. Static Dijkstra retains it. Dynamic Dijkstra recomputes at the first reached node after a new frame becomes valid. GeoPulse compares the current planned next edge with one reachable alternative at each intersection. Each candidate is scored as its current predicted edge cost plus the Dijkstra remaining-route cost. Choosing the planned edge retains its plan; choosing the alternative adopts its Dijkstra tail.
- GeoPulse's candidate choice remains two-edge and sequential. Dijkstra is used for initial routing, remaining-route evaluation, dynamic rerouting, and safety fallback. Safety fallback edge steps are counted separately and do not count toward `two_edge_only_success`.
- A reverse Dijkstra tree is cached per destination and prediction frame for tail costs. If its shortest tail revisits the active journey, a constrained Dijkstra is run for that candidate. A journey is bounded by a graph-size step limit, and repeated nodes are counted.

`HistoricalTrafficReplay` now exposes stored realized speeds separately from predicted speeds. The temporal engine refuses prediction-only frames. `Vehicle` gained temporal methods that record actual edge times and preserve the current node while route plans change.

## Validation of observed-speed labels

The training script creates `target_speed` with a one-row forward shift per segment after chronological sorting. The saved prediction artifact contains 30,800 held-out rows: 700 segments across 44 hourly origins. Every stored `actual_speed` value was checked against `currentSpeed` in `datasets/traffic_structured_v1.parquet` at `origin + 1 hour`:

- Matched observations: **30,800 / 30,800**
- Exact value matches: **30,800 / 30,800**
- Target-valid range: **2026-01-15 09:00 UTC to 2026-01-17 04:00 UTC**
- No traffic observations were synthesized.

The real graph has 18,260 nodes and 46,679 directed edges. The available mapping provides valid dynamic observations for 690 directed edges per frame (about **1.48%** of graph edges); remaining edges use the existing static speed fallback.

## Real O-D evaluation

The final comparisons use the first ten reproducible pairs in `results/phase8_od_pairs.csv`, the Bhubaneswar GraphML graph, the same mapping, the same saved predictions, and the same realized-speed timeline for all strategies. Every run uses one common departure time across the three strategies. The two reported departures place the journeys immediately before a stored hourly update.

| Departure UTC | Strategy | Completed | GeoPulse-only completed | Mean actual time | Mean distance | Prediction updates applied | Route changes / alternatives | Fallback steps | Mean execution per trip |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026-01-15 09:59 | Static Dijkstra | 10/10 | — | 940.63 s | 8,132.45 m | 0 | 0 | 0 | 0.070 s |
| 2026-01-15 09:59 | Dynamic Dijkstra | 10/10 | — | 942.33 s | 8,205.43 m | 10 | 1 route change | 0 | 0.128 s |
| 2026-01-15 09:59 | GeoPulse Two-Edge | 10/10 | 10/10 | 942.33 s | 8,205.43 m | 10 | 1 alternative selected | 0 | 1.919 s |
| 2026-01-15 15:59 | Static Dijkstra | 10/10 | — | 938.35 s | 8,214.43 m | 0 | 0 | 0 | 0.079 s |
| 2026-01-15 15:59 | Dynamic Dijkstra | 10/10 | — | 908.78 s | 8,157.17 m | 10 | 4 route changes | 0 | 0.101 s |
| 2026-01-15 15:59 | GeoPulse Two-Edge | 10/10 | 10/10 | 908.78 s | 8,157.17 m | 10 | 4 alternatives selected | 0 | 1.876 s |

At 09:59, Dynamic Dijkstra and GeoPulse each produced one slower trip and nine unchanged trips versus Static Dijkstra: **17.07 seconds more total**. At 15:59, both dynamic strategies improved four trips and left six unchanged, saving **295.68 seconds total** versus Static Dijkstra. GeoPulse's actual outcomes matched Dynamic Dijkstra in both scenarios; it did not demonstrate a travel-time advantage over Dynamic Dijkstra.

GeoPulse made 433 two-candidate intersection decisions at 09:59 and 429 at 15:59. It selected the alternative once and four times, respectively. Both runs had **10/10 Two-Edge-only completions**, zero Dijkstra safety-fallback steps, zero backtracking steps, zero repeated-node visits, and zero loop traps. Thus, the completion counts do not rely on fallback routing.

Mean measured pair-selection latency was **36.18 ms** at 09:59 and **35.79 ms** at 15:59; p95 pair latency was **126.06 ms** and **121.89 ms**, respectively. Mean per-journey engine execution was **1.92 seconds** and **1.88 seconds** for GeoPulse, versus 0.10–0.13 seconds for Dynamic Dijkstra. These are routing simulation wall-clock costs; they are separate from simulated trip time.

## Conclusion and limits

Sequential Two-Edge Selection is executing independently on the real network: all 20 GeoPulse evaluation journeys completed with no safety fallback or backtracking, and the traces show explicit planned-edge versus alternative comparisons. The implementation meets the sequential two-edge behavior and is not reporting fallback journeys as standalone successes.

The experiment does **not** establish that GeoPulse beats Dynamic Dijkstra on actual journey time. In these two temporal slices, it matched Dynamic Dijkstra, while incurring much higher computation time. Dynamic routing improved the 15:59 slice but made the 09:59 slice slightly worse than the fixed route, showing that prediction error can hurt. The evaluation covers ten O-D pairs and two departures from one held-out historical period; the dynamic mapping covers only 690 of 46,679 directed edges. These results are evidence of working temporal simulation, not broad performance superiority.

Recommended next step: evaluate more O-D pairs and departure times across the full 44-frame test horizon, then profile candidate-tail and constrained-Dijkstra latency before considering algorithm changes. Keep prediction inputs, observed execution speeds, and fallback counts separate in those comparisons.

## Reproduction commands

```powershell
.\.venv\Scripts\python.exe scripts/run_phase4_temporal_benchmark.py --od-count 10 --departure 2026-01-15T09:59:00Z --output-dir results/phase4_20261124_temporal_v14
.\.venv\Scripts\python.exe scripts/run_phase4_temporal_benchmark.py --od-count 10 --departure 2026-01-15T15:59:00Z --output-dir results/phase4_20261124_temporal_v15
.\.venv\Scripts\python.exe -m pytest tests/test_phase4_temporal_journey.py tests/test_traffic_replay.py -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q src/traffic src/experiments/temporal_journey.py src/simulation/vehicle.py scripts/run_phase4_temporal_benchmark.py tests/test_phase4_temporal_journey.py
git diff --check
```

Verification on the final code completed successfully:

- Focused replay and Phase 4 tests: **34 passed**.
- Full project suite: **116 passed**.
- Python compilation: exit code **0**.
- `git diff --check`: exit code **0**. Git printed only its standard LF-to-CRLF notices for the edited Python files.
- The protected dataset, mapping, graph, model, prediction artifact, and O-D source paths had no working-tree changes. No commit or push was made.

## Files and results

- [Temporal journey engine](src/experiments/temporal_journey.py)
- [Replay changes](src/traffic/replay.py)
- [Vehicle temporal methods](src/simulation/vehicle.py)
- [Benchmark runner](scripts/run_phase4_temporal_benchmark.py)
- [Phase 4 regression tests](tests/test_phase4_temporal_journey.py)
- [Combined journey-level results CSV](GEOPULSE_PHASE4_TEMPORAL_BENCHMARK_RESULTS.csv)
- [Combined strategy summary CSV](GEOPULSE_PHASE4_TEMPORAL_SUMMARY.csv)
- Versioned traces, routes, per-run summaries, and input hashes: `results/phase4_20261124_temporal_v14/` and `results/phase4_20261124_temporal_v15/`.
