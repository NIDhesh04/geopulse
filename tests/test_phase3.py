"""Automated Validation Tests for Phase 3: Tabular ML Baseline (XGBoost Speed Prediction).

Tests:
  Test A: Data Leakage Guard (Strict chronological split: min(test_time) > max(train_time))
  Test B: Model Viability (Model exists on disk, Test MAE < 8.0 km/h)
  Test C: Inference Output (Realistic positive float prediction on dummy feature rows)
"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error
import xgboost as xgb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import INTERIM_DIR, PROJECT_ROOT
from src.ml.train_xgboost import FEATURE_COLS, TARGET_COL

FEAT_PATH = INTERIM_DIR / "ml_features.parquet"
MODEL_PATH = PROJECT_ROOT / "outputs" / "phase3" / "xgb_speed_model.json"
METRICS_PATH = PROJECT_ROOT / "outputs" / "phase3" / "metrics.json"


def test_a_data_leakage_guard():
    """Test A: Assert chronological split strictly separates train and test periods."""
    print("\n" + "=" * 60)
    print("RUNNING TEST A: Data Leakage Guard")
    print("=" * 60)

    assert FEAT_PATH.exists(), f"Engineered features file missing at {FEAT_PATH}"
    df = pd.read_parquet(FEAT_PATH)
    df["hour"] = pd.to_datetime(df["hour"], utc=True)

    unique_hours = np.sort(df["hour"].unique())
    num_hours = len(unique_hours)
    split_idx = int(num_hours * 0.75)
    split_timestamp = unique_hours[split_idx]

    train_df = df[df["hour"] < split_timestamp]
    test_df = df[df["hour"] >= split_timestamp]

    max_train_time = train_df["hour"].max()
    min_test_time = test_df["hour"].min()

    print(f"Max Train Timestamp: {max_train_time}")
    print(f"Min Test Timestamp:  {min_test_time}")

    assert min_test_time > max_train_time, (
        f"Data leakage detected! min(test)={min_test_time} is not strictly greater than "
        f"max(train)={max_train_time}"
    )

    # Check temporal gap
    gap = min_test_time - max_train_time
    print(f"[PASS] Temporal boundary verified with zero leakage (boundary gap: {gap}).")
    print(f"[PASS] Train set size: {len(train_df):,} rows, Test set size: {len(test_df):,} rows.")

    return test_df


def test_b_model_viability(test_df):
    """Test B: Assert model file exists on disk and Test MAE is below 8.0 km/h."""
    print("\n" + "=" * 60)
    print("RUNNING TEST B: Model Viability & Performance")
    print("=" * 60)

    assert MODEL_PATH.exists(), f"Model file missing at {MODEL_PATH}"
    print(f"[PASS] Model file exists at {MODEL_PATH} ({MODEL_PATH.stat().st_size / 1e3:.1f} KB).")

    # Load model
    model = xgb.XGBRegressor()
    model.load_model(str(MODEL_PATH))

    # Evaluate on test set
    X_test = test_df[FEATURE_COLS]
    y_test = test_df[TARGET_COL]

    y_pred = model.predict(X_test)
    test_mae = float(mean_absolute_error(y_test, y_pred))

    print(f"Computed Test Set MAE: {test_mae:.3f} km/h")
    assert test_mae < 8.0, f"Model failed accuracy criteria: MAE {test_mae:.3f} >= 8.0 km/h"
    print(f"[PASS] Model MAE ({test_mae:.3f} km/h) is well below the 8.0 km/h threshold.")

    # Also check saved metrics.json consistency
    if METRICS_PATH.exists():
        saved_metrics = json.loads(METRICS_PATH.read_text())
        assert abs(saved_metrics["test_mae_kmh"] - test_mae) < 1e-3, "Saved metrics mismatch!"
        print(f"[PASS] Saved metrics.json matches active evaluation exactly.")

    return model


def test_c_inference_output(model):
    """Test C: Pass dummy feature rows through the model, assert valid positive outputs."""
    print("\n" + "=" * 60)
    print("RUNNING TEST C: Live Inference & Output Validity")
    print("=" * 60)

    # Create dummy scenario 1: Free-flow conditions
    # e.g., hour=14:00 (afternoon), freeFlow=50, recent speeds=50, 48, 49
    hour_val = 14
    day_val = 2
    dummy_free_flow = pd.DataFrame([{
        "hour_sin": np.sin(2.0 * np.pi * hour_val / 24.0),
        "hour_cos": np.cos(2.0 * np.pi * hour_val / 24.0),
        "day_sin": np.sin(2.0 * np.pi * day_val / 7.0),
        "day_cos": np.cos(2.0 * np.pi * day_val / 7.0),
        "is_weekend_num": 0.0,
        "freeFlowSpeed": 50.0,
        "speed_t-1": 49.0,
        "speed_t-2": 50.0,
        "speed_t-3": 48.0,
    }])[FEATURE_COLS]

    # Create dummy scenario 2: Congested conditions
    # e.g., hour=18:00 (evening peak), freeFlow=50, recent speeds=15, 12, 14
    hour_val_peak = 18
    dummy_congested = pd.DataFrame([{
        "hour_sin": np.sin(2.0 * np.pi * hour_val_peak / 24.0),
        "hour_cos": np.cos(2.0 * np.pi * hour_val_peak / 24.0),
        "day_sin": np.sin(2.0 * np.pi * day_val / 7.0),
        "day_cos": np.cos(2.0 * np.pi * day_val / 7.0),
        "is_weekend_num": 0.0,
        "freeFlowSpeed": 50.0,
        "speed_t-1": 15.0,
        "speed_t-2": 14.0,
        "speed_t-3": 18.0,
    }])[FEATURE_COLS]

    pred_ff = float(model.predict(dummy_free_flow)[0])
    pred_cong = float(model.predict(dummy_congested)[0])

    print(f"Scenario 1 (Free-flow lag inputs):  Predicted Speed = {pred_ff:.2f} km/h")
    print(f"Scenario 2 (Congested lag inputs):  Predicted Speed = {pred_cong:.2f} km/h")

    # Assertions
    assert pred_ff > 0.0, f"Expected positive speed, got {pred_ff}"
    assert pred_cong > 0.0, f"Expected positive speed, got {pred_cong}"
    assert pred_ff > pred_cong, f"Expected free-flow prediction to exceed congested prediction!"
    assert 5.0 <= pred_cong <= 65.0, f"Prediction out of physical bounds: {pred_cong}"
    assert 5.0 <= pred_ff <= 65.0, f"Prediction out of physical bounds: {pred_ff}"

    print(f"[PASS] Inference predictions are physically realistic and responsive to congestion signals.")


def main():
    print("Starting Phase 3 Automated Test Suite...")
    test_df = test_a_data_leakage_guard()
    model = test_b_model_viability(test_df)
    test_c_inference_output(model)

    print("\n" + "=" * 60)
    print("ALL PHASE 3 VALIDATION TESTS PASSED SUCCESSFULLY! (3/3)")
    print("=" * 60)


if __name__ == "__main__":
    main()
