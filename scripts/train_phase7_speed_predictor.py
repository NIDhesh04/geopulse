"""
GeoPulse Phase 7 — ML Next-Hour Speed Prediction & Visual Analysis
Pipeline script implementing:
- Feature engineering (temporal, lag, rolling, traffic, road, historical)
- Chronological Train / Val / Test splitting (70% / 15% / 15%)
- Baseline models (Persistence & Historical same-hour mean)
- LightGBM Regressor training with early stopping
- Test set evaluation and metrics calculation
- Breakdown analysis (Overall, Peak, Off-Peak, Weekday, Weekend)
- Generation of all 12 publication-ready figures
- Model artifact and predictions serialization
"""

import os
import json
import joblib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import lightgbm as lgb
from sklearn.metrics import mean_absolute_error, root_mean_squared_error, r2_score, median_absolute_error

# Set styling
plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.size'] = 11
plt.rcParams['axes.titlesize'] = 13
plt.rcParams['axes.labelsize'] = 11
plt.rcParams['figure.titlesize'] = 14

# Output directories
os.makedirs('results/phase7/figures', exist_ok=True)
os.makedirs('models', exist_ok=True)
os.makedirs('docs', exist_ok=True)

print("=" * 60)
print("GeoPulse Phase 7: ML Next-Hour Speed Prediction Pipeline")
print("=" * 60)

# ---------------------------------------------------------
# 1. LOAD DATA
# ---------------------------------------------------------
print("\n[Step 1/8] Loading and filtering datasets...")
df_raw = pd.read_parquet('datasets/traffic_structured_v1.parquet')
df_obs = df_raw[df_raw['is_observed'] == True].copy()
if not pd.api.types.is_datetime64_any_dtype(df_obs['timestamp']):
    df_obs['timestamp'] = pd.to_datetime(df_obs['timestamp'])

# Clean continuous period: 2026-01-04 to 2026-01-17
df_clean = df_obs[(df_obs['timestamp'] >= '2026-01-04') & (df_obs['timestamp'] <= '2026-01-17 04:00:05')].copy()
df_clean['ts_round'] = df_clean['timestamp'].dt.round('h')
df_clean['ts_ist'] = df_clean['ts_round'].dt.tz_convert('Asia/Kolkata')

# Road mapping features
mapping = pd.read_parquet('data/processed/traffic_to_osm_mapping_final.parquet')
seg_meta = mapping[['traffic_segment_id', 'confidence', 'routing_eligibility']].drop_duplicates().set_index('traffic_segment_id')

df_clean['mapping_confidence'] = df_clean['segment_id'].map(seg_meta['confidence'])
df_clean['routing_eligibility'] = df_clean['segment_id'].map(seg_meta['routing_eligibility'])

# Sort strictly by segment and time
df_clean = df_clean.sort_values(['segment_id', 'ts_round']).reset_index(drop=True)
print(f"Clean continuous rows: {len(df_clean)}, Segments: {df_clean['segment_id'].nunique()}")

# ---------------------------------------------------------
# 2. FEATURE ENGINEERING
# ---------------------------------------------------------
print("\n[Step 2/8] Engineering temporal, lag, rolling, and traffic features...")
g = df_clean.groupby('segment_id')['currentSpeed']

# Target: next hour currentSpeed
df_clean['target_speed'] = g.shift(-1)

# Lags relative to observation time t
df_clean['speed_lag_1h'] = g.shift(1)
df_clean['speed_lag_2h'] = g.shift(2)
df_clean['speed_lag_3h'] = g.shift(3)
df_clean['speed_lag_6h'] = g.shift(6)
df_clean['speed_lag_12h'] = g.shift(12)
df_clean['speed_lag_24h'] = g.shift(24)

# Rolling features up to and including observation time t
df_clean['rolling_mean_3h'] = g.rolling(3, min_periods=3).mean().reset_index(level=0, drop=True)
df_clean['rolling_mean_6h'] = g.rolling(6, min_periods=6).mean().reset_index(level=0, drop=True)
df_clean['rolling_mean_24h'] = g.rolling(24, min_periods=24).mean().reset_index(level=0, drop=True)
df_clean['rolling_std_6h'] = g.rolling(6, min_periods=6).std().reset_index(level=0, drop=True).fillna(0.0)
df_clean['rolling_std_24h'] = g.rolling(24, min_periods=24).std().reset_index(level=0, drop=True).fillna(0.0)

# Temporal features in IST
df_clean['hour'] = df_clean['ts_ist'].dt.hour
df_clean['day_of_week'] = df_clean['ts_ist'].dt.dayofweek
df_clean['is_weekend'] = (df_clean['day_of_week'] >= 5).astype(int)

df_clean['sin_hour'] = np.sin(2 * np.pi * df_clean['hour'] / 24.0)
df_clean['cos_hour'] = np.cos(2 * np.pi * df_clean['hour'] / 24.0)
df_clean['sin_dow'] = np.sin(2 * np.pi * df_clean['day_of_week'] / 7.0)
df_clean['cos_dow'] = np.cos(2 * np.pi * df_clean['day_of_week'] / 7.0)

# Target hour (IST)
df_clean['target_hour'] = (df_clean['hour'] + 1) % 24

# Traffic features
df_clean['speed_ratio'] = df_clean['currentSpeed'] / df_clean['freeFlowSpeed'].clip(lower=1.0)

# Road & mapping features
df_clean['road_type_code'] = df_clean['road_type'].astype('category').cat.codes
conf_map = {'HIGH': 2, 'MEDIUM': 1, 'LOW': 0}
df_clean['conf_code'] = df_clean['mapping_confidence'].map(conf_map).fillna(1).astype(int)

# Filter valid rows (requiring full 24h lag and valid target)
valid_mask = df_clean['target_speed'].notna() & df_clean['speed_lag_24h'].notna()
df_valid = df_clean[valid_mask].copy().reset_index(drop=True)
print(f"Total valid samples: {len(df_valid)}")

# ---------------------------------------------------------
# 3. CHRONOLOGICAL DATA SPLIT
# ---------------------------------------------------------
print("\n[Step 3/8] Performing strict chronological data split...")
unique_ts = np.sort(df_valid['ts_round'].unique())
n_ts = len(unique_ts)

# Split: 204 train (~70%), 44 val (~15%), 44 test (~15%)
train_ts = unique_ts[:204]
val_ts = unique_ts[204:248]
test_ts = unique_ts[248:]

train_df = df_valid[df_valid['ts_round'].isin(train_ts)].copy().reset_index(drop=True)
val_df = df_valid[df_valid['ts_round'].isin(val_ts)].copy().reset_index(drop=True)
test_df = df_valid[df_valid['ts_round'].isin(test_ts)].copy().reset_index(drop=True)

print(f"Train samples: {len(train_df):,} ({len(train_df)/len(df_valid)*100:.2f}%) | Timestamps: {len(train_ts)}")
print(f"  Range UTC: {train_df['ts_round'].min()} to {train_df['ts_round'].max()}")
print(f"  Range IST: {train_df['ts_ist'].min()} to {train_df['ts_ist'].max()}")
print(f"Val samples:   {len(val_df):,} ({len(val_df)/len(df_valid)*100:.2f}%) | Timestamps: {len(val_ts)}")
print(f"  Range UTC: {val_df['ts_round'].min()} to {val_df['ts_round'].max()}")
print(f"  Range IST: {val_df['ts_ist'].min()} to {val_df['ts_ist'].max()}")
print(f"Test samples:  {len(test_df):,} ({len(test_df)/len(df_valid)*100:.2f}%) | Timestamps: {len(test_ts)}")
print(f"  Range UTC: {test_df['ts_round'].min()} to {test_df['ts_round'].max()}")
print(f"  Range IST: {test_df['ts_ist'].min()} to {test_df['ts_ist'].max()}")

# ---------------------------------------------------------
# 4. HISTORICAL BASELINE LOOKUP (STRICTLY FROM TRAIN)
# ---------------------------------------------------------
print("\n[Step 4/8] Building historical baseline lookup strictly from TRAIN...")
hist_lookup = train_df.groupby(['segment_id', 'target_hour'])['target_speed'].mean().to_dict()
global_hist = train_df['target_speed'].mean()

for subset in [train_df, val_df, test_df]:
    keys = list(zip(subset['segment_id'], subset['target_hour']))
    subset['hist_speed'] = np.array([hist_lookup.get(k, global_hist) for k in keys])

# Feature list for LightGBM
feature_cols = [
    'hour', 'day_of_week', 'is_weekend', 'sin_hour', 'cos_hour', 'sin_dow', 'cos_dow',
    'speed_lag_1h', 'speed_lag_2h', 'speed_lag_3h', 'speed_lag_6h', 'speed_lag_12h', 'speed_lag_24h',
    'rolling_mean_3h', 'rolling_mean_6h', 'rolling_mean_24h', 'rolling_std_6h', 'rolling_std_24h',
    'currentSpeed', 'freeFlowSpeed', 'speed_ratio', 'length_m',
    'road_type_code', 'conf_code', 'hist_speed'
]

X_train = train_df[feature_cols]
y_train = train_df['target_speed'].values
X_val = val_df[feature_cols]
y_val = val_df['target_speed'].values
X_test = test_df[feature_cols]
y_test = test_df['target_speed'].values

# ---------------------------------------------------------
# 5. MODEL TRAINING & SELECTION
# ---------------------------------------------------------
print(f"\n[Step 5/8] Training LightGBM Regressor with {len(feature_cols)} features...")
model = lgb.LGBMRegressor(
    n_estimators=600,
    learning_rate=0.03,
    num_leaves=31,
    min_child_samples=30,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=42,
    n_jobs=-1,
    verbose=-1
)

model.fit(
    X_train, y_train,
    eval_set=[(X_val, y_val)],
    callbacks=[lgb.early_stopping(stopping_rounds=50, verbose=False)]
)

print(f"Best iteration: {model.best_iteration_}")

# Predict on val & test
y_pred_val = np.clip(model.predict(X_val), 3.0, 120.0)
y_pred_test = np.clip(model.predict(X_test), 3.0, 120.0)

# Baselines on test
y_pers_test = test_df['currentSpeed'].values
y_hist_test = test_df['hist_speed'].values

# ---------------------------------------------------------
# 6. EVALUATION METRICS & BREAKDOWNS
# ---------------------------------------------------------
print("\n[Step 6/8] Calculating evaluation metrics and breakdowns...")

def compute_all_metrics(y_true, y_pred, model_name, slice_name="overall"):
    mae = float(mean_absolute_error(y_true, y_pred))
    rmse = float(root_mean_squared_error(y_true, y_pred))
    r2 = float(r2_score(y_true, y_pred))
    med_ae = float(median_absolute_error(y_true, y_pred))
    denom = np.abs(y_true) + np.abs(y_pred)
    smape = float(np.mean(np.where(denom == 0, 0, 2.0 * np.abs(y_true - y_pred) / denom)) * 100.0)
    return {
        'model': model_name,
        'slice': slice_name,
        'MAE': round(mae, 4),
        'RMSE': round(rmse, 4),
        'R2': round(r2, 4),
        'median_absolute_error': round(med_ae, 4),
        'sMAPE': round(smape, 4),
        'sample_count': len(y_true)
    }

# Define slices
# Peak hours in IST: Morning (9, 10, 11) & Evening (17, 18, 19)
peak_hours = [9, 10, 11, 17, 18, 19]
test_df['is_peak'] = test_df['hour'].isin(peak_hours).astype(int)

slices = {
    'overall': np.ones(len(test_df), dtype=bool),
    'peak': (test_df['is_peak'] == 1).values,
    'off_peak': (test_df['is_peak'] == 0).values,
    'weekday': (test_df['is_weekend'] == 0).values,
    'weekend': (test_df['is_weekend'] == 1).values
}

metrics_records = []
for s_name, mask in slices.items():
    yt = y_test[mask]
    yp_pers = y_pers_test[mask]
    yp_hist = y_hist_test[mask]
    yp_ml = y_pred_test[mask]
    
    metrics_records.append(compute_all_metrics(yt, yp_pers, "Persistence", s_name))
    metrics_records.append(compute_all_metrics(yt, yp_hist, "Historical Baseline", s_name))
    metrics_records.append(compute_all_metrics(yt, yp_ml, "LightGBM Regressor", s_name))

df_metrics = pd.DataFrame(metrics_records)
df_metrics.to_csv('results/phase7_metrics.csv', index=False)
with open('results/phase7_metrics.json', 'w') as f:
    json.dump(metrics_records, f, indent=2)

print("\n--- TEST EVALUATION SUMMARY (OVERALL) ---")
overall_metrics = df_metrics[df_metrics['slice'] == 'overall']
print(overall_metrics[['model', 'MAE', 'RMSE', 'R2', 'median_absolute_error', 'sMAPE']].to_string(index=False))

# Calculate improvement
pers_mae = overall_metrics[overall_metrics['model'] == 'Persistence']['MAE'].values[0]
pers_rmse = overall_metrics[overall_metrics['model'] == 'Persistence']['RMSE'].values[0]
ml_mae = overall_metrics[overall_metrics['model'] == 'LightGBM Regressor']['MAE'].values[0]
ml_rmse = overall_metrics[overall_metrics['model'] == 'LightGBM Regressor']['RMSE'].values[0]

abs_imp_mae = pers_mae - ml_mae
pct_imp_mae = (abs_imp_mae / pers_mae) * 100.0
abs_imp_rmse = pers_rmse - ml_rmse
pct_imp_rmse = (abs_imp_rmse / pers_rmse) * 100.0

print(f"\nLightGBM improvement over Persistence:")
print(f"  MAE:  {abs_imp_mae:.4f} km/h reduction ({pct_imp_mae:.2f}%)")
print(f"  RMSE: {abs_imp_rmse:.4f} km/h reduction ({pct_imp_rmse:.2f}%)")

# Save prediction data
test_df['actual_speed'] = y_test
test_df['predicted_speed'] = y_pred_test
test_df['persistence_prediction'] = y_pers_test
test_df['historical_prediction'] = y_hist_test
test_df['residual'] = y_test - y_pred_test
test_df['traffic_segment_id'] = test_df['segment_id']

pred_cols = [
    'timestamp', 'traffic_segment_id', 'actual_speed', 'predicted_speed',
    'persistence_prediction', 'historical_prediction', 'residual',
    'hour', 'day_of_week', 'is_peak', 'is_weekend'
]
test_df[pred_cols].to_parquet('results/phase7_predictions.parquet', index=False)
print(f"Saved predictions to results/phase7_predictions.parquet ({len(test_df):,} rows)")

# Save model and feature metadata
joblib.dump(model, 'models/speed_predictor.joblib')
model_meta = {
    'model_type': 'LightGBMRegressor',
    'feature_cols': feature_cols,
    'n_features': len(feature_cols),
    'best_iteration': model.best_iteration_,
    'train_samples': len(train_df),
    'val_samples': len(val_df),
    'test_samples': len(test_df),
    'train_date_range': [str(train_df['ts_round'].min()), str(train_df['ts_round'].max())],
    'val_date_range': [str(val_df['ts_round'].min()), str(val_df['ts_round'].max())],
    'test_date_range': [str(test_df['ts_round'].min()), str(test_df['ts_round'].max())],
    'speed_clipping': [3.0, 120.0],
    'peak_hours_ist': peak_hours
}
with open('models/feature_metadata.json', 'w') as f:
    json.dump(model_meta, f, indent=2)
print("Saved model to models/speed_predictor.joblib and metadata to models/feature_metadata.json")

# ---------------------------------------------------------
# 7. GENERATE ALL 12 REQUIRED VISUALIZATIONS
# ---------------------------------------------------------
print("\n[Step 7/8] Generating high-resolution presentation figures...")

palette = {'ml': '#1f77b4', 'pers': '#ff7f0e', 'hist': '#2ca02c', 'actual': '#333333', 'accent': '#d62728'}

# FIGURE 1: Actual Speed Distribution
fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
sns.histplot(y_test, bins=40, kde=True, color='#2b5c8f', edgecolor='white', alpha=0.75, ax=ax)
ax.axvline(np.mean(y_test), color='#d62728', linestyle='--', linewidth=2, label=f'Mean Speed: {np.mean(y_test):.2f} km/h')
ax.axvline(np.median(y_test), color='#2ca02c', linestyle=':', linewidth=2, label=f'Median Speed: {np.median(y_test):.2f} km/h')
ax.set_title('Figure 1: Distribution of Actual Traffic Speeds (Test Period)', fontweight='bold', pad=12)
ax.set_xlabel('Actual Speed (km/h)')
ax.set_ylabel('Observation Frequency')
ax.legend(loc='upper right', frameon=True)
plt.tight_layout()
fig.savefig('results/phase7/figures/01_actual_speed_distribution.png', bbox_inches='tight')
plt.close(fig)

# FIGURE 2: Predicted vs Actual Speed Scatter Plot
fig, ax = plt.subplots(figsize=(7, 7), dpi=300)
# Subsample for clear scatter visualization
sample_idx = np.random.choice(len(y_test), size=min(5000, len(y_test)), replace=False)
ax.scatter(y_test[sample_idx], y_pred_test[sample_idx], alpha=0.25, color='#1f77b4', edgecolors='none', s=16, label='Test Observations')
lims = [0, max(np.max(y_test), np.max(y_pred_test)) + 5]
ax.plot(lims, lims, color='#d62728', linestyle='--', linewidth=2, label='Ideal 1:1 Reference Line')
ax.set_xlim(lims)
ax.set_ylim(lims)
ax.set_title('Figure 2: Predicted vs. Actual Next-Hour Speed (LightGBM)', fontweight='bold', pad=12)
ax.set_xlabel('Actual Speed (km/h)')
ax.set_ylabel('Predicted Speed (km/h)')
r2_val = r2_score(y_test, y_pred_test)
corr_val = np.corrcoef(y_test, y_pred_test)[0, 1]
ax.text(0.05, 0.90, f'Pearson r: {corr_val:.4f}\n$R^2$ Score: {r2_val:.4f}\nMAE: {ml_mae:.4f} km/h',
        transform=ax.transAxes, bbox=dict(boxstyle='round,pad=0.5', facecolor='white', alpha=0.9, edgecolor='#ccc'))
ax.legend(loc='lower right', frameon=True)
plt.tight_layout()
fig.savefig('results/phase7/figures/02_predicted_vs_actual_speed.png', bbox_inches='tight')
plt.close(fig)

# FIGURE 3: Model Residual Distribution
residuals = y_test - y_pred_test
fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
sns.histplot(residuals, bins=50, kde=True, color='#4a5568', edgecolor='white', alpha=0.75, ax=ax)
ax.axvline(0, color='#d62728', linestyle='--', linewidth=2, label='Zero Error Reference')
ax.axvline(np.mean(residuals), color='#ff7f0e', linestyle=':', linewidth=2, label=f'Mean Bias: {np.mean(residuals):.3f} km/h')
ax.set_title('Figure 3: Prediction Residual Distribution ($y - \hat{y}$)', fontweight='bold', pad=12)
ax.set_xlabel('Prediction Error / Residual (km/h)')
ax.set_ylabel('Observation Count')
ax.set_xlim([-12, 12])
ax.text(0.05, 0.85, f'Std of Error: {np.std(residuals):.3f} km/h\nMedian Abs Error: {median_absolute_error(y_test, y_pred_test):.3f} km/h',
        transform=ax.transAxes, bbox=dict(boxstyle='round,pad=0.5', facecolor='white', alpha=0.9, edgecolor='#ccc'))
ax.legend(loc='upper right', frameon=True)
plt.tight_layout()
fig.savefig('results/phase7/figures/03_residual_distribution.png', bbox_inches='tight')
plt.close(fig)

# FIGURE 4: Actual vs Predicted Time Series (Representative Segment 349)
rep_seg_id = 349
seg_data = test_df[test_df['segment_id'] == rep_seg_id].sort_values('ts_round')
fig, ax = plt.subplots(figsize=(12, 5), dpi=300)
ax.plot(seg_data['ts_ist'], seg_data['actual_speed'], marker='o', markersize=4, linewidth=2, color='#222222', label='Actual Speed (Ground Truth)')
ax.plot(seg_data['ts_ist'], seg_data['predicted_speed'], marker='s', markersize=4, linewidth=2, linestyle='--', color='#1f77b4', label='LightGBM Prediction')
ax.plot(seg_data['ts_ist'], seg_data['persistence_prediction'], marker='^', markersize=3, linewidth=1, linestyle=':', color='#ff7f0e', alpha=0.7, label='Persistence Baseline')
ax.set_title(f'Figure 4: Next-Hour Speed Time Series Tracking — Segment #{rep_seg_id} (Primary Road)', fontweight='bold', pad=12)
ax.set_xlabel('Local Timestamp (IST, Bhubaneswar)')
ax.set_ylabel('Vehicle Speed (km/h)')
ax.grid(True, linestyle='--', alpha=0.6)
ax.legend(loc='lower left', frameon=True)
plt.xticks(rotation=25)
plt.tight_layout()
fig.savefig('results/phase7/figures/04_actual_vs_predicted_timeseries.png', bbox_inches='tight')
plt.close(fig)

# FIGURE 5: Baseline vs ML Error (MAE Comparison Bar Chart)
fig, ax = plt.subplots(figsize=(7, 5), dpi=300)
models = ['Persistence', 'Historical Baseline', 'LightGBM Regressor']
maes = [
    overall_metrics[overall_metrics['model'] == 'Persistence']['MAE'].values[0],
    overall_metrics[overall_metrics['model'] == 'Historical Baseline']['MAE'].values[0],
    overall_metrics[overall_metrics['model'] == 'LightGBM Regressor']['MAE'].values[0]
]
bars = ax.bar(models, maes, color=['#ff7f0e', '#2ca02c', '#1f77b4'], width=0.55, edgecolor='black', alpha=0.85)
for bar in bars:
    yval = bar.get_height()
    ax.text(bar.get_x() + bar.get_width()/2.0, yval + 0.02, f'{yval:.4f} km/h', ha='center', va='bottom', fontweight='bold')
ax.set_title('Figure 5: Test Set Mean Absolute Error (MAE) by Model', fontweight='bold', pad=12)
ax.set_ylabel('Mean Absolute Error (km/h)')
ax.set_ylim(0, max(maes) * 1.2)
ax.grid(axis='y', linestyle='--', alpha=0.7)
plt.tight_layout()
fig.savefig('results/phase7/figures/05_model_comparison_mae.png', bbox_inches='tight')
plt.close(fig)

# FIGURE 6: Baseline vs ML RMSE Bar Chart
fig, ax = plt.subplots(figsize=(7, 5), dpi=300)
rmses = [
    overall_metrics[overall_metrics['model'] == 'Persistence']['RMSE'].values[0],
    overall_metrics[overall_metrics['model'] == 'Historical Baseline']['RMSE'].values[0],
    overall_metrics[overall_metrics['model'] == 'LightGBM Regressor']['RMSE'].values[0]
]
bars = ax.bar(models, rmses, color=['#ff7f0e', '#2ca02c', '#1f77b4'], width=0.55, edgecolor='black', alpha=0.85)
for bar in bars:
    yval = bar.get_height()
    ax.text(bar.get_x() + bar.get_width()/2.0, yval + 0.04, f'{yval:.4f} km/h', ha='center', va='bottom', fontweight='bold')
ax.set_title('Figure 6: Test Set Root Mean Squared Error (RMSE) by Model', fontweight='bold', pad=12)
ax.set_ylabel('Root Mean Squared Error (km/h)')
ax.set_ylim(0, max(rmses) * 1.2)
ax.grid(axis='y', linestyle='--', alpha=0.7)
plt.tight_layout()
fig.savefig('results/phase7/figures/06_model_comparison_rmse.png', bbox_inches='tight')
plt.close(fig)

# FIGURE 7: Error by Hour of Day
hourly_stats = test_df.groupby('hour').apply(
    lambda df_h: pd.Series({
        'ml_mae': mean_absolute_error(df_h['actual_speed'], df_h['predicted_speed']),
        'pers_mae': mean_absolute_error(df_h['actual_speed'], df_h['persistence_prediction']),
        'hist_mae': mean_absolute_error(df_h['actual_speed'], df_h['historical_prediction'])
    })
).reset_index()

fig, ax = plt.subplots(figsize=(10, 5), dpi=300)
ax.plot(hourly_stats['hour'], hourly_stats['pers_mae'], marker='^', linewidth=2, linestyle=':', color='#ff7f0e', label='Persistence MAE')
ax.plot(hourly_stats['hour'], hourly_stats['hist_mae'], marker='s', linewidth=2, linestyle='--', color='#2ca02c', label='Historical Baseline MAE')
ax.plot(hourly_stats['hour'], hourly_stats['ml_mae'], marker='o', linewidth=2.5, color='#1f77b4', label='LightGBM MAE')
ax.set_title('Figure 7: Mean Absolute Error by Hour of Day (Local IST)', fontweight='bold', pad=12)
ax.set_xlabel('Hour of Day (IST)')
ax.set_ylabel('Test Set MAE (km/h)')
ax.set_xticks(range(24))
ax.axvspan(9, 12, alpha=0.15, color='#ff9999', label='Morning Peak (9-12 IST)')
ax.axvspan(17, 20, alpha=0.15, color='#99ccff', label='Evening Peak (17-20 IST)')
ax.legend(loc='upper right', frameon=True)
ax.grid(True, linestyle='--', alpha=0.6)
plt.tight_layout()
fig.savefig('results/phase7/figures/07_error_by_hour.png', bbox_inches='tight')
plt.close(fig)

# FIGURE 8: Peak vs Off-Peak Performance
fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
peak_data = df_metrics[df_metrics['slice'].isin(['peak', 'off_peak'])]
x = np.arange(2)
width = 0.25

pers_bars = peak_data[peak_data['model'] == 'Persistence']['MAE'].values
hist_bars = peak_data[peak_data['model'] == 'Historical Baseline']['MAE'].values
ml_bars = peak_data[peak_data['model'] == 'LightGBM Regressor']['MAE'].values

ax.bar(x - width, pers_bars, width, label='Persistence', color='#ff7f0e', edgecolor='black', alpha=0.85)
ax.bar(x, hist_bars, width, label='Historical Baseline', color='#2ca02c', edgecolor='black', alpha=0.85)
ax.bar(x + width, ml_bars, width, label='LightGBM', color='#1f77b4', edgecolor='black', alpha=0.85)

ax.set_xticks(x)
ax.set_xticklabels(['Peak Traffic (09:00-12:00 & 17:00-20:00 IST)', 'Off-Peak Traffic'], fontweight='bold')
ax.set_ylabel('Mean Absolute Error (km/h)')
ax.set_title('Figure 8: Error Comparison During Peak vs. Off-Peak Hours', fontweight='bold', pad=12)
ax.legend(loc='upper right', frameon=True)
ax.grid(axis='y', linestyle='--', alpha=0.7)
plt.tight_layout()
fig.savefig('results/phase7/figures/08_peak_vs_offpeak_mae.png', bbox_inches='tight')
plt.close(fig)

# FIGURE 9: Weekday vs Weekend Performance
fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
wk_data = df_metrics[df_metrics['slice'].isin(['weekday', 'weekend'])]
x = np.arange(2)
pers_wk = wk_data[wk_data['model'] == 'Persistence']['MAE'].values
hist_wk = wk_data[wk_data['model'] == 'Historical Baseline']['MAE'].values
ml_wk = wk_data[wk_data['model'] == 'LightGBM Regressor']['MAE'].values

ax.bar(x - width, pers_wk, width, label='Persistence', color='#ff7f0e', edgecolor='black', alpha=0.85)
ax.bar(x, hist_wk, width, label='Historical Baseline', color='#2ca02c', edgecolor='black', alpha=0.85)
ax.bar(x + width, ml_wk, width, label='LightGBM', color='#1f77b4', edgecolor='black', alpha=0.85)

ax.set_xticks(x)
ax.set_xticklabels(['Weekday (Thursday - Friday)', 'Weekend (Saturday)'], fontweight='bold')
ax.set_ylabel('Mean Absolute Error (km/h)')
ax.set_title('Figure 9: Prediction Error on Weekdays vs. Weekends', fontweight='bold', pad=12)
ax.legend(loc='upper right', frameon=True)
ax.grid(axis='y', linestyle='--', alpha=0.7)
plt.tight_layout()
fig.savefig('results/phase7/figures/09_weekday_vs_weekend_mae.png', bbox_inches='tight')
plt.close(fig)

# FIGURE 10: Rolling Prediction Error Over Time
rolling_time = test_df.groupby('ts_ist').apply(
    lambda df_t: pd.Series({
        'ml_mae': mean_absolute_error(df_t['actual_speed'], df_t['predicted_speed']),
        'pers_mae': mean_absolute_error(df_t['actual_speed'], df_t['persistence_prediction'])
    })
).reset_index()

rolling_time['ml_roll_mae'] = rolling_time['ml_mae'].rolling(6, min_periods=1).mean()
rolling_time['pers_roll_mae'] = rolling_time['pers_mae'].rolling(6, min_periods=1).mean()

fig, ax = plt.subplots(figsize=(11, 5), dpi=300)
ax.plot(rolling_time['ts_ist'], rolling_time['pers_roll_mae'], color='#ff7f0e', linestyle='--', linewidth=2, label='Persistence 6h-Rolling MAE')
ax.plot(rolling_time['ts_ist'], rolling_time['ml_roll_mae'], color='#1f77b4', linewidth=2.5, label='LightGBM 6h-Rolling MAE')
ax.fill_between(rolling_time['ts_ist'], rolling_time['ml_roll_mae'], rolling_time['pers_roll_mae'], color='#1f77b4', alpha=0.15, label='Performance Advantage')
ax.set_title('Figure 10: Rolling Prediction Error Over Test Period (6-Hour Window)', fontweight='bold', pad=12)
ax.set_xlabel('Timestamp (IST)')
ax.set_ylabel('Rolling MAE (km/h)')
ax.legend(loc='upper left', frameon=True)
ax.grid(True, linestyle='--', alpha=0.6)
plt.xticks(rotation=20)
plt.tight_layout()
fig.savefig('results/phase7/figures/10_rolling_prediction_error.png', bbox_inches='tight')
plt.close(fig)

# FIGURE 11: Feature Importance (Top 15 Features)
importances = model.feature_importances_
feat_imp = pd.DataFrame({'feature': feature_cols, 'importance': importances}).sort_values('importance', ascending=False)
top15 = feat_imp.head(15).sort_values('importance', ascending=True)

fig, ax = plt.subplots(figsize=(9, 6), dpi=300)
bars = ax.barh(top15['feature'], top15['importance'], color='#2b5c8f', edgecolor='black', alpha=0.85)
ax.set_title('Figure 11: Top 15 Feature Importances (LightGBM Split Count)', fontweight='bold', pad=12)
ax.set_xlabel('Split Importance')
ax.grid(axis='x', linestyle='--', alpha=0.7)
plt.tight_layout()
fig.savefig('results/phase7/figures/11_feature_importance.png', bbox_inches='tight')
plt.close(fig)

# FIGURE 12: Traffic Congestion Heatmap (Hour of Day vs Date)
df_clean['date_str'] = df_clean['ts_ist'].dt.strftime('%b %d (%a)')
heatmap_data = df_clean.groupby(['hour', 'date_str'])['speed_ratio'].mean().unstack()

# Sort columns chronologically
unique_dates = df_clean.sort_values('ts_ist')['date_str'].unique()
heatmap_data = heatmap_data[unique_dates]

fig, ax = plt.subplots(figsize=(13, 7), dpi=300)
sns.heatmap(heatmap_data, cmap='RdYlGn', vmin=0.60, vmax=1.00, cbar_kws={'label': 'Speed Ratio (currentSpeed / freeFlowSpeed)'}, ax=ax)
ax.set_title('Figure 12: Citywide Traffic Congestion Heatmap (Bhubaneswar, Jan 4–17, 2026)', fontweight='bold', pad=12)
ax.set_xlabel('Date (Local IST)')
ax.set_ylabel('Hour of Day (IST)')
ax.set_yticks(np.arange(0.5, 24.5, 1))
ax.set_yticklabels(range(24))
plt.xticks(rotation=35, ha='right')
plt.tight_layout()
fig.savefig('results/phase7/figures/12_traffic_congestion_heatmap.png', bbox_inches='tight')
plt.close(fig)

print("All 12 figures successfully generated and saved to results/phase7/figures/")

# Print top 5 features
print("\nTop 5 Most Important Features:")
for i, row in feat_imp.head(5).reset_index().iterrows():
    print(f"  {i+1}. {row['feature']} (Importance: {row['importance']})")

print("\n[Step 8/8] Pipeline execution complete.")
