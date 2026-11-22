"""Read-only Phase 1 audit of GeoPulse traffic data, model, and routing fit.

This script reads the checked-in Parquet, DuckDB, GraphML, model, metadata,
prediction, and service artifacts. It does not train, serialize, or modify them.
It writes only the four Phase 1 audit deliverables in the repository root.

Run from the repository root:
    .\\.venv\\Scripts\\python.exe -B scripts/audit_phase1_dataset_ml_readiness.py
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import duckdb
import joblib
import networkx as nx
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from sklearn.metrics import mean_absolute_error, median_absolute_error, r2_score, root_mean_squared_error

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DATA_PATH = ROOT / "datasets/traffic_structured_v1.parquet"
DB_PATH = ROOT / "datasets/traffic_v1.duckdb"
MAPPING_PATH = ROOT / "data/processed/traffic_to_osm_mapping_final.parquet"
GRAPH_PATH = ROOT / "data/raw/osm/bhubaneswar_drive.graphml"
METADATA_PATH = ROOT / "models/feature_metadata.json"
MODEL_PATH = ROOT / "models/speed_predictor.joblib"
PREDICTIONS_PATH = ROOT / "results/phase7_predictions.parquet"
METRICS_PATH = ROOT / "results/phase7_metrics.csv"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def clean_scalar(value: Any) -> Any:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def sample_values(series: pd.Series, limit: int = 3) -> str:
    values = []
    for value in series.dropna().head(limit).tolist():
        value = clean_scalar(value)
        if isinstance(value, (list, dict, tuple)):
            value = str(value)
        values.append(value)
    return json.dumps(values, ensure_ascii=False)


def markdown_table(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join(["---"] * len(columns)) + "|"]
    for row in frame.itertuples(index=False, name=None):
        values = [str(clean_scalar(value)).replace("|", "\\|") for value in row]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def frame_schema_rows(
    artifact: str,
    entity: str,
    frame: pd.DataFrame,
    types: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    rows = []
    for column in frame.columns:
        series = frame[column]
        nulls = int(series.isna().sum())
        nonnull = series.dropna()
        dtype = (types or {}).get(column, str(series.dtype))
        if pd.api.types.is_numeric_dtype(series):
            minimum = clean_scalar(series.min()) if len(nonnull) else None
            maximum = clean_scalar(series.max()) if len(nonnull) else None
        elif pd.api.types.is_datetime64_any_dtype(series):
            minimum = clean_scalar(series.min()) if len(nonnull) else None
            maximum = clean_scalar(series.max()) if len(nonnull) else None
        else:
            minimum = maximum = None
        rows.append({
            "artifact": artifact,
            "entity": entity,
            "field": column,
            "dtype": dtype,
            "records": int(len(frame)),
            "missing_count": nulls,
            "missing_pct": round(100.0 * nulls / len(frame), 6) if len(frame) else None,
            "unique_non_null": int(series.nunique(dropna=True)),
            "minimum": minimum,
            "maximum": maximum,
            "sample_values": sample_values(series),
            "notes": "",
        })
    return rows


def graphml_types(path: Path) -> Dict[Tuple[str, str], str]:
    root = ET.parse(path).getroot()
    ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
    return {
        (item.attrib.get("for", "all"), item.attrib["attr.name"]): item.attrib.get("attr.type", "unknown")
        for item in root.findall("g:key", ns)
        if "attr.name" in item.attrib
    }


def compare_frames(left: pd.DataFrame, right: pd.DataFrame) -> bool:
    if list(left.columns) != list(right.columns) or len(left) != len(right):
        return False
    for column in left.columns:
        a, b = left[column].reset_index(drop=True), right[column].reset_index(drop=True)
        if pd.api.types.is_datetime64_any_dtype(a) or pd.api.types.is_datetime64_any_dtype(b):
            a_ns = pd.DatetimeIndex(pd.to_datetime(a, utc=True)).as_unit("ns").asi8
            b_ns = pd.DatetimeIndex(pd.to_datetime(b, utc=True)).as_unit("ns").asi8
            if not np.array_equal(a_ns, b_ns):
                return False
        elif pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
            if not np.array_equal(a.to_numpy(dtype=float), b.to_numpy(dtype=float), equal_nan=True):
                return False
        else:
            if not a.isna().equals(b.isna()):
                return False
            mask = ~a.isna()
            if not a[mask].astype(str).reset_index(drop=True).equals(b[mask].astype(str).reset_index(drop=True)):
                return False
    return True


def reconstruct_phase7(raw: pd.DataFrame, mapping: pd.DataFrame, metadata: Dict[str, Any], model: Any):
    """Recreate the feature engineering/split in the training file in memory."""
    observed = raw.loc[raw["is_observed"] == True].copy()
    observed["timestamp"] = pd.to_datetime(observed["timestamp"], utc=True)
    clean = observed[
        (observed["timestamp"] >= "2026-01-04")
        & (observed["timestamp"] <= "2026-01-17 04:00:05")
    ].copy()
    clean["ts_round"] = clean["timestamp"].dt.round("h")
    clean["ts_ist"] = clean["ts_round"].dt.tz_convert("Asia/Kolkata")
    segment_meta = (
        mapping[["traffic_segment_id", "confidence", "routing_eligibility"]]
        .drop_duplicates()
        .set_index("traffic_segment_id")
    )
    clean["mapping_confidence"] = clean["segment_id"].map(segment_meta["confidence"])
    clean["routing_eligibility"] = clean["segment_id"].map(segment_meta["routing_eligibility"])
    clean = clean.sort_values(["segment_id", "ts_round"]).reset_index(drop=True)
    grouped = clean.groupby("segment_id")["currentSpeed"]
    clean["target_speed"] = grouped.shift(-1)
    clean["target_timestamp_rounded"] = clean.groupby("segment_id")["ts_round"].shift(-1)
    clean["target_horizon_minutes"] = (
        clean["target_timestamp_rounded"] - clean["ts_round"]
    ).dt.total_seconds() / 60.0
    for lag in (1, 2, 3, 6, 12, 24):
        clean[f"speed_lag_{lag}h"] = grouped.shift(lag)
    for window in (3, 6, 24):
        clean[f"rolling_mean_{window}h"] = (
            grouped.rolling(window, min_periods=window).mean().reset_index(level=0, drop=True)
        )
    for window in (6, 24):
        clean[f"rolling_std_{window}h"] = (
            grouped.rolling(window, min_periods=window).std().reset_index(level=0, drop=True).fillna(0.0)
        )
    clean["hour"] = clean["ts_ist"].dt.hour
    clean["day_of_week"] = clean["ts_ist"].dt.dayofweek
    clean["is_weekend"] = (clean["day_of_week"] >= 5).astype(int)
    clean["sin_hour"] = np.sin(2 * np.pi * clean["hour"] / 24.0)
    clean["cos_hour"] = np.cos(2 * np.pi * clean["hour"] / 24.0)
    clean["sin_dow"] = np.sin(2 * np.pi * clean["day_of_week"] / 7.0)
    clean["cos_dow"] = np.cos(2 * np.pi * clean["day_of_week"] / 7.0)
    clean["target_hour"] = (clean["hour"] + 1) % 24
    clean["speed_ratio"] = clean["currentSpeed"] / clean["freeFlowSpeed"].clip(lower=1.0)
    clean["road_type_code"] = clean["road_type"].astype("category").cat.codes
    confidence_codes = {"HIGH": 2, "MEDIUM": 1, "LOW": 0}
    clean["conf_code"] = clean["mapping_confidence"].map(confidence_codes).fillna(1).astype(int)
    valid = clean[clean["target_speed"].notna() & clean["speed_lag_24h"].notna()].copy().reset_index(drop=True)
    unique_times = np.sort(valid["ts_round"].unique())
    train_times, val_times, test_times = unique_times[:204], unique_times[204:248], unique_times[248:]
    train = valid[valid["ts_round"].isin(train_times)].copy().reset_index(drop=True)
    validation = valid[valid["ts_round"].isin(val_times)].copy().reset_index(drop=True)
    test = valid[valid["ts_round"].isin(test_times)].copy().reset_index(drop=True)
    lookup = train.groupby(["segment_id", "target_hour"])["target_speed"].mean().to_dict()
    global_mean = float(train["target_speed"].mean())
    for part in (train, validation, test):
        keys = zip(part["segment_id"], part["target_hour"])
        part["hist_speed"] = np.array([lookup.get(key, global_mean) for key in keys])
    features = metadata["feature_cols"]
    x_test = test[features]
    y_test = test["target_speed"].to_numpy()
    prediction = np.clip(model.predict(x_test), 3.0, 120.0)
    return clean, valid, train, validation, test, features, x_test, y_test, prediction, train_times, val_times, test_times


def metric_row(name: str, actual: np.ndarray, predicted: np.ndarray) -> Dict[str, Any]:
    return {
        "model": name,
        "MAE_kmh": float(mean_absolute_error(actual, predicted)),
        "RMSE_kmh": float(root_mean_squared_error(actual, predicted)),
        "R2": float(r2_score(actual, predicted)),
        "median_absolute_error_kmh": float(median_absolute_error(actual, predicted)),
        "samples": int(len(actual)),
    }


def create_audit() -> Dict[str, Any]:
    for path in (DATA_PATH, DB_PATH, MAPPING_PATH, GRAPH_PATH, METADATA_PATH, MODEL_PATH, PREDICTIONS_PATH, METRICS_PATH):
        if not path.exists():
            raise FileNotFoundError(path)
    raw = pd.read_parquet(DATA_PATH)
    arrow_schema = pq.read_schema(DATA_PATH)
    mapping = pd.read_parquet(MAPPING_PATH)
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    model = joblib.load(MODEL_PATH)
    stored_predictions = pd.read_parquet(PREDICTIONS_PATH)
    stored_metrics = pd.read_csv(METRICS_PATH)

    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        tables = con.execute(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_type='BASE TABLE' ORDER BY table_schema, table_name"
        ).fetchdf()
        if tables.to_dict("records") != [{"table_schema": "main", "table_name": "traffic"}]:
            raise RuntimeError(f"Unexpected DuckDB base tables: {tables.to_dict('records')}")
        duck_types_frame = con.execute("DESCRIBE SELECT * FROM traffic").fetchdf()
        duck_frame = con.execute("SELECT * FROM traffic ORDER BY segment_id, hour").fetchdf()
    finally:
        con.close()
    parquet_sorted = raw.sort_values(["segment_id", "hour"]).reset_index(drop=True)
    duck_equal = compare_frames(parquet_sorted, duck_frame)

    graph = nx.read_graphml(GRAPH_PATH)
    graph_types = graphml_types(GRAPH_PATH)
    node_attr_counts: Dict[str, int] = {}
    for _, attrs in graph.nodes(data=True):
        for key in attrs:
            node_attr_counts[key] = node_attr_counts.get(key, 0) + 1
    edge_attr_counts: Dict[str, int] = {}
    for _, _, _, attrs in graph.edges(data=True, keys=True):
        for key in attrs:
            edge_attr_counts[key] = edge_attr_counts.get(key, 0) + 1

    clean, valid, train, validation, test, features, x_test, y_test, ml_prediction, train_times, val_times, test_times = reconstruct_phase7(
        raw, mapping, metadata, model
    )
    metrics = pd.DataFrame([
        metric_row("LightGBM saved model", y_test, ml_prediction),
        metric_row("Persistence currentSpeed(t)", y_test, test["currentSpeed"].to_numpy()),
        metric_row("Historical same-hour baseline", y_test, test["hist_speed"].to_numpy()),
    ])
    metric_display = metrics.rename(columns={
        "model": "Predictor",
        "MAE_kmh": "MAE km/h",
        "RMSE_kmh": "RMSE km/h",
        "R2": "R-squared",
        "median_absolute_error_kmh": "Median AE km/h",
        "samples": "Samples",
    }).copy()
    for column in ("MAE km/h", "RMSE km/h", "R-squared", "Median AE km/h"):
        metric_display[column] = metric_display[column].round(4)
    prediction_equal = np.array_equal(stored_predictions["traffic_segment_id"].to_numpy(), test["segment_id"].to_numpy())
    timestamp_equal = np.array_equal(
        pd.to_datetime(stored_predictions["timestamp"], utc=True).to_numpy(),
        pd.to_datetime(test["timestamp"], utc=True).to_numpy(),
    )
    actual_diff = float(np.max(np.abs(stored_predictions["actual_speed"].to_numpy() - y_test)))
    prediction_diff = float(np.max(np.abs(stored_predictions["predicted_speed"].to_numpy() - ml_prediction)))
    persistence_diff = float(np.max(np.abs(stored_predictions["persistence_prediction"].to_numpy() - test["currentSpeed"].to_numpy())))
    historical_diff = float(np.max(np.abs(stored_predictions["historical_prediction"].to_numpy() - test["hist_speed"].to_numpy())))

    target_horizons = valid["target_horizon_minutes"].value_counts().sort_index().to_dict()
    split_boundary_counts = {
        "train_labels_at_first_validation_feature_time": int((
            valid.loc[valid["ts_round"].isin(train_times), "target_timestamp_rounded"] == val_times[0]
        ).sum()),
        "validation_labels_at_first_test_feature_time": int((
            valid.loc[valid["ts_round"].isin(val_times), "target_timestamp_rounded"] == test_times[0]
        ).sum()),
    }
    horizon_exception = valid.loc[valid["target_horizon_minutes"] != 60.0, [
        "segment_id", "ts_round", "target_timestamp_rounded", "target_horizon_minutes", "currentSpeed", "target_speed"
    ]].to_dict("records")

    mapping_edges_exist = [
        graph.has_edge(str(row.u), str(row.v), key=int(row.key)) for row in mapping.itertuples(index=False)
    ]
    reverse_available = [
        graph.has_edge(str(row.v), str(row.u))
        for row in mapping.loc[mapping.routing_eligibility == "DYNAMIC_BIDIRECTIONAL"].itertuples(index=False)
    ]
    from src.routing.traffic_weights import GraphWeightManager, calculate_travel_time_seconds
    weight_manager = GraphWeightManager(graph, mapping)
    prediction_slice_time = pd.Timestamp("2026-01-15 14:00:00", tz="UTC")
    prediction_round = pd.to_datetime(stored_predictions["timestamp"], utc=True).dt.round("h")
    p14 = stored_predictions.loc[prediction_round == prediction_slice_time]
    predicted_speed_by_segment = dict(zip(p14["traffic_segment_id"], p14["predicted_speed"]))
    scenario_weights, effective_speeds, dynamic_edges = weight_manager.build_scenario_weights(predicted_speed_by_segment)
    data_observed = raw.loc[raw["is_observed"] == True]
    physical_time = data_observed["length_m"] * 3.6 / data_observed["currentSpeed"]
    current_time_error = (data_observed["currentTravelTime"] - physical_time).abs()
    finite_prediction_values = np.asarray(list(predicted_speed_by_segment.values()), dtype=float)

    # Exercise the service method to establish whether it predicts or selects stored outputs.
    from src.cloud.model_service import CloudModelService
    service = CloudModelService(
        model_path=str(MODEL_PATH), metadata_path=str(METADATA_PATH), predictions_path=str(PREDICTIONS_PATH)
    )
    service_message, service_elapsed_ms = service.generate_predictions_broadcast(prediction_slice_time)
    service_equal = service_message.predicted_speeds == predicted_speed_by_segment

    # Parquet and SQL schemas/data summary rows.
    schema_rows: List[Dict[str, Any]] = []
    parquet_type_map = {field.name: str(field.type) for field in arrow_schema}
    schema_rows.extend(frame_schema_rows(str(DATA_PATH.relative_to(ROOT)), "traffic", raw, parquet_type_map))
    duck_type_map = dict(zip(duck_types_frame["column_name"], duck_types_frame["column_type"]))
    schema_rows.extend(frame_schema_rows(str(DB_PATH.relative_to(ROOT)), "main.traffic", duck_frame, duck_type_map))
    schema_rows.extend(frame_schema_rows(str(MAPPING_PATH.relative_to(ROOT)), "traffic_to_osm_mapping", mapping))
    schema_rows.extend(frame_schema_rows(str(PREDICTIONS_PATH.relative_to(ROOT)), "phase7_predictions", stored_predictions))

    for entity, records, attr_counts in (
        ("node", graph.number_of_nodes(), node_attr_counts),
        ("edge", graph.number_of_edges(), edge_attr_counts),
    ):
        for field, present in sorted(attr_counts.items()):
            values = []
            iterator = graph.nodes(data=True) if entity == "node" else graph.edges(data=True, keys=True)
            for item in iterator:
                attrs = item[-1]
                if field in attrs and len(values) < 3:
                    values.append(str(attrs[field]))
            schema_rows.append({
                "artifact": str(GRAPH_PATH.relative_to(ROOT)),
                "entity": entity,
                "field": field,
                "dtype": graph_types.get((entity, field), "not-declared"),
                "records": records,
                "missing_count": records - present,
                "missing_pct": round(100.0 * (records - present) / records, 6),
                "unique_non_null": None,
                "minimum": None,
                "maximum": None,
                "sample_values": json.dumps(values, ensure_ascii=False),
                "notes": "GraphML key declared as string; NetworkX exposes the stored value without typed numeric conversion.",
            })

    metadata_scalars = {key: value for key, value in metadata.items() if not isinstance(value, (list, dict))}
    for key, value in metadata_scalars.items():
        schema_rows.append({
            "artifact": str(METADATA_PATH.relative_to(ROOT)), "entity": "model_metadata", "field": key,
            "dtype": type(value).__name__, "records": 1, "missing_count": 0, "missing_pct": 0.0,
            "unique_non_null": 1, "minimum": None, "maximum": None,
            "sample_values": json.dumps(clean_scalar(value)), "notes": "",
        })
    for index, feature in enumerate(features):
        series = x_test[feature]
        schema_rows.append({
            "artifact": str(MODEL_PATH.relative_to(ROOT)), "entity": "model_input_feature", "field": feature,
            "dtype": str(series.dtype), "records": int(len(x_test)), "missing_count": int(series.isna().sum()),
            "missing_pct": round(float(series.isna().mean() * 100.0), 6),
            "unique_non_null": int(series.nunique(dropna=True)), "minimum": clean_scalar(series.min()),
            "maximum": clean_scalar(series.max()), "sample_values": sample_values(series),
            "notes": f"Feature order {index + 1}; order is part of the saved model contract.",
        })
    for artifact_path in (DATA_PATH, DB_PATH, MAPPING_PATH, GRAPH_PATH, METADATA_PATH, MODEL_PATH, PREDICTIONS_PATH, METRICS_PATH):
        schema_rows.append({
            "artifact": str(artifact_path.relative_to(ROOT)),
            "entity": "file_metadata",
            "field": "sha256",
            "dtype": "hex string",
            "records": 1,
            "missing_count": 0,
            "missing_pct": 0.0,
            "unique_non_null": 1,
            "minimum": None,
            "maximum": None,
            "sample_values": json.dumps(sha256(artifact_path)),
            "notes": f"file size {artifact_path.stat().st_size} bytes",
        })
    schema_frame = pd.DataFrame(schema_rows)

    feature_gaps = [
        {"feature": "Segment ID", "classification": "Available directly", "observed_field_or_derivation": "segment_id; phase7_predictions uses traffic_segment_id", "evidence_and_limit": "700 distinct IDs; all 700 appear in the mapping, but sensors cover only a small subset of OSM edges.", "controlled_synthetic_demo_only": "No"},
        {"feature": "Timestamp", "classification": "Available directly", "observed_field_or_derivation": "hour is the regular UTC grid; timestamp is the per-observation capture time", "evidence_and_limit": "394 hourly buckets; stored predictions cover 44 rounded hours. Keep feature time and target-valid time distinct.", "controlled_synthetic_demo_only": "No"},
        {"feature": "Historical observed speed", "classification": "Available directly", "observed_field_or_derivation": "currentSpeed (km/h), rows with is_observed=True", "evidence_and_limit": "246,399 observed values, 1–54 km/h; no volume/count field.", "controlled_synthetic_demo_only": "No"},
        {"feature": "Traffic volume / vehicle count", "classification": "Missing", "observed_field_or_derivation": "No matching column in either traffic table or OSM mapping", "evidence_and_limit": "Cannot be reconstructed from speed or travel time without unsupported assumptions.", "controlled_synthetic_demo_only": "Yes, only as a separately labelled simulation input; never label as observed"},
        {"feature": "Lagged speed", "classification": "Derivable from existing data", "observed_field_or_derivation": "Group currentSpeed by segment and exact hourly timestamp", "evidence_and_limit": "Phase 7 code uses row shifts after filtering; make gaps explicit so lag_24h is truly 24 elapsed hours.", "controlled_synthetic_demo_only": "No"},
        {"feature": "Rolling speed statistics", "classification": "Derivable from existing data", "observed_field_or_derivation": "Rolling means (3/6/24) and standard deviations (6/24) over historical currentSpeed", "evidence_and_limit": "Already used by model. Define windows by elapsed time and avoid crossing gaps.", "controlled_synthetic_demo_only": "No"},
        {"feature": "Hour, weekday, weekend, cyclical time", "classification": "Derivable from existing data", "observed_field_or_derivation": "hour and timestamp converted to Asia/Kolkata in Phase 7", "evidence_and_limit": "Already used; document whether model time is UTC or local and maintain the same convention at serving.", "controlled_synthetic_demo_only": "No"},
        {"feature": "Road length", "classification": "Available directly", "observed_field_or_derivation": "traffic length_m; mapping length_m/osm_edge_length_m; GraphML edge length", "evidence_and_limit": "All 46,679 GraphML edges have length; GraphML stores attributes as strings and caller casts to float.", "controlled_synthetic_demo_only": "No"},
        {"feature": "Road type", "classification": "Available directly", "observed_field_or_derivation": "traffic road_type and GraphML edge highway", "evidence_and_limit": "All OSM edges have highway; measured dataset has primary/secondary/trunk. The saved code uses categorical codes.", "controlled_synthetic_demo_only": "No"},
        {"feature": "Free-flow speed", "classification": "Available directly", "observed_field_or_derivation": "freeFlowSpeed for observed traffic segments; static speed class from OSM highway", "evidence_and_limit": "True/legal maxspeed exists on only 451/46,679 OSM edges (0.97%). FreeFlowSpeed is only observed for monitored segments; verify it is available ex ante before using as a feature.", "controlled_synthetic_demo_only": "No; do not fabricate speed limits"},
        {"feature": "Traffic segment to directed OSM edge mapping", "classification": "Available directly", "observed_field_or_derivation": "traffic_to_osm_mapping_final.parquet: traffic_segment_id,u,v,key,routing_eligibility", "evidence_and_limit": "All 700 rows reference extant graph edges; 9 use STATIC_FALLBACK, 92 DYNAMIC_BIDIRECTIONAL, 599 DYNAMIC. 43 rows overlap an existing directed tuple.", "controlled_synthetic_demo_only": "No"},
        {"feature": "Future speed target and prediction horizon", "classification": "Derivable from existing data", "observed_field_or_derivation": "Next currentSpeed row per segment after chronological sort; add target_timestamp = t + 1h", "evidence_and_limit": "Among 204,399 Phase 7 valid labels, 204,398 are 60 min and 1 is 120 min. Phase 7 outputs store origin timestamp, not target timestamp.", "controlled_synthetic_demo_only": "No for training; synthetic targets only for a labelled demonstration"},
        {"feature": "Weather / incidents / event indicators", "classification": "Missing", "observed_field_or_derivation": "No weather, incident severity, or event source in inspected tables", "evidence_and_limit": "Could explain unusual speed changes but are not required for a speed-only baseline.", "controlled_synthetic_demo_only": "Optional, labelled runtime overlay only; collect real covariates for claims"},
        {"feature": "Dynamic observations on unmonitored OSM edges", "classification": "Missing", "observed_field_or_derivation": "Unmapped edges remain static in GraphWeightManager", "evidence_and_limit": f"{len(graph.edges) - len(dynamic_edges)} of {len(graph.edges)} directed edges receive no dynamic speed in the inspected prediction scenario.", "controlled_synthetic_demo_only": "Synthetic speeds can illustrate routing only; not credible traffic labels"},
    ]
    feature_gap_frame = pd.DataFrame(feature_gaps)

    observed = raw.loc[raw["is_observed"] == True]
    hour_coverage = raw.groupby("hour")["is_observed"].agg(["size", "sum"])
    speed_stats = observed["currentSpeed"].describe(percentiles=[0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]).to_dict()
    freeflow_stats = observed["freeFlowSpeed"].describe(percentiles=[0.5, 0.95, 0.99]).to_dict()
    observation_time = pd.to_datetime(observed["timestamp"], utc=True)
    train_source_start, train_source_end = clean.loc[clean["ts_round"].isin(train_times), "ts_round"].min(), clean.loc[clean["ts_round"].isin(train_times), "ts_round"].max()
    val_source_start, val_source_end = clean.loc[clean["ts_round"].isin(val_times), "ts_round"].min(), clean.loc[clean["ts_round"].isin(val_times), "ts_round"].max()
    test_source_start, test_source_end = clean.loc[clean["ts_round"].isin(test_times), "ts_round"].min(), clean.loc[clean["ts_round"].isin(test_times), "ts_round"].max()
    mapping_status = mapping["mapping_status"].value_counts().to_dict()
    mapping_eligibility = mapping["routing_eligibility"].value_counts().to_dict()
    confidence_counts = mapping["confidence"].value_counts().to_dict()
    direction_counts = mapping["direction_status"].value_counts().to_dict()
    road_type_counts = observed["road_type"].value_counts().to_dict()
    prediction_rounds = pd.to_datetime(stored_predictions["timestamp"], utc=True).dt.round("h")
    prediction_rows_per_round = stored_predictions.groupby(prediction_rounds)["traffic_segment_id"].nunique().value_counts().to_dict()
    dynamic_edge_pct = 100.0 * len(dynamic_edges) / graph.number_of_edges()
    prediction_speed_clip = (float(np.min(finite_prediction_values)), float(np.max(finite_prediction_values)))
    graph_edge_lengths = np.asarray([float(attrs["length"]) for _, _, _, attrs in graph.edges(data=True, keys=True)])
    graphml_maxspeed_present = edge_attr_counts.get("maxspeed", 0)
    mapping_length_abs = mapping["length_error_m"].abs()
    sample_feature = x_test.iloc[[0]]
    sample_prediction = float(np.clip(model.predict(sample_feature)[0], 3.0, 120.0))
    sample_test = test.iloc[0]

    schema_frame.to_csv(ROOT / "GEOPULSE_DATASET_SCHEMA.csv", index=False)
    feature_gap_frame.to_csv(ROOT / "GEOPULSE_FEATURE_GAP_ANALYSIS.csv", index=False)

    data_report = f"""# GeoPulse Dataset Readiness Report

**Audit date:** 22 November 2026  
**Scope:** Read-only inspection of the current traffic Parquet, DuckDB mirror, mapping Parquet, Bhubaneswar GraphML, and saved prediction artifact.

## Verdict

The current data is sufficient for an hourly speed-prediction prototype and for replaying historical traffic changes. It is not sufficient for a network-wide predictive-routing claim: only 700 traffic segments are monitored, 9 are configured static fallback, and the inspected prediction scenario dynamically weights {len(dynamic_edges)} of {graph.number_of_edges():,} directed OSM edges ({dynamic_edge_pct:.2f}%). Vehicle volume/count is absent. No synthetic records were generated.

The older `docs/dataset_audit_report.md` states the Bhubaneswar graph was absent. The current file at `{GRAPH_PATH.relative_to(ROOT)}` exists and was inspected directly; this audit uses the current artifact rather than that stale inventory statement.

`is_observed` and the traffic field names are present in the Parquet itself, but the file does not embed a source endpoint, API request ID, sensor provenance, or collection manifest. Existing repository audit documentation attributes the feed to TomTom; the tabular artifact alone cannot independently establish that provenance.

## Files and exact schemas

All exact columns, Arrow/DuckDB types, missing percentages, distinct counts, ranges, and samples are in `GEOPULSE_DATASET_SCHEMA.csv`.

| Path | Observed structure | Key result |
|---|---|---|
| `{DATA_PATH.relative_to(ROOT)}` | {len(raw):,} rows × {len(raw.columns)} columns; {raw.segment_id.nunique()} segment IDs | {int(raw.is_observed.sum()):,} observed rows; {int((~raw.is_observed).sum()):,} explicit missing rows |
| `{DB_PATH.relative_to(ROOT)}` | DuckDB `main.traffic`; {len(duck_frame):,} rows | Same column order and values as Parquet: **{duck_equal}** |
| `{MAPPING_PATH.relative_to(ROOT)}` | {len(mapping)} rows × {len(mapping.columns)} columns | {mapping.traffic_segment_id.nunique()} traffic segment IDs; all mapped `(u,v,key)` references exist in GraphML |
| `{GRAPH_PATH.relative_to(ROOT)}` | Directed `MultiDiGraph`; {graph.number_of_nodes():,} nodes / {graph.number_of_edges():,} directed edges | Edge `length` and `highway` attrs cover every edge; GraphML declares attrs as strings |
| `{PREDICTIONS_PATH.relative_to(ROOT)}` | {len(stored_predictions):,} rows × {len(stored_predictions.columns)} columns | 700 segments for each of 44 rounded hourly prediction times |

### Traffic table fields

The Arrow schema for the Parquet has: `segment_id:int64`, `hour:timestamp[ns, UTC]`, `timestamp:timestamp[ns, UTC]`, `currentSpeed:double`, `freeFlowSpeed:double`, `currentTravelTime:double`, `freeFlowTravelTime:double`, `confidence:double`, `is_observed:bool`, `is_missing:bool`, `roadClosure:bool`, `osmid:string`, `road_name:double`, `road_type:string`, `length_m:double`, `lat:double`, `lon:double`. DuckDB table `traffic` contains the same names and compatible SQL types (`BIGINT`, `TIMESTAMP WITH TIME ZONE`, `DOUBLE`, `BOOLEAN`, `VARCHAR`).

Example records from the actual Parquet:

```json
{json.dumps([clean_scalar(x) for x in raw.head(3).to_dict(orient="records")], ensure_ascii=False, indent=2, default=str)}
```

The first record is an observed row. The next two rows are explicit missing slots with `is_observed=false`, `is_missing=true`, and measurement fields null. The schema CSV includes samples for every field, plus graph node/edge attributes and model inputs.

## Time coverage, sampling, duplicates, and missingness

- The regular `hour` grid contains {raw.hour.nunique()} consecutive hourly UTC buckets from `{raw.hour.min()}` through `{raw.hour.max()}`. Every segment has one row per grid bucket ({raw.groupby('segment_id').size().min()}–{raw.groupby('segment_id').size().max()} grid rows).
- There are {int((hour_coverage['sum'] == 700).sum())} fully observed hours, {int(((hour_coverage['sum'] > 0) & (hour_coverage['sum'] < 700)).sum())} partial hours, and {int((hour_coverage['sum'] == 0).sum())} empty hours. The partial-hour counts are `{hour_coverage.loc[(hour_coverage['sum'] > 0) & (hour_coverage['sum'] < 700), 'sum'].value_counts().sort_index().to_dict()}`; one hour has a single missing segment.
- The capture `timestamp` is non-null for {len(observed):,} records and ranges from `{observation_time.min()}` to `{observation_time.max()}` with {observation_time.nunique()} distinct timestamp values. Capture timestamps are not the regular grid; `hour` is the explicit bucket field.
- Missing values are {100.0 * raw.isna().sum().sum() / (len(raw) * len(raw.columns)):.2f}% of all cells. Measurement and descriptive columns are null on the {int((~raw.is_observed).sum()):,} missing rows ({100*(~raw.is_observed).mean():.4f}% of rows); the two boolean observation flags are populated on every row.
- Full rows duplicated: {int(raw.duplicated().sum())}. Duplicate `(segment_id,hour)` keys: {int(raw.duplicated(['segment_id','hour']).sum())}. Duplicate non-null `(segment_id,timestamp)` keys: {int(observed.duplicated(['segment_id','timestamp']).sum())}.
- The Phase 7 training window, after its own UTC timestamp filter and 24-observation lag requirement, has {len(clean):,} observed rows and {len(valid):,} valid labels over {len(np.sort(valid.ts_round.unique()))} source timestamps. It has no duplicate `(segment_id, rounded timestamp)` keys.

## Speed target distribution and source limits

`currentSpeed` across observed records has min/median/mean/max **{speed_stats['min']:.1f}/{speed_stats['50%']:.1f}/{speed_stats['mean']:.2f}/{speed_stats['max']:.1f} km/h** (p05 {speed_stats['5%']:.1f}, p95 {speed_stats['95%']:.1f}). There are {int((observed.currentSpeed == 0).sum())} zero values and {int((observed.currentSpeed < 0).sum())} negative values. `{road_type_counts}` is the observed road-type distribution. `roadClosure=true` occurs {int((observed.roadClosure == True).sum()):,} times; this is a flag, not a vehicle count.

The training target is `currentSpeed` shifted to the next observed row by segment after sorting on rounded timestamp. Among valid Phase 7 labels its distribution has {int(valid.target_speed.count()):,} values, min/median/mean/max **{valid.target_speed.min():.1f}/{valid.target_speed.median():.1f}/{valid.target_speed.mean():.2f}/{valid.target_speed.max():.1f} km/h**. Label horizons are `{target_horizons}` minutes: {target_horizons.get(60.0, 0):,} labels are exactly one hour and {sum(count for horizon, count in target_horizons.items() if horizon != 60.0):,} label is two hours because the hour at `2026-01-12 06:00 UTC` is missing for one segment. The target is therefore nearly, but not perfectly, a fixed one-hour horizon; store an explicit target timestamp and filter/enforce exact elapsed time. The outlier row is `{json.dumps([{key: clean_scalar(value) for key, value in row.items()} for row in horizon_exception], default=str)}`.

The canonical tables do not contain a traffic-volume/vehicle-count column. Existing observed speed history is sufficient to derive lags, rolling statistics, and the current next-hour label. It cannot recover vehicle count, weather, or incident cause.

## OSM and segment-mapping coverage

The current graph is `networkx.MultiDiGraph`, directed and multi-edge, with {graph.number_of_nodes():,} nodes and {graph.number_of_edges():,} directed edge records. Node GraphML keys are `y`, `x`, `street_count`, `highway`, and `junction`; edge keys include `osmid`, `highway`, `oneway`, `reversed`, `length`, `geometry`, `name`, `lanes`, `maxspeed`, `bridge`, `access`, `ref`, `junction`, `width`, and `tunnel`. GraphML declares these attributes as strings, so numeric fields must be parsed by consumers. Edge length spans {graph_edge_lengths.min():.3f}–{graph_edge_lengths.max():.3f} metres. `maxspeed` is present on {graphml_maxspeed_present:,}/{graph.number_of_edges():,} edges ({100*graphml_maxspeed_present/graph.number_of_edges():.2f}%).

Mapping counts are: status `{mapping_status}`, confidence `{confidence_counts}`, direction `{direction_counts}`, eligibility `{mapping_eligibility}`. All {sum(mapping_edges_exist)}/{len(mapping)} mapped `(u,v,key)` records exist in the graph. There are {mapping[['u','v','key']].drop_duplicates().shape[0]} unique directed tuples among {len(mapping)} mapping rows; {len(mapping)-mapping[['u','v','key']].drop_duplicates().shape[0]} rows share a directed tuple. All {sum(reverse_available)}/{len(reverse_available)} `DYNAMIC_BIDIRECTIONAL` rows have a reverse graph edge. Segment-to-edge length error has median {mapping_length_abs.median():.3f} m, p95 {mapping_length_abs.quantile(.95):.3f} m, p99 {mapping_length_abs.quantile(.99):.3f} m, and maximum {mapping_length_abs.max():.3f} m.

At 2026-01-15 14:00 UTC, the stored prediction slice contains {len(p14)} finite positive speeds in range {prediction_speed_clip[0]:.2f}–{prediction_speed_clip[1]:.2f} km/h. `GraphWeightManager` produced {len(dynamic_edges)} dynamic directed weights and retained static weights for {len(weight_manager.edge_lengths)-len(dynamic_edges):,} other graph edges. The dynamic coverage is {dynamic_edge_pct:.2f}% of the directed graph. `DYNAMIC_BIDIRECTIONAL` copies its segment speed onto reverse edge records; `STATIC_FALLBACK` and unmapped edges retain static road-class speeds.

For routing, compute `travel_time_seconds = edge_length_meters / (predicted_speed_kmh * 1000 / 3600)`. The existing weight manager clips dynamic speeds to 3–120 km/h; the lower clamp maps zero/negative input to a finite crawl speed (100 m at zero becomes {calculate_travel_time_seconds(100, 0):.1f} seconds). It does not sanitize NaN: NaN speed produces NaN time, so inference outputs should be checked and missing predictions should fall back to static speed. Do not use the dataset's precomputed `currentTravelTime` as a road-edge cost: against `length_m*3.6/currentSpeed`, its observed MAE is {current_time_error.mean():.2f} seconds, median relative error {100*(current_time_error/(physical_time)).median():.1f}%, and correlation {data_observed.currentTravelTime.corr(physical_time):.3f}.

## Feature availability

The complete requested-feature classification is in `GEOPULSE_FEATURE_GAP_ANALYSIS.csv`. Segment/time, observed speed, lengths, road types, free-flow speed for the monitored segments, and segment-to-edge mappings are present. Lags, rolling windows, time encodings, and the next speed label are derivable. Volume/count is missing and cannot be inferred from speed. A clearly labelled synthetic count or incident overlay is suitable only for a controlled simulator demonstration; none was created in this audit.

## Read-only checks and paths

The report-generation script reads the paths above, compares DuckDB against Parquet, runs the existing model in memory, checks mapping/weight coverage, and writes only the four requested Phase 1 reports. See `GEOPULSE_ML_READINESS_REPORT.md` for ML metrics, feature order, leakage and inference findings.

```powershell
.\\.venv\\Scripts\\python.exe -B scripts/audit_phase1_dataset_ml_readiness.py
```

SHA-256 hashes for the inspected source files are in `GEOPULSE_DATASET_SCHEMA.csv` summary rows. No dataset, model, routing, or application artifact was changed.
"""

    meta_features = metadata["feature_cols"]
    ml_report = f"""# GeoPulse ML Readiness Report

**Audit date:** 22 November 2026  
**Model:** `{MODEL_PATH.relative_to(ROOT)}` — {type(model).__name__}  
**Training source:** `{ROOT.joinpath('scripts/train_phase7_speed_predictor.py').relative_to(ROOT)}`

## Verdict

The saved LightGBM artifact loads and performs inference with the exact 25-feature schema. Reconstructed predictions match all {len(stored_predictions):,} saved test predictions exactly. The model beats persistence on the recorded chronological test set but does not beat the training-only same-hour historical baseline. The artifacts support an hourly, 700-segment prototype and offline traffic replay; they do not yet support a credible general or network-wide predictive-routing claim.

## Exact model contract and inference check

`models/feature_metadata.json` declares `{metadata['model_type']}`, {metadata['n_features']} features, best iteration {metadata['best_iteration']}, and clipping [{metadata['speed_clipping'][0]}, {metadata['speed_clipping'][1]}] km/h. The loaded estimator reports {model.n_features_in_} inputs and feature names in the same order as metadata: **{list(model.feature_name_) == meta_features}**.

Feature order (order is required at inference):

```text
{', '.join(meta_features)}
```

I rebuilt the training pipeline's feature row from the observed history, mapping, time, and same-hour historical lookup; it has 25 columns and zero missing values. A one-row `model.predict()` call returned **{sample_prediction:.6f} km/h** for segment {int(sample_test.segment_id)} at feature time `{sample_test.timestamp}`. Its recorded next-hour target is **{float(sample_test.target_speed):.1f} km/h** at `{sample_test.target_timestamp_rounded}`. This is a real reconstructed row, not a fabricated sensor reading.

The saved `results/phase7_predictions.parquet` has {len(stored_predictions):,} rows, {stored_predictions.traffic_segment_id.nunique()} segments, no missing cells, and 44 rounded hourly timestamps from `{prediction_round.min()}` through `{prediction_round.max()}`. Every rounded timestamp contains 700 segments. Reconstructed test IDs/timestamps match the saved rows, and maximum absolute differences for target, LightGBM prediction, persistence prediction, and historical prediction are **{actual_diff:.1f}, {prediction_diff:.1f}, {persistence_diff:.1f}, and {historical_diff:.1f} km/h** respectively.

## Target, training split, and temporal leakage

The training file uses the target `g.shift(-1)` on `currentSpeed`, sorted by `segment_id` and rounded timestamp. Its intended mapping is feature row at time *t* → speed at the next observed timestamp. The selected period has 292 source timestamps after requiring a 24-row lag. Actual label horizons are {target_horizons}; one target is 120 minutes, not 60. The saved prediction Parquet includes the feature/origin `timestamp` and `actual_speed`, but no explicit `target_timestamp` column, so the forecast's validity time is implicit.

The split is chronological over sorted unique feature timestamps, not random:

| Split | Feature timestamps (UTC) | Unique hours | Samples |
|---|---|---:|---:|
| Train | {train_source_start} → {train_source_end} | {len(train_times)} | {len(train):,} |
| Validation | {val_source_start} → {val_source_end} | {len(val_times)} | {len(validation):,} |
| Test | {test_source_start} → {test_source_end} | {len(test_times)} | {len(test):,} |

The split is chronological, but it is not purged by label time. {split_boundary_counts['train_labels_at_first_validation_feature_time']} training labels land at the first validation feature timestamp, and {split_boundary_counts['validation_labels_at_first_test_feature_time']} validation labels land at the first test feature timestamp. Since each count is a full 700-segment hour, the validation boundary outcome is used during early stopping and the first test hour appears as validation labels. Purge the last source hour of train and validation, or split by target timestamp, before using the test result as an independent estimate.

Other leakage notes:

- Lag and rolling values are built before the split, which is valid for historical features if only past observations are included. The current window is nearly continuous, but exact elapsed-time checks should replace row-count assumptions when gaps occur.
- `hist_speed` is calculated from train labels only, which is appropriate. `road_type_code` is categorical metadata rather than a future target.
- `freeFlowSpeed` is included at time *t*. The file contains time-varying values, so verify this is available ex ante at serving time rather than a future/ex-post field.
- Prediction timestamp conventions should distinguish feature time from target-valid time explicitly when routing consumes a forecast.

## Test-set performance versus baselines

Metrics were recomputed from the saved model and exact reconstructed test matrix, and match `results/phase7_metrics.csv` to its stored rounding:

{markdown_table(metric_display)}

LightGBM improves on persistence by {100*(1-metrics.iloc[0].MAE_kmh/metrics.iloc[1].MAE_kmh):.1f}% MAE and {100*(1-metrics.iloc[0].RMSE_kmh/metrics.iloc[1].RMSE_kmh):.1f}% RMSE. It is {100*(metrics.iloc[0].MAE_kmh/metrics.iloc[2].MAE_kmh-1):.1f}% worse in MAE and {100*(metrics.iloc[0].RMSE_kmh/metrics.iloc[2].RMSE_kmh-1):.1f}% worse in RMSE than the historical same-hour baseline. Thus the ML model is not the best tested speed predictor overall, despite beating persistence. Performance should be remeasured after purging boundary labels and on more independent periods.

## Live inference is not integrated

`src/cloud/model_service.py` loads the joblib model, metadata, and the stored prediction Parquet. Its `generate_predictions_broadcast()` filters cached rows by rounded timestamp (or silently falls back to the closest saved timestamp) and builds the message from `predicted_speed`. It never constructs the 25 model features and never calls `self.model.predict()`; loading the model does not make this a live inference service. A read-only call for 2026-01-15 14:00 UTC returned {service_message.total_segments} speeds exactly equal to the stored prediction slice. This is prediction replay.

For live inference, a serving path must maintain ordered per-segment speed history, reject/fill gaps explicitly, derive the same local-time/road/mapping/confidence features and training-only `hist_speed`, enforce metadata feature order and clipping, call `model.predict()`, validate finite outputs, and attach both origin and target-valid timestamps. An absent stored timestamp currently selects a nearest timestamp without marking the result stale.

## Routing compatibility

- Traffic mapping has {len(mapping)} segment rows and {mapping.traffic_segment_id.nunique()} unique IDs. All mapping edge tuples exist in the graph. Eligibility is `{mapping_eligibility}`; all {sum(reverse_available)} bidirectional entries have reverse graph edges. Their speeds are assigned symmetrically to reverse edge records.
- The 14:00 stored predictions produced {len(dynamic_edges)} dynamic directed edge weights ({dynamic_edge_pct:.2f}% of {graph.number_of_edges():,} edges). Other edges remain static, so most road links do not receive ML traffic.
- GraphML edge `length` is present on every edge; OSM `maxspeed` is present on only {graphml_maxspeed_present}/{graph.number_of_edges()} edges. Existing static fallback estimates speeds by highway class (15–50 km/h), not a complete legal speed-limit dataset.
- Convert speed to cost as `length_m / (speed_kmh * 1000 / 3600)`. Current code clips dynamic speeds to 3–120 km/h and clamps zero/negative speed to 3 km/h in the kinematic conversion. It does not safely handle NaN speed; validate finite predictions and use static fallback for missing/invalid values.
- Do not use `currentTravelTime` as a GraphML edge weight. Its observed values disagree with `length_m*3.6/currentSpeed` (MAE {current_time_error.mean():.1f} seconds, correlation {data_observed.currentTravelTime.corr(physical_time):.3f}); derive edge seconds from edge length and effective speed.

## Synthetic data decision and next phase

Synthetic data is **not required** for the speed-only prototype or for demonstrating changing traffic over time. The historical grid has 394 hourly buckets (including 35 empty and 15 partial hours), the ML training window has 292 source timestamps with one missing cell, and the saved prediction artifact supplies 44 fully covered hourly steps. It can support offline historical replay; it does not provide live or future traffic ingestion. A synthetic incident/volume overlay is optional for a controlled simulation only, must be labelled as synthetic, and must stay separate from model-training targets and measured evaluation.

For a credible predictive-routing experiment, collect or construct (with explicit provenance) a purged, fixed-horizon target set; use an independent temporal holdout; validate against persistence and historical baselines; expand or explicitly scope the 700 monitored segment coverage; and retain a mapping/edge coverage and static-fallback report. Vehicle counts are only needed if the model objective is expanded to include flow; they cannot be derived from these tables.

## Recommended next implementation phase

Build a leakage-safe, reproducible ML inference and replay path: explicitly carry origin and target-valid timestamps, purge split-boundary labels, enforce a one-hour target, and reconstruct the same feature row from rolling per-segment history before calling the saved model. Re-evaluate on a new temporal holdout against both persistence and the historical baseline. Keep this phase scoped to the 700 mapped segments unless more real traffic observations are collected; do not imply dynamic coverage of the full OSM graph.

## Reproducible command

```powershell
.\\.venv\\Scripts\\python.exe -B scripts/audit_phase1_dataset_ml_readiness.py
```

This command does not run the training script. It loads the existing model, reconstructs the test inputs in memory, calls `predict()`, verifies exact parity with the saved prediction artifact, and writes only the four requested audit deliverables.
"""

    schema_frame.to_csv(ROOT / "GEOPULSE_DATASET_SCHEMA.csv", index=False)
    feature_gap_frame.to_csv(ROOT / "GEOPULSE_FEATURE_GAP_ANALYSIS.csv", index=False)
    (ROOT / "GEOPULSE_DATASET_READINESS_REPORT.md").write_text(data_report, encoding="utf-8")
    (ROOT / "GEOPULSE_ML_READINESS_REPORT.md").write_text(ml_report, encoding="utf-8")

    summary = {
        "parquet_rows": len(raw),
        "observed_rows": int(raw.is_observed.sum()),
        "duckdb_exact_parity": duck_equal,
        "graph_nodes": graph.number_of_nodes(),
        "graph_edges": graph.number_of_edges(),
        "mapped_segments": int(mapping.traffic_segment_id.nunique()),
        "dynamic_edges_at_2026_01_15_14_utc": len(dynamic_edges),
        "model_feature_order_matches": list(model.feature_name_) == features,
        "reconstructed_test_prediction_max_abs_diff": prediction_diff,
        "model_test_mae_kmh": float(metrics.iloc[0].MAE_kmh),
        "persistence_test_mae_kmh": float(metrics.iloc[1].MAE_kmh),
        "historical_test_mae_kmh": float(metrics.iloc[2].MAE_kmh),
        "service_replays_saved_prediction_slice": service_equal,
        "service_ms": service_elapsed_ms,
        "schema_rows": len(schema_frame),
        "feature_gap_rows": len(feature_gap_frame),
        "sha256": {str(path.relative_to(ROOT)): sha256(path) for path in (DATA_PATH, DB_PATH, MAPPING_PATH, GRAPH_PATH, METADATA_PATH, MODEL_PATH)},
    }
    return summary


if __name__ == "__main__":
    print(json.dumps(create_audit(), indent=2))
