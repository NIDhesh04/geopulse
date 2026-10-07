"""Phase 1 structural, temporal, missingness and semantic validation of the
Bhubaneswar CSV. Read-only on raw data.

Outputs (outputs/phase1/metrics/):
  dataset_structure.json, segment_missingness.csv, timestamp_missingness.csv,
  hour_of_day_missingness.csv, gap_runs.csv, numeric_summary.csv,
  semantic_checks.json, csv_vs_parquet.json
Figures: missingness_by_segment.png, coverage_over_time.png,
  missingness_hour_of_day.png, gap_length_hist.png, traffic_distributions.png
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.config import CSV_PATH, PARQUET_PATH, METRIC_DIR, FIG_DIR, INTERIM_DIR  # noqa: E402

NUMERIC = ["currentSpeed", "freeFlowSpeed", "currentTravelTime", "freeFlowTravelTime",
           "confidence", "speed_ratio"]


def load():
    df = pd.read_csv(CSV_PATH)
    df["hour"] = pd.to_datetime(df["hour"], utc=True)
    for c in ["is_weekend", "is_congested", "is_observed", "is_missing"]:
        df[c] = df[c].astype(str).str.lower().map({"true": True, "false": False})
    return df


def structure(df):
    hours = df["hour"].drop_duplicates().sort_values()
    full_grid = pd.date_range(hours.min(), hours.max(), freq="h", tz="UTC")
    seg_hour_dups = int(df.duplicated(["segment_id", "hour"]).sum())
    per_seg_counts = df.groupby("segment_id").size()
    ist = df["hour"].dt.tz_convert("Asia/Kolkata")
    # verify hour_of_day / day_of_week columns: UTC or local?
    hod_matches_utc = float((df["hour_of_day"] == df["hour"].dt.hour).mean())
    hod_matches_ist = float((df["hour_of_day"] == ist.dt.hour).mean())
    dow_matches_utc = float((df["day_of_week"] == df["hour"].dt.dayofweek).mean())
    out = {
        "rows": len(df), "columns": df.shape[1], "column_names": list(df.columns),
        "unique_segments": int(df["segment_id"].nunique()),
        "segment_id_min": int(df["segment_id"].min()), "segment_id_max": int(df["segment_id"].max()),
        "unique_hours": int(hours.size),
        "min_hour_utc": str(hours.min()), "max_hour_utc": str(hours.max()),
        "min_hour_ist": str(hours.min().tz_convert("Asia/Kolkata")),
        "max_hour_ist": str(hours.max().tz_convert("Asia/Kolkata")),
        "span_hours": (hours.max() - hours.min()) / pd.Timedelta("1h") + 1,
        "full_hourly_grid_len": len(full_grid),
        "hours_missing_from_grid": int(len(full_grid.difference(pd.DatetimeIndex(hours)))),
        "expected_rows_segments_x_hours": int(df["segment_id"].nunique() * len(full_grid)),
        "duplicate_segment_hour_rows": seg_hour_dups,
        "rows_per_segment_min": int(per_seg_counts.min()), "rows_per_segment_max": int(per_seg_counts.max()),
        "is_regular_grid": bool(seg_hour_dups == 0 and per_seg_counts.nunique() == 1
                                and len(full_grid) == hours.size),
        "unique_days_utc": int(df["hour"].dt.date.nunique()),
        "unique_days_ist": int(ist.dt.date.nunique()),
        "hour_of_day_col_matches_utc": hod_matches_utc,
        "hour_of_day_col_matches_ist": hod_matches_ist,
        "day_of_week_col_matches_utc": dow_matches_utc,
        "is_observed_true": int(df["is_observed"].sum()),
        "is_observed_false": int((~df["is_observed"]).sum()),
        "is_missing_true": int(df["is_missing"].sum()),
        "observed_and_missing_consistent": bool((df["is_observed"] == ~df["is_missing"]).all()),
        "observed_pct": float(df["is_observed"].mean() * 100),
        "weekend_rows": int(df["is_weekend"].sum()), "weekday_rows": int((~df["is_weekend"]).sum()),
        "congestion_level_counts": df["congestion_level"].value_counts(dropna=False).to_dict(),
    }
    # per-day / per-hour-of-day / per-dow observation counts (observed rows only)
    obs = df[df["is_observed"]]
    out["observed_rows_per_day_utc"] = {str(k): int(v) for k, v in obs.groupby(obs["hour"].dt.date).size().items()}
    out["observed_rows_per_hour_of_day_utc"] = {int(k): int(v) for k, v in obs.groupby(obs["hour"].dt.hour).size().items()}
    out["observed_rows_per_day_of_week_utc"] = {int(k): int(v) for k, v in obs.groupby(obs["hour"].dt.dayofweek).size().items()}
    out["observed_rows_per_hour_stats"] = obs.groupby("hour").size().describe().to_dict()
    return out


def missingness(df, struct):
    seg = df.groupby("segment_id").agg(total=("is_observed", "size"), observed=("is_observed", "sum"))
    seg["missing"] = seg["total"] - seg["observed"]
    seg["missing_pct"] = seg["missing"] / seg["total"] * 100
    seg.sort_values("missing_pct").to_csv(METRIC_DIR / "segment_missingness.csv")

    ts = df.groupby("hour").agg(observed=("is_observed", "sum"), total=("is_observed", "size"))
    ts["missing_pct"] = (1 - ts["observed"] / ts["total"]) * 100
    ts.to_csv(METRIC_DIR / "timestamp_missingness.csv")

    ist_hod = df["hour"].dt.tz_convert("Asia/Kolkata").dt.hour
    hod = df.groupby(ist_hod)["is_missing"].mean().mul(100).rename("missing_pct_ist_hour")
    hod.to_csv(METRIC_DIR / "hour_of_day_missingness.csv")

    # consecutive-gap runs per segment
    runs = []
    for sid, g in df.sort_values("hour").groupby("segment_id"):
        m = g["is_missing"].to_numpy()
        h = g["hour"].to_numpy()
        i = 0
        while i < len(m):
            if m[i]:
                j = i
                while j + 1 < len(m) and m[j + 1]:
                    j += 1
                runs.append((sid, h[i], h[j], j - i + 1))
                i = j + 1
            else:
                i += 1
    runs = pd.DataFrame(runs, columns=["segment_id", "start", "end", "length_h"])
    runs.to_csv(METRIC_DIR / "gap_runs.csv", index=False)

    # whole-timestamp outages: hours with >=90% missing
    outage_hours = ts[ts["missing_pct"] >= 90].index
    res = {
        "segment_missing_pct": seg["missing_pct"].describe().to_dict(),
        "segments_with_0pct_missing": int((seg["missing_pct"] == 0).sum()),
        "segments_missing_gt_20pct": int((seg["missing_pct"] > 20).sum()),
        "segments_missing_gt_50pct": int((seg["missing_pct"] > 50).sum()),
        "best_segments": seg.nsmallest(5, "missing_pct")["missing_pct"].round(2).to_dict(),
        "worst_segments": seg.nlargest(10, "missing_pct")["missing_pct"].round(2).to_dict(),
        "timestamp_missing_pct": ts["missing_pct"].describe().to_dict(),
        "hours_fully_missing": int((ts["observed"] == 0).sum()),
        "hours_ge90pct_missing": int(len(outage_hours)),
        "hours_fully_observed": int((ts["observed"] == ts["total"]).sum()),
        "worst_hours": {str(k): round(v, 2) for k, v in ts["missing_pct"].nlargest(15).items()},
        "missing_by_ist_hour_of_day": hod.round(2).to_dict(),
        "gap_runs_total": int(len(runs)),
        "gap_run_length_dist": runs["length_h"].value_counts().sort_index().head(30).to_dict(),
        "gap_runs_len1": int((runs["length_h"] == 1).sum()),
        "gap_runs_len_le3": int((runs["length_h"] <= 3).sum()),
        "gap_runs_len_ge6": int((runs["length_h"] >= 6).sum()),
        "gap_runs_len_ge24": int((runs["length_h"] >= 24).sum()),
        "max_gap_h": int(runs["length_h"].max()) if len(runs) else 0,
        "missing_rows_in_runs_ge6": int(runs.loc[runs["length_h"] >= 6, "length_h"].sum()),
        "leading_gap_note": "first grid hour per segment is "
                            f"{df.sort_values('hour').groupby('segment_id').head(1)['is_observed'].mean()*100:.1f}% observed",
    }

    # Figures
    fig, ax = plt.subplots(figsize=(11, 4))
    s = seg.sort_values("missing_pct", ascending=False)
    ax.bar(range(len(s)), s["missing_pct"], width=1.0, color="#c0504d")
    ax.set_xlabel("segments (sorted by missingness)"); ax.set_ylabel("% hours missing")
    ax.set_title("Missingness by segment (700 segments)")
    ax.axhline(s["missing_pct"].median(), ls="--", c="k", lw=1, label=f"median {s['missing_pct'].median():.1f}%")
    ax.legend(); fig.tight_layout(); fig.savefig(FIG_DIR / "missingness_by_segment.png", dpi=130); plt.close(fig)

    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(ts.index.tz_convert("Asia/Kolkata"), ts["observed"], lw=1, color="#1f77b4")
    ax.set_ylabel("observed segments"); ax.set_title("Traffic coverage over time (observed segments per hour, IST)")
    ax.set_ylim(0, 720); ax.axhline(700, ls=":", c="grey")
    fig.autofmt_xdate(); fig.tight_layout(); fig.savefig(FIG_DIR / "coverage_over_time.png", dpi=130); plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 3.5))
    ax.bar(hod.index, hod.values, color="#8064a2")
    ax.set_xlabel("hour of day (IST)"); ax.set_ylabel("% missing"); ax.set_title("Missingness by hour of day (IST)")
    fig.tight_layout(); fig.savefig(FIG_DIR / "missingness_hour_of_day.png", dpi=130); plt.close(fig)

    if len(runs):
        fig, ax = plt.subplots(figsize=(8, 3.5))
        vc = runs["length_h"].value_counts().sort_index()
        ax.bar(vc.index, vc.values, color="#4bacc6"); ax.set_yscale("log")
        ax.set_xlabel("consecutive missing hours"); ax.set_ylabel("number of gap runs (log)")
        ax.set_title("Gap-run length distribution")
        fig.tight_layout(); fig.savefig(FIG_DIR / "gap_length_hist.png", dpi=130); plt.close(fig)
    return res


def semantics(df):
    obs = df[df["is_observed"]].copy()
    pct = [0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]
    rows = []
    for c in NUMERIC:
        x = obs[c]
        d = x.describe(percentiles=pct).to_dict()
        d.update(field=c, nulls_in_observed=int(x.isna().sum()), negatives=int((x < 0).sum()),
                 zeros=int((x == 0).sum()), non_integer=int((x.dropna() % 1 != 0).sum()))
        rows.append(d)
    num = pd.DataFrame(rows).set_index("field")
    num.to_csv(METRIC_DIR / "numeric_summary.csv")

    # Non-observed rows should be all-null
    nonobs = df[~df["is_observed"]]
    sr_calc = obs["currentSpeed"] / obs["freeFlowSpeed"]
    tt_ratio = obs["freeFlowTravelTime"] / obs["currentTravelTime"]
    # implied length from each speed/time pair (km/h * s / 3.6 = m)
    obs["L_cur_m"] = obs["currentSpeed"] * obs["currentTravelTime"] / 3.6
    obs["L_ff_m"] = obs["freeFlowSpeed"] * obs["freeFlowTravelTime"] / 3.6
    per_seg_L = obs.groupby("segment_id").agg(L_cur_med=("L_cur_m", "median"), L_ff_med=("L_ff_m", "median"),
                                              L_ff_cv=("L_ff_m", lambda s: s.std() / s.mean()),
                                              L_cur_cv=("L_cur_m", lambda s: s.std() / s.mean()),
                                              ffs_nunique=("freeFlowSpeed", "nunique"),
                                              fftt_nunique=("freeFlowTravelTime", "nunique"),
                                              ffs_med=("freeFlowSpeed", "median"),
                                              fftt_med=("freeFlowTravelTime", "median"))
    per_seg_L.to_csv(INTERIM_DIR / "segment_implied_length.csv")

    # congestion_level thresholds inferred from speed_ratio
    lvl = obs.groupby("congestion_level")["speed_ratio"].agg(["min", "max", "count"]).sort_values("min")
    cong = obs.groupby("is_congested")["speed_ratio"].agg(["min", "max", "count"])

    checks = {
        "nonobserved_rows_all_traffic_null": bool(nonobs[NUMERIC].isna().all().all()),
        "nonobserved_congestion_level_null": bool(nonobs["congestion_level"].isna().all()),
        "nonobserved_is_congested_values": nonobs["is_congested"].value_counts().to_dict(),
        "observed_rows_with_any_null_traffic": int(obs[NUMERIC].isna().any(axis=1).sum()),
        "currentSpeed_le_0": int((obs["currentSpeed"] <= 0).sum()),
        "currentSpeed_gt_freeFlowSpeed": int((obs["currentSpeed"] > obs["freeFlowSpeed"]).sum()),
        "currentSpeed_eq_freeFlowSpeed": int((obs["currentSpeed"] == obs["freeFlowSpeed"]).sum()),
        "currentTT_lt_freeFlowTT": int((obs["currentTravelTime"] < obs["freeFlowTravelTime"]).sum()),
        "currentTT_eq_freeFlowTT": int((obs["currentTravelTime"] == obs["freeFlowTravelTime"]).sum()),
        "speed_ratio_gt_1": int((obs["speed_ratio"] > 1).sum()),
        "speed_ratio_lt_0": int((obs["speed_ratio"] < 0).sum()),
        "speed_ratio_equals_cs_over_ffs_maxabs": float((obs["speed_ratio"] - sr_calc).abs().max()),
        "speed_ratio_vs_tt_ratio_maxabs": float((obs["speed_ratio"] - tt_ratio).abs().max()),
        "speed_ratio_vs_tt_ratio_p99abs": float((obs["speed_ratio"] - tt_ratio).abs().quantile(.99)),
        "corr_speed_ratio_tt_ratio": float(np.corrcoef(obs["speed_ratio"], tt_ratio)[0, 1]),
        "congestion_level_speed_ratio_ranges": lvl.to_dict(orient="index"),
        "is_congested_speed_ratio_ranges": {str(k): v for k, v in cong.to_dict(orient="index").items()},
        "confidence_unique_values": int(obs["confidence"].nunique()),
        "confidence_eq_1_pct": float((obs["confidence"] == 1).mean() * 100),
        "confidence_lt_0_7_pct": float((obs["confidence"] < 0.7).mean() * 100),
        "roadClosure_column_present": "roadClosure" in df.columns,
        "implied_length_cur_vs_ff_rel_diff_median": float(((obs["L_cur_m"] - obs["L_ff_m"]).abs() / obs["L_ff_m"]).median()),
        "implied_length_cur_vs_ff_rel_diff_p95": float(((obs["L_cur_m"] - obs["L_ff_m"]).abs() / obs["L_ff_m"]).quantile(.95)),
        "per_segment_ff_length_cv_median": float(per_seg_L["L_ff_cv"].median()),
        "per_segment_ff_length_cv_p95": float(per_seg_L["L_ff_cv"].quantile(.95)),
        "segments_constant_freeFlowSpeed": int((per_seg_L["ffs_nunique"] == 1).sum()),
        "segments_constant_freeFlowTT": int((per_seg_L["fftt_nunique"] == 1).sum()),
        "implied_ff_length_m_summary": per_seg_L["L_ff_med"].describe().to_dict(),
        "fftt_median_s_summary": per_seg_L["fftt_med"].describe().to_dict(),
    }
    (METRIC_DIR / "semantic_checks.json").write_text(json.dumps(checks, indent=2, default=str))

    fig, axes = plt.subplots(2, 3, figsize=(13, 7))
    for ax, c in zip(axes.flat, NUMERIC):
        x = obs[c].dropna()
        if "TravelTime" in c:
            ax.hist(np.log10(x.clip(lower=1)), bins=60, color="#4f81bd"); ax.set_xlabel(f"log10({c} s)")
        else:
            ax.hist(x, bins=60, color="#4f81bd"); ax.set_xlabel(c)
        ax.set_yscale("log")
    fig.suptitle("Distributions of traffic fields (observed rows)")
    fig.tight_layout(); fig.savefig(FIG_DIR / "traffic_distributions.png", dpi=130); plt.close(fig)
    return num, checks


def csv_vs_parquet(df):
    try:
        pq = pd.read_parquet(PARQUET_PATH)
    except Exception as e:
        return {"error": str(e)}
    res = {"parquet_rows": len(pq), "parquet_cols": list(pq.columns),
           "extra_cols_vs_csv": sorted(set(pq.columns) - set(df.columns)),
           "missing_cols_vs_csv": sorted(set(df.columns) - set(pq.columns))}
    return res


def main():
    df = load()
    struct = structure(df)
    miss = missingness(df, struct)
    num, checks = semantics(df)
    cvp = csv_vs_parquet(df)
    (METRIC_DIR / "dataset_structure.json").write_text(json.dumps(struct, indent=2, default=str))
    (METRIC_DIR / "missingness_summary.json").write_text(json.dumps(miss, indent=2, default=str))
    (METRIC_DIR / "csv_vs_parquet.json").write_text(json.dumps(cvp, indent=2, default=str))
    print(json.dumps({k: v for k, v in struct.items() if not k.startswith("observed_rows_per")}, indent=1, default=str))
    print(json.dumps(miss, indent=1, default=str))
    print(num.round(3).to_string())
    print(json.dumps(checks, indent=1, default=str))
    print(json.dumps(cvp, indent=1, default=str))


if __name__ == "__main__":
    main()
