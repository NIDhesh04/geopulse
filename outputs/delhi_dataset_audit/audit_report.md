# Delhi traffic dataset scientific audit

Read-only ZIP analysis; the source archive was not extracted or changed. No machine-learning models were trained.

Archive: `C:\Users\Mohit sharma\Desktop\7th sem\new major project\delhi dataset.zip` (66,158,375 bytes); 33 files; 20 daily GeoJSONs.

## Package inventory

Full per-file row/feature counts, columns, purposes, and compressed/uncompressed sizes are in `file_inventory.csv`.

## Documentation and probe semantics

The README describes hourly road probe counts for Aug 11-30, 2024. Each daily GeoJSON has a metadata feature and road-segment features with `segmentProbeCounts` entries indexed by `timeSet` and `dateRange`; metadata sets `zoneId=Asia/Kolkata`, `probeSource=ALL`, and 24 intervals from 00:00-01:00 through 23:00-24:00. The documentation does not define what one probe represents. **Semantics unresolved**: do not label counts as vehicles, volume, density, GPS fixes, or congestion without provider documentation/validation.

## Traffic target assessment

`probeCount` is present as a nested hourly count for each road-segment feature, but it is not a validated speed or travel-time target. Segment-level `speedLimit` is static metadata (its unit is undocumented in the row schema); no observed speed or segment-hour travel time is present. City/year aggregate JSON and weekday CSVs do contain average speed/travel-time/congestion summaries, but they are city/urban summaries rather than segment-hour targets. The `congestion_level` field in annual JSON has no documented scale (for example, values 147 and 123 coexist with separate average percentages 33 and 29).

## Temporal and segment structure

Date files span 2024-08-11 through 2024-08-30 (20 calendar days). Time buckets are hourly by `timeSet`, labeled as intervals in Asia/Kolkata; exact sample instant/start-vs-end convention is not specified. Expected segment-hour cells for the segments present on each date: 11,970,240; unique bucket entries found: 11,970,240; missing buckets: 0 (0.0000%). Duplicate segment-ID rows: 0; duplicate segment-hour occurrences: 0.

Unique segment IDs: 24,938; segment-days: 498,760; IDs present all 20 days: 24,938; IDs reappearing after a day-level absence: 0. ID and geometry stability counts are in `summary.json` and `segment_persistence.csv`.

| Persistence category | Segment IDs |
|---|---:|
| present all days | 24938 |

## Geometry-equivalent segment pairs

A direction-agnostic LineString check on 2024-08-11 found 3,588 geometry groups, each containing exactly two segment IDs. All 3,588 pairs reverse coordinate order, use opposite signed `segmentId` values, and match on `frc`, `streetName`, and `distance`. Their 24 hourly `probeCount` sequences differ in 3,565 pairs. This is evidence for reciprocal directed edges, not duplicate same-direction physical records; retain both directions when constructing the graph. This does not establish graph connectivity. Full machine-readable counts are in `geometry_pair_audit.json`.

## Probe-count quality

Across stored `probeCount` values: {"n": 11970240, "min": 0.0, "max": 2766.0, "mean": 124.03170654890796, "median": 46.0, "std_population": 196.2645187027768, "p01": 0.0, "p05": 0.0, "p25": 9.0, "p75": 148.0, "p90": 355.0, "p95": 526.0, "p99": 938.0, "p999": 1509.0, "zeros": 772658, "zero_pct": 6.454824631753415}. Zero is retained as a recorded count, but it cannot be interpreted as no traffic or free-flow absent semantics. Negative values: 0; non-integer values: 0; expected cells missing or ambiguous: 0; explicit null entries: 0.

Probe-count means by hour show morning 07:00-10:00 average 120.4063 and evening 16:00-20:00 average 180.5402 (count units unresolved). Weekday daily-mean distribution: {"n": 15, "min": 102.32241291736841, "max": 139.03807609538322, "mean": 123.83716762014237, "median": 127.65360761354826, "std_population": 11.634727705121461, "p90": 136.7927921244687, "p95": 138.64329219798435, "p99": 138.95911931590345}; weekend daily-mean distribution: {"n": 5, "min": 96.37949949207368, "max": 136.94098531023604, "mean": 124.61532333520464, "median": 129.87013627128613, "std_population": 14.487472038484738, "p90": 135.26852895180048, "p95": 136.10475713101826, "p99": 136.7737396743925}.

Segments with constant nonmissing probeCount: 185; all-zero segments: 185. Spike candidates use a screening rule of above the global 99.9th percentile and at least 10x the previous valid hour; this is not proof of an error. Top candidates are in `spike_candidates_top100.csv`.

## Temporal signal (not model results)

Per-segment autocorrelation summaries (minimum 30 valid pairs per lag): `{"1": {"n": 24753, "min": -0.08243521514722024, "max": 0.9512637804742076, "mean": 0.7789596315048852, "median": 0.8497621360995922, "std_population": 0.18478126361289682, "p90": 0.9111478570486093, "p95": 0.9209725776341797, "p99": 0.9341890604464727, "segments_estimable": 24753, "segments_total": 24938}, "3": {"n": 24753, "min": -0.18595946406940472, "max": 0.8213654424083966, "mean": 0.46921899358512176, "median": 0.5147338105048372, "std_population": 0.14815248578891257, "p90": 0.61317356842841, "p95": 0.6311328842340219, "p99": 0.6576462588488977, "segments_estimable": 24753, "segments_total": 24938}, "6": {"n": 24753, "min": -0.4171761241874699, "max": 0.6264880339401759, "mean": 0.0013903087170821305, "median": 0.003635908517357304, "std_population": 0.07607648551440578, "p90": 0.07776603286795371, "p95": 0.11191287337687841, "p99": 0.23395300263555543, "segments_estimable": 24753, "segments_total": 24938}, "12": {"n": 24753, "min": -0.8468802341302019, "max": 0.5556389403411655, "mean": -0.46293183595990667, "median": -0.5218286452330406, "std_population": 0.24093185303773695, "p90": -0.10287917935926921, "p95": -0.005096403235527554, "p99": 0.2166618475760381, "segments_estimable": 24753, "segments_total": 24938}, "24": {"n": 24753, "min": -0.06627867352031437, "max": 0.9211928388145427, "mean": 0.6859825254756355, "median": 0.7507205522475037, "std_population": 0.18943798504997997, "p90": 0.848448160888114, "p95": 0.8645275145544633, "p99": 0.8890202785505111, "segments_estimable": 24753, "segments_total": 24938}}`. Lag 24 is same-hour next-day association. These statistics concern probe counts only and cannot establish predictable speed or routing cost.

## Important limitations

The README claim of over 4,000,000 entries/day is kept separate from the observed feature and segment-hour counts in the report. `frc`, `speedLimit`, distance-field semantics, probe unit, and exact bucket timestamp convention lack a field-level codebook. The annual aggregate and weekday tables are not substitutes for segment-level observed speed/travel-time labels. No values were imputed or altered.
