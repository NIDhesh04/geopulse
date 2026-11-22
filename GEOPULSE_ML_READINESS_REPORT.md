# GeoPulse ML Readiness Report

**Audit date:** 22 November 2026  
**Model:** `models\speed_predictor.joblib` — LGBMRegressor  
**Training source:** `scripts\train_phase7_speed_predictor.py`

## Verdict

The saved LightGBM artifact loads and performs inference with the exact 25-feature schema. Reconstructed predictions match all 30,800 saved test predictions exactly. The model beats persistence on the recorded chronological test set but does not beat the training-only same-hour historical baseline. The artifacts support an hourly, 700-segment prototype and offline traffic replay; they do not yet support a credible general or network-wide predictive-routing claim.

## Exact model contract and inference check

`models/feature_metadata.json` declares `LightGBMRegressor`, 25 features, best iteration 112, and clipping [3.0, 120.0] km/h. The loaded estimator reports 25 inputs and feature names in the same order as metadata: **True**.

Feature order (order is required at inference):

```text
hour, day_of_week, is_weekend, sin_hour, cos_hour, sin_dow, cos_dow, speed_lag_1h, speed_lag_2h, speed_lag_3h, speed_lag_6h, speed_lag_12h, speed_lag_24h, rolling_mean_3h, rolling_mean_6h, rolling_mean_24h, rolling_std_6h, rolling_std_24h, currentSpeed, freeFlowSpeed, speed_ratio, length_m, road_type_code, conf_code, hist_speed
```

I rebuilt the training pipeline's feature row from the observed history, mapping, time, and same-hour historical lookup; it has 25 columns and zero missing values. A one-row `model.predict()` call returned **53.213165 km/h** for segment 0 at feature time `2026-01-15 08:00:01+00:00`. Its recorded next-hour target is **54.0 km/h** at `2026-01-15 09:00:00+00:00`. This is a real reconstructed row, not a fabricated sensor reading.

The saved `results/phase7_predictions.parquet` has 30,800 rows, 700 segments, no missing cells, and 44 rounded hourly timestamps from `2026-01-15 08:00:00+00:00` through `2026-01-17 03:00:00+00:00`. Every rounded timestamp contains 700 segments. Reconstructed test IDs/timestamps match the saved rows, and maximum absolute differences for target, LightGBM prediction, persistence prediction, and historical prediction are **0.0, 0.0, 0.0, and 0.0 km/h** respectively.

## Target, training split, and temporal leakage

The training file uses the target `g.shift(-1)` on `currentSpeed`, sorted by `segment_id` and rounded timestamp. Its intended mapping is feature row at time *t* → speed at the next observed timestamp. The selected period has 292 source timestamps after requiring a 24-row lag. Actual label horizons are {60.0: 204398, 120.0: 1}; one target is 120 minutes, not 60. The saved prediction Parquet includes the feature/origin `timestamp` and `actual_speed`, but no explicit `target_timestamp` column, so the forecast's validity time is implicit.

The split is chronological over sorted unique feature timestamps, not random:

| Split | Feature timestamps (UTC) | Unique hours | Samples |
|---|---|---:|---:|
| Train | 2026-01-05 00:00:00+00:00 → 2026-01-13 11:00:00+00:00 | 204 | 142,799 |
| Validation | 2026-01-13 12:00:00+00:00 → 2026-01-15 07:00:00+00:00 | 44 | 30,800 |
| Test | 2026-01-15 08:00:00+00:00 → 2026-01-17 03:00:00+00:00 | 44 | 30,800 |

The split is chronological, but it is not purged by label time. 700 training labels land at the first validation feature timestamp, and 700 validation labels land at the first test feature timestamp. Since each count is a full 700-segment hour, the validation boundary outcome is used during early stopping and the first test hour appears as validation labels. Purge the last source hour of train and validation, or split by target timestamp, before using the test result as an independent estimate.

Other leakage notes:

- Lag and rolling values are built before the split, which is valid for historical features if only past observations are included. The current window is nearly continuous, but exact elapsed-time checks should replace row-count assumptions when gaps occur.
- `hist_speed` is calculated from train labels only, which is appropriate. `road_type_code` is categorical metadata rather than a future target.
- `freeFlowSpeed` is included at time *t*. The file contains time-varying values, so verify this is available ex ante at serving time rather than a future/ex-post field.
- Prediction timestamp conventions should distinguish feature time from target-valid time explicitly when routing consumes a forecast.

## Test-set performance versus baselines

Metrics were recomputed from the saved model and exact reconstructed test matrix, and match `results/phase7_metrics.csv` to its stored rounding:

| Predictor | MAE km/h | RMSE km/h | R-squared | Median AE km/h | Samples |
|---|---|---|---|---|---|
| LightGBM saved model | 0.934 | 1.6005 | 0.9679 | 0.4269 | 30800 |
| Persistence currentSpeed(t) | 1.2101 | 2.5551 | 0.9182 | 0.0 | 30800 |
| Historical same-hour baseline | 0.8354 | 1.568 | 0.9692 | 0.3333 | 30800 |

LightGBM improves on persistence by 22.8% MAE and 37.4% RMSE. It is 11.8% worse in MAE and 2.1% worse in RMSE than the historical same-hour baseline. Thus the ML model is not the best tested speed predictor overall, despite beating persistence. Performance should be remeasured after purging boundary labels and on more independent periods.

## Live inference is not integrated

`src/cloud/model_service.py` loads the joblib model, metadata, and the stored prediction Parquet. Its `generate_predictions_broadcast()` filters cached rows by rounded timestamp (or silently falls back to the closest saved timestamp) and builds the message from `predicted_speed`. It never constructs the 25 model features and never calls `self.model.predict()`; loading the model does not make this a live inference service. A read-only call for 2026-01-15 14:00 UTC returned 700 speeds exactly equal to the stored prediction slice. This is prediction replay.

For live inference, a serving path must maintain ordered per-segment speed history, reject/fill gaps explicitly, derive the same local-time/road/mapping/confidence features and training-only `hist_speed`, enforce metadata feature order and clipping, call `model.predict()`, validate finite outputs, and attach both origin and target-valid timestamps. An absent stored timestamp currently selects a nearest timestamp without marking the result stale.

## Routing compatibility

- Traffic mapping has 700 segment rows and 700 unique IDs. All mapping edge tuples exist in the graph. Eligibility is `{'DYNAMIC': 599, 'DYNAMIC_BIDIRECTIONAL': 92, 'STATIC_FALLBACK': 9}`; all 92 bidirectional entries have reverse graph edges. Their speeds are assigned symmetrically to reverse edge records.
- The 14:00 stored predictions produced 690 dynamic directed edge weights (1.48% of 46,679 edges). Other edges remain static, so most road links do not receive ML traffic.
- GraphML edge `length` is present on every edge; OSM `maxspeed` is present on only 451/46679 edges. Existing static fallback estimates speeds by highway class (15–50 km/h), not a complete legal speed-limit dataset.
- Convert speed to cost as `length_m / (speed_kmh * 1000 / 3600)`. Current code clips dynamic speeds to 3–120 km/h and clamps zero/negative speed to 3 km/h in the kinematic conversion. It does not safely handle NaN speed; validate finite predictions and use static fallback for missing/invalid values.
- Do not use `currentTravelTime` as a GraphML edge weight. Its observed values disagree with `length_m*3.6/currentSpeed` (MAE 1440.0 seconds, correlation -0.133); derive edge seconds from edge length and effective speed.

## Synthetic data decision and next phase

Synthetic data is **not required** for the speed-only prototype or for demonstrating changing traffic over time. The historical grid has 394 hourly buckets (including 35 empty and 15 partial hours), the ML training window has 292 source timestamps with one missing cell, and the saved prediction artifact supplies 44 fully covered hourly steps. It can support offline historical replay; it does not provide live or future traffic ingestion. A synthetic incident/volume overlay is optional for a controlled simulation only, must be labelled as synthetic, and must stay separate from model-training targets and measured evaluation.

For a credible predictive-routing experiment, collect or construct (with explicit provenance) a purged, fixed-horizon target set; use an independent temporal holdout; validate against persistence and historical baselines; expand or explicitly scope the 700 monitored segment coverage; and retain a mapping/edge coverage and static-fallback report. Vehicle counts are only needed if the model objective is expanded to include flow; they cannot be derived from these tables.

## Recommended next implementation phase

Build a leakage-safe, reproducible ML inference and replay path: explicitly carry origin and target-valid timestamps, purge split-boundary labels, enforce a one-hour target, and reconstruct the same feature row from rolling per-segment history before calling the saved model. Re-evaluate on a new temporal holdout against both persistence and the historical baseline. Keep this phase scoped to the 700 mapped segments unless more real traffic observations are collected; do not imply dynamic coverage of the full OSM graph.

## Reproducible command

```powershell
.\.venv\Scripts\python.exe -B scripts/audit_phase1_dataset_ml_readiness.py
```

This command does not run the training script. It loads the existing model, reconstructs the test inputs in memory, calls `predict()`, verifies exact parity with the saved prediction artifact, and writes only the four requested audit deliverables.
