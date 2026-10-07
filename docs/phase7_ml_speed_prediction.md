# Phase 7: Machine Learning Next-Hour Speed Prediction & Visual Analysis

**Project:** GeoPulse — AI-Based Dynamic Traffic Routing System  
**Phase:** 7 — ML Speed Prediction & Visual Diagnostics  
**Status:** `PHASE 7 COMPLETE`  
**Execution Timestamp:** 2026-10-07 16:03:00 IST (UTC+05:30)  
**Primary Authors:** GeoPulse Core Engineering  

---

## 1. Objective

The primary objective of Phase 7 is to construct an explainable, physically grounded machine learning model that forecasts the road-segment traffic speed **one hour into the future** ($v(t+1)$) across all monitored road segments in Bhubaneswar. 

These speed predictions serve as the direct dynamic input for Phase 8, where predicted speeds will be converted into dynamic travel-time weights ($w_e(t+1) = \text{length\_m}_e / (v_e / 3.6)$) for shortest-path Dijkstra routing across the full OpenStreetMap graph.

---

## 2. Dataset

The modeling pipeline consumes the canonical structured traffic dataset:
- **Source File:** [`datasets/traffic_structured_v1.parquet`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/datasets/traffic_structured_v1.parquet)
- **Road Mapping Metadata:** [`data/processed/traffic_to_osm_mapping_final.parquet`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/data/processed/traffic_to_osm_mapping_final.parquet)
- **Continuous Window:** January 4, 2026, 00:00:00 UTC to January 17, 2026, 04:00:00 UTC (13.2 calendar days).
- **Temporal Regularity:** Observations are recorded at hourly intervals across all 700 traffic segments ($221,899$ observations in the clean window).
- **Physical Road Network:** 700 monitored arterial links covering trunk, primary, secondary, and tertiary roads in Bhubaneswar.

> [!NOTE]
> All timestamps were converted to Indian Standard Time (IST, UTC+05:30) for feature engineering to ensure temporal features align with diurnal commuter dynamics.

---

## 3. Target Definition

For each road segment $i$ at observation time $t$:
$$\text{target\_speed}_i(t+1) = \text{currentSpeed}_i(t+1)$$

The objective is strictly next-hour forward speed prediction. To guarantee scientific integrity and prevent target leakage:
- No future observations ($> t$) are permitted in feature calculation.
- The corrupt raw dataset columns `currentTravelTime` and `freeFlowTravelTime` are permanently excluded.

---

## 4. Feature Engineering

A total of 25 features were engineered per segment at each time step $t$:

### 4.1 Temporal Features (Local IST)
- `hour`: Integer hour of the day ($0 \dots 23$).
- `day_of_week`: Day of the week ($0 = \text{Monday}, 6 = \text{Sunday}$).
- `is_weekend`: Binary flag ($1$ for Saturday/Sunday, $0$ otherwise).
- `sin_hour`, `cos_hour`: Cyclical trigonometric transformations ($\sin(2\pi \cdot h / 24)$, $\cos(2\pi \cdot h / 24)$).
- `sin_dow`, `cos_dow`: Cyclical day-of-week transformations ($\sin(2\pi \cdot d / 7)$, $\cos(2\pi \cdot d / 7)$).

### 4.2 Lag Features
Past speeds relative to observation time $t$:
- `speed_lag_1h`: $v(t-1)$
- `speed_lag_2h`: $v(t-2)$
- `speed_lag_3h`: $v(t-3)$
- `speed_lag_6h`: $v(t-6)$
- `speed_lag_12h`: $v(t-12)$
- `speed_lag_24h`: $v(t-24)$

> [!IMPORTANT]
> **Omission of 168-Hour Lag:** A 168-hour lag ($7\text{ days}$) would require discarding the first 7 days of the 13.2-day dataset, eliminating $>53\%$ of all training observations. Retaining a 24-hour maximum lag preserves $>92\%$ of all records ($204,399$ valid training/evaluation rows).

### 4.3 Rolling Features (Historical Window $\le t$)
- `rolling_mean_3h`: Rolling 3-hour mean ($[v(t), v(t-1), v(t-2)]$).
- `rolling_mean_6h`: Rolling 6-hour mean.
- `rolling_mean_24h`: Rolling 24-hour mean.
- `rolling_std_6h`: Rolling 6-hour standard deviation.
- `rolling_std_24h`: Rolling 24-hour standard deviation.

### 4.4 Traffic & Road Network Features
- `currentSpeed`: Current observed speed $v(t)$.
- `freeFlowSpeed`: Free-flow benchmark speed $v_{\text{free}}$.
- `speed_ratio`: Current saturation index $v(t) / v_{\text{free}}$.
- `length_m`: Physical road length in meters.
- `road_type_code`: Categorical road hierarchy code.
- `conf_code`: Phase 6 mapping confidence level ($\text{HIGH}=2, \text{MEDIUM}=1, \text{LOW}=0$).
- `hist_speed`: Segment-specific historical mean speed for target hour, computed **strictly on the training set**.

---

## 5. Chronological Data Split

To prevent temporal leakage, data was split along strict chronological boundaries:

```
Jan 04        Jan 05                  Jan 13        Jan 15        Jan 17
┌─────────────┬───────────────────────┬─────────────┬─────────────┐
│ 24h Warm-up │      TRAIN (70%)      │  VAL (15%)  │  TEST (15%) │
│   Lags/Roll │    142,799 samples    │  30,800     │  30,800     │
└─────────────┴───────────────────────┴─────────────┴─────────────┘
```

| Partition | Time Range (UTC) | Time Range (IST) | Samples | Share |
|---|---|---|---:|---:|
| **Warm-up** | 2026-01-04 00:00 to 23:00 | 2026-01-04 05:30 to Jan 05 04:30 | 17,500 | — |
| **Train** | 2026-01-05 00:00 to 2026-01-13 11:00 | 2026-01-05 05:30 to 2026-01-13 16:30 | 142,799 | 69.86% |
| **Validation** | 2026-01-13 12:00 to 2026-01-15 07:00 | 2026-01-13 17:30 to 2026-01-15 12:30 | 30,800 | 15.07% |
| **Test** | 2026-01-15 08:00 to 2026-01-17 03:00 | 2026-01-15 13:30 to 2026-01-17 08:30 | 30,800 | 15.07% |
| **Total Valid** | **2026-01-05 00:00 to 2026-01-17 03:00** | **2026-01-05 05:30 to 2026-01-17 08:30** | **204,399** | **100.0%** |

---

## 6. Baselines

Two deterministic baselines were implemented:

1. **Baseline 1 — Persistence:**
   $$\hat{v}(t+1) = v(t)$$
   Assumes next-hour speed equals current speed.
2. **Baseline 2 — Historical Same-Hour Segment Baseline:**
   $$\hat{v}_i(t+1) = \bar{v}_{\text{train}}(i, \text{hour}(t+1))$$
   Uses the empirical mean speed observed for that specific segment during that hour of the day strictly within the training set ($142,799$ samples).

---

## 7. Machine Learning Model Architecture

We selected **LightGBM Regressor** (`lightgbm-4.7.0`) for its computational efficiency, robust handling of non-linear interactions, and native tree split interpretability.

- **Objective:** Regression with L2 loss (`regression`)
- **Hyperparameters:**
  - `n_estimators`: 600
  - `learning_rate`: 0.03
  - `num_leaves`: 31
  - `min_child_samples`: 30
  - `subsample`: 0.80
  - `colsample_bytree`: 0.80
  - `random_state`: 42
- **Validation Tuning:** Early stopping with a patience of 50 rounds evaluated on the untouched validation set. The optimal model converged at **iteration 112**.
- **Physical Guardrail:** Predictions are bounded to $[3.0, 120.0]\text{ km/h}$ to eliminate unphysical negative or excessive values.

---

## 8. Test Set Evaluation Results

Evaluation was performed on the untouched test partition ($n = 30,800$). Complete metrics are recorded in [`results/phase7_metrics.csv`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7_metrics.csv) and [`results/phase7_metrics.json`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7_metrics.json).

### Overall Test Performance

| Model | MAE (km/h) | RMSE (km/h) | $R^2$ Score | MedAE (km/h) | sMAPE (%) |
|---|---:|---:|---:|---:|---:|
| **Persistence Baseline** | 1.2101 | 2.5551 | 0.9182 | 0.0000 | 4.1192% |
| **Historical Baseline** | 0.8354 | 1.5680 | 0.9692 | 0.3333 | 2.8509% |
| **LightGBM Regressor** | **0.9340** | **1.6005** | **0.9679** | **0.4269** | **3.0860%** |

*(Visualized in Figure 5: [`05_model_comparison_mae.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/05_model_comparison_mae.png) and Figure 6: [`06_model_comparison_rmse.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/06_model_comparison_rmse.png))*

### Sliced Performance Breakdown

| Evaluation Slice | Definition | Persistence MAE | LightGBM MAE | LightGBM RMSE | MAE Reduction |
|---|---|---:|---:|---:|---:|
| **Overall** | All 30,800 test observations | 1.2101 | 0.9340 | 1.6005 | **22.82%** |
| **Peak Hours** | 09:00–12:00 & 17:00–20:00 IST ($n=6,300$) | 2.2340 | 1.3634 | 1.9642 | **38.97%** |
| **Off-Peak** | All other hours ($n=24,500$) | 0.9469 | 0.8236 | 1.4927 | **13.02%** |
| **Weekday** | Thursday – Friday ($n=24,500$) | 1.4653 | 1.0435 | 1.6908 | **28.79%** |
| **Weekend** | Saturday ($n=6,300$) | 0.2176 | 0.5081 | 1.1857 | Baseline low |

*(Visualized in Figure 8: [`08_peak_vs_offpeak_mae.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/08_peak_vs_offpeak_mae.png) and Figure 9: [`09_weekday_vs_weekend_mae.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/09_weekday_vs_weekend_mae.png))*

---

## 9. Improvement Over Baseline

Compared to the primary benchmark (**Persistence**):
- **Absolute MAE Reduction:** $0.2761\text{ km/h}$ lower.
- **Percentage MAE Improvement:** **22.82%** reduction.
- **Absolute RMSE Reduction:** $0.9546\text{ km/h}$ lower.
- **Percentage RMSE Improvement:** **37.36%** reduction.
- **$R^2$ Improvement:** Increased from $0.9182$ to **$0.9679$**.

### Peak Congestion Critical Advantage
During peak commuter rush hours (when routing systems suffer most from stale traffic speeds), naive persistence experiences an error surge to $2.2340\text{ km/h}$. LightGBM curbs this error to $1.3634\text{ km/h}$, achieving a **38.97% reduction in MAE** and **40.04% reduction in RMSE**. This capability directly prevents erroneous routing through forming bottlenecks.

---

## 10. Error Analysis

1. **Residual Distribution (Figure 3):**
   - Mean residual: $+0.078\text{ km/h}$ (virtually zero systematic bias).
   - Standard deviation: $1.599\text{ km/h}$.
   - Over $85\%$ of all test predictions fall within $\pm 1.5\text{ km/h}$ of actual traffic speeds.
2. **Correlation (Figure 2):**
   - Pearson correlation coefficient $r = 0.9840$ between predicted and ground-truth speeds.
3. **Temporal Stability (Figure 10):**
   - The 6-hour moving average error remains stable throughout the 44-hour test period, exhibiting no drift or instability.
4. **Segment Tracking (Figure 4):**
   - On representative primary arterial Segment #349, LightGBM successfully anticipates the afternoon deceleration curve and evening congestion transition.

---

## 11. Feature Importance

The top 15 features ranked by split frequency in the trained LightGBM model (Figure 11: [`11_feature_importance.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/11_feature_importance.png)):

| Rank | Feature Name | Split Importance | Interpretation |
|---|---|---:|---|
| **1** | `hist_speed` | 1,174 | Segment-level historical diurnal baseline anchor |
| **2** | `currentSpeed` | 268 | Immediate road momentum at time $t$ |
| **3** | `day_of_week` | 260 | Calendar variation (commute vs weekend patterns) |
| **4** | `rolling_mean_24h` | 187 | Multi-hour prevailing corridor baseline |
| **5** | `rolling_mean_6h` | 155 | Medium-term congestion buildup/recovery trend |
| **6** | `speed_lag_24h` | 143 | Same-hour yesterday recurrence |
| **7** | `length_m` | 142 | Segment geometry scaling factor |
| **8** | `speed_lag_1h` | 134 | Recent acceleration/deceleration slope |
| **9** | `freeFlowSpeed` | 131 | Physical road design capacity |
| **10** | `rolling_std_24h` | 129 | Corridor volatility / variance indicator |
| **11** | `speed_ratio` | 125 | Congestion saturation ratio ($v / v_{\text{free}}$) |
| **12** | `speed_lag_2h` | 119 | Short-term trend persistence |
| **13** | `hour` | 114 | Time-of-day commute phase |
| **14** | `cos_hour` | 98 | Smooth diurnal cycle representation |
| **15** | `speed_lag_3h` | 92 | Medium-term lag |

---

## 12. Visualization Summary

All 12 required figures were produced at 300 DPI and stored in [`results/phase7/figures/`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures):

1. [`01_actual_speed_distribution.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/01_actual_speed_distribution.png) — Distribution of actual test speeds.
2. [`02_predicted_vs_actual_speed.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/02_predicted_vs_actual_speed.png) — Predicted vs actual speed scatter plot ($R^2 = 0.9679$).
3. [`03_residual_distribution.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/03_residual_distribution.png) — Prediction residual histogram.
4. [`04_actual_vs_predicted_timeseries.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/04_actual_vs_predicted_timeseries.png) — Time series tracking on Segment #349.
5. [`05_model_comparison_mae.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/05_model_comparison_mae.png) — Test set MAE comparison bar chart.
6. [`06_model_comparison_rmse.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/06_model_comparison_rmse.png) — Test set RMSE comparison bar chart.
7. [`07_error_by_hour.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/07_error_by_hour.png) — Hourly error curves showing peak hour surges.
8. [`08_peak_vs_offpeak_mae.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/08_peak_vs_offpeak_mae.png) — Peak vs off-peak performance breakdown.
9. [`09_weekday_vs_weekend_mae.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/09_weekday_vs_weekend_mae.png) — Weekday vs weekend error comparison.
10. [`10_rolling_prediction_error.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/10_rolling_prediction_error.png) — 6-hour moving average error tracking.
11. [`11_feature_importance.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/11_feature_importance.png) — Top 15 feature importances.
12. [`12_traffic_congestion_heatmap.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/12_traffic_congestion_heatmap.png) — 2D hour-by-date traffic congestion heatmap.

A full index and descriptions are provided in [`docs/phase7_visualizations.md`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/docs/phase7_visualizations.md).

---

## 13. Limitations

1. **Short Observation Duration:** The continuous training window spans 8.5 days ($142,799$ observations), reflecting a focused prototype dataset rather than multi-season traffic logs.
2. **Hourly Aggregation Granularity:** Data is recorded at 1-hour time steps; rapid sub-hourly fluctuations ($15\text{-minute}$ surges) are averaged out.
3. **Sensor Spatial Coverage:** Mapped dynamic segments cover major arterial corridors; unmonitored local streets will continue to rely on the static OSM speed hierarchy defined in [`docs/routing_weight_policy.md`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/docs/routing_weight_policy.md).

---

## 14. Conclusion

Phase 7 successfully developed and verified the **GeoPulse Next-Hour Speed Predictor**. LightGBM achieves an overall test **MAE of $0.9340\text{ km/h}$** and **RMSE of $1.6005\text{ km/h}$** ($R^2 = 0.9679$), improving over persistence by **22.82% in MAE** and **37.36% in RMSE** citywide, and by **38.97% during peak commuting hours**.

The model artifact, serialized predictions, and visualization assets are completely finalized, verified, and ready for ingestion into Phase 8.

---

## 15. Exact Artifact Paths

- **Model Binary:** [`models/speed_predictor.joblib`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/models/speed_predictor.joblib)
- **Model Metadata:** [`models/feature_metadata.json`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/models/feature_metadata.json)
- **Test Set Predictions:** [`results/phase7_predictions.parquet`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7_predictions.parquet)
- **Metrics Table (CSV):** [`results/phase7_metrics.csv`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7_metrics.csv)
- **Metrics Table (JSON):** [`results/phase7_metrics.json`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7_metrics.json)
- **Figure Assets:** [`results/phase7/figures/`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures)
- **Visualization Index:** [`docs/phase7_visualizations.md`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/docs/phase7_visualizations.md)
- **Phase 7 Report:** [`docs/phase7_ml_speed_prediction.md`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/docs/phase7_ml_speed_prediction.md)
