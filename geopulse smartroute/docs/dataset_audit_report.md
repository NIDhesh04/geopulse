# GeoPulse: Bhubaneswar Dataset and Routing Audit

**Status:** Audit complete and routing audit rechecked on 2026-10-07.  
**Scope:** Supplied package at `geopulse/geopulse smartroute/archive.zip`, matching project snapshots, and the related Bhubaneswar OSM routing assets.  
**Integrity:** The ZIP was inspected without extraction. DuckDB was queried read-only. The deleted Git-tracked GraphML was read from a temporary copy of its committed blob. No dataset or source file was changed; no ML model was trained; no synthetic values were generated.

## Executive summary

The canonical analytical table is the processed 17-column `traffic_structured_v1.parquet` snapshot: 275,800 segment-hour grid rows, 700 segments, and 394 consecutive hourly buckets spanning 16.375 days. There are 246,399 observed rows (89.3397%) and 29,401 explicit missing cells. Missingness is overwhelmingly at the start: 98.8068% of all missing cells occur on Jan 1-2, and 99.9966% occur on Jan 1-3. Jan 4 onward is 99.9996% complete, with one missing cell.

The data supports a cautious next-hour speed prediction pilot: all 700 segments have at least 239 consecutive observed hours, and the verified lag-24 design yields 207,893 usable samples under the existing chronological split. This is a short-window result, not evidence of seasonal or annual generalization. No model has been trained.

The full directed Bhubaneswar OSM graph is connected and can support static-cost routes. It is deleted from the current working tree but remains in Git `HEAD`; the routing audit was reproduced from that committed graph without restoring it. The traffic mapping is the blocker for dynamic routing: the largest improved best-edge component covers only 25/700 traffic segments (3.57%), or 59/700 (8.43%) when expanding all supplied OSM IDs. Across 100 sampled routes on the full graph, median dynamic-edge coverage is 11.52%.

Both supplied travel-time columns fail the documented physical consistency check. Do not use them as routing costs. Current evidence supports a prediction pilot and a static OSM routing baseline, but not a citywide GeoPulse dynamic-routing benefit claim.

## 1. Package inventory and provenance

At initial inspection, the supplied package folder contained `archive.zip`; the report and machine-readable summary are now saved in its `docs/` subfolder. The ZIP contains five members, passes CRC validation, and was not extracted.

| File | Type / size | Rows and columns | Role |
|---|---|---:|---|
| `archive.zip` | ZIP, 3,089,387 B | 5 members | Supplied package |
| `DATA_DICTIONARY.md` | Markdown, 3,715 B | Documentation | Field units and meaning |
| `SNAPSHOT_NOTES.md` | Markdown, 446 B | Documentation | Processing notes; snapshot date remains `YYYY-MM-DD` |
| `traffic_bhubaneswar.csv` | CSV, 27,441,756 B | 275,800 x 15 | Derived feature export; provenance incomplete |
| `traffic_structured_v1.parquet` | Parquet, 612,145 B | 275,800 x 17 | Recommended canonical processed table |
| `traffic_v1.duckdb` | DuckDB, 11,808,768 B | `traffic`, 275,800 x 17 | Query mirror of the processed table |

The archived Parquet and DuckDB are byte-identical to `geopulse/datasets/traffic_structured_v1.parquet` and `geopulse/datasets/traffic_v1.duckdb`. Parquet and DuckDB rows agree after timestamp timezone/precision normalization. The CSV has the same segment-hour keys and shared measurement values, but adds derived calendar/congestion columns and omits timestamp, closure, OSM, road-type, length, and coordinate fields. Treat these as three representations of one dataset, not three independent sources. No original TomTom API response or complete transformation log is present.

The current worktree has 12 tracked notebook/OSM-validation files marked deleted, including `notebooks/bhubaneswar_drive.graphml`. I left those deletions untouched. The Bhubaneswar GraphML is available in Git `HEAD` as blob `da960993ca28ce4443c674eb98799c86d0f3934f` (18,569,800 B); that committed version was used from a temporary copy for the recheck. The Jaipur GraphML is a different city and was not used.

## 2. Schema and documented meanings

The data dictionary documents speeds in km/h, travel times in seconds, lengths in metres, UTC timestamps, `hour` as the hourly alignment key, and `lat`/`lon` as segment centroids. `timestamp` is the actual observation time and is not itself hourly. Missing grid cells are explicit null placeholders; no interpolation is documented.

| Field | Type / distinct values | Nulls | Meaning / audit note |
|---|---|---:|---|
| `segment_id` | int64 / 700 | 0 | Segment key, IDs 0-699 |
| `hour` | UTC timestamp / 394 | 0 | Hourly alignment bucket |
| `timestamp` | UTC timestamp / 509 non-null | 29,401 | Actual API observation time |
| `currentSpeed` | float64 / 53 | 29,401 | Observed speed, km/h |
| `freeFlowSpeed` | float64 / 35 | 29,401 | Free-flow reference speed, km/h; time-varying on 671 segments |
| `currentTravelTime` | float64 / 450 | 29,401 | Documented seconds; fails physical consistency check |
| `freeFlowTravelTime` | float64 / 134 | 29,401 | Documented seconds; fails physical consistency check |
| `confidence` | float64 / 6,458 | 29,401 | Confidence score, range 0.505346-1.0 |
| `is_observed`, `is_missing` | bool / 2 each | 0 | Complementary observation/missing flags |
| `roadClosure` | nullable bool / 2 observed values | 29,401 | Closure flag; availability time is undocumented |
| `osmid` | string / 266 composite strings | 29,401 | Some segments contain multiple OSM IDs |
| `road_name` | float64 / 350 | 29,401 | Numeric identifier, not a street name |
| `road_type` | string / 3 | 29,401 | `primary`, `secondary`, `trunk` |
| `length_m` | float64 / 663 | 29,401 | Segment length, 60.37-3,016.998 m |
| `lat`, `lon` | float64 / 662, 663 | 29,401 each | Centroid coordinates, not endpoints or geometry |

The CSV adds `hour_of_day`, `day_of_week`, `is_weekend`, `speed_ratio`, `congestion_level`, and `is_congested`. `is_congested` is false on all 29,401 missing rows, so it must always be masked by `is_observed`.

## 3. Temporal coverage and missingness

The 394 UTC buckets are one hour apart and span 393 elapsed hours. In local time they run from 2026-01-01 00:30 IST to 2026-01-17 09:30 IST. There are no missing global hour buckets. The 509 actual `timestamp` values are not hourly aligned. Use `hour` for the time grid and convert UTC to `Asia/Kolkata` only for local calendar features.

| IST date | Expected cells | Observed | Missing | Coverage |
|---|---:|---:|---:|---:|
| Jan 1 | 16,800 | 350 | 16,450 | 2.0833% |
| Jan 2 | 16,800 | 4,200 | 12,600 | 25.0000% |
| Jan 3 | 16,800 | 16,450 | 350 | 97.9167% |
| Jan 4-11 | 16,800/day | 16,800/day | 0/day | 100% each day |
| Jan 12 | 16,800 | 16,799 | 1 | 99.9940% |
| Jan 13-16 | 16,800/day | 16,800/day | 0/day | 100% each day |
| Jan 17 | 7,000 (10 buckets) | 7,000 | 0 | 100% |

Overall coverage is 246,399/275,800 = **89.3397%**. Jan 1-2 contain 29,050 missing cells (**98.8068% of all missing**); Jan 1-3 contain 29,400 (**99.9966%**). Only one missing cell occurs after Jan 3. Excluding Jan 1-3 gives 225,399/225,400 = **99.9996%** coverage across 322 hours. Nothing was removed or filled.

Each of the 700 segments has 394 grid rows. Observed counts are 345 for 350 segments, 358 for one, and 359 for 349. Continuity counts are 350 segments with one observed run, 349 with two, and one with three. Longest-run lengths are 239-358 hours (median 345); all segments have at least 24 continuous hours. For segments with two runs, median run length is 179.5 hours and the largest elapsed gap is 36 hours. These data permit lag construction while still requiring an explicit missingness mask.

## 4. Segment, road and traffic quality

Stable metadata (`osmid`, numeric `road_name`, `road_type`, `length_m`, `lat`, `lon`) does not vary within segment. `freeFlowSpeed` and `freeFlowTravelTime` vary on 671/700 segments, so do not assume they are static or available in advance.

| Road type | Segments | Observed rows | Mean current speed | Mean free-flow speed |
|---|---:|---:|---:|---:|
| primary | 334 | 117,651 | 35.639 km/h | 37.666 km/h |
| secondary | 275 | 96,331 | 27.245 km/h | 29.357 km/h |
| trunk | 91 | 32,417 | 41.570 km/h | 42.534 km/h |

For 246,399 observed rows, `currentSpeed` ranges 1-54 km/h (mean 33.137, median 32, SD 8.970); `freeFlowSpeed` ranges 16-55 km/h (mean 35.058, median 34, SD 8.519). There are no zero/negative values, no current speed above free-flow, and no extreme speed threshold violations. The ratio `currentSpeed/freeFlowSpeed` has mean 0.9438 and equals 1 in 166,828 rows (67.71%), indicating a ceiling-heavy distribution. `roadClosure=true` occurs in 25,374 observed rows (10.30%).

The CSV congestion fields are derived, not independent ground truth: `speed_ratio` equals current speed divided by free-flow speed, and `is_congested` is exactly ratio < 0.7. Categories use inferred, undocumented thresholds. Prefer the continuous ratio (or `1 - ratio`) as a descriptive proxy and label it as derived. Do not infer traffic volume, density, or vehicle counts from `probeCount`; no such field or documented probe semantics appears in this package.

Five segments have nearly constant speed (SD <= 0.1), while 123 never fall below a speed/free-flow ratio of 0.8. Hourly average speed varies from about 35.13 km/h at midnight to 28.02 km/h at 18:00. Per-segment autocorrelation is estimable for 695 segments: lag-1 mean/median 0.575/0.678; lag-3 0.175/0.189; lag-6 0.014/0.012; lag-12 -0.397/-0.442; lag-24 0.585/0.661. This shows short-window temporal association, not broad generalization evidence.

There are no duplicate traffic rows or duplicate `(segment_id, hour)` keys. `is_observed` and `is_missing` are complementary, and finite speed availability agrees with `is_observed` on every row.

## 5. Travel-time validation

The dictionary units imply `expected_seconds = 3.6 * length_m / speed_kmh`. Against that independent calculation:

| Field | MAE | Median absolute error | Correlation | Within 10% of physical estimate |
|---|---:|---:|---:|---:|
| `currentTravelTime` | 1,440.01 s | 1,551.29 s | -0.1334 | 0.1457% |
| `freeFlowTravelTime` | 1,351.83 s | 1,376.72 s | -0.1249 | 0.1457% |

Both stored fields fail the documented physical consistency check. For example, 3,017 m at 54 km/h implies about 201 seconds, while a stored current travel time can be around 1,376 seconds. Do not use either stored travel-time column as routing cost. A derived travel time is appropriate only after the mapped edge length, direction, speed, and availability time are validated.

## 6. OSM matching and routing-network audit

The traffic table alone cannot define a directed graph: it has centroids, but no provider segment geometry, endpoints, or direction. The related Bhubaneswar GraphML was rechecked from its committed Git blob in a temporary workspace. No centroid-proximity tolerance is treated as an endpoint connection.

| Representation | Nodes | Directed edges | Weak components | Largest component |
|---|---:|---:|---:|---:|
| Full Bhubaneswar OSM graph | 18,260 | 46,679 | 1 | 18,260 nodes; largest SCC 18,230 nodes (99.84%) |
| Improved best-edge traffic mapping | 869 | 651 | 221 | 20 nodes, 19 edges, 25/700 segments (3.57%) |
| All graph edges for supplied OSM IDs | 1,041 | 1,102 | 44 | 101 nodes, 100 edges, 59/700 segments (8.43%) |

All 700 segments received an OSM-ID-supported candidate in the improved ranking. Candidate centroid-to-edge distances have median 0.135 m, p95 6.435 m, and maximum 87.490 m; broad road-class agreement is 100%. These are candidate-ranking results, not independent ground-truth validation: OSM-ID evidence and road class are inputs to the ranking, and the provider polyline/direction is absent. The 648 unique mapped undirected endpoint pairs cover only 2.64% of the full undirected OSM network.

Of 87 segments with multiple OSM IDs, all IDs appear in GraphML and 85 ID groups are topologically connected, but none has a single connected geometry component. Combined OSM geometry length divided by traffic `length_m` has median 2.57 and maximum 31.99. This is suspicious length compatibility and requires segment-level review. The previous mapping had 55 repeated directed endpoint pairs; the improved ranking still has 49. A nearby-centroid geometry screen classified 47 likely duplicate pairs among 525 pairs, but these are proxy classifications, not confirmed duplicate provider records. Do not delete or merge them without independent evidence.

A feasibility sample of 100 ordered OD pairs on the full OSM graph produced 100 successful static-length routes. Median route dynamic-edge coverage was 11.52% (mean 14.07%); only 17% of sampled routes exceeded 25% coverage and 3% exceeded 50%. This is not a route-benefit experiment. Static fallback on the full network is technically possible, but the currently mapped traffic subset is too sparse, fragmented, and direction-ambiguous for citywide dynamic-routing claims.

## 7. Leakage and prediction feasibility

For `X(t) -> currentSpeed(t+1)`, safe candidate features are speeds available at or before time `t`, prior-only rolling summaries, static metadata, and calendar features known at forecast time. Same-time `currentSpeed` is the target; same-time ratio/congestion fields derive from it; current travel time is target-related. Shift all target-derived features. Verify availability time for `freeFlowSpeed`, confidence, closure and observation flags. Recompute local calendar features in IST rather than using CSV calendar fields derived in UTC.

On the 322-hour Jan 4-Jan 17 window, strict past-only features `[speed(t), speed(t-1), speed(t-3), speed(t-6), speed(t-12), speed(t-24)]` yield these verified sample counts:

| Chronological partition | Target-hour indices | Samples |
|---|---:|---:|
| Train | 25-224 | 139,994 |
| Validation | 225-272 | 33,599 |
| Test | 273-321 | 34,300 |
| **Total** | | **207,893** |

The sample shares are 67.34/16.16/16.50%; the time cut points are approximately 70/15/15% of the full clean window, with the initial 24-hour lag warm-up reducing training labels. One missing cell invalidates seven target windows under these particular lag offsets. Do not random-split rows. A next-hour prediction pilot is feasible; the 16.375-day total duration and roughly 13.4 near-complete days do not support annual/seasonal claims, and one-step performance does not establish recursive multi-step performance. No model was trained.

## 8. Synthetic-data requirement

Synthetic data is not needed for speed prediction or replay of held-out real observations. The 25,374 observed `roadClosure=true` rows may provide real events after their timing and mapped edges are validated. If a controlled rerouting demonstration later needs an incident, use a separate runtime-only speed perturbation, clearly labelled `data_source="synthetic"` and `synthetic_type="incident_perturbation"`; do not append it to the real dataset. No synthetic data was created.

## 9. Recommended preprocessing and engineering decision

1. Use `traffic_structured_v1.parquet` as the canonical processed table; retain DuckDB as its exact query copy and CSV as a derived export. There is no original API capture to designate as raw.
2. Keep `archive.zip` immutable. Mask targets/features by `is_observed`; never treat missing-row `is_congested=false` as a negative label. Do not interpolate or fabricate values.
3. Use Jan 4 onward for a first model pilot, preserve UTC timestamps, derive IST calendar fields explicitly, and construct strictly past-only segment lags with chronological splits.
4. Use speed ratio only as a derived descriptive proxy. Exclude stored travel-time fields from routing cost until their units/alignment are resolved.
5. Review the tracked GraphML deletion before restoring it. Independently validate OSM edge identity, direction, traffic length compatibility, and dynamic coverage. Use full OSM topology plus explicit static fallback only for a clearly scoped baseline; report per-route dynamic coverage.

**A. Dataset:** `traffic_structured_v1.parquet`.  
**B. Raw/original:** No original API response is supplied; the ZIP is the immutable package, while Parquet/DB are processed snapshots and CSV is derived.  
**C. Derived:** IST calendar features, lags, continuous speed ratio, and physically calculated travel times after edge validation.  
**D. Synthetic:** None required now; optional separate incident overlay only for a controlled demo.  
**E. Preprocessing:** Preserve missing masks, use observed values, omit Jan 1-3 from the first pilot, use UTC/IST correctly, shift lags, and split chronologically.  
**F. Graph:** The full OSM graph is connected and supports static routes; the traffic mapping is not sufficiently connected or direction-validated for citywide dynamic routing.  
**G. Prediction:** A short-window next-hour speed pilot is feasible; this audit did not train it.  
**H. Next step:** Review the tracked deletion and recover/version the committed graph, then independently validate traffic-edge mapping, direction, length, and coverage before dynamic-routing evaluation.

**Final recommendation:** Proceed with a narrowly scoped next-hour speed-prediction pilot after review. A static OSM routing baseline is possible with explicit fallback costs. Defer dynamic-routing benefit claims until edge mapping and travel-time consistency are resolved and measured dynamic coverage is adequate for the stated route scope.

