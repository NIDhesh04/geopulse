"""Chronological XGBoost Model Training for Traffic Speed Prediction.

Trains an XGBoost Regressor strictly chronologically (first 75% hours for train,
last 25% hours for test) to prevent temporal data leakage. Evaluates MAE, RMSE, R2,
plots Actual vs Predicted speeds for a 48-hour window, and serializes the model.

Outputs:
  outputs/phase3/xgb_speed_model.json
  outputs/phase3/actual_vs_predicted.png
  outputs/phase3/metrics.json
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import xgboost as xgb

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.config import INTERIM_DIR, PROJECT_ROOT

PHASE3_OUT = PROJECT_ROOT / "outputs" / "phase3"
PHASE3_OUT.mkdir(parents=True, exist_ok=True)

FEATURE_COLS = [
    "hour_sin",
    "hour_cos",
    "day_sin",
    "day_cos",
    "is_weekend_num",
    "freeFlowSpeed",
    "speed_t-1",
    "speed_t-2",
    "speed_t-3",
]
TARGET_COL = "currentSpeed"


def main():
    print("=" * 60)
    print("Step 1: Loading engineered feature dataset...")
    print("=" * 60)
    feat_path = INTERIM_DIR / "ml_features.parquet"
    df = pd.read_parquet(feat_path)
    df["hour"] = pd.to_datetime(df["hour"], utc=True)
    print(f"Loaded {len(df):,} rows from {feat_path.name}")

    print("\nStep 2: Performing strict chronological split (75% train, 25% test)...")
    unique_hours = np.sort(df["hour"].unique())
    num_hours = len(unique_hours)
    split_idx = int(num_hours * 0.75)
    split_timestamp = unique_hours[split_idx]

    train_df = df[df["hour"] < split_timestamp].copy()
    test_df = df[df["hour"] >= split_timestamp].copy()

    print(f"Total Unique Timestamps: {num_hours}")
    print(f"Train Timestamps: {len(train_df['hour'].unique())} (up to {train_df['hour'].max()})")
    print(f"Test Timestamps:  {len(test_df['hour'].unique())} (from {test_df['hour'].min()})")
    print(f"Train Rows: {len(train_df):,} ({len(train_df)/len(df)*100:.1f}%)")
    print(f"Test Rows:  {len(test_df):,} ({len(test_df)/len(df)*100:.1f}%)")

    # Guard against leakage
    assert test_df["hour"].min() > train_df["hour"].max(), "Data leakage detected: test overlaps train!"

    X_train = train_df[FEATURE_COLS]
    y_train = train_df[TARGET_COL]
    X_test = test_df[FEATURE_COLS]
    y_test = test_df[TARGET_COL]

    print("\nStep 3: Training XGBoost Regressor...")
    model = xgb.XGBRegressor(
        n_estimators=150,
        max_depth=6,
        learning_rate=0.08,
        subsample=0.85,
        colsample_bytree=0.85,
        random_state=42,
        n_jobs=-1,
        early_stopping_rounds=15,
        eval_metric="mae",
    )

    model.fit(
        X_train,
        y_train,
        eval_set=[(X_train, y_train), (X_test, y_test)],
        verbose=30,
    )

    print("\nStep 4: Evaluating on test set...")
    y_pred = model.predict(X_test)
    test_df["y_pred"] = y_pred

    mae = float(mean_absolute_error(y_test, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
    r2 = float(r2_score(y_test, y_pred))

    print(f"Test Set Evaluation Metrics:")
    print(f"  - Mean Absolute Error (MAE):     {mae:.3f} km/h")
    print(f"  - Root Mean Squared Error (RMSE): {rmse:.3f} km/h")
    print(f"  - Coefficient of Determination (R2): {r2:.3f}")

    metrics_dict = {
        "train_rows": len(train_df),
        "test_rows": len(test_df),
        "train_hours": int(len(train_df["hour"].unique())),
        "test_hours": int(len(test_df["hour"].unique())),
        "split_timestamp": str(split_timestamp),
        "features": FEATURE_COLS,
        "test_mae_kmh": mae,
        "test_rmse_kmh": rmse,
        "test_r2": r2,
    }
    metrics_path = PHASE3_OUT / "metrics.json"
    metrics_path.write_text(json.dumps(metrics_dict, indent=2))
    print(f"Saved evaluation metrics to {metrics_path}")

    print("\nStep 5: Serializing trained model to outputs/phase3/xgb_speed_model.json...")
    model_path = PHASE3_OUT / "xgb_speed_model.json"
    model.save_model(str(model_path))
    print(f"Model saved successfully ({model_path.stat().st_size / 1e3:.1f} KB).")

    print("\nStep 6: Generating Actual vs Predicted Speed comparison chart (48-hour window)...")
    # Select a segment that has complete observations across test hours
    sample_sid = 10  # representative arterial segment
    seg_test = test_df[test_df["segment_id"] == sample_sid].sort_values("hour")
    # Take first 48 hours of test window
    seg_48h = seg_test.head(48).copy()
    seg_48h["ist_time"] = seg_48h["hour"].dt.tz_convert("Asia/Kolkata")

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(
        seg_48h["ist_time"],
        seg_48h["currentSpeed"],
        label="Actual Observed Speed",
        color="#1f77b4",
        lw=2.2,
        marker="o",
        markersize=4,
    )
    ax.plot(
        seg_48h["ist_time"],
        seg_48h["y_pred"],
        label="XGBoost Predicted Speed",
        color="#d62728",
        lw=2.0,
        ls="--",
        marker="s",
        markersize=3,
    )
    ax.axhline(
        seg_48h["freeFlowSpeed"].iloc[0],
        color="grey",
        ls=":",
        lw=1.5,
        label=f"Free Flow Speed ({seg_48h['freeFlowSpeed'].iloc[0]:.0f} km/h)",
    )

    ax.set_title(
        f"XGBoost Traffic Speed Prediction: Actual vs Predicted (Segment {sample_sid})\n"
        f"48-Hour Continuous Test Window (IST) | Test MAE = {mae:.2f} km/h, R2 = {r2:.2f}",
        fontsize=12,
    )
    ax.set_ylabel("Speed (km/h)", fontsize=11)
    ax.set_xlabel("Date & Time (IST)", fontsize=11)
    ax.legend(loc="lower left", fontsize=10)
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()

    chart_path = PHASE3_OUT / "actual_vs_predicted.png"
    fig.savefig(chart_path, dpi=140)
    plt.close(fig)
    print(f"Comparison chart saved successfully to {chart_path}")


if __name__ == "__main__":
    main()
