# GeoPulse traffic dataset suitability and reliability audit

Read-only analysis of `C:\Users\Mohit sharma\Desktop\7th sem\new major project\geopulse\datasets\traffic_v1.duckdb` and `C:\Users\Mohit sharma\Desktop\7th sem\new major project\geopulse\notebooks\bhubaneswar_drive.graphml`. Calendar coverage is grouped in IST. The archive data dictionary says timestamps are UTC, while the DuckDB session renders the timestamptz values at +05:30; this report uses that same instant converted to IST for local traffic calendars. Neither source file was modified.

## Overall assessment

**Suitable with preprocessing for speed prediction; unsuitable for end-to-end routing evaluation in its current form.** The segment-hour grid is complete, and observed speeds have meaningful variation and temporal signal. However, only 16.375 days are available, the traffic-covered OSM subgraph is fragmented, travel-time fields fail the documented length/speed consistency check, and congestion labels are absent. Resolve these before comparing dynamic routes against the baseline.

## 1. Structure

Tables: traffic. Rows: **275,800**; segments: **700**; distinct non-null raw `timestamp` values: **509**; distinct hourly grid values in `hour`: **394**. Expected rows = segments x hourly grid = **275,800**; complete grid: **True**. Unique `(segment_id, hour)` pairs: 275,800; duplicate full-row records involved: 0; duplicate pairs involved: 0.

Per-column dtype, null count, and distinct count are in `column_inventory.csv`.

## 2-4. Temporal coverage, missingness, continuity

Hourly grid range (IST): 2026-01-01 00:30:00+05:30 to 2026-01-17 09:30:00+05:30 (16.375 days); 394 hourly buckets; all 393 consecutive `hour` differences are 1.0 hour(s); missing global hourly buckets: 0. Raw `timestamp` values range from 2026-01-01 01:09:50+05:30 to 2026-01-17 09:30:01+05:30; raw timestamp is strictly hourly: False; raw timestamp-difference counts in hours are {'0.000278': 148, '0.073056': 1, '0.269444': 1, '0.411389': 1, '0.730556': 1, '0.926944': 1, '0.999722': 166, '1.0': 171, '1.000278': 17, '35.925278': 1}. Offsets from the `hour` bucket in minutes (min/median/max): {'min': 0.016666666666666666, 'median': 0.016666666666666666, 'max': 43.85}.

Per-segment valid observation coverage min/mean/median/max/std: 87.563%/89.340%/89.213%/91.117%/1.778%. Valid observations: 246,399; missing rows: 29,401. Observation/missing flags are complementary on 275,800/275,800 rows; is_observed differs from finite-speed availability on 0 rows.

Twenty lowest-coverage segments:

| segment_id | records | observed | missing | coverage_pct | observed_record_pct |
| --- | --- | --- | --- | --- | --- |
| 350 | 394 | 345 | 49 | 87.56345177664974 | 87.56345177664974 |
| 351 | 394 | 345 | 49 | 87.56345177664974 | 87.56345177664974 |
| 352 | 394 | 345 | 49 | 87.56345177664974 | 87.56345177664974 |
| 353 | 394 | 345 | 49 | 87.56345177664974 | 87.56345177664974 |
| 354 | 394 | 345 | 49 | 87.56345177664974 | 87.56345177664974 |
| 355 | 394 | 345 | 49 | 87.56345177664974 | 87.56345177664974 |
| 356 | 394 | 345 | 49 | 87.56345177664974 | 87.56345177664974 |
| 357 | 394 | 345 | 49 | 87.56345177664974 | 87.56345177664974 |
| 358 | 394 | 345 | 49 | 87.56345177664974 | 87.56345177664974 |
| 359 | 394 | 345 | 49 | 87.56345177664974 | 87.56345177664974 |
| 360 | 394 | 345 | 49 | 87.56345177664974 | 87.56345177664974 |
| 361 | 394 | 345 | 49 | 87.56345177664974 | 87.56345177664974 |
| 362 | 394 | 345 | 49 | 87.56345177664974 | 87.56345177664974 |
| 363 | 394 | 345 | 49 | 87.56345177664974 | 87.56345177664974 |
| 364 | 394 | 345 | 49 | 87.56345177664974 | 87.56345177664974 |
| 365 | 394 | 345 | 49 | 87.56345177664974 | 87.56345177664974 |
| 366 | 394 | 345 | 49 | 87.56345177664974 | 87.56345177664974 |
| 367 | 394 | 345 | 49 | 87.56345177664974 | 87.56345177664974 |
| 368 | 394 | 345 | 49 | 87.56345177664974 | 87.56345177664974 |
| 369 | 394 | 345 | 49 | 87.56345177664974 | 87.56345177664974 |

Missingness details by date, hour, weekday, segment, and road type are in the CSV outputs. Hour-of-day coverage:

| hour | total | observed | missing | coverage_pct |
| --- | --- | --- | --- | --- |
| 0 | 11900 | 10500 | 1400 | 88.23529411764706 |
| 1 | 11900 | 10500 | 1400 | 88.23529411764706 |
| 2 | 11900 | 10500 | 1400 | 88.23529411764706 |
| 3 | 11900 | 10500 | 1400 | 88.23529411764706 |
| 4 | 11900 | 10500 | 1400 | 88.23529411764706 |
| 5 | 11900 | 10500 | 1400 | 88.23529411764706 |
| 6 | 11900 | 10500 | 1400 | 88.23529411764706 |
| 7 | 11900 | 10500 | 1400 | 88.23529411764706 |
| 8 | 11900 | 10500 | 1400 | 88.23529411764706 |
| 9 | 11900 | 10500 | 1400 | 88.23529411764706 |
| 10 | 11200 | 9800 | 1400 | 87.5 |
| 11 | 11200 | 9799 | 1401 | 87.49107142857143 |
| 12 | 11200 | 10150 | 1050 | 90.625 |
| 13 | 11200 | 10150 | 1050 | 90.625 |
| 14 | 11200 | 10150 | 1050 | 90.625 |
| 15 | 11200 | 10150 | 1050 | 90.625 |
| 16 | 11200 | 10150 | 1050 | 90.625 |
| 17 | 11200 | 10150 | 1050 | 90.625 |
| 18 | 11200 | 10150 | 1050 | 90.625 |
| 19 | 11200 | 10150 | 1050 | 90.625 |
| 20 | 11200 | 10150 | 1050 | 90.625 |
| 21 | 11200 | 10150 | 1050 | 90.625 |
| 22 | 11200 | 10150 | 1050 | 90.625 |
| 23 | 11200 | 10150 | 1050 | 90.625 |

There are 1,051 observed sequences across all segments; median longest run is 345.0 hours, with 1 one-hour missing gaps, 350 gaps of 2+ missing hours, and largest elapsed gap 36.0 hours. Segments whose longest run can supply lags 1/3/6/12/24: 1: 700, 3: 700, 6: 700, 12: 700, 24: 700. See `continuity_by_segment.csv`. Missingness is strongly front-loaded: Jan 1 had 16,450 missing of 16,800 records; Jan 2 had 12,600; Jan 3 had 350. From Jan 4 onward, 225,399 of 225,400 rows are observed (99.9996%), so a clean 322-hour window is feasible by excluding the first three days.

## 5-7. Speed quality and variation

currentSpeed: {"n": 246399, "min": 1.0, "max": 54.0, "mean": 33.13745997345769, "median": 32.0, "std": 8.969907109882877, "q": {"0.01": 19.0, "0.05": 21.0, "0.25": 27.0, "0.5": 32.0, "0.75": 38.0, "0.95": 53.0, "0.99": 54.0}}; nonpositive 0, greater than free-flow 0, over 120/160 0/0, infinite 0.

freeFlowSpeed: {"n": 246399, "min": 16.0, "max": 55.0, "mean": 35.05807653440152, "median": 34.0, "std": 8.51862504404215, "q": {"0.01": 21.0, "0.05": 26.0, "0.25": 28.0, "0.5": 34.0, "0.75": 43.0, "0.95": 54.0, "0.99": 54.0}}; nonpositive 0, over 160 0, infinite 0; stable on 29 segments and varies on 671. Do not assume it is a static feature.

current/free-flow speed ratio: {"n": 246399, "min": 0.05263157894736842, "max": 1.0, "mean": 0.9437597163655201, "median": 1.0, "std": 0.09336138751289555, "q": {"0.01": 0.6666666666666666, "0.05": 0.75, "0.25": 0.8888888888888888, "0.5": 1.0, "0.75": 1.0, "0.95": 1.0, "0.99": 1.0}}. Counts: {"lt_0_9": 65738, "lt_0_8": 28243, "lt_0_7": 4335, "lt_0_5": 124, "gt_1": 0, "eq_1": 166828, "lt_1": 79571, "n": 246399}; ratio equals 1 for 166,828/246,399 (67.71%) of valid observations and never exceeds 1. Segment metrics are in `segment_quality.csv`.

## 8. Congestion labels

`congestion_level` and `is_congested` are absent, so supplied label counts and consistency cannot be audited. A derived ratio < 0.8 occurs in 28,243 valid rows; this is only an audit proxy, not a source label.

## 9-10. Segment variation and time signal

Nearly constant (speed SD <= 0.1): 5 segments; no ratio < 0.8: 123; ratio < 0.8 on over half of observations: 0. Mean/median per-segment autocorrelations at exact hourly lags are in this summary (estimable segments, mean, median, pooled): {"1": {"segments_with_estimable_acf": 695, "mean_segment_acf": 0.5750804836836433, "median_segment_acf": 0.6777190366186453, "pooled_mean_acf": 0.5744767316550565}, "3": {"segments_with_estimable_acf": 695, "mean_segment_acf": 0.17464661144803367, "median_segment_acf": 0.18931605820980948, "pooled_mean_acf": 0.17427775098068699}, "6": {"segments_with_estimable_acf": 695, "mean_segment_acf": 0.013791027136129437, "median_segment_acf": 0.012452007636400178, "pooled_mean_acf": 0.013727388614137078}, "12": {"segments_with_estimable_acf": 695, "mean_segment_acf": -0.3971663904948924, "median_segment_acf": -0.4419408011027866, "pooled_mean_acf": -0.39648095734618766}, "24": {"segments_with_estimable_acf": 695, "mean_segment_acf": 0.5851245200764162, "median_segment_acf": 0.6611509871226587, "pooled_mean_acf": 0.584123528947618}}. This supports short-lag predictive signal statistically; no model was trained. Full per-segment metrics are in `autocorrelation_by_segment.csv`.

## 11. Feature leakage

Candidate safe features: static road metadata/topology, calendar values known at forecast time, and speed lags strictly earlier than the forecast origin. Same-time `currentSpeed` is the target and leaks it; same-time `speed_ratio` inherits that leakage, and `currentTravelTime` is target-derived. `freeFlowTravelTime` is safe only if its provenance is static. `confidence`, `is_observed`, `is_missing`, and `roadClosure` need availability-time checks and should not be used contemporaneously unless known at forecast origin. Never use same-timestep speed_ratio to predict same-timestep speed.

## 12. Travel-time consistency

Assuming speed in km/h, length in metres, and time in seconds, expected travel time = 3.6 x length_m / speed_kmh. The large errors below indicate inconsistency under those units:

{
  "unit_assumption": "speeds in km/h; length in metres; travel times in seconds",
  "current": {
    "n": 246399,
    "mean_abs_difference_seconds": 1440.0071869371038,
    "median_abs_difference_seconds": 1551.2929681324629,
    "max_abs_difference_seconds": 3202.711910514178,
    "within_1s_pct": 0.14569864325748075,
    "within_5s_pct": 0.14569864325748075,
    "within_10pct_expected_pct": 0.14569864325748075
  },
  "free_flow": {
    "n": 246399,
    "mean_abs_difference_seconds": 1351.8345322039183,
    "median_abs_difference_seconds": 1376.721282178459,
    "max_abs_difference_seconds": 2709.2946935119967,
    "within_1s_pct": 0.14569864325748075,
    "within_5s_pct": 0.14569864325748075,
    "within_10pct_expected_pct": 0.14569864325748075
  }
}

## 13-16. Metadata, OSM ID, spatial and connectivity checks

`road_name` is DOUBLE, but the archive data dictionary allows numeric road identifiers, so it is not automatically malformed or human-readable. The same dictionary documents speed in km/h, length in metres, and travel time in seconds. Parsed OSM IDs: one ID on 613 segments, multiple on 87, malformed on 0. Graph: 18,260 nodes / 46,679 directed edges. ID existence matched 700/700 traffic segments (100.00%).

Independent traffic-point to OSM-edge validation in metric EPSG:32645: 700 matched within 500 m. Distance summary: {"n": 700, "min": 4.511267194658609e-07, "max": 76.53052254558584, "mean": 1.5115784549116043, "median": 0.13502719471679303, "std": 6.414898631862227, "q": {"0.5": 0.13502719471679303, "0.9": 2.1361768030339867, "0.95": 5.808417342883748}}; counts within 25/50/100/250/500 m: {"25": 688, "50": 697, "100": 700, "250": 700, "500": 700}; percentages within those thresholds: {"25": 98.28571428571429, "50": 99.57142857142857, "100": 100.0, "250": 100.0, "500": 100.0}; broad road-class match: 100.0%; chosen-edge length-ratio summary: {"n": 700, "min": 0.2845189186725737, "max": 1.6562418742783498, "mean": 0.9997811396895115, "median": 1.0036922708938287, "std": 0.07019911760860142, "q": {"0.5": 1.0036922708938287, "0.9": 1.0046071368548082, "0.95": 1.0046224476079293}}. Candidate rank combines distance, road type, and log length ratio. Full records are in `spatial_edge_matches.csv`.

OSM-ID-covered subgraph: 1,102 directed edges, 1,041 nodes, 44 weak components; largest component 101 nodes (9.70%). Independently using each segment's best spatially matched OSM edge: 645 unique directed edges, 867 nodes, 227 weak components; largest component 20 nodes (2.31%). The physical-match subgraph is the more relevant routing diagnostic.

## Output files and limitations

`summary.json` is machine-readable. CSVs contain column inventory, coverage, quality, continuity, autocorrelation, missingness, free-flow stability, OSM ID matches, and spatial edge candidates. No models were trained and source data was not modified. The pasted task ends after the opening of Audit 16, so later connectivity criteria were not supplied. The Bhubaneswar graph is under `notebooks/`; `datasets/jaipur_osm/` is a separate Jaipur graph.
