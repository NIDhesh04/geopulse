# GeoPulse Phase 3 — Historical Traffic Replay and Dynamic Edge-Cost Engine

**Completed:** 22 November 2026  
**Scope:** Deterministic replay of saved Phase 7 predictions and dynamic travel-time costs on a working copy of the Bhubaneswar OSM graph.

## Summary

Phase 3 adds an hourly replay service for `results/phase7_predictions.parquet` and a dynamic edge-cost updater built on the existing `GraphWeightManager`. Replay results are historical saved predictions; the service does not run LightGBM inference. A caller must request an exact UTC hour. Missing hours raise an error instead of silently substituting a nearby hour.

The updater maps valid segment speeds to directed OSM edges, updates reverse edges only for `DYNAMIC_BIDIRECTIONAL` mappings, and leaves all other edges at their static highway-class fallback costs. It returns a working graph copy and diagnostics. The source graph is not changed.

This phase did not change Dijkstra or Sequential Two-Edge Selection, generate a synthetic traffic dataset, retrain the model, or measure routing improvement. The real-network run validates replay and edge-cost construction only.

## Files inspected

- `datasets/traffic_structured_v1.parquet`
- `datasets/traffic_v1.duckdb`
- `data/processed/traffic_to_osm_mapping_final.parquet`
- `data/raw/osm/bhubaneswar_drive.graphml`
- `models/speed_predictor.joblib`
- `models/feature_metadata.json`
- `results/phase7_predictions.parquet`
- `src/cloud/model_service.py`
- `src/routing/traffic_weights.py`
- Existing graph-loading utilities and traffic/routing tests, including `tests/test_phase8_routing.py`, `tests/test_phase9_rerouting.py`, and `tests/test_phase11_integration.py`.

The inspected artifacts contain 275,800 traffic rows across 17 columns, 700 traffic segments, 30,800 saved prediction rows in 44 hourly frames, and a directed Bhubaneswar `MultiDiGraph` with 18,260 nodes and 46,679 edges. The mapping has 599 `DYNAMIC`, 92 `DYNAMIC_BIDIRECTIONAL`, and 9 `STATIC_FALLBACK` rows.

## Files created and modified

### Created

- `src/traffic/replay.py` — exact-hour prediction replay and frame data structure.
- `src/traffic/__init__.py` — exports the replay service and error type.
- `scripts/run_historical_traffic_replay.py` — command-line replay and in-memory graph update.
- `tests/test_traffic_replay.py` — replay and edge-cost regression tests.

### Modified

- `src/routing/traffic_weights.py` — mapping validation, invalid-speed handling, sensor aggregation, diagnostics, and working-copy edge-cost updater.
- `src/routing/__init__.py` — exports edge-cost update classes.
- `src/cloud/model_service.py` — delegates saved prediction retrieval to exact-hour replay and removes nearest-hour substitution.
- `src/edge/messages.py` — adds explicit origin and target-valid timestamps to model update messages.

No dataset, GraphML, model, or historical experiment artifact was changed. The Phase 1 audit files that were already uncommitted remain untouched.

## Data flow and behavior

1. `HistoricalTrafficReplay` loads the saved prediction Parquet and validates its required fields: `timestamp`, `traffic_segment_id`, and `predicted_speed`.
2. The artifact's per-segment source timestamps have small offsets around the hour. The loader assigns them to an hourly UTC origin bucket only when the offset is within five minutes, and retains each raw source timestamp in the returned frame.
3. The caller selects an exact hourly UTC `origin_timestamp`. The frame exposes `target_valid_timestamp` one hour later, matching the saved model's next-hour forecast contract.
4. `advance()` moves exactly one hour. If an interior hour is absent, it raises `MissingReplayTimestampError`; it does not skip the gap. It returns `None` after the final stored frame.
5. `TrafficEdgeCostUpdater` passes frame speeds to `GraphWeightManager`, calculates edge weights, and updates a copy of the graph in memory.

The resulting graph edges carry `travel_time_seconds`, `effective_speed_kmh`, and `traffic_cost_source` attributes. The updater also returns weight and speed dictionaries, the set of dynamic edges, and timestamped coverage diagnostics.

### Speed validation and mapping policy

- Valid positive speeds are clipped to the model-supported range of 3–120 km/h before aggregation.
- Missing, nonnumeric, NaN, infinite, zero, and negative predictions are invalid. Affected edges retain their static fallback costs.
- Multiple valid sensors mapped to one directed edge are combined by deterministic arithmetic mean.
- Exact duplicate mapping rows are deduplicated, so a repeated row cannot overweight a sensor.
- `DYNAMIC` applies only to its directed edge. `DYNAMIC_BIDIRECTIONAL` applies to its mapped edge and existing reverse edge records. `STATIC_FALLBACK` never applies the segment prediction.
- Unmapped edges remain at the existing static highway-class fallback speed.
- Every final edge cost is checked to be finite and strictly positive. Invalid OSM lengths fail explicitly during weight-manager initialization.

Travel time uses GraphML edge length and effective speed:

```text
travel_time_seconds = length_meters / (speed_kmh * 1000 / 3600)
```

`currentTravelTime` from the traffic dataset is not used as an edge cost.

## Real Bhubaneswar replay evaluation

Command executed:

```powershell
.\.venv\Scripts\python.exe scripts/run_historical_traffic_replay.py --start 2026-01-15T14:00:00Z --steps 3
```

The command replayed three consecutive origin hours and built a working graph for each frame:

| Origin timestamp (UTC) | Target-valid timestamp (UTC) | Directed edges | Dynamic edges | Static fallback edges | Unmapped edges | Missing predictions | Invalid predictions | Dynamic coverage |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-01-15 14:00 | 2026-01-15 15:00 | 46,679 | 690 | 45,989 | 45,984 | 0 | 0 | 1.4782% |
| 2026-01-15 15:00 | 2026-01-15 16:00 | 46,679 | 690 | 45,989 | 45,984 | 0 | 0 | 1.4782% |
| 2026-01-15 16:00 | 2026-01-15 17:00 | 46,679 | 690 | 45,989 | 45,984 | 0 | 0 | 1.4782% |

The 45,989 static fallback edges include the 45,984 unmapped edges and 5 explicitly mapped static fallback edges. Thus each frame accounts for all 46,679 graph edges. The predictions covered all 700 expected segments in these frames. The source graph file was loaded read-only; edge costs were written only to returned in-memory copies.

The replay loader also read the full saved prediction artifact and verified 44 distinct hourly frames, from `2026-01-15 08:00 UTC` through `2026-01-17 03:00 UTC`. The real graph updater was exercised on the three hours listed above, not all 44 hours.

## Tests and verification

New regression suite:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_traffic_replay.py -q
```

Result: **21 passed**. Coverage includes saved-artifact loading, chronological advancement, timestamp semantics, exact-hour and gap errors, missing and duplicate predictions, direction-aware mapping, duplicate mapping aggregation, static fallback, invalid speeds, clipping, travel-time calculation, positive finite weights, coverage diagnostics, determinism, CloudModelService replay, and source-graph immutability.

Full test suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Result: **103 passed in 44.11 seconds**.

Compilation and whitespace checks also passed:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src/traffic src/routing src/cloud/model_service.py src/edge/messages.py scripts/run_historical_traffic_replay.py tests/test_traffic_replay.py
git diff --check
```

The test suite generated two timestamped dashboard demo files as side effects; those two files were removed after the run. No historical result files were removed or overwritten.

## Run locally

From the repository root, replay one frame:

```powershell
.\.venv\Scripts\python.exe scripts/run_historical_traffic_replay.py --start 2026-01-15T14:00:00Z
```

Replay several consecutive hours:

```powershell
.\.venv\Scripts\python.exe scripts/run_historical_traffic_replay.py --start 2026-01-15T14:00:00Z --steps 3
```

Optional `--graph`, `--mapping`, and `--predictions` arguments select alternate existing inputs. The command prints one JSON diagnostics record per frame and does not write a graph or prediction artifact.

## Limitations and conclusion

- Dynamic costs cover only 690 of 46,679 directed edges in the evaluated timestamps (**1.48%**). Most of the network uses static fallback costs; this is not network-wide dynamic traffic coverage.
- The replay is a deterministic playback of saved historical model outputs. It is not live ingestion or live model inference.
- `target_valid_timestamp` is represented as the canonical hourly origin plus one hour. The per-segment raw source origin timestamps are retained because the artifact has small capture-time offsets.
- This evaluation validates replay and edge-cost construction, not route quality, journey-time reduction, or superiority over static or dynamic Dijkstra.
- No synthetic traffic dataset was generated. Toy values used in unit fixtures are test-only and are not presented as observations.
- No Git commit or push was made.

Phase 3's completion criterion is met for the existing Bhubaneswar graph and saved prediction artifact: an exact replay frame can be loaded, applied to a working graph copy, and inspected through explicit coverage diagnostics. The next routing phase should retain the reported static fallback and low dynamic coverage as part of every evaluation.
