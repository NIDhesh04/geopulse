# Phase 7 Visualizations Index

**Project:** GeoPulse — AI-Based Dynamic Traffic Routing System  
**Component:** Next-Hour Speed Prediction (ML Baseline & Evaluation)  
**Figure Directory:** [`results/phase7/figures/`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures)  
**Figure Resolution:** 300 DPI (Publication / Presentation Quality)

---

## Overview of Figures

| Figure | Filename | Type | Purpose & Key Takeaway |
|---|---|---|---|
| **01** | [`01_actual_speed_distribution.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/01_actual_speed_distribution.png) | Histogram + KDE | Shows unimodal ground-truth speed distribution across 30,800 test observations (Mean: 32.88 km/h, Median: 32.00 km/h). |
| **02** | [`02_predicted_vs_actual_speed.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/02_predicted_vs_actual_speed.png) | Scatter Plot | Plots actual vs predicted speed against ideal 1:1 reference line ($r = 0.9840, R^2 = 0.9679$). |
| **03** | [`03_residual_distribution.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/03_residual_distribution.png) | Histogram + KDE | Error distribution ($y - \hat{y}$) centered tightly at zero (Mean bias: +0.078 km/h, Std: 1.599 km/h, MedAE: 0.427 km/h). |
| **04** | [`04_actual_vs_predicted_timeseries.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/04_actual_vs_predicted_timeseries.png) | Time Series | Chronological speed tracking on primary arterial road (Segment #349) across 44 hours of the test window. |
| **05** | [`05_model_comparison_mae.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/05_model_comparison_mae.png) | Bar Chart | Direct comparison of Mean Absolute Error: Persistence (1.2101 km/h) vs Historical (0.8354 km/h) vs LightGBM (0.9340 km/h). |
| **06** | [`06_model_comparison_rmse.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/06_model_comparison_rmse.png) | Bar Chart | Direct comparison of Root Mean Squared Error: Persistence (2.5551 km/h) vs Historical (1.5680 km/h) vs LightGBM (1.6005 km/h). |
| **07** | [`07_error_by_hour.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/07_error_by_hour.png) | Line Chart | Hourly MAE profile across 00:00 to 23:00 IST highlighting morning (09–12) and evening (17–20) peak congestion periods. |
| **08** | [`08_peak_vs_offpeak_mae.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/08_peak_vs_offpeak_mae.png) | Grouped Bar Chart | Performance breakdown in peak vs off-peak hours (LightGBM cuts peak MAE from 2.2340 to 1.3634 km/h, a 38.97% reduction). |
| **09** | [`09_weekday_vs_weekend_mae.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/09_weekday_vs_weekend_mae.png) | Grouped Bar Chart | Performance breakdown on weekdays vs weekends (LightGBM reduces weekday MAE from 1.4653 to 1.0435 km/h, a 28.79% reduction). |
| **10** | [`10_rolling_prediction_error.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/10_rolling_prediction_error.png) | Rolling Line Chart | 6-hour moving average MAE across the entire test timeline showing sustained ML advantage without temporal degradation. |
| **11** | [`11_feature_importance.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/11_feature_importance.png) | Horizontal Bar Chart | Top 15 split-importance features indicating dominance of historical mean calibration, current speed, day of week, and rolling aggregates. |
| **12** | [`12_traffic_congestion_heatmap.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/12_traffic_congestion_heatmap.png) | Heatmap | 24-hour diurnal speed ratio ($v / v_{\text{free}}$) across all 14 calendar days (Jan 4–17, 2026), capturing morning & evening rush hours. |

---

## Detailed Figure Descriptions

### Figure 1: Actual Speed Distribution
- **Path:** [`results/phase7/figures/01_actual_speed_distribution.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/01_actual_speed_distribution.png)
- **Description:** Depicts the empirical distribution of vehicle speeds on the test set ($n = 30,800$). The distribution is roughly Gaussian with mean $32.88\text{ km/h}$, standard deviation $8.93\text{ km/h}$, and bounds between $3.0\text{ km/h}$ and $72.0\text{ km/h}$.

### Figure 2: Predicted vs Actual Speed
- **Path:** [`results/phase7/figures/02_predicted_vs_actual_speed.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/02_predicted_vs_actual_speed.png)
- **Description:** Scatter plot comparing LightGBM predictions against ground-truth speeds. Shows tight adherence to the red dashed $y=x$ line ($R^2 = 0.9679$, Pearson $r = 0.9840$), demonstrating that model predictions track physical reality across both slow congested corridors and fast free-flowing bypasses.

### Figure 3: Model Residual Distribution
- **Path:** [`results/phase7/figures/03_residual_distribution.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/03_residual_distribution.png)
- **Description:** Displays the error distribution ($e = y - \hat{y}$). The residual bell curve is symmetric, centered at $+0.078\text{ km/h}$ (negligible bias), with over $80\%$ of errors within $\pm 1.5\text{ km/h}$.

### Figure 4: Actual vs Predicted Time Series
- **Path:** [`results/phase7/figures/04_actual_vs_predicted_timeseries.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/04_actual_vs_predicted_timeseries.png)
- **Description:** Continuous tracking on primary arterial road Segment #349 ($129.3\text{ m}$ length) across 44 consecutive test hours. Shows LightGBM accurately anticipating peak evening deceleration drops and morning recovery transitions ahead of naive persistence lag.

### Figure 5 & 6: Baseline vs ML Error (MAE & RMSE)
- **Path:** [`results/phase7/figures/05_model_comparison_mae.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/05_model_comparison_mae.png), [`results/phase7/figures/06_model_comparison_rmse.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/06_model_comparison_rmse.png)
- **Description:** Direct side-by-side bar plots demonstrating that LightGBM achieves a $22.82\%$ reduction in MAE and a $37.36\%$ reduction in RMSE relative to naive persistence.

### Figure 7 & 8: Diurnal & Peak vs Off-Peak Dynamics
- **Path:** [`results/phase7/figures/07_error_by_hour.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/07_error_by_hour.png), [`results/phase7/figures/08_peak_vs_offpeak_mae.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/08_peak_vs_offpeak_mae.png)
- **Description:** Highlights that persistence error surges to $>2.23\text{ km/h}$ during peak commuting hours (09:00–12:00 and 17:00–20:00 IST), whereas LightGBM dampens peak volatility down to $1.36\text{ km/h}$ ($38.97\%$ reduction).

### Figure 9: Weekday vs Weekend Performance
- **Path:** [`results/phase7/figures/09_weekday_vs_weekend_mae.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/09_weekday_vs_weekend_mae.png)
- **Description:** Evaluates weekday traffic volatility versus quieter weekend conditions.

### Figure 10: Rolling Prediction Error Over Time
- **Path:** [`results/phase7/figures/10_rolling_prediction_error.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/10_rolling_prediction_error.png)
- **Description:** 6-hour moving average error across the test period demonstrating consistent, stable error envelopes without concept drift.

### Figure 11: Feature Importance
- **Path:** [`results/phase7/figures/11_feature_importance.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/11_feature_importance.png)
- **Description:** Ranks top features by split frequency. Segment historical expectation (`hist_speed`), current speed (`currentSpeed`), day of week (`day_of_week`), and 24h rolling mean (`rolling_mean_24h`) drive the predictions.

### Figure 12: Congestion Heatmap
- **Path:** [`results/phase7/figures/12_traffic_congestion_heatmap.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase7/figures/12_traffic_congestion_heatmap.png)
- **Description:** 2D matrix of hour-of-day vs calendar date colored by speed ratio ($v / v_{\text{free}}$). Clearly reveals the recurring morning (10:00–12:00) and evening (17:00–19:00) citywide congestion dips across the full observation period.
