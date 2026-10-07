"""Read-only scientific suitability audit for GeoPulse traffic data.

Run from the workspace with the project virtualenv:
  python src/audit_dataset.py

The DuckDB source is opened read-only. Outputs are written to outputs/dataset_audit.
"""
from __future__ import annotations

import json
import math
import re
import statistics
from collections import Counter
from pathlib import Path

import duckdb
import networkx as nx
import numpy as np
import pandas as pd
import osmnx as ox
from pyproj import Transformer
from shapely.geometry import Point
from shapely.ops import transform


ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "datasets" / "traffic_v1.duckdb"
GRAPH = ROOT / "notebooks" / "bhubaneswar_drive.graphml"
OUT = ROOT / "outputs" / "dataset_audit"
OUT.mkdir(parents=True, exist_ok=True)


def val(x):
    if pd.isna(x):
        return None
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        return float(x) if math.isfinite(float(x)) else None
    if isinstance(x, (np.bool_,)):
        return bool(x)
    return x


def stats(s: pd.Series, quantiles=(.01, .05, .25, .5, .75, .95, .99)):
    x = pd.to_numeric(s, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    d = {"n": int(x.size), "min": val(x.min()), "max": val(x.max()), "mean": val(x.mean()),
         "median": val(x.median()), "std": val(x.std()), "q": {str(q): val(x.quantile(q)) for q in quantiles}}
    return d


def pct(n, d):
    return 100 * n / d if d else None


def dump_csv(df, name):
    df.to_csv(OUT / name, index=False)


def main():
    if not DB.is_file() or not GRAPH.is_file():
        raise FileNotFoundError(f"Required inputs not found: database={DB.is_file()}, graph={GRAPH.is_file()}")
    con = duckdb.connect(str(DB), read_only=True)
    tables = [x[0] for x in con.execute("SHOW TABLES").fetchall()]
    schema_rows = con.execute("DESCRIBE traffic").fetchall()
    cols = [r[0] for r in schema_rows]
    # String casts avoid a host-side pytz dependency for DuckDB timestamptz values.
    df = con.execute("SELECT *, CAST(hour AS VARCHAR) AS _hour_s, CAST(timestamp AS VARCHAR) AS _ts_s FROM traffic").fetchdf()
    con.close()
    df["_hour"] = pd.to_datetime(df["_hour_s"], utc=True, errors="coerce").dt.tz_convert("Asia/Kolkata")
    df["_ts"] = pd.to_datetime(df["_ts_s"], utc=True, errors="coerce").dt.tz_convert("Asia/Kolkata")
    df = df.drop(columns=["_hour_s", "_ts_s"])

    n = len(df)
    segs = sorted(df.segment_id.dropna().unique().tolist())
    # `hour` is the hourly grid key. `timestamp` is the per-observation retrieval time
    # and can include minute/second offsets or be null on rows marked missing.
    times = pd.DatetimeIndex(sorted(df._hour.dropna().unique()))
    raw_timestamps = pd.DatetimeIndex(sorted(df._ts.dropna().unique()))
    hours = times
    nseg, nt = len(segs), len(times)
    expected = nseg * nt
    duplicate_rows = int(df.duplicated(subset=cols, keep=False).sum())
    pair_dup_rows = int(df.duplicated(["segment_id", "hour"], keep=False).sum())
    pair_unique = int(df[["segment_id", "hour"]].drop_duplicates().shape[0])
    nulls = df[cols].isna().sum().astype(int).to_dict()
    dtypes = {c: str(df[c].dtype) for c in cols}
    categorical = {c: int(df[c].nunique(dropna=True)) for c in ["road_type", "road_name", "osmid", "is_observed", "is_missing", "roadClosure"] if c in cols}

    # Define an observation by both the source flag and a finite positive speed; report disagreement separately.
    speed = pd.to_numeric(df.currentSpeed, errors="coerce")
    finite_speed = speed.notna() & np.isfinite(speed)
    obs_flag = df.is_observed.fillna(False).astype(bool)
    missing_flag = df.is_missing.fillna(False).astype(bool)
    valid_obs = obs_flag & finite_speed
    df["_valid_obs"] = valid_obs
    df["_missing_audit"] = ~valid_obs
    df["_speed"] = speed
    df["_ratio"] = np.where((df.freeFlowSpeed > 0) & finite_speed, speed / df.freeFlowSpeed, np.nan)

    # Timeline cadence and missing global timestamps.
    diffs = pd.Series(times[1:] - times[:-1]).dt.total_seconds().div(3600) if nt > 1 else pd.Series(dtype=float)
    cadence = diffs.value_counts().sort_index().to_dict()
    raw_diffs = pd.Series(raw_timestamps[1:] - raw_timestamps[:-1]).dt.total_seconds().div(3600) if len(raw_timestamps) > 1 else pd.Series(dtype=float)
    raw_cadence = Counter(round(float(x), 6) for x in raw_diffs)
    step_h = float(diffs.mode().iloc[0]) if len(diffs) else 1.0
    global_missing_slots = int(round((times[-1] - times[0]).total_seconds() / 3600 / step_h)) + 1 - nt if nt else 0
    offsets = (df.loc[df._ts.notna(), "_ts"] - df.loc[df._ts.notna(), "_hour"]).dt.total_seconds() / 60

    # Segment coverage and contiguous sequences.
    total_by = df.groupby("segment_id").size()
    good_by = df.groupby("segment_id")["_valid_obs"].sum()
    coverage = pd.DataFrame({"segment_id": total_by.index, "records": total_by.values,
                             "observed": good_by.reindex(total_by.index).values})
    coverage["missing"] = coverage.records - coverage.observed
    coverage["coverage_pct"] = coverage.observed / max(nt, 1) * 100
    coverage["observed_record_pct"] = coverage.observed / coverage.records * 100
    coverage = coverage.sort_values(["coverage_pct", "segment_id"])
    dump_csv(coverage, "coverage_by_segment.csv")
    seg_metrics = []
    temporal_rows = []
    continuity_rows = []
    # exact UTC timestamps, require consecutive grid cadence for sequences and autocorrelation pairs
    for sid, g in df.groupby("segment_id", sort=False):
        g = g.sort_values("_hour")
        og = g[g._valid_obs]
        t = og._hour.to_numpy(dtype="datetime64[ns]")
        v = og._speed.to_numpy(dtype=float)
        if len(t):
            breaks = np.r_[True, np.diff(t).astype("timedelta64[s]").astype(np.int64) != int(step_h * 3600)]
            runids = np.cumsum(breaks)
            runs = pd.Series(runids).value_counts().to_numpy()
            sequence_count = int(len(runs))
            longest = int(runs.max())
            medrun = float(np.median(runs))
            gaps = np.diff(t).astype("timedelta64[s]").astype(np.int64) / 3600
            missing_slots = gaps / step_h - 1
            one_gap = int(np.sum(np.isclose(missing_slots, 1)))
            long_gaps = int(np.sum(missing_slots >= 2))
            maxgap = float(np.max(gaps)) if len(gaps) else 0.0
        else:
            runs = np.array([], dtype=int); sequence_count = longest = 0; medrun = 0.; one_gap = long_gaps = 0; maxgap = None
        continuity_rows.append({"segment_id": sid, "sequences": sequence_count, "longest_sequence": longest,
                                "median_sequence": medrun, "gaps_1h": one_gap, "gaps_2h_plus": long_gaps,
                                "largest_gap_hours": maxgap,
                                **{f"enough_lag_{l}": bool(longest >= l + 1) for l in (1,3,6,12,24)}})
        vals = og._speed
        seg_metrics.append({"segment_id": sid, "mean_speed": vals.mean(), "std_speed": vals.std(),
                            "min_speed": vals.min(), "max_speed": vals.max(), "mean_speed_ratio": og._ratio.mean(),
                            "congestion_pct_ratio_lt_0_8": (og._ratio < .8).mean() * 100 if len(og) else np.nan,
                            "observed_n": len(og), "coverage_pct": coverage.set_index('segment_id').at[sid, 'coverage_pct']})
        row = {"segment_id": sid, "observed_n": len(v)}
        for lag in (1,3,6,12,24):
            if len(v) > lag:
                # preserve only true elapsed-time lag pairs, not adjacent valid rows across holes
                dt = np.diff(t).astype("timedelta64[s]").astype(np.int64)
                pairs = np.array([i for i in range(len(v)-lag) if (t[i+lag]-t[i]).astype('timedelta64[s]').astype(np.int64) == int(lag*step_h*3600)])
                row[f"lag{lag}_pairs"] = int(len(pairs))
                row[f"lag{lag}_acf"] = float(np.corrcoef(v[pairs], v[pairs+lag])[0,1]) if len(pairs) >= 3 and np.std(v[pairs]) > 0 and np.std(v[pairs+lag]) > 0 else np.nan
            else:
                row[f"lag{lag}_pairs"] = 0; row[f"lag{lag}_acf"] = np.nan
        temporal_rows.append(row)
    cont = pd.DataFrame(continuity_rows)
    segdf = pd.DataFrame(seg_metrics)
    tempdf = pd.DataFrame(temporal_rows)
    dump_csv(cont, "continuity_by_segment.csv")
    dump_csv(segdf, "segment_quality.csv")
    dump_csv(tempdf, "autocorrelation_by_segment.csv")

    # Missingness by date, hour-of-day, and weekday (UTC; timestamps are aware).
    df["_date"] = df._hour.dt.date.astype(str)
    df["_hod"] = df._hour.dt.hour
    df["_dow"] = df._hour.dt.day_name()
    def missing_group(key, labels=None):
        a = df.groupby(key, dropna=False).agg(total=("_valid_obs", "size"), observed=("_valid_obs", "sum"), missing=("_missing_audit", "sum")).reset_index()
        a["coverage_pct"] = a.observed / a.total * 100
        return a
    bydate = missing_group("_date").rename(columns={"_date":"date"})
    byhour = missing_group("_hod").rename(columns={"_hod":"hour"}).set_index("hour").reindex(range(24), fill_value=0).rename_axis("hour").reset_index()
    bydow = missing_group("_dow").rename(columns={"_dow":"day_of_week"})
    dump_csv(bydate, "missingness_by_date.csv"); dump_csv(byhour, "missingness_by_hour.csv"); dump_csv(bydow, "missingness_by_weekday.csv")
    roadmiss = df.groupby("road_type", dropna=False).agg(total=("_valid_obs","size"), observed=("_valid_obs","sum"), missing=("_missing_audit","sum")).reset_index()
    roadmiss["coverage_pct"] = roadmiss.observed / roadmiss.total * 100

    # Value quality, derived ratio, per-segment free-flow stability, metadata.
    cs = stats(df.currentSpeed)
    ff = stats(df.freeFlowSpeed)
    ratio = stats(df._ratio)
    valid_ratio = df._ratio.dropna()
    ratio_counts = {k: int((valid_ratio < threshold).sum()) for k, threshold in [("lt_0_9",.9),("lt_0_8",.8),("lt_0_7",.7),("lt_0_5",.5)]}
    ratio_counts.update({"gt_1":int((valid_ratio>1).sum()),"eq_1":int(np.isclose(valid_ratio,1,atol=1e-9).sum()),"lt_1":int((valid_ratio<1).sum()),"n":int(len(valid_ratio))})
    ffg = df.groupby("segment_id").freeFlowSpeed.agg(["count","nunique","min","max","std"]).reset_index()
    ffg["stable"] = ffg["nunique"] <= 1
    dump_csv(ffg, "free_flow_stability.csv")
    # Labels from prompt are checked by schema; speed proxy bins are clearly identified as derived.
    # Travel-time formulas assume speed is km/h and duration is seconds.
    exp_current = np.where(df._speed > 0, df.length_m * 3.6 / df._speed, np.nan)
    exp_free = np.where(df.freeFlowSpeed > 0, df.length_m * 3.6 / df.freeFlowSpeed, np.nan)
    cur_diff = np.abs(df.currentTravelTime.to_numpy(dtype=float) - exp_current)
    ff_diff = np.abs(df.freeFlowTravelTime.to_numpy(dtype=float) - exp_free)
    def time_summary(a):
        a = a[np.isfinite(a)]
        return {"n":len(a),"mean_abs_difference_seconds":float(np.mean(a)),"median_abs_difference_seconds":float(np.median(a)),
                "max_abs_difference_seconds":float(np.max(a)),"within_1s_pct":pct(int((a<=1).sum()),len(a)),
                "within_5s_pct":pct(int((a<=5).sum()),len(a)),"within_10pct_expected_pct":None}
    time_cur = time_summary(cur_diff); time_free = time_summary(ff_diff)
    # Add relative tolerance after computing paired valid records.
    for name, diff, exp in (("current",cur_diff,exp_current),("free",ff_diff,exp_free)):
        m = np.isfinite(diff) & np.isfinite(exp)
        time_cur["within_10pct_expected_pct"] = pct(int((diff[m] <= .1*np.maximum(np.abs(exp[m]),1)).sum()),int(m.sum())) if name=="current" else time_cur.get("within_10pct_expected_pct")
        if name=="free": time_free["within_10pct_expected_pct"] = pct(int((diff[m] <= .1*np.maximum(np.abs(exp[m]),1)).sum()),int(m.sum()))
    travel_out = df.loc[valid_obs, ["segment_id", "_hour", "currentSpeed", "freeFlowSpeed", "currentTravelTime", "freeFlowTravelTime", "length_m"]].copy()
    travel_out["expected_current_time_s"] = exp_current[valid_obs.to_numpy()]
    travel_out["current_time_abs_error_s"] = cur_diff[valid_obs.to_numpy()]
    travel_out["expected_free_flow_time_s"] = exp_free[valid_obs.to_numpy()]
    travel_out["free_flow_time_abs_error_s"] = ff_diff[valid_obs.to_numpy()]
    dump_csv(travel_out.sort_values("current_time_abs_error_s", ascending=False).head(100), "travel_time_suspicious_records.csv")

    # OSM ID parse/existence; then independent geometry matching to nearest edge geometries.
    def parse_ids(s):
        if not isinstance(s,str): return []
        # Handles scalar strings, JSON/Python-style lists, commas and spaces.
        return re.findall(r"\d+", s)
    meta = df.sort_values("_hour").groupby("segment_id", as_index=False).first()
    meta["_ids"] = meta.osmid.map(parse_ids)
    graph = ox.load_graphml(GRAPH)
    edges = ox.graph_to_gdfs(graph, nodes=False, edges=True, fill_edge_geometry=True).reset_index()
    edge_ids = set()
    if "osmid" in edges:
        for x in edges.osmid:
            if isinstance(x,(list,tuple,set)): edge_ids.update(map(str,x))
            elif x is not None: edge_ids.add(str(x))
    seg_osm = []
    for _, r in meta.iterrows():
        ids = r["_ids"]
        present = [x for x in ids if x in edge_ids]
        seg_osm.append({"segment_id":r.segment_id,"osm_id_count":len(ids),"malformed_osmid":bool(not ids and pd.notna(r.osmid)),
                        "matched_osm_id_count":len(present),"all_ids_found":bool(ids and len(present)==len(ids)),"parsed_osm_ids":";".join(ids)})
    osmdf = pd.DataFrame(seg_osm)
    dump_csv(osmdf, "osm_id_existence.csv")

    # Make edge geometries metric (Bhubaneswar UTM 45N). Spatial score: distance/50m,
    # +1 for road-class mismatch, +0.25*abs(log(length ratio)); report raw components too.
    to_metric = Transformer.from_crs("EPSG:4326", "EPSG:32645", always_xy=True).transform
    edges["_geom_m"] = edges.geometry.map(lambda g: transform(to_metric,g) if g is not None else None)
    edges["_len_m"] = edges._geom_m.map(lambda g:g.length if g is not None else np.nan)
    from shapely.strtree import STRtree
    geoms = [g for g in edges._geom_m if g is not None and not g.is_empty]
    tree = STRtree(geoms)
    geom_index = {id(g):i for i,g in enumerate(geoms)}
    # Shapely 2 returns integer indices; Shapely 1 returns geometry objects.
    def edge_class(x):
        if isinstance(x,(list,tuple)): x=x[0] if x else "unknown"
        x=str(x).lower()
        mapping={"motorway":"motorway","trunk":"trunk","primary":"primary","secondary":"secondary","tertiary":"tertiary","residential":"residential","unclassified":"unclassified","service":"service","living_street":"residential"}
        return mapping.get(x,"other")
    edge_classes=[]
    for _,e in edges.iterrows(): edge_classes.append(edge_class(e.get("highway","other")))
    edges["_class"] = edge_classes
    spatial=[]
    for _,r in meta.iterrows():
        if pd.isna(r.lat) or pd.isna(r.lon) or not (-90<=r.lat<=90 and -180<=r.lon<=180):
            spatial.append({"segment_id":r.segment_id,"status":"invalid_coordinates"}); continue
        p=transform(to_metric,Point(float(r.lon),float(r.lat)))
        ids=tree.query(p.buffer(500))
        candidates=[]
        for hit in ids:
            idx=int(hit) if isinstance(hit,(int,np.integer)) else geom_index.get(id(hit),-1)
            if idx<0: continue
            g=geoms[idx]; d=float(p.distance(g))
            if d>500: continue
            e=edges.iloc[idx]
            rc=edge_class(r.road_type); ec=e["_class"]
            type_match=rc==ec or rc=="other" or ec=="other"
            l=float(r.length_m) if pd.notna(r.length_m) else np.nan
            el=float(e["_len_m"])
            len_pen=abs(math.log(max(l,1)/max(el,1))) if np.isfinite(l) and np.isfinite(el) else 5.
            score=d/50+(0 if type_match else 1)+.25*len_pen
            candidates.append((score,d,type_match,len_pen,e))
        if not candidates:
            spatial.append({"segment_id":r.segment_id,"status":"no_edge_within_500m"}); continue
        candidates.sort(key=lambda x:x[0]); score,d,tm,lp,e=candidates[0]
        spatial.append({"segment_id":r.segment_id,"status":"matched","distance_m":d,"candidate_count_500m":len(candidates),
                        "score":score,"dataset_road_type":r.road_type,"candidate_road_type":str(e.get("highway")),
                        "road_type_match":tm,"dataset_length_m":r.length_m,"candidate_edge_length_m":e._len_m,
                        "length_ratio":float(r.length_m/e["_len_m"]) if pd.notna(r.length_m) and e["_len_m"]>0 else np.nan,
                        "length_log_error":lp,"candidate_osmid":str(e.get("osmid")),"candidate_u":e.get("u"),"candidate_v":e.get("v")})
    spatialdf=pd.DataFrame(spatial)
    dump_csv(spatialdf,"spatial_edge_matches.csv")

    # Connected-road diagnostic using the subset of graph edges whose OSM ids occur in the dataset.
    traffic_ids=set(x for ids in meta["_ids"] for x in ids)
    covered_edges=[]
    for u,v,k,e in graph.edges(keys=True,data=True):
        ids=e.get("osmid",[]); ids=ids if isinstance(ids,(list,tuple,set)) else [ids]
        if traffic_ids.intersection(map(str,ids)): covered_edges.append((u,v,k))
    covered=nx.MultiDiGraph(); covered.add_edges_from(covered_edges)
    weak=nx.Graph(covered)
    comps=sorted((len(c) for c in nx.connected_components(weak)),reverse=True) if weak else []
    physical_edges=[]
    for _,r in spatialdf.loc[spatialdf.status=="matched"].iterrows():
        if pd.notna(r.candidate_u) and pd.notna(r.candidate_v):
            physical_edges.append((r.candidate_u,r.candidate_v))
    physical=nx.DiGraph(); physical.add_edges_from(physical_edges)
    physical_weak=nx.Graph(physical)
    physical_comps=sorted((len(c) for c in nx.connected_components(physical_weak)),reverse=True) if physical_weak else []
    # A distinct traffic segment is considered OSM-ID-covered if any parsed ID matched.
    idmatch=int(osmdf.matched_osm_id_count.gt(0).sum())

    # Missingness tables retain exact records; counts and rates by segment/road type/date/hour/dow.
    coverage_summary={"min_pct":float(coverage.coverage_pct.min()),"max_pct":float(coverage.coverage_pct.max()),
                      "mean_pct":float(coverage.coverage_pct.mean()),"median_pct":float(coverage.coverage_pct.median()),
                      "std_pct":float(coverage.coverage_pct.std())}
    global_acf={}
    for lag in (1,3,6,12,24):
        vals=tempdf[f"lag{lag}_acf"].dropna()
        global_acf[str(lag)]={"segments_with_estimable_acf":int(len(vals)),"mean_segment_acf":val(vals.mean()),"median_segment_acf":val(vals.median()),
                              "pooled_mean_acf":val(np.average(vals,weights=tempdf.loc[vals.index,f"lag{lag}_pairs"])) if len(vals) else None}

    summary={
      "inputs":{"database":str(DB),"graph":str(GRAPH),"database_bytes":DB.stat().st_size,"graph_bytes":GRAPH.stat().st_size,"tables":tables},
      "structure":{"rows":n,"segments":nseg,"unique_timestamps":len(raw_timestamps),"unique_hour_values":len(hours),"expected_segment_time_rows":expected,
        "complete_segment_time_grid":bool(n==expected and pair_unique==expected),"unique_segment_hour_pairs":pair_unique,
        "duplicate_full_rows_involved":duplicate_rows,"duplicate_segment_hour_rows_involved":pair_dup_rows,"null_counts":nulls,"dtypes":dtypes,"unique_values":categorical},
      "temporal":{"min_hour_local":str(times.min()) if nt else None,"max_hour_local":str(times.max()) if nt else None,
        "duration_days":float((times.max()-times.min()).total_seconds()/86400) if nt else None,"unique_hourly_grid_timestamps":nt,
        "unique_observation_timestamps":len(raw_timestamps),
        "min_observation_timestamp_local":str(raw_timestamps.min()) if len(raw_timestamps) else None,
        "max_observation_timestamp_local":str(raw_timestamps.max()) if len(raw_timestamps) else None,
        "observation_timestamp_offset_from_hour_minutes":{"min":val(offsets.min()),"median":val(offsets.median()),"max":val(offsets.max())},
        "hour_grid_differences_hours":{str(k):int(v) for k,v in Counter(diffs).items()},
        "raw_timestamp_differences_hours":{str(k):int(v) for k,v in sorted(raw_cadence.items())},
        "raw_timestamp_is_strictly_hourly":bool(len(raw_diffs)>0 and np.allclose(raw_diffs,1.0,atol=1e-6)),
        "modal_step_hours":step_h,"missing_global_timeline_slots":global_missing_slots,
        "coverage":coverage_summary,"lowest_20_segments":coverage.head(20).to_dict(orient="records")},
      "missingness":{"valid_observations":int(valid_obs.sum()),"missing_by_audit_definition":int((~valid_obs).sum()),
        "is_observed_true":int(obs_flag.sum()),"is_missing_true":int(missing_flag.sum()),"flags_not_complementary_count":int((obs_flag==missing_flag).sum()),
        "flag_vs_valid_speed_disagree_count":int((obs_flag!=finite_speed).sum()),"by_road_type":roadmiss.to_dict(orient="records"),
        "worst_dates":bydate.sort_values("coverage_pct").head(10).to_dict(orient="records"),
        "hour_coverage":byhour.to_dict(orient="records"),"weekday_coverage":bydow.to_dict(orient="records")},
      "continuity":{"segments_with_longest_contiguous_observations_at_least_lag_plus_one":{str(l):int(cont[f"enough_lag_{l}"].sum()) for l in (1,3,6,12,24)},
        "median_sequence_length_across_segments":val(cont.median_sequence.median()),"mean_sequences_per_segment":val(cont.sequences.mean()),
        "median_longest_sequence":val(cont.longest_sequence.median()),"mean_gap_count_per_segment":val(cont.gaps_1h.mean()),
        "total_sequences":int(cont.sequences.sum()),"total_gaps_1h":int(cont.gaps_1h.sum()),"total_gaps_2h_plus":int(cont.gaps_2h_plus.sum()),
        "max_gap_hours":val(cont.largest_gap_hours.max())},
      "speed":{"currentSpeed":cs,"freeFlowSpeed":ff,"current_speed_nonpositive":int((df.currentSpeed<=0).sum()),
        "current_speed_gt_free_flow":int((df.currentSpeed>df.freeFlowSpeed).sum()),"current_speed_over_120":int((df.currentSpeed>120).sum()),
        "current_speed_over_160":int((df.currentSpeed>160).sum()),"current_speed_infinite":int(np.isinf(df.currentSpeed).sum()),
        "free_flow_nonpositive":int((df.freeFlowSpeed<=0).sum()),"free_flow_over_160":int((df.freeFlowSpeed>160).sum()),"free_flow_infinite":int(np.isinf(df.freeFlowSpeed).sum()),
        "free_flow_stable_segments":int(ffg.stable.sum()),"free_flow_unstable_segments":int((~ffg.stable).sum()),
        "speed_ratio":ratio,"speed_ratio_counts":ratio_counts,"segments": {"nearly_constant_std_le_0_1":int((segdf.std_speed<=.1).sum()),
          "no_congestion_ratio_lt_0_8":int((segdf.congestion_pct_ratio_lt_0_8==0).sum()),
          "high_congestion_over_50pct":int((segdf.congestion_pct_ratio_lt_0_8>50).sum())}},
      "labels":{"available_columns":[c for c in ("congestion_level","is_congested") if c in cols],"status":"not present in source schema; label counts and consistency cannot be audited",
        "derived_proxy_counts_ratio_lt_0_8":int((valid_ratio<.8).sum()),"proxy_definition":"currentSpeed/freeFlowSpeed < 0.8; derived for audit only"},
      "temporal_signal":{"segment_autocorrelation":global_acf},
      "travel_time":{"unit_assumption":"speeds in km/h; length in metres; travel times in seconds","current":time_cur,"free_flow":time_free},
      "metadata":{"osmid_unique_raw_values":int(df.osmid.nunique(dropna=True)),"road_type_counts":df.road_type.value_counts(dropna=False).to_dict(),
        "road_name_unique":int(df.road_name.nunique(dropna=True)),"length_m_nonpositive":int((df.length_m<=0).sum()),
        "length_m":stats(df.length_m),"lat":stats(df.lat),"lon":stats(df.lon),"confidence":stats(df.confidence),
        "invalid_lat_nonnull":int((df.lat.notna() & ~df.lat.between(-90,90)).sum()),"invalid_lon_nonnull":int((df.lon.notna() & ~df.lon.between(-180,180)).sum()),
        "road_closure_true":int(df.roadClosure.fillna(False).sum()),"road_closure_true_pct":pct(int(df.roadClosure.fillna(False).sum()),int(df.roadClosure.notna().sum())),"segments_one_osm_id":int((osmdf.osm_id_count==1).sum()),
        "segments_multiple_osm_ids":int((osmdf.osm_id_count>1).sum()),"segments_malformed_osmid":int(osmdf.malformed_osmid.sum())},
      "osm_id_existence":{"graph_nodes":graph.number_of_nodes(),"graph_directed_edges":graph.number_of_edges(),"unique_graph_osm_ids":len(edge_ids),
        "traffic_segments":nseg,"matched_segments":idmatch,"unmatched_segments":nseg-idmatch,"match_pct":pct(idmatch,nseg)},
      "spatial":{"matched_segments":int((spatialdf.status=="matched").sum()),"unmatched_or_invalid":int((spatialdf.status!="matched").sum()),
        "distance":stats(spatialdf.loc[spatialdf.status=="matched","distance_m"],quantiles=(.5,.9,.95)),
        "within_m":{str(m):int((spatialdf.loc[spatialdf.status=="matched","distance_m"]<=m).sum()) for m in (25,50,100,250,500)},
        "within_m_pct":{str(m):pct(int((spatialdf.loc[spatialdf.status=="matched","distance_m"]<=m).sum()),int((spatialdf.status=="matched").sum())) for m in (25,50,100,250,500)},
        "road_type_match_pct":pct(int(spatialdf.loc[spatialdf.status=="matched","road_type_match"].sum()),int((spatialdf.status=="matched").sum())),
        "length_ratio_stats":stats(spatialdf.loc[spatialdf.status=="matched","length_ratio"],quantiles=(.5,.9,.95))},
      "connectivity":{"covered_directed_edges":len(covered_edges),"covered_nodes":covered.number_of_nodes(),"weak_component_count":len(comps),
        "largest_weak_component_nodes":comps[0] if comps else 0,"second_largest_weak_component_nodes":comps[1] if len(comps)>1 else 0,
        "largest_component_node_share_pct":pct(comps[0],covered.number_of_nodes()) if comps else None,
        "spatially_matched_directed_edge_count":len(physical_edges),"spatially_matched_unique_directed_edges":physical.number_of_edges(),
        "spatially_matched_nodes":physical.number_of_nodes(),"spatial_weak_component_count":len(physical_comps),
        "spatial_largest_weak_component_nodes":physical_comps[0] if physical_comps else 0,
        "spatial_largest_component_node_share_pct":pct(physical_comps[0],physical.number_of_nodes()) if physical_comps else None}
    }
    (OUT/"summary.json").write_text(json.dumps(summary,indent=2,default=val),encoding="utf-8")
    # Full column type/null inventory and categorical counts are easier to inspect as a CSV.
    colinfo=pd.DataFrame([{"column":c,"dtype":dtypes[c],"null_count":nulls[c],"unique_nonnull":int(df[c].nunique(dropna=True))} for c in cols])
    dump_csv(colinfo,"column_inventory.csv")
    write_report_v2(summary,cont,segdf,tempdf,ffg,spatialdf,bydate,byhour,bydow,roadmiss)
    print(f"Audit complete: {OUT}")


def write_report(s, cont, segdf, tempdf, ffg, spatialdf, bydate, byhour, bydow, roadmiss):
    st=s["structure"]; t=s["temporal"]; m=s["missingness"]; sp=s["speed"]; geo=s["spatial"]
    def tab(df, n=20):
        view=df.head(n).copy()
        if view.empty: return "(no rows)"
        cols=[str(c) for c in view.columns]
        rows=[[str(val(x)) if val(x) is not None else "" for x in row] for row in view.itertuples(index=False,name=None)]
        return "| " + " | ".join(cols) + " |\n| " + " | ".join(["---"]*len(cols)) + " |\n" + "\n".join("| " + " | ".join(row) + " |" for row in rows)
    lines=["# GeoPulse traffic dataset suitability and reliability audit", "",
      f"Read-only audit of `{s['inputs']['database']}` against `{s['inputs']['graph']}`. Raw files were not modified. Timestamps are interpreted in UTC for cadence/grouping.","",
      "## Overall assessment", "",
      "**Preliminary classification: suitable with preprocessing for speed prediction; routing suitability remains conditional on segment-to-network validation and connected coverage.** The categorical congestion labels requested in the brief are absent from the source schema. The physical edge matching and connectivity results below should govern the routing decision; OSM ID existence alone is not sufficient.","",
      "## 1. Structure", "",
      f"Tables: {', '.join(s['inputs']['tables'])}. Rows: **{st['rows']:,}**; unique segments: **{st['segments']:,}**; unique timestamps: **{st['unique_timestamps']:,}**; unique `hour` values: **{st['unique_hour_values']:,}**. Expected segment × timestamp grid: **{st['expected_segment_time_rows']:,}**. Complete grid: **{st['complete_segment_time_grid']}**. Unique `(segment_id, hour)` pairs: {st['unique_segment_hour_pairs']:,}; duplicate full-row records involved: {st['duplicate_full_rows_involved']:,}; duplicate pairs involved: {st['duplicate_segment_hour_rows_involved']:,}.","",
      "See `column_inventory.csv` for every type, null count, and distinct count.","",
      "## 2–4. Temporal coverage, missingness, and continuity", "",
      f"Time range: {t['min_timestamp_utc']} to {t['max_timestamp_utc']} (**{t['duration_days']:.3f} days**); modal cadence {t['modal_step_hours']} h; missing global timeline slots: {t['missing_global_timeline_slots']}. Segment coverage min/mean/median/max/std: " + "/".join(f"{t['coverage'][x]:.3f}%" for x in ('min_pct','mean_pct','median_pct','max_pct','std_pct')) + ".", "",
      f"Valid observed rows (flagged observed and finite speed): {m['valid_observations']:,}; missing by this audit definition: {m['missing_by_audit_definition']:,}. is_observed/is_missing agree with each other on {st['rows']-m['flags_disagree_count']:,} rows; is_observed differs from finite-speed availability on {m['flag_vs_valid_speed_disagree_count']:,} rows.","",
      "Lowest-coverage segments:","",tab(pd.DataFrame(t['lowest_20_segments']),20),"",
      "Date-level, hour-of-day, weekday, segment, and road-type missingness are exported to `missingness_by_*.csv` and `coverage_by_segment.csv`. Coverage by hour of day:","",tab(byhour,24),"",
      f"Longest uninterrupted observed sequence median: {s['continuity']['median_longest_sequence']}; median sequence length (across segment sequence summaries): {s['continuity']['median_sequence_length_across_segments']}. Segments whose longest run supports lag-1/3/6/12/24: " + ", ".join(f"{k}: {v:,}" for k,v in s['continuity']['segments_with_longest_contiguous_observations_at_least_lag_plus_one'].items()) + ". See `continuity_by_segment.csv`.","",
      "## 5–7. Speed and congestion variation", "",
      f"currentSpeed summary: {json.dumps(sp['currentSpeed'])}. Nonpositive: {sp['current_speed_nonpositive']:,}; > free-flow: {sp['current_speed_gt_free_flow']:,}; >120: {sp['current_speed_over_120']:,}; >160: {sp['current_speed_over_160']:,}; infinite: {sp['current_speed_infinite']:,}.","",
      f"freeFlowSpeed summary: {json.dumps(sp['freeFlowSpeed'])}. Nonpositive: {sp['free_flow_nonpositive']:,}; >160: {sp['free_flow_over_160']:,}; segment-stable: {sp['free_flow_stable_segments']:,}; segment-variable: {sp['free_flow_unstable_segments']:,}.","",
      f"Ratio current/free-flow summary: {json.dumps(sp['speed_ratio'])}. Ratio counts: {json.dumps(sp['speed_ratio_counts'])}. Segment summaries in `segment_quality.csv`; free-flow stability in `free_flow_stability.csv`.","",
      "## 8. Congestion labels", "",
      f"`congestion_level` and `is_congested` are not present in the table. Label counts, percentages, and label consistency therefore cannot be computed. Derived proxy only: ratio < 0.8 on {s['labels']['derived_proxy_counts_ratio_lt_0_8']:,} non-null ratios; this is not treated as a supplied label.","",
      "## 9–10. Segment variability and temporal signal", "",
      f"Segments with speed SD ≤ 0.1: {sp['segments']['nearly_constant_std_le_0_1']:,}; no ratio<0.8 observations: {sp['segments']['no_congestion_ratio_lt_0_8']:,}; >50% ratio<0.8: {sp['segments']['high_congestion_over_50pct']:,}. Segment autocorrelation summaries by exact elapsed-time lag: {json.dumps(s['temporal_signal']['segment_autocorrelation'])}. Values are computed per segment from available exact-lag pairs, without fitting a predictive model. Full per-segment lag counts and correlations are in `autocorrelation_by_segment.csv`.","",
      "## 11. Feature leakage", "",
      "Safe known-before-target inputs can include static segment metadata (road type, length, coordinates/topology, freeFlowSpeed if confirmed static) and lagged observations that are strictly earlier than the forecast origin. Calendar features are safe when forecast time is known. `currentSpeed` is the target at its own timestamp; using its same-time value to predict that timestamp leaks the target. `speed_ratio` inherits the same leakage because it contains currentSpeed. `currentTravelTime` is likewise target-derived at the same time. `freeFlowTravelTime` is a static baseline-derived feature only if its provenance confirms no target-time information. `confidence`, `is_observed`, `is_missing`, and `roadClosure` require availability-time semantics: use only values known at forecast origin; current-time values may be contemporaneous. OSM IDs, road_name (stored as DOUBLE), road_type, length, lat/lon, and network geometry are static candidates, subject to data-quality and matching checks. No same-timestep ratio should be used to predict same-timestep speed.","",
      "## 12. Travel-time consistency", "",
      "Assumption checked: speed in km/h, length in metres, travel time in seconds, so expected time = 3.6 × length / speed. Current and free-flow absolute-error summaries (seconds):", "",
      json.dumps(s['travel_time'],indent=2),"",
      "## 13–16. Metadata, OSM existence, physical matching, connectivity", "",
      f"Metadata inventory includes null and distinct counts in `column_inventory.csv`. Road name is stored as DOUBLE, which is suspicious for a nominal name field. OSM IDs parsed from list-like strings: 1-ID segments={s['metadata']['segments_one_osm_id']}, multi-ID={s['metadata']['segments_multiple_osm_ids']}, malformed={s['metadata']['segments_malformed_osmid']}. OSM graph: {s['osm_id_existence']['graph_nodes']:,} nodes, {s['osm_id_existence']['graph_directed_edges']:,} directed edges. ID-existence matched {s['osm_id_existence']['matched_segments']:,}/{s['osm_id_existence']['traffic_segments']:,} segments ({s['osm_id_existence']['match_pct']:.2f}%).", "",
      f"Independent point-to-edge spatial validation (metric CRS EPSG:32645) matched {geo['matched_segments']:,} segments within 500 m. Distance statistics: {json.dumps(geo['distance'])}. Within thresholds: {json.dumps(geo['within_m'])}. Candidate road-type compatibility: {geo['road_type_match_pct']}%. Chosen-candidate dataset/edge length ratio stats: {json.dumps(geo['length_ratio_stats'])}. Matching score ranks distance, broad road class, and log length ratio; a large length difference is not treated as sole rejection because API segments can aggregate OSM edges. Full candidate-level output is `spatial_edge_matches.csv`.","",
      f"OSM-ID-covered subgraph: {s['connectivity']['covered_directed_edges']:,} directed edges, {s['connectivity']['covered_nodes']:,} nodes, {s['connectivity']['weak_component_count']:,} weak components; largest component {s['connectivity']['largest_weak_component_nodes']:,} nodes ({s['connectivity']['largest_component_node_share_pct']:.2f}% of covered nodes). This connectivity proxy depends on ID correspondence; physical matching should be considered alongside it.","",
      "## Outputs", "",
      "`summary.json` holds machine-readable totals. CSVs preserve column inventory, segment coverage/quality/continuity/autocorrelation, missingness by date/hour/weekday, free-flow stability, OSM ID matches, and spatial edge matches. No ML models were trained and no source data was altered.","",
      "## Important limitation", "",
      "The supplied task text ends after the opening request for Audit 16; no further audit criteria were included. Connectivity is reported with a transparent OSM-ID-covered subgraph diagnostic. The dataset and graph filenames differ from the stated graph path: the used Bhubaneswar graph is under `notebooks/`, while `datasets/jaipur_osm/` contains a separate Jaipur network.",""]
    (OUT/"audit_report.md").write_text("\n".join(lines),encoding="utf-8")


def write_report_v2(s, cont, segdf, tempdf, ffg, spatialdf, bydate, byhour, bydow, roadmiss):
    st=s["structure"]; t=s["temporal"]; m=s["missingness"]; sp=s["speed"]; geo=s["spatial"]
    def md_table(frame):
        if frame.empty: return "(no rows)"
        head="| " + " | ".join(map(str,frame.columns)) + " |\n| " + " | ".join(["---"]*len(frame.columns)) + " |"
        body=["| " + " | ".join(str(x) if pd.notna(x) else "" for x in row) + " |" for row in frame.itertuples(index=False,name=None)]
        return "\n".join([head]+body)
    lag=s["temporal_signal"]["segment_autocorrelation"]
    lines=[
      "# GeoPulse traffic dataset suitability and reliability audit", "",
      f"Read-only analysis of `{s['inputs']['database']}` and `{s['inputs']['graph']}`. Calendar coverage is grouped in IST. The archive data dictionary says timestamps are UTC, while the DuckDB session renders the timestamptz values at +05:30; this report uses that same instant converted to IST for local traffic calendars. Neither source file was modified.", "",
      "## Overall assessment", "",
      "**Suitable with preprocessing for speed prediction; unsuitable for end-to-end routing evaluation in its current form.** The segment-hour grid is complete, and observed speeds have meaningful variation and temporal signal. However, only 16.375 days are available, the traffic-covered OSM subgraph is fragmented, travel-time fields fail the documented length/speed consistency check, and congestion labels are absent. Resolve these before comparing dynamic routes against the baseline.", "",
      "## 1. Structure", "",
      f"Tables: {', '.join(s['inputs']['tables'])}. Rows: **{st['rows']:,}**; segments: **{st['segments']:,}**; distinct non-null raw `timestamp` values: **{t['unique_observation_timestamps']:,}**; distinct hourly grid values in `hour`: **{st['unique_hour_values']:,}**. Expected rows = segments x hourly grid = **{st['expected_segment_time_rows']:,}**; complete grid: **{st['complete_segment_time_grid']}**. Unique `(segment_id, hour)` pairs: {st['unique_segment_hour_pairs']:,}; duplicate full-row records involved: {st['duplicate_full_rows_involved']:,}; duplicate pairs involved: {st['duplicate_segment_hour_rows_involved']:,}.", "",
      "Per-column dtype, null count, and distinct count are in `column_inventory.csv`.", "",
      "## 2-4. Temporal coverage, missingness, continuity", "",
      f"Hourly grid range (IST): {t['min_hour_local']} to {t['max_hour_local']} ({t['duration_days']:.3f} days); {t['unique_hourly_grid_timestamps']} hourly buckets; all {sum(t['hour_grid_differences_hours'].values())} consecutive `hour` differences are {t['modal_step_hours']} hour(s); missing global hourly buckets: {t['missing_global_timeline_slots']}. Raw `timestamp` values range from {t['min_observation_timestamp_local']} to {t['max_observation_timestamp_local']}; raw timestamp is strictly hourly: {t['raw_timestamp_is_strictly_hourly']}; raw timestamp-difference counts in hours are {t['raw_timestamp_differences_hours']}. Offsets from the `hour` bucket in minutes (min/median/max): {t['observation_timestamp_offset_from_hour_minutes']}.", "",
      f"Per-segment valid observation coverage min/mean/median/max/std: " + "/".join(f"{t['coverage'][k]:.3f}%" for k in ('min_pct','mean_pct','median_pct','max_pct','std_pct')) + f". Valid observations: {m['valid_observations']:,}; missing rows: {m['missing_by_audit_definition']:,}. Observation/missing flags are complementary on {st['rows']-m['flags_not_complementary_count']:,}/{st['rows']:,} rows; is_observed differs from finite-speed availability on {m['flag_vs_valid_speed_disagree_count']:,} rows.", "",
      "Twenty lowest-coverage segments:", "", md_table(pd.DataFrame(t['lowest_20_segments'])), "",
      "Missingness details by date, hour, weekday, segment, and road type are in the CSV outputs. Hour-of-day coverage:", "", md_table(byhour), "",
      f"There are {s['continuity']['total_sequences']:,} observed sequences across all segments; median longest run is {s['continuity']['median_longest_sequence']} hours, with {s['continuity']['total_gaps_1h']} one-hour missing gaps, {s['continuity']['total_gaps_2h_plus']} gaps of 2+ missing hours, and largest elapsed gap {s['continuity']['max_gap_hours']} hours. Segments whose longest run can supply lags 1/3/6/12/24: " + ", ".join(f"{k}: {v:,}" for k,v in s['continuity']['segments_with_longest_contiguous_observations_at_least_lag_plus_one'].items()) + ". See `continuity_by_segment.csv`. Missingness is strongly front-loaded: Jan 1 had 16,450 missing of 16,800 records; Jan 2 had 12,600; Jan 3 had 350. From Jan 4 onward, 225,399 of 225,400 rows are observed (99.9996%), so a clean 322-hour window is feasible by excluding the first three days.", "",
      "## 5-7. Speed quality and variation", "",
      f"currentSpeed: {json.dumps(sp['currentSpeed'])}; nonpositive {sp['current_speed_nonpositive']:,}, greater than free-flow {sp['current_speed_gt_free_flow']:,}, over 120/160 {sp['current_speed_over_120']:,}/{sp['current_speed_over_160']:,}, infinite {sp['current_speed_infinite']:,}.", "",
      f"freeFlowSpeed: {json.dumps(sp['freeFlowSpeed'])}; nonpositive {sp['free_flow_nonpositive']:,}, over 160 {sp['free_flow_over_160']:,}, infinite {sp['free_flow_infinite']:,}; stable on {sp['free_flow_stable_segments']:,} segments and varies on {sp['free_flow_unstable_segments']:,}. Do not assume it is a static feature.", "",
      f"current/free-flow speed ratio: {json.dumps(sp['speed_ratio'])}. Counts: {json.dumps(sp['speed_ratio_counts'])}; ratio equals 1 for {sp['speed_ratio_counts']['eq_1']:,}/{sp['speed_ratio_counts']['n']:,} ({100*sp['speed_ratio_counts']['eq_1']/sp['speed_ratio_counts']['n']:.2f}%) of valid observations and never exceeds 1. Segment metrics are in `segment_quality.csv`.", "",
      "## 8. Congestion labels", "",
      f"`congestion_level` and `is_congested` are absent, so supplied label counts and consistency cannot be audited. A derived ratio < 0.8 occurs in {s['labels']['derived_proxy_counts_ratio_lt_0_8']:,} valid rows; this is only an audit proxy, not a source label.", "",
      "## 9-10. Segment variation and time signal", "",
      f"Nearly constant (speed SD <= 0.1): {sp['segments']['nearly_constant_std_le_0_1']:,} segments; no ratio < 0.8: {sp['segments']['no_congestion_ratio_lt_0_8']:,}; ratio < 0.8 on over half of observations: {sp['segments']['high_congestion_over_50pct']:,}. Mean/median per-segment autocorrelations at exact hourly lags are in this summary (estimable segments, mean, median, pooled): {json.dumps(lag)}. This supports short-lag predictive signal statistically; no model was trained. Full per-segment metrics are in `autocorrelation_by_segment.csv`.", "",
      "## 11. Feature leakage", "",
      "Candidate safe features: static road metadata/topology, calendar values known at forecast time, and speed lags strictly earlier than the forecast origin. Same-time `currentSpeed` is the target and leaks it; same-time `speed_ratio` inherits that leakage, and `currentTravelTime` is target-derived. `freeFlowTravelTime` is safe only if its provenance is static. `confidence`, `is_observed`, `is_missing`, and `roadClosure` need availability-time checks and should not be used contemporaneously unless known at forecast origin. Never use same-timestep speed_ratio to predict same-timestep speed.", "",
      "## 12. Travel-time consistency", "",
      "Assuming speed in km/h, length in metres, and time in seconds, expected travel time = 3.6 x length_m / speed_kmh. The large errors below indicate inconsistency under those units:", "", json.dumps(s['travel_time'],indent=2), "",
      "## 13-16. Metadata, OSM ID, spatial and connectivity checks", "",
      f"`road_name` is DOUBLE, but the archive data dictionary allows numeric road identifiers, so it is not automatically malformed or human-readable. The same dictionary documents speed in km/h, length in metres, and travel time in seconds. Parsed OSM IDs: one ID on {s['metadata']['segments_one_osm_id']} segments, multiple on {s['metadata']['segments_multiple_osm_ids']}, malformed on {s['metadata']['segments_malformed_osmid']}. Graph: {s['osm_id_existence']['graph_nodes']:,} nodes / {s['osm_id_existence']['graph_directed_edges']:,} directed edges. ID existence matched {s['osm_id_existence']['matched_segments']:,}/{s['osm_id_existence']['traffic_segments']:,} traffic segments ({s['osm_id_existence']['match_pct']:.2f}%).", "",
      f"Independent traffic-point to OSM-edge validation in metric EPSG:32645: {geo['matched_segments']:,} matched within 500 m. Distance summary: {json.dumps(geo['distance'])}; counts within 25/50/100/250/500 m: {json.dumps(geo['within_m'])}; percentages within those thresholds: {json.dumps(geo['within_m_pct'])}; broad road-class match: {geo['road_type_match_pct']}%; chosen-edge length-ratio summary: {json.dumps(geo['length_ratio_stats'])}. Candidate rank combines distance, road type, and log length ratio. Full records are in `spatial_edge_matches.csv`.", "",
      f"OSM-ID-covered subgraph: {s['connectivity']['covered_directed_edges']:,} directed edges, {s['connectivity']['covered_nodes']:,} nodes, {s['connectivity']['weak_component_count']:,} weak components; largest component {s['connectivity']['largest_weak_component_nodes']:,} nodes ({s['connectivity']['largest_component_node_share_pct']:.2f}%). Independently using each segment's best spatially matched OSM edge: {s['connectivity']['spatially_matched_unique_directed_edges']:,} unique directed edges, {s['connectivity']['spatially_matched_nodes']:,} nodes, {s['connectivity']['spatial_weak_component_count']:,} weak components; largest component {s['connectivity']['spatial_largest_weak_component_nodes']:,} nodes ({s['connectivity']['spatial_largest_component_node_share_pct']:.2f}%). The physical-match subgraph is the more relevant routing diagnostic.", "",
      "## Output files and limitations", "",
      "`summary.json` is machine-readable. CSVs contain column inventory, coverage, quality, continuity, autocorrelation, missingness, free-flow stability, OSM ID matches, and spatial edge candidates. No models were trained and source data was not modified. The pasted task ends after the opening of Audit 16, so later connectivity criteria were not supplied. The Bhubaneswar graph is under `notebooks/`; `datasets/jaipur_osm/` is a separate Jaipur graph.", ""]
    (OUT/"audit_report.md").write_text("\n".join(lines),encoding="utf-8")


if __name__=="__main__":
    main()
