# GeoPulse Dataset Readiness Report

**Audit date:** 22 November 2026  
**Scope:** Read-only inspection of the current traffic Parquet, DuckDB mirror, mapping Parquet, Bhubaneswar GraphML, and saved prediction artifact.

## Verdict

The current data is sufficient for an hourly speed-prediction prototype and for replaying historical traffic changes. It is not sufficient for a network-wide predictive-routing claim: only 700 traffic segments are monitored, 9 are configured static fallback, and the inspected prediction scenario dynamically weights 690 of 46,679 directed OSM edges (1.48%). Vehicle volume/count is absent. No synthetic records were generated.

The older `docs/dataset_audit_report.md` states the Bhubaneswar graph was absent. The current file at `data\raw\osm\bhubaneswar_drive.graphml` exists and was inspected directly; this audit uses the current artifact rather than that stale inventory statement.

`is_observed` and the traffic field names are present in the Parquet itself, but the file does not embed a source endpoint, API request ID, sensor provenance, or collection manifest. Existing repository audit documentation attributes the feed to TomTom; the tabular artifact alone cannot independently establish that provenance.

## Files and exact schemas

All exact columns, Arrow/DuckDB types, missing percentages, distinct counts, ranges, and samples are in `GEOPULSE_DATASET_SCHEMA.csv`.

| Path | Observed structure | Key result |
|---|---|---|
| `datasets\traffic_structured_v1.parquet` | 275,800 rows × 17 columns; 700 segment IDs | 246,399 observed rows; 29,401 explicit missing rows |
| `datasets\traffic_v1.duckdb` | DuckDB `main.traffic`; 275,800 rows | Same column order and values as Parquet: **True** |
| `data\processed\traffic_to_osm_mapping_final.parquet` | 700 rows × 16 columns | 700 traffic segment IDs; all mapped `(u,v,key)` references exist in GraphML |
| `data\raw\osm\bhubaneswar_drive.graphml` | Directed `MultiDiGraph`; 18,260 nodes / 46,679 directed edges | Edge `length` and `highway` attrs cover every edge; GraphML declares attrs as strings |
| `results\phase7_predictions.parquet` | 30,800 rows × 11 columns | 700 segments for each of 44 rounded hourly prediction times |

### Traffic table fields

The Arrow schema for the Parquet has: `segment_id:int64`, `hour:timestamp[ns, UTC]`, `timestamp:timestamp[ns, UTC]`, `currentSpeed:double`, `freeFlowSpeed:double`, `currentTravelTime:double`, `freeFlowTravelTime:double`, `confidence:double`, `is_observed:bool`, `is_missing:bool`, `roadClosure:bool`, `osmid:string`, `road_name:double`, `road_type:string`, `length_m:double`, `lat:double`, `lon:double`. DuckDB table `traffic` contains the same names and compatible SQL types (`BIGINT`, `TIMESTAMP WITH TIME ZONE`, `DOUBLE`, `BOOLEAN`, `VARCHAR`).

Example records from the actual Parquet:

```json
[
  {
    "segment_id": 0,
    "hour": "2025-12-31 19:00:00+00:00",
    "timestamp": "2025-12-31 19:39:50+00:00",
    "currentSpeed": 54.0,
    "freeFlowSpeed": 54.0,
    "currentTravelTime": 1376.0,
    "freeFlowTravelTime": 1376.0,
    "confidence": 1.0,
    "is_observed": true,
    "is_missing": false,
    "roadClosure": false,
    "osmid": "[1209033472, 280421140, 1317533102]",
    "road_name": 0.0,
    "road_type": "trunk",
    "length_m": 3016.9979383186064,
    "lat": 20.283950272583752,
    "lon": 85.80626747532335
  },
  {
    "segment_id": 0,
    "hour": "2025-12-31 20:00:00+00:00",
    "timestamp": "NaT",
    "currentSpeed": NaN,
    "freeFlowSpeed": NaN,
    "currentTravelTime": NaN,
    "freeFlowTravelTime": NaN,
    "confidence": NaN,
    "is_observed": false,
    "is_missing": true,
    "roadClosure": null,
    "osmid": NaN,
    "road_name": NaN,
    "road_type": NaN,
    "length_m": NaN,
    "lat": NaN,
    "lon": NaN
  },
  {
    "segment_id": 0,
    "hour": "2025-12-31 21:00:00+00:00",
    "timestamp": "NaT",
    "currentSpeed": NaN,
    "freeFlowSpeed": NaN,
    "currentTravelTime": NaN,
    "freeFlowTravelTime": NaN,
    "confidence": NaN,
    "is_observed": false,
    "is_missing": true,
    "roadClosure": null,
    "osmid": NaN,
    "road_name": NaN,
    "road_type": NaN,
    "length_m": NaN,
    "lat": NaN,
    "lon": NaN
  }
]
```

The first record is an observed row. The next two rows are explicit missing slots with `is_observed=false`, `is_missing=true`, and measurement fields null. The schema CSV includes samples for every field, plus graph node/edge attributes and model inputs.

## Time coverage, sampling, duplicates, and missingness

- The regular `hour` grid contains 394 consecutive hourly UTC buckets from `2025-12-31 19:00:00+00:00` through `2026-01-17 04:00:00+00:00`. Every segment has one row per grid bucket (394–394 grid rows).
- There are 344 fully observed hours, 15 partial hours, and 35 empty hours. The partial-hour counts are `{350: 14, 699: 1}`; one hour has a single missing segment.
- The capture `timestamp` is non-null for 246,399 records and ranges from `2025-12-31 19:39:50+00:00` to `2026-01-17 04:00:01+00:00` with 509 distinct timestamp values. Capture timestamps are not the regular grid; `hour` is the explicit bucket field.
- Missing values are 8.15% of all cells. Measurement and descriptive columns are null on the 29,401 missing rows (10.6603% of rows); the two boolean observation flags are populated on every row.
- Full rows duplicated: 0. Duplicate `(segment_id,hour)` keys: 0. Duplicate non-null `(segment_id,timestamp)` keys: 0.
- The Phase 7 training window, after its own UTC timestamp filter and 24-observation lag requirement, has 221,899 observed rows and 204,399 valid labels over 292 source timestamps. It has no duplicate `(segment_id, rounded timestamp)` keys.

## Speed target distribution and source limits

`currentSpeed` across observed records has min/median/mean/max **1.0/32.0/33.14/54.0 km/h** (p05 21.0, p95 53.0). There are 0 zero values and 0 negative values. `{'primary': 117651, 'secondary': 96331, 'trunk': 32417}` is the observed road-type distribution. `roadClosure=true` occurs 25,374 times; this is a flag, not a vehicle count.

The training target is `currentSpeed` shifted to the next observed row by segment after sorting on rounded timestamp. Among valid Phase 7 labels its distribution has 204,399 values, min/median/mean/max **1.0/32.0/33.07/54.0 km/h**. Label horizons are `{60.0: 204398, 120.0: 1}` minutes: 204,398 labels are exactly one hour and 1 label is two hours because the hour at `2026-01-12 06:00 UTC` is missing for one segment. The target is therefore nearly, but not perfectly, a fixed one-hour horizon; store an explicit target timestamp and filter/enforce exact elapsed time. The outlier row is `[{"segment_id": 103, "ts_round": "2026-01-12T05:00:00+00:00", "target_timestamp_rounded": "2026-01-12T07:00:00+00:00", "target_horizon_minutes": 120.0, "currentSpeed": 27.0, "target_speed": 27.0}]`.

The canonical tables do not contain a traffic-volume/vehicle-count column. Existing observed speed history is sufficient to derive lags, rolling statistics, and the current next-hour label. It cannot recover vehicle count, weather, or incident cause.

## OSM and segment-mapping coverage

The current graph is `networkx.MultiDiGraph`, directed and multi-edge, with 18,260 nodes and 46,679 directed edge records. Node GraphML keys are `y`, `x`, `street_count`, `highway`, and `junction`; edge keys include `osmid`, `highway`, `oneway`, `reversed`, `length`, `geometry`, `name`, `lanes`, `maxspeed`, `bridge`, `access`, `ref`, `junction`, `width`, and `tunnel`. GraphML declares these attributes as strings, so numeric fields must be parsed by consumers. Edge length spans 1.065–3016.998 metres. `maxspeed` is present on 451/46,679 edges (0.97%).

Mapping counts are: status `{'MAPPED': 599, 'AMBIGUOUS': 100, 'UNRESOLVED': 1}`, confidence `{'HIGH': 593, 'MEDIUM': 99, 'LOW': 8}`, direction `{'CLEAR': 608, 'AMBIGUOUS': 92}`, eligibility `{'DYNAMIC': 599, 'DYNAMIC_BIDIRECTIONAL': 92, 'STATIC_FALLBACK': 9}`. All 700/700 mapped `(u,v,key)` records exist in the graph. There are 657 unique directed tuples among 700 mapping rows; 43 rows share a directed tuple. All 92/92 `DYNAMIC_BIDIRECTIONAL` rows have a reverse graph edge. Segment-to-edge length error has median 0.000 m, p95 0.000 m, p99 91.611 m, and maximum 1420.906 m.

At 2026-01-15 14:00 UTC, the stored prediction slice contains 700 finite positive speeds in range 16.01–53.21 km/h. `GraphWeightManager` produced 690 dynamic directed weights and retained static weights for 45,989 other graph edges. The dynamic coverage is 1.48% of the directed graph. `DYNAMIC_BIDIRECTIONAL` copies its segment speed onto reverse edge records; `STATIC_FALLBACK` and unmapped edges retain static road-class speeds.

For routing, compute `travel_time_seconds = edge_length_meters / (predicted_speed_kmh * 1000 / 3600)`. The existing weight manager clips dynamic speeds to 3–120 km/h; the lower clamp maps zero/negative input to a finite crawl speed (100 m at zero becomes 120.0 seconds). It does not sanitize NaN: NaN speed produces NaN time, so inference outputs should be checked and missing predictions should fall back to static speed. Do not use the dataset's precomputed `currentTravelTime` as a road-edge cost: against `length_m*3.6/currentSpeed`, its observed MAE is 1440.01 seconds, median relative error 9063.3%, and correlation -0.133.

## Feature availability

The complete requested-feature classification is in `GEOPULSE_FEATURE_GAP_ANALYSIS.csv`. Segment/time, observed speed, lengths, road types, free-flow speed for the monitored segments, and segment-to-edge mappings are present. Lags, rolling windows, time encodings, and the next speed label are derivable. Volume/count is missing and cannot be inferred from speed. A clearly labelled synthetic count or incident overlay is suitable only for a controlled simulator demonstration; none was created in this audit.

## Read-only checks and paths

The report-generation script reads the paths above, compares DuckDB against Parquet, runs the existing model in memory, checks mapping/weight coverage, and writes only the four requested Phase 1 reports. See `GEOPULSE_ML_READINESS_REPORT.md` for ML metrics, feature order, leakage and inference findings.

```powershell
.\.venv\Scripts\python.exe -B scripts/audit_phase1_dataset_ml_readiness.py
```

SHA-256 hashes for the inspected source files are in `GEOPULSE_DATASET_SCHEMA.csv` summary rows. No dataset, model, routing, or application artifact was changed.
