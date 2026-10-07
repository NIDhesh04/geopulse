"""Temporal Feature Engineering for XGBoost Traffic Speed Prediction.

Loads the full regular hourly grid from Parquet, computes lag features per segment_id,
generates cyclical sine/cosine encodings for time-of-day and day-of-week, filters for
observed rows, drops NaNs, and exports the clean training dataset to ml_features.parquet.

Outputs:
  data/interim/ml_features.parquet
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.config import PARQUET_PATH, INTERIM_DIR, CSV_PATH


def main():
    print("=" * 60)
    print("Step 1: Loading raw dataset...")
    print("=" * 60)

    # Use parquet if available, otherwise csv
    if PARQUET_PATH.exists():
        df = pd.read_parquet(PARQUET_PATH)
        print(f"Loaded {len(df):,} rows from {PARQUET_PATH.name}")
    else:
        df = pd.read_csv(CSV_PATH)
        print(f"Loaded {len(df):,} rows from {CSV_PATH.name}")

    df["hour"] = pd.to_datetime(df["hour"], utc=True)

    # Ensure sorting chronologically per segment_id on full regular grid
    print("\nStep 2: Sorting chronologically per segment_id...")
    df = df.sort_values(["segment_id", "hour"]).reset_index(drop=True)

    # Convert hour to local IST (UTC+5:30) for proper diurnal periodicity
    ist_time = df["hour"].dt.tz_convert("Asia/Kolkata")
    df["hour_of_day_ist"] = ist_time.dt.hour
    df["day_of_week_ist"] = ist_time.dt.dayofweek
    df["is_weekend_num"] = df["day_of_week_ist"].isin([5, 6]).astype(float)

    print("\nStep 3: Generating cyclical sine/cosine encodings...")
    # Cyclical hour of day (period 24)
    df["hour_sin"] = np.sin(2.0 * np.pi * df["hour_of_day_ist"] / 24.0)
    df["hour_cos"] = np.cos(2.0 * np.pi * df["hour_of_day_ist"] / 24.0)

    # Cyclical day of week (period 7)
    df["day_sin"] = np.sin(2.0 * np.pi * df["day_of_week_ist"] / 7.0)
    df["day_cos"] = np.cos(2.0 * np.pi * df["day_of_week_ist"] / 7.0)

    print("\nStep 4: Computing lag features (t-1, t-2, t-3) per segment_id...")
    # Group by segment_id before shifting to strictly prevent cross-segment leakage
    grouped = df.groupby("segment_id")["currentSpeed"]
    df["speed_t-1"] = grouped.shift(1)
    df["speed_t-2"] = grouped.shift(2)
    df["speed_t-3"] = grouped.shift(3)

    print("\nStep 5: Filtering observed rows and dropping missing lags...")
    # Filter for observed rows only
    obs_mask = df["is_observed"].astype(bool)
    df_obs = df[obs_mask].copy()

    # Drop rows where lag features are NaN (e.g. beginning of time series or after multi-hour gaps)
    lag_cols = ["speed_t-1", "speed_t-2", "speed_t-3"]
    df_clean = df_obs.dropna(subset=["currentSpeed", "freeFlowSpeed"] + lag_cols).copy()

    print(f"Total rows before filtering: {len(df):,}")
    print(f"Observed rows: {len(df_obs):,}")
    print(f"Final clean feature rows with complete lags: {len(df_clean):,}")

    # Keep relevant feature columns
    keep_cols = [
        "segment_id",
        "hour",
        "hour_of_day_ist",
        "day_of_week_ist",
        "is_weekend_num",
        "hour_sin",
        "hour_cos",
        "day_sin",
        "day_cos",
        "freeFlowSpeed",
        "speed_t-1",
        "speed_t-2",
        "speed_t-3",
        "currentSpeed",
    ]
    df_export = df_clean[keep_cols].copy()

    out_path = INTERIM_DIR / "ml_features.parquet"
    print(f"\nStep 6: Saving engineered dataset to {out_path}...")
    df_export.to_parquet(out_path, index=False)
    print(f"ml_features.parquet saved successfully! ({out_path.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
