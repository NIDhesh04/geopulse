"""Static per-segment metadata extraction + segment->physical road mapping checks.

Reads the Parquet (identical content to DuckDB table `traffic`) because it holds
osmid / road_name / road_type / length_m / lat / lon that the CSV lacks.

Outputs:
  data/interim/segment_metadata.csv
  outputs/phase1/metrics/metadata_checks.json
  outputs/phase1/metrics/tomtom_signature_groups.csv
"""
import ast
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.config import PARQUET_PATH, METRIC_DIR, INTERIM_DIR  # noqa: E402


def parse_osmid(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    s = str(v).strip()
    if s.startswith("["):
        return tuple(int(x) for x in ast.literal_eval(s))
    return (int(float(s)),)


def main():
    df = pd.read_parquet(PARQUET_PATH)
    static_cols = ["osmid", "road_name", "road_type", "length_m", "lat", "lon"]
    obs = df[df["is_observed"]]

    # Is static metadata constant per segment? (only populated on observed rows)
    nun = obs.groupby("segment_id")[static_cols].nunique(dropna=False)
    meta = obs.groupby("segment_id")[static_cols].first()
    meta["osmid_tuple"] = meta["osmid"].map(parse_osmid)
    meta["n_osm_ways"] = meta["osmid_tuple"].map(lambda t: len(t) if t else 0)
    meta["osmid_key"] = meta["osmid_tuple"].map(lambda t: "|".join(map(str, sorted(t))) if t else None)

    # TomTom-side quantities (per segment, robust medians)
    tt = obs.groupby("segment_id").agg(
        ffs=("freeFlowSpeed", "median"), fftt=("freeFlowTravelTime", "median"),
        cs_med=("currentSpeed", "median"), cs_min=("currentSpeed", "min"),
        conf_med=("confidence", "median"),
        roadClosure_any=("roadClosure", lambda s: bool(s.fillna(False).any())))
    meta = meta.join(tt)
    meta["tomtom_len_m"] = meta["ffs"] * meta["fftt"] / 3.6  # length implied by TomTom
    meta["tomtom_len_over_osm_len"] = meta["tomtom_len_m"] / meta["length_m"]
    meta["edge_fftt_s"] = meta["length_m"] / (meta["ffs"] / 3.6)  # free-flow time for the OSM edge itself

    # Identical TomTom time-series signatures -> many OSM edges answered by same TomTom flow segment?
    piv = obs.pivot_table(index="segment_id", columns="hour", values="currentSpeed")
    sig = piv.round(3).astype(str).agg("|".join, axis=1) + "#" + meta["fftt"].astype(str)
    meta["tomtom_signature"] = pd.factorize(sig)[0]
    grp = meta.groupby("tomtom_signature").agg(n_segments=("road_type", "size"),
                                               road_types=("road_type", lambda s: ",".join(sorted(set(map(str, s))))),
                                               fftt=("fftt", "first"), ffs=("ffs", "first"),
                                               tomtom_len_m=("tomtom_len_m", "first"))
    grp.sort_values("n_segments", ascending=False).to_csv(METRIC_DIR / "tomtom_signature_groups.csv")

    # Spatial spread of segments sharing a signature
    spreads = []
    for g, sub in meta.groupby("tomtom_signature"):
        if len(sub) > 1:
            dlat = (sub["lat"].max() - sub["lat"].min()) * 111_000
            dlon = (sub["lon"].max() - sub["lon"].min()) * 111_000 * np.cos(np.radians(20.3))
            spreads.append(np.hypot(dlat, dlon))

    # Pairwise correlation of currentSpeed series (how independent are segments?)
    pf = piv.T.ffill().bfill()
    corr = np.corrcoef(pf.T.values)
    iu = np.triu_indices_from(corr, 1)
    cvals = corr[iu][~np.isnan(corr[iu])]

    dup_osm = meta["osmid_key"].duplicated(keep=False)
    dup_xy = meta[["lat", "lon"]].round(6).duplicated(keep=False)

    checks = {
        "static_cols_constant_per_segment": {c: bool((nun[c] <= 1).all()) for c in static_cols},
        "static_cols_null_on_missing_rows": bool(df.loc[~df["is_observed"], static_cols].isna().all().all()),
        "road_type_counts": meta["road_type"].astype(str).value_counts().to_dict(),
        "road_name_unique": int(meta["road_name"].nunique()),
        "road_name_sample": meta["road_name"].head(10).tolist(),
        "road_name_eq_segment_id_pct": float((meta["road_name"] == meta.index).mean() * 100),
        "n_osm_ways_dist": meta["n_osm_ways"].value_counts().sort_index().to_dict(),
        "unique_osm_ways_total": int(len({w for t in meta["osmid_tuple"] if t for w in t})),
        "segments_sharing_identical_osmid_set": int(dup_osm.sum()),
        "segments_sharing_identical_centroid": int(dup_xy.sum()),
        "length_m_summary": meta["length_m"].describe().to_dict(),
        "tomtom_len_m_summary": meta["tomtom_len_m"].describe().to_dict(),
        "tomtom_len_over_osm_len_summary": meta["tomtom_len_over_osm_len"].describe().to_dict(),
        "segments_tomtom_len_within_20pct_of_osm": int((meta["tomtom_len_over_osm_len"].between(0.8, 1.25)).sum()),
        "segments_tomtom_len_gt_2x_osm": int((meta["tomtom_len_over_osm_len"] > 2).sum()),
        "distinct_tomtom_signatures": int(meta["tomtom_signature"].nunique()),
        "largest_signature_group": int(grp["n_segments"].max()),
        "segments_in_shared_signature_groups": int(grp.loc[grp["n_segments"] > 1, "n_segments"].sum()),
        "shared_group_spatial_spread_m": pd.Series(spreads).describe().to_dict() if spreads else None,
        "pairwise_speed_corr_summary": pd.Series(cvals).describe().to_dict(),
        "pairs_corr_gt_0_99_pct": float((cvals > 0.99).mean() * 100),
        "roadClosure_true_segments": int(meta["roadClosure_any"].sum()),
        "bbox": {"lat_min": meta["lat"].min(), "lat_max": meta["lat"].max(),
                 "lon_min": meta["lon"].min(), "lon_max": meta["lon"].max()},
        "endpoint_fields_present": False,
        "geometry_fields_present": False,
        "direction_field_present": False,
    }
    meta.drop(columns=["osmid_tuple"]).to_csv(INTERIM_DIR / "segment_metadata.csv")
    (METRIC_DIR / "metadata_checks.json").write_text(json.dumps(checks, indent=2, default=str))
    print(json.dumps(checks, indent=1, default=str))
    print(grp.sort_values("n_segments", ascending=False).head(15).to_string())


if __name__ == "__main__":
    main()
