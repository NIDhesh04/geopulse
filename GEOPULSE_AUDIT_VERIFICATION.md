# GeoPulse – Audit Verification and Discrepancy Report

---

## 1. Git Repository State (Second‑Pass)

| Command | Output (trimmed) |
|---------|------------------|
| `git branch --show-current` | `main` |
| `git rev-parse HEAD` | `eb14d9efdfc1973cc7a522249affccd4efdb53fe` |
| `git status --short` | *(no output – working tree clean)* |
| `git log -15 --oneline` | <pre>eb14d9e  updated<br>b2d1cd1  updated<br>23e3413  updated<br>51252d0 feat: update GeoPulse project<br>51f6dae feat: update GeoPulse project<br>9075ea3 tried bhubhneshwar data<br>81a851a baseline created</pre> |
| `git ls‑files` | Full list of tracked files (see transcript step 8). The audit file `GEOPULSE_AUDIT_VERIFICATION.md` does **not** yet exist in the repository. |

**Verification of commit `eb14d9efdfc1973cc7a522249affccd4efdb53fe`:**
The current `HEAD` hash matches this commit exactly, confirming it is the current commit (not merely an ancestor).

---

## 2. `src/routing/route_controller.py` – Exact Implementation Details

| Feature | Location (file:line) | Summary |
|---------|---------------------|---------|
| **Main journey loop** | `src/routing/route_controller.py:164‑170` | `while step < computed_max_hops:` … checks destination, then proceeds. |
| **Traffic‑update handling** | `src/routing/route_controller.py:171‑210` | Executes once when `step == traffic_update_step`. Computes `remaining_old_time` and `remaining_new_time`, calculates `absolute_saving` & `relative_saving`. If both thresholds met (`>= self.reroute_threshold_s` **and** `>= self.reroute_threshold_pct`) `reroute_count += 1`; otherwise reverts `current_weights` and `current_speeds`. |
| **Threshold calculations** | Same block (lines 195‑204). Uses `self.reroute_threshold_s` (seconds) and `self.reroute_threshold_pct` (percent). |
| **Weight & speed restoration** | Lines 208‑209 – restores `current_weights` = `old_weights`; `current_speeds` = `old_speeds` when thresholds not met. |
| **Two‑edge decision invocation** | `src/routing/route_controller.py:212‑221` – calls `self.selector.decide_next_edge(...)` and records latency. |
| **Dead‑end / missing decision handling** | `src/routing/route_controller.py:226‑294` – if `decision.is_dead_end` or no edge, enters recovery: first tries forward Dijkstra fallback (lines 228‑236), else backtrack (lines 257‑284). |
| **Reverse‑edge lookup (backtrack)** | Lines 259‑264 – constructs `reverse_edge = (curr_node, prev_node, 0)` (lane‑id placeholder). Looks up only this key in `self.edge_lengths`. |
| **Cycle detection** | `src/routing/route_controller.py:299‑330` – counts visits (`node_visits`). If exceeds `self.max_node_visits`, triggers Dijkstra fallback and creates a new `TwoEdgeDecisionStep` with the first edge of the fallback path. |
| **Dijkstra fallback (used for dead‑end, cycle)** | Lines 228‑236 (dead‑end) and 303‑311 (cycle) – calls `custom_dijkstra(...)` and extracts the first edge (`rec_edge`). |
| **Reroute event counting** | Line 205 – `reroute_count += 1` only when both thresholds satisfied. |
| **Maximum‑hop termination** | Post‑loop block `src/routing/route_controller.py:346‑349` – if not `is_success` and `step >= computed_max_hops`, sets `termination_reason = "Maximum hops exceeded …"` . |

---

## 3. Verification of Disputed Claims

| Claim | Code Evidence (file:line) | Verdict |
|-------|---------------------------|----------|
| **A. Backtracking searches all lane IDs** | `reverse_edge = (curr_node, prev_node, 0)` (lines 259‑260). Only lane `0` is considered; no iteration over other lane IDs. | **INCORRECT** – backtrack assumes lane 0 only. |
| **B. Cycle fallback avoids the edge that caused the cycle** | Cycle block selects `rec_edge = fallback_res.edge_path[0]` without checking whether this edge is the one that formed the cycle. | **NOT VERIFIED** – implementation may re‑select the same edge. |
| **C. Fallback terminates safely when no alternative path exists** | Backtrack `else` block (lines 289‑290) sets `termination_reason` and `break`s; dead‑end forward fallback also falls back to `break` when no Dijkstra path (lines 292‑293). | **VERIFIED** – controller exits loop with a clear termination reason. |
| **D. `reroute_events` increments only when a *different* edge is actually selected** | Increment occurs at line 205 **before** any edge is examined; it counts any accepted traffic update regardless of whether the selected edge changes. | **INCORRECT** – `reroute_events` may increment even if the route does not change. |
| **E. Rejected traffic update restores both original weights **and** original speeds** | Lines 208‑209 restore `current_weights` and `current_speeds` from saved copies. | **VERIFIED**. |
| **F. Controller distinguishes between accepting a traffic update **and** physically changing the route** | No separate flag; only `reroute_count` is incremented. The controller does not record whether the selected edge changed after the update. | **NOT VERIFIED** – no explicit distinction. |

---

## 4. Independent Test Execution

### 4.1 Compilation
```
python -m py_compile src/routing/route_controller.py
```
*Exit code:* `0` (no syntax errors). 
*Output:* *(none)*

### 4.2 Running `tests/test_two_edge_routing.py`
```
pytest -q tests/test_two_edge_routing.py
```
**Exit code:** `1` (failures). 
**Full output (truncated in transcript, full file at `.../steps/624/output.txt`):**
```
......F..FFFF.F.F                                                        [100%]
================================== FAILURES ===================================
... (multiple failures, including NameError for LimitedLookaheadEvaluator and dead‑end failures) ...
7 failed, 10 passed in 3.54s
```
### 4.3 Running the entire test suite
```
pytest -q
```
*Exit code:* `1` (overall failures). 
*Output:* Same failures as above (7 failing tests).

### 4.4 Test Assertions – Do They Validate Their Objectives?
| Test | Intended Goal | Observation |
|------|---------------|-------------|
| `test_limited_lookahead_evaluation` | Verify that look‑ahead strategy prefers edge C over B. | Fails due to `NameError` – `LimitedLookaheadEvaluator` not imported/defined, so the strategy never runs. |
| `test_dead_end_recovery` | Ensure dead‑end triggers Dijkstra fallback and success. | Fails: controller reports *unrecoverable dead‑end* because backtrack reverse edge uses lane 0 only (no reverse edge exists). |
| `test_sequential_journey_with_dynamic_traffic_update` | Verify that a traffic update with thresholds 0 causes a reroute to the faster path. | Fails: after update, controller still follows original edge B; `reroute_events` increments but route unchanged. |
| `test_traffic_update_accepts_and_changes_route` | Same as above (different test layout). | Fails for same reason – route does not change. |
| `test_lookahead_uses_updated_weights_after_reroute` | Look‑ahead decision should use **updated** weights after a successful traffic update. | Fails due to `NameError` in the selector (same missing evaluator). |
| `test_backtrack_recovery_records_reverse_movement` | Verify backtrack records reverse movement when a dead‑end is encountered. | Fails because backtrack only checks lane 0, missing reverse edge, leading to termination. |
| `test_complete_sequential_journey_matches_dijkstra_on_diamond` | Full journey should match Dijkstra baseline on a diamond graph. | Fails (reported in the full suite) – likely caused by the same backtrack/traffic‑update issues. |

Overall, the tests **do not** currently validate the intended behavior because of missing imports (`LimitedLookaheadEvaluator`) and logical shortcomings in backtrack, cycle handling, and reroute counting.

---

## 5. ML Model & Benchmark Claims
| Item | Actual Repository Evidence |
|------|----------------------------|
| **Dataset dimensions** | `datasets/traffic_structured_v1.parquet` (size ≈ *not inspected here*); the repository contains CSV/Parquet files, but no script prints row/column counts. No explicit dimensions listed in code. |
| **Model file** | `models/speed_predictor.joblib` (binary LightGBM model) and `models/feature_metadata.json`. No training script executed; evaluation metrics are only described in `docs/phase7_ml_speed_prediction.md` (no numeric values). |
| **Baseline metrics** | No CSV or JSON file with baseline travel‑time numbers. Benchmark scripts (`src/experiments/benchmark_runner.py`) exist but not run in this verification. |
| **Benchmark success rates / travel‑time comparisons** | No generated CSVs in `results/` contain per‑algorithm travel‑time tables; only dashboard JSON runs (`results/dashboard_runs/...`). No explicit numbers extracted. |
| **Missing evidence** | The repository lacks concrete numeric evidence for model accuracy (e.g., RMSE) or benchmark success rates. |

**Conclusion:** The claims about model performance and benchmark numbers cannot be corroborated from the current files; they are undocumented or absent.

---

## 6. Pygame Integration Check
All files under `src/pygame_simulation/` were inspected (listing in git‑ls‑files). 

| Observation | Evidence |
|-------------|----------|
| **RouteController used?** | No import of `src.routing.route_controller.RouteController` appears in any Pygame module (`main.py`, `simulation_controller.py`, etc.). The simulation uses its own `SimulationController` and `VehicleSprite` without consulting the sequential controller. |
| **Vehicle movement follows routing decisions?** | Vehicle moves along a *hard‑coded* path defined in `scenario_manager.py`. Routing decisions are not queried from `RouteController`. |
| **OSM graph loading?** | `scenario_manager.py` loads custom synthetic graphs; there is no loading of the full OSM graph (`datasets/.../bhubaneswar_drive.graphml`). |
| **Traffic updates affect vehicle?** | No mechanism in the simulation to receive or apply traffic‑weight updates. |
| **Edge weights used?** | Edge traversal times are taken from the scenario’s static `edge_lengths`; no reference to the predictive model or dynamic weights. |

**Verdict:** The Pygame simulation currently **does not** integrate the actual `RouteController`, does not use real OSM data, nor does it react to traffic updates. It functions as an isolated demo.

---

## 7. Final Discrepancy Table

| Earlier Report Claim | Actual Repository Evidence | Verdict | Required Action |
|----------------------|---------------------------|--------|-----------------|
| *RouteController implements backtrack across all lane IDs* | Backtrack creates `reverse_edge = (curr_node, prev_node, 0)` only (lines 259‑260). | **INCORRECT** | Update backtrack to search `self.edge_lengths` for any matching `(curr_node, prev_node, *)`. |
| *Cycle fallback never selects the edge that caused the cycle* | Cycle fallback selects `fallback_res.edge_path[0]` without exclusion (lines 304‑306). | **NOT VERIFIED** | Add check to avoid the edge that leads to the cycle, or use a different fallback strategy. |
| *Fallback terminates safely when no alternative* | Backtrack dead‑end `else` sets `termination_reason` and `break`s (lines 289‑293). | **VERIFIED** | None. |
| *`reroute_events` only increments on a genuine route change* | Increment occurs at line 205 solely based on thresholds, regardless of edge change. | **INCORRECT** | Increment only after confirming `selected_edge` differs from pre‑update edge. |
| *Rejected traffic update restores both weights and speeds* | Lines 208‑209 restore both dictionaries. | **VERIFIED** | None. |
| *Controller distinguishes traffic‑update acceptance vs. actual reroute* | No distinct flag; only `reroute_count`. | **NOT VERIFIED** | Add a boolean `route_changed` flag or similar. |
| *Two‑edge selection works with Lookahead* | `LimitedLookaheadEvaluator` is not imported/defined; tests raise `NameError`. | **INCORRECT** | Import or implement `LimitedLookaheadEvaluator` (e.g., from `src.routing.lookahead`). |
| *Dead‑end recovery works via Dijkstra* | Backtrack fails due to lane‑id assumption; dead‑end test fails. | **INCORRECT** | Fix reverse edge lookup; ensure fallback path is used. |
| *Traffic‑update test expects route change when new route is slower* | Test provides slower new route but expects success; implementation correctly rejects (thresholds not met) – test asserts changed route, causing failure. | **INCORRECT** | Adjust test data to make new route faster, or revise thresholds/logic. |
| *Pygame uses real RouteController and traffic predictions* | No imports or usage of `RouteController`; uses static demo graphs. | **INCORRECT** | Refactor simulation to call `RouteController` for each decision and feed live weights/predictions. |
| *Benchmark CSVs contain travel‑time comparisons* | No such CSVs are present; only dashboard JSON runs. | **MISSING** | Generate and commit benchmark result files or update documentation to reflect available artefacts. |
| *ML model evaluation metrics are recorded* | No metric files (e.g., RMSE) are stored in the repo. | **MISSING** | Add evaluation script output (e.g., `model_evaluation.json`) to the repository. |

---

*Prepared by Antigravity on 2026‑11‑19.*