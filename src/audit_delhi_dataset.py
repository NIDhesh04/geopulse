"""Read-only inventory and temporal audit for the Delhi dataset ZIP.

The ZIP is read in place (no extraction or rewriting). GeoJSON features are
streamed so the large day files are not held in memory as a full object tree.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import statistics
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ZIP_PATH = ROOT.parent / "delhi dataset.zip"
OUT = ROOT / "outputs" / "delhi_dataset_audit"


def read_json_array(zf, member, array_key="features", limit=None):
    decoder = json.JSONDecoder()
    with zf.open(member, "r") as f:
        buf = ""
        pos = 0
        started = False
        while not started:
            chunk = f.read(1 << 16)
            if not chunk:
                return
            buf += chunk.decode("utf-8")
            marker = buf.find('"' + array_key + '"')
            if marker >= 0:
                arr = buf.find("[", marker)
                if arr >= 0:
                    pos = arr + 1
                    started = True
            if not started and len(buf) > (1 << 20):
                buf = buf[-128:]
        emitted = 0
        while True:
            while True:
                while pos < len(buf) and buf[pos].isspace():
                    pos += 1
                if pos < len(buf) and buf[pos] == ",":
                    pos += 1
                    continue
                break
            if pos < len(buf) and buf[pos] == "]":
                return
            try:
                obj, end = decoder.raw_decode(buf, pos)
            except json.JSONDecodeError:
                chunk = f.read(1 << 16)
                if not chunk:
                    return
                buf = buf[pos:] + chunk.decode("utf-8")
                pos = 0
                continue
            yield obj
            emitted += 1
            pos = end
            if limit is not None and emitted >= limit:
                return
            if pos > (1 << 20):
                buf = buf[pos:]
                pos = 0


def archive_inventory(zf):
    records = []
    for item in zf.infolist():
        suffix = Path(item.filename).suffix.lower()
        records.append({"file": item.filename, "file_type": suffix or "directory",
                        "uncompressed_bytes": item.file_size, "compressed_bytes": item.compress_size})
    return records


class Distribution:
    def __init__(self):
        self.freq = Counter()
        self.total = 0.0
        self.total_sq = 0.0

    def add(self, value):
        value = float(value)
        self.freq[value] += 1
        self.total += value
        self.total_sq += value * value

    @property
    def n(self):
        return sum(self.freq.values())

    def quantile(self, p):
        if not self.n:
            return None
        ordered = sorted(self.freq.items())
        rank = p * (self.n - 1)
        lo, hi = int(rank), int(np.ceil(rank))
        def at(index):
            acc = 0
            for value, count in ordered:
                acc += count
                if index < acc:
                    return value
            return ordered[-1][0]
        a, b = at(lo), at(hi)
        return a + (rank - lo) * (b - a)

    def summary(self):
        if not self.n:
            return {"n": 0}
        mean = self.total / self.n
        variance = max(0.0, self.total_sq / self.n - mean * mean)
        return {"n": self.n, "min": min(self.freq), "max": max(self.freq),
                "mean": mean, "median": self.quantile(.5), "std_population": variance ** .5,
                "p01": self.quantile(.01), "p05": self.quantile(.05),
                "p25": self.quantile(.25), "p75": self.quantile(.75),
                "p90": self.quantile(.90), "p95": self.quantile(.95),
                "p99": self.quantile(.99), "p999": self.quantile(.999),
                "zeros": self.freq.get(0.0, 0),
                "zero_pct": 100 * self.freq.get(0.0, 0) / self.n}


def geometry_digest(geometry):
    if not geometry or geometry.get("type") != "LineString":
        return None
    coords = geometry.get("coordinates") or []
    forward = json.dumps(coords, separators=(",", ":"), ensure_ascii=True)
    reverse = json.dumps(list(reversed(coords)), separators=(",", ":"), ensure_ascii=True)
    canonical = min(forward, reverse)
    return hashlib.sha1(canonical.encode("ascii")).hexdigest()


def safe_day_from_name(name):
    m = re.search(r"(2024-\d\d-\d\d)_to_", name)
    return date.fromisoformat(m.group(1)) if m else None


def autocorrelation(values, lag, min_pairs=30):
    if len(values) <= lag:
        return None, 0
    a, b = values[:-lag], values[lag:]
    mask = np.isfinite(a) & np.isfinite(b)
    n = int(mask.sum())
    if n < min_pairs or np.std(a[mask]) == 0 or np.std(b[mask]) == 0:
        return None, n
    return float(np.corrcoef(a[mask], b[mask])[0, 1]), n


def stats_of(values):
    clean = [float(x) for x in values if x is not None and np.isfinite(x)]
    if not clean:
        return {"n": 0}
    arr = np.asarray(clean, dtype=float)
    return {"n": int(len(arr)), "min": float(arr.min()), "max": float(arr.max()),
            "mean": float(arr.mean()), "median": float(np.median(arr)),
            "std_population": float(arr.std()), "p90": float(np.quantile(arr, .90)),
            "p95": float(np.quantile(arr, .95)), "p99": float(np.quantile(arr, .99))}


def write_csv(path, rows, fieldnames=None):
    rows = list(rows)
    if fieldnames is None:
        fieldnames = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def make_inventory_rows(zf, probe_daily_stats):
    daily_by_name = {r["file"]: r for r in probe_daily_stats}
    rows = []
    for item in zf.infolist():
        if item.is_dir():
            continue
        name = item.filename
        suffix = Path(name).suffix.lower()
        row = {"file": name, "type": suffix or "unknown", "size_uncompressed_bytes": item.file_size,
               "size_compressed_bytes": item.compress_size, "rows": None, "columns": None,
               "purpose": ""}
        if name in daily_by_name:
            r = daily_by_name[name]
            data_columns = ["geometry", *filter(None, r["property_columns"].split(";"))]
            row.update({"rows": r["data_features"], "columns": ";".join(data_columns),
                        "purpose": "Daily road-segment GeoJSON; 24 hourly probeCount buckets per segment when complete"})
        elif suffix == ".csv":
            with zf.open(name, "r") as f:
                reader = csv.reader((line.decode("utf-8-sig") for line in f))
                header = next(reader, [])
                row["columns"] = ";".join(header)
                row["rows"] = sum(1 for _ in reader)
            row["purpose"] = "Weekday by time-of-day aggregate metrics"
        elif suffix in (".json", ".geojson"):
            obj = json.loads(zf.read(name))
            if isinstance(obj, dict) and obj.get("type") == "Feature":
                row["rows"] = 1
                row["columns"] = "geometry;properties:" + ";".join((obj.get("properties") or {}).keys())
                row["purpose"] = "Administrative boundary GeoJSON"
            elif isinstance(obj, dict) and "facilities" in obj:
                feats = obj["facilities"]
                row["rows"] = len(feats)
                row["columns"] = "facility;features"
                row["purpose"] = "Facility category and OSM tag lookup"
            elif isinstance(obj, dict):
                row["rows"] = 1
                row["columns"] = ";".join(obj.keys())
                row["purpose"] = "Annual/city-level aggregate traffic metrics"
            elif isinstance(obj, list):
                row["rows"] = len(obj)
                row["columns"] = ";".join(obj[0].keys()) if obj and isinstance(obj[0], dict) else ""
                row["purpose"] = "JSON array"
        elif suffix == ".md":
            text = zf.read(name).decode("utf-8", "replace")
            row["rows"] = sum(bool(line.strip()) for line in text.splitlines())
            row["purpose"] = "Dataset documentation; not tabular"
        rows.append(row)
    return rows


def sample_features(zf, member, limit=4):
    print("SAMPLE", member)
    for i, feat in enumerate(read_json_array(zf, member, limit=limit)):
        props = feat.get("properties") or {}
        sample = {"feature_index": i, "geometry_type": (feat.get("geometry") or {}).get("type"),
                  "property_keys": list(props), "properties": props}
        print(json.dumps(sample, ensure_ascii=True, default=str)[:12000])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true", help="print first few feature schemas and exit")
    args = ap.parse_args()
    if not ZIP_PATH.is_file():
        raise FileNotFoundError(f"Delhi archive not found: {ZIP_PATH}")
    with zipfile.ZipFile(ZIP_PATH, "r") as zf:
        members = [n for n in zf.namelist() if n.endswith(".geojson") and "/probe_counts/" in n]
        if args.sample:
            sample_features(zf, members[0])
            return
        members = sorted(members, key=lambda n: safe_day_from_name(n) or date.min)
        dates = [safe_day_from_name(n) for n in members]
        if not members or any(d is None for d in dates):
            raise ValueError("Could not identify daily probe GeoJSON dates from filenames")
        day_index = {d: i for i, d in enumerate(dates)}
        day_rows = []
        global_dist = Distribution()
        by_hour = defaultdict(Distribution)
        by_day = defaultdict(Distribution)
        by_frc = defaultdict(Distribution)
        by_speed_limit = defaultdict(Distribution)
        segment = defaultdict(lambda: {"count": 0, "sum": 0.0, "sum_sq": 0.0, "zero": 0,
                                      "min": None, "max": None, "days": set(),
                                      "frc": Counter(), "new_ids": set(), "geometries": set(),
                                      "street_names": set()})
        series = {}
        id_to_new = defaultdict(set)
        new_to_id = defaultdict(set)
        id_to_geom = defaultdict(set)
        all_geometry_ids = defaultdict(set)
        global_geometry_counts = Counter()
        road_names = Counter()
        road_name_segment_ids = defaultdict(set)
        geometries_shared_by_ids_per_day = 0
        prop_types = defaultdict(Counter)
        prop_missing = Counter()
        prop_nonnull = Counter()
        total_data_property_records = 0
        metadata_examples = []
        geometry_types = Counter()
        null_data_geometries = 0
        unsupported_data_geometries = 0
        non_integer_counts = 0
        negative_counts = 0
        missing_probe_values = 0
        null_probe_value_entries = 0
        malformed_time_entries = 0
        malformed_segment_records = 0
        duplicate_feature_rows = 0
        duplicate_new_ids = 0
        duplicate_cell_occurrences = 0
        expected_segment_hour_cells = 0
        actual_unique_segment_hour_cells = 0
        schema_columns = set()
        data_property_keys = set()
        time_set_definitions = {}
        time_zone_values = Counter()
        probe_source_values = Counter()
        day_total_probe = {}
        spike_rows = []
        unique_ids_day_map = defaultdict(set)

        for member, day in zip(members, dates):
            di = day_index[day]
            d_records = 0
            d_metadata = 0
            d_segment_ids = set()
            d_feature_ids = Counter()
            d_cell_seen = set()
            d_cell_unique = set()
            d_valid_cells = set()
            d_ambiguous_cells = set()
            d_duplicate_cell_count = 0
            d_null_probe_count = 0
            d_values = Distribution()
            d_missing = 0
            d_expected = 0
            d_invalid_entries = 0
            d_geometry_missing = 0
            d_geom_counts = Counter()
            d_id_geom = defaultdict(set)
            d_newid_count = Counter()
            d_feature_count = 0
            d_property_keys = set()
            d_timezone = None
            d_probe_source = None

            for feat in read_json_array(zf, member):
                d_feature_count += 1
                props = feat.get("properties") or {}
                geom = feat.get("geometry")
                if "segmentId" not in props:
                    d_metadata += 1
                    if len(metadata_examples) < 2:
                        metadata_examples.append(props)
                    if props.get("zoneId"):
                        time_zone_values[str(props["zoneId"])] += 1
                        d_timezone = props["zoneId"]
                    if props.get("probeSource"):
                        probe_source_values[str(props["probeSource"])] += 1
                        d_probe_source = props["probeSource"]
                    for ts in props.get("timeSets", []):
                        try:
                            time_set_definitions[int(ts["@id"])] = ts.get("name")
                        except (KeyError, TypeError, ValueError):
                            pass
                    continue
                d_records += 1
                d_property_keys.update(props)
                data_property_keys.update(props)
                schema_columns.update(("type", "geometry", "properties"))
                sid = props.get("segmentId")
                if sid is None:
                    malformed_segment_records += 1
                    continue
                try:
                    sid = int(sid)
                except (TypeError, ValueError):
                    malformed_segment_records += 1
                    continue
                d_segment_ids.add(sid)
                d_feature_ids[sid] += 1
                unique_ids_day_map[day].add(sid)
                seg = segment[sid]
                seg["days"].add(di)
                st_name = props.get("streetName")
                if st_name not in (None, ""):
                    st_name = str(st_name)
                    road_names[st_name] += 1
                    road_name_segment_ids[st_name].add(sid)
                    seg["street_names"].add(st_name)
                frc = props.get("frc")
                frc_key = str(frc) if frc is not None else "missing"
                seg["frc"][frc_key] += 1
                new_id = props.get("newSegmentId")
                if new_id is not None:
                    new_id = str(new_id)
                    seg["new_ids"].add(new_id)
                    id_to_new[sid].add(new_id)
                    new_to_id[new_id].add(sid)
                    d_newid_count[new_id] += 1
                gh = geometry_digest(geom)
                if gh:
                    seg["geometries"].add(gh)
                    id_to_geom[sid].add(gh)
                    d_geom_counts[gh] += 1
                    d_id_geom[gh].add(sid)
                    all_geometry_ids[gh].add(sid)
                    global_geometry_counts[gh] += 1
                elif geom is None:
                    null_data_geometries += 1
                    d_geometry_missing += 1
                else:
                    unsupported_data_geometries += 1
                geometry_types[(geom or {}).get("type", "null")] += 1
                for key in set(props) | data_property_keys:
                    if key not in props or props.get(key) is None:
                        pass
                    else:
                        prop_nonnull[key] += 1
                for key, value in props.items():
                    if value is None:
                        continue
                    prop_types[key][type(value).__name__] += 1
                total_data_property_records += 1
                if isinstance(props.get("speedLimit"), (int, float)):
                    by_speed_limit[str(props["speedLimit"])].add(props["speedLimit"])
                counts = props.get("segmentProbeCounts")
                if not isinstance(counts, list):
                    continue
                seen_in_feature = set()
                for entry in counts:
                    if not isinstance(entry, dict):
                        d_invalid_entries += 1
                        malformed_time_entries += 1
                        continue
                    ts = entry.get("timeSet")
                    try:
                        ts = int(ts)
                        hour = ts - 2
                    except (TypeError, ValueError):
                        d_invalid_entries += 1
                        malformed_time_entries += 1
                        continue
                    if not 0 <= hour < 24:
                        d_invalid_entries += 1
                        malformed_time_entries += 1
                        continue
                    key = (sid, hour)
                    global_key = (di, sid, hour)
                    duplicate_cell = key in seen_in_feature or global_key in d_cell_seen
                    if duplicate_cell:
                        duplicate_cell_occurrences += 1
                        d_duplicate_cell_count += 1
                        d_ambiguous_cells.add(key)
                        d_cell_seen.add(global_key)
                        d_cell_unique.add(global_key)
                    else:
                        seen_in_feature.add(key)
                    d_cell_seen.add(global_key)
                    d_cell_unique.add(global_key)
                    value = entry.get("probeCount")
                    if value is None or isinstance(value, bool):
                        d_null_probe_count += 1
                        null_probe_value_entries += 1
                        continue
                    try:
                        value_f = float(value)
                    except (TypeError, ValueError):
                        d_invalid_entries += 1
                        malformed_time_entries += 1
                        continue
                    if not np.isfinite(value_f):
                        d_null_probe_count += 1
                        null_probe_value_entries += 1
                        continue
                    if value_f < 0:
                        negative_counts += 1
                    if not value_f.is_integer():
                        non_integer_counts += 1
                    global_dist.add(value_f)
                    d_values.add(value_f)
                    by_hour[hour].add(value_f)
                    by_day[day.isoformat()].add(value_f)
                    by_frc[frc_key].add(value_f)
                    seg["count"] += 1
                    seg["sum"] += value_f
                    seg["sum_sq"] += value_f * value_f
                    seg["zero"] += (value_f == 0)
                    seg["min"] = value_f if seg["min"] is None else min(seg["min"], value_f)
                    seg["max"] = value_f if seg["max"] is None else max(seg["max"], value_f)
                    if sid not in series:
                        series[sid] = np.full(len(members) * 24, np.nan, dtype=np.float32)
                    flat_idx = di * 24 + hour
                    if duplicate_cell:
                        # Exclude ambiguous duplicates only from derived temporal signal;
                        # all duplicate source values remain included in descriptive counts.
                        series[sid][flat_idx] = np.nan
                    elif np.isfinite(series[sid][flat_idx]):
                        series[sid][flat_idx] = np.nan
                    else:
                        series[sid][flat_idx] = value_f
                        d_valid_cells.add(key)
            for sid, occurrences in d_feature_ids.items():
                if occurrences > 1:
                    duplicate_feature_rows += occurrences - 1
                    d_ambiguous_cells.update((sid, hour) for hour in range(24))
                    # Duplicate segment-day records make all of that segment-day's
                    # temporal positions ambiguous for sequence/ACF analysis.
                    if sid in series:
                        series[sid][di * 24:(di + 1) * 24] = np.nan
            d_expected = len(d_segment_ids) * 24
            expected_segment_hour_cells += d_expected
            d_missing = max(0, d_expected - len(d_valid_cells - d_ambiguous_cells))
            missing_probe_values += d_missing
            prop_missing = Counter({k: total_data_property_records - prop_nonnull[k]
                                    for k in data_property_keys})
            actual_unique_segment_hour_cells += len(d_cell_unique)
            d_duplicate_new_ids = sum(n - 1 for n in d_newid_count.values() if n > 1)
            d_exact_duplicate_geometries = sum(n - 1 for n in d_geom_counts.values() if n > 1)
            geometries_shared_by_ids_per_day += sum(len(ids) > 1 for ids in d_id_geom.values())
            day_total_probe[day.isoformat()] = d_values.total
            day_rows.append({"date": day.isoformat(), "data_features": d_records,
                             "file": member, "total_geojson_features": d_feature_count,
                             "metadata_features": d_metadata, "unique_segment_ids": len(d_segment_ids),
                             "expected_segment_hour_cells": d_expected,
                             "unique_segment_hour_cells_present": len(d_cell_unique),
                             "missing_hour_buckets": max(0, d_expected - len(d_cell_unique)),
                             "valid_probe_count_values": d_values.n, "missing_probe_count_values": d_missing,
                             "null_probe_count_entries": d_null_probe_count,
                             "duplicate_segment_id_rows": sum(n - 1 for n in d_feature_ids.values() if n > 1),
                             "duplicate_segment_hour_occurrences": d_duplicate_cell_count,
                             "invalid_time_entries": d_invalid_entries,
                             "null_geometry_segment_features": d_geometry_missing,
                             "duplicate_geometry_occurrences": d_exact_duplicate_geometries,
                             "duplicate_newSegmentId_occurrences": d_duplicate_new_ids,
                             "probe_count_sum": d_values.total,
                             "probe_count_mean": d_values.total / d_values.n if d_values.n else None,
                             "timezone": d_timezone, "probeSource": d_probe_source,
                             "property_columns": ";".join(sorted(d_property_keys))})
            print(f"Processed {day.isoformat()}: {d_records:,} segment features, {d_values.n:,} probeCount values", flush=True)

        # Segment persistence and per-segment concentration/variability.
        persistence = []
        segment_quality = []
        acf_rows = []
        segment_means = []
        segment_zero_pcts = []
        constant_segments = 0
        all_zero_segments = 0
        reappearing_segments = 0
        total_presence_sequences = 0
        for sid, rec in segment.items():
            days = sorted(rec["days"])
            n_days = len(days)
            if n_days == len(dates):
                category = "present all days"
            elif 15 <= n_days <= 19:
                category = "present 15-19 days"
            elif 10 <= n_days <= 14:
                category = "present 10-14 days"
            else:
                category = "present <10 days"
            runs = 0
            previous = -2
            for di in days:
                if di != previous + 1:
                    runs += 1
                previous = di
            total_presence_sequences += runs
            if runs > 1:
                reappearing_segments += 1
            n = rec["count"]
            mean = rec["sum"] / n if n else None
            var = max(0.0, rec["sum_sq"] / n - mean * mean) if n else None
            zero_pct = 100 * rec["zero"] / n if n else None
            if n and rec["min"] == rec["max"]:
                constant_segments += 1
            if n and rec["zero"] == n:
                all_zero_segments += 1
            if mean is not None:
                segment_means.append(mean)
                segment_zero_pcts.append(zero_pct)
            persistence.append({"segmentId": sid, "days_present": n_days, "persistence_category": category,
                               "presence_runs": runs, "missing_days_within_window": len(dates) - n_days,
                               "unique_newSegmentIds": len(rec["new_ids"]),
                               "unique_geometries_direction_agnostic": len(rec["geometries"]),
                               "unique_street_names": len(rec["street_names"]),
                               "most_common_frc": rec["frc"].most_common(1)[0][0] if rec["frc"] else None})
            segment_quality.append({"segmentId": sid, "valid_probe_count_values": n,
                                    "days_present": n_days, "sum_probeCount": rec["sum"],
                                    "mean_probeCount": mean, "std_probeCount": var ** .5 if var is not None else None,
                                    "min_probeCount": rec["min"], "max_probeCount": rec["max"],
                                    "zero_count": rec["zero"], "zero_pct": zero_pct,
                                    "unique_newSegmentIds": len(rec["new_ids"]),
                                    "unique_geometries_direction_agnostic": len(rec["geometries"]),
                                    "street_names": ";".join(sorted(rec["street_names"]))})
            values = series.get(sid)
            if values is not None:
                acf_row = {"segmentId": sid, "days_present": n_days}
                for lag in (1, 3, 6, 12, 24):
                    value, pairs = autocorrelation(values, lag)
                    acf_row[f"lag{lag}_acf"] = value
                    acf_row[f"lag{lag}_valid_pairs"] = pairs
                acf_rows.append(acf_row)
        categories = Counter(r["persistence_category"] for r in persistence)
        present_all_days = sum(r["days_present"] == len(dates) for r in persistence)
        multi_new_ids = sum(len(v) > 1 for v in id_to_new.values())
        multi_geometries = sum(len(v) > 1 for v in id_to_geom.values())
        new_id_conflicts = sum(len(v) > 1 for v in new_to_id.values())
        repeated_geometry_sids = sum(len(v) > 1 for v in all_geometry_ids.values())

        acf_summary = {}
        for lag in (1, 3, 6, 12, 24):
            vals = [r[f"lag{lag}_acf"] for r in acf_rows if r[f"lag{lag}_acf"] is not None]
            acf_summary[str(lag)] = {**stats_of(vals), "segments_estimable": len(vals),
                                     "segments_total": len(acf_rows)}

        def table_rows(dists, keyname):
            return [{keyname: k, **dist.summary()} for k, dist in sorted(dists.items(), key=lambda kv: str(kv[0]))]

        probe_rows_by_hour = table_rows(by_hour, "hour_start_local")
        probe_rows_by_day = table_rows(by_day, "date")
        probe_rows_by_frc = table_rows(by_frc, "frc_code_undocumented")
        speed_limit_rows = table_rows(by_speed_limit, "speedLimit_value")
        inventory_rows = make_inventory_rows(zf, day_rows)
        OUT.mkdir(parents=True, exist_ok=True)
        write_csv(OUT / "file_inventory.csv", inventory_rows)
        write_csv(OUT / "daily_coverage.csv", day_rows)
        write_csv(OUT / "probe_by_hour.csv", probe_rows_by_hour)
        write_csv(OUT / "probe_by_day.csv", probe_rows_by_day)
        write_csv(OUT / "probe_by_frc.csv", probe_rows_by_frc)
        write_csv(OUT / "speed_limit_distribution.csv", speed_limit_rows)
        write_csv(OUT / "segment_persistence.csv", persistence)
        write_csv(OUT / "segment_probe_quality.csv", segment_quality)
        write_csv(OUT / "autocorrelation_by_segment.csv", acf_rows)

        expected_unique_cells = sum(r["expected_segment_hour_cells"] for r in day_rows)
        present_cells = sum(r["unique_segment_hour_cells_present"] for r in day_rows)
        missing_expected_buckets = max(0, expected_unique_cells - present_cells)
        total_segment_days = sum(r["unique_segment_ids"] for r in day_rows)
        all_count_values = global_dist.summary()
        q999 = global_dist.quantile(.999)
        top_segments = sorted(segment_quality, key=lambda r: (r["max_probeCount"] or -1), reverse=True)[:25]
        for sid, values in series.items():
            valid_idx = np.flatnonzero(np.isfinite(values))
            for idx in valid_idx:
                current = float(values[idx])
                if current <= (q999 or 0) or idx % 24 == 0:
                    continue
                prior = float(values[idx - 1])
                if np.isfinite(prior) and prior > 0 and current >= 10 * prior:
                    day = dates[idx // 24]
                    spike_rows.append({"segmentId": sid, "date": day.isoformat(), "hour_start_local": idx % 24,
                                       "probeCount": current, "previous_hour_probeCount": prior,
                                       "global_p999": q999, "ratio_to_previous_hour": current / prior})
        spike_rows.sort(key=lambda r: (r["probeCount"], r["ratio_to_previous_hour"]), reverse=True)
        write_csv(OUT / "spike_candidates_top100.csv", spike_rows[:100])

        # Compute peak windows from the actual hourly profile, without asserting
        # that probe count is congestion or volume.
        hourly_mean = {int(r["hour_start_local"]): r["mean"] for r in probe_rows_by_hour}
        morning_hours = [7, 8, 9]
        evening_hours = [16, 17, 18, 19]
        morning_mean = float(np.mean([hourly_mean[h] for h in morning_hours if h in hourly_mean])) if hourly_mean else None
        evening_mean = float(np.mean([hourly_mean[h] for h in evening_hours if h in hourly_mean])) if hourly_mean else None
        weekend_days = {d.isoformat() for d in dates if d.weekday() >= 5}
        weekday_vals = [r["mean"] for r in probe_rows_by_day if r["date"] not in weekend_days]
        weekend_vals = [r["mean"] for r in probe_rows_by_day if r["date"] in weekend_days]

        # Small auxiliary documents and annual aggregate metrics.
        aux = {}
        with zipfile.ZipFile(ZIP_PATH, "r") as z2:
            for name in z2.namelist():
                if "/global_metrics/" in name and name.endswith(".json"):
                    aux[name.rsplit("/", 1)[-1]] = json.loads(z2.read(name))
        summary = {
            "archive": {"path": str(ZIP_PATH), "bytes": ZIP_PATH.stat().st_size,
                        "entries": len(inventory_rows), "probe_geojson_files": len(members),
                        "uncompressed_bytes_total": sum(i.file_size for i in zf.infolist() if not i.is_dir()),
                        "compressed_bytes_total": sum(i.compress_size for i in zf.infolist() if not i.is_dir())},
            "documentation": {"readme": "Describes the files as hourly road probe counts for 2024-08-11 through 2024-08-30 and gives high-level global metrics; no field-level definition of probeCount, one-probe unit, FRC, or speedLimit unit was found.",
                              "probe_semantics": "Semantics unresolved. README uses 'probe count' but does not define one probe or validate it as a vehicle, GPS observation, connected vehicle, trip, trajectory, volume, or density.",
                              "timezone": sorted(time_zone_values), "probeSource": dict(probe_source_values),
                              "distance_unit_preference": "KILOMETERS", "time_bucket_definition": time_set_definitions},
            "daily_data": {"files": len(members), "first_date": dates[0].isoformat(), "last_date": dates[-1].isoformat(),
                           "calendar_days_inclusive": len(dates), "total_segment_features": sum(r["data_features"] for r in day_rows),
                           "hourly_bucket_slots_per_segment_if_complete": 24,
                           "calendar_hour_bucket_slots": len(dates) * 24,
                           "earliest_hour_interval_local": f"{dates[0].isoformat()} 00:00-01:00",
                           "latest_hour_interval_local": f"{dates[-1].isoformat()} 23:00-24:00",
                           "standalone_timestamp_field_in_road_features": False,
                           "duplicate_timestamp_check": "No standalone timestamp exists; duplicate segmentId/timeSet/dateRange cells are counted as duplicate segment-hour occurrences.",
                           "total_metadata_features": sum(r["metadata_features"] for r in day_rows),
                           "unique_segment_ids": len(segment), "segment_days": total_segment_days,
                           "rows_per_day_min": min(r["data_features"] for r in day_rows),
                           "rows_per_day_median": float(np.median([r["data_features"] for r in day_rows])),
                           "rows_per_day_max": max(r["data_features"] for r in day_rows),
                           "daily_rows_claim_readme": "over 4,000,000 entries per day; compare with actual feature and segment-hour counts",
                           "expected_segment_hour_cells_for_segments_present_each_day": expected_unique_cells,
                           "unique_segment_hour_cells_present": present_cells,
                           "missing_segment_hour_buckets": missing_expected_buckets,
                           "missing_bucket_pct": 100 * missing_expected_buckets / max(expected_unique_cells, 1),
                           "probeCount_values_nonnull": global_dist.n,
                           "probeCount_cells_missing_or_ambiguous": missing_probe_values,
                           "probeCount_entries_explicitly_null": null_probe_value_entries,
                           "duplicate_segment_id_rows_within_day": duplicate_feature_rows,
                           "duplicate_segment_hour_occurrences": duplicate_cell_occurrences,
                           "malformed_time_entries": malformed_time_entries,
                           "malformed_segment_records": malformed_segment_records,
                           "null_geometry_segment_features": null_data_geometries,
                           "unsupported_geometry_segment_features": unsupported_data_geometries,
                           "geometry_types": dict(geometry_types),
                           "per_day": day_rows},
            "schema": {"data_feature_fields": ["geometry", *sorted(data_property_keys)],
                       "property_types": {k: dict(v) for k, v in prop_types.items()},
                       "property_missing_counts": dict(prop_missing),
                       "segment_property_record_counts": {k: total_data_property_records for k in data_property_keys},
                       "non_integer_probeCount_values": non_integer_counts,
                       "negative_probeCount_values": negative_counts,
                       "metadata_feature_property_keys": list(metadata_examples[0]) if metadata_examples else [],
                       "coordinate_reference": "GeoJSON; no explicit CRS member found (RFC 7946 default is longitude/latitude WGS84)",
                       "geometry_digest_unique_direction_agnostic": len(global_geometry_counts),
                       "duplicate_geometry_occurrences_within_day": sum(r["duplicate_geometry_occurrences"] for r in day_rows),
                       "geometries_linking_multiple_segmentIds": repeated_geometry_sids},
            "probeCount": {"stored_values": all_count_values,
                           "missing_pct_of_expected_segment_hour_cells": 100 * missing_probe_values / max(expected_unique_cells, 1),
                           "by_hour_local": probe_rows_by_hour, "by_date": probe_rows_by_day,
                           "by_frc_code_undocumented": probe_rows_by_frc,
                           "by_speedLimit_value_unit_undocumented": speed_limit_rows,
                           "zero_inflation_pct": all_count_values.get("zero_pct"),
                           "global_p999": q999,
                           "constant_segments": constant_segments,
                           "all_zero_segments": all_zero_segments,
                           "segment_mean_distribution": stats_of(segment_means),
                           "segment_zero_pct_distribution": stats_of(segment_zero_pcts),
                           "segments_with_at_least_one_candidate_spike": len({r["segmentId"] for r in spike_rows}),
                           "top_spike_candidates": spike_rows[:20]},
            "segments": {"unique_segmentId": len(segment),
                         "unique_newSegmentId": len(new_to_id),
                         "persistence_categories": dict(categories),
                         "present_all_days": present_all_days,
                         "present_some_days": len(segment) - present_all_days,
                         "segments_reappearing_after_absence": reappearing_segments,
                         "total_contiguous_presence_runs": total_presence_sequences,
                         "segmentId_with_multiple_newSegmentIds": multi_new_ids,
                         "newSegmentId_mapping_to_multiple_segmentIds": new_id_conflicts,
                         "segmentId_with_multiple_geometries": multi_geometries,
                         "unique_street_names": len(road_names),
                         "street_names_used_by_multiple_segmentIds": sum(len(ids) > 1 for ids in road_name_segment_ids.values()),
                         "segments_with_multiple_street_names": sum(len(r["street_names"]) > 1 for r in segment.values()),
                         "duplicate_same_day_geometry_occurrences": sum(r["duplicate_geometry_occurrences"] for r in day_rows),
                         "same_day_geometry_keys_shared_by_multiple_segmentIds": geometries_shared_by_ids_per_day,
                         "persistence_rows": len(persistence)},
            "temporal_signal": {"hourly_lags_across_local_time_buckets": acf_summary,
                                "hour_of_day_mean_probeCount": hourly_mean,
                                "morning_07_10_mean": morning_mean,
                                "evening_16_20_mean": evening_mean,
                                "daily_mean_weekday_distribution": stats_of(weekday_vals),
                                "daily_mean_weekend_distribution": stats_of(weekend_vals),
                                "interpretation_limit": "These are temporal patterns in probeCount; they do not prove traffic volume, congestion, speed, or route-cost predictability."},
            "annual_aggregate_files": aux,
            "inventory_csv": "file_inventory.csv", "outputs_dir": str(OUT)}
        (OUT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        report_lines = [
            "# Delhi traffic dataset scientific audit", "",
            "Read-only ZIP analysis; the source archive was not extracted or changed. No machine-learning models were trained.", "",
            f"Archive: `{ZIP_PATH}` ({ZIP_PATH.stat().st_size:,} bytes); {len(inventory_rows)} files; {len(members)} daily GeoJSONs.", "",
            "## Package inventory", "",
            "Full per-file row/feature counts, columns, purposes, and compressed/uncompressed sizes are in `file_inventory.csv`.", "",
            "## Documentation and probe semantics", "",
            "The README describes hourly road probe counts for Aug 11-30, 2024. Each daily GeoJSON has a metadata feature and road-segment features with `segmentProbeCounts` entries indexed by `timeSet` and `dateRange`; metadata sets `zoneId=Asia/Kolkata`, `probeSource=ALL`, and 24 intervals from 00:00-01:00 through 23:00-24:00. The documentation does not define what one probe represents. **Semantics unresolved**: do not label counts as vehicles, volume, density, GPS fixes, or congestion without provider documentation/validation.", "",
            "## Traffic target assessment", "",
            "`probeCount` is present as a nested hourly count for each road-segment feature, but it is not a validated speed or travel-time target. Segment-level `speedLimit` is static metadata (its unit is undocumented in the row schema); no observed speed or segment-hour travel time is present. City/year aggregate JSON and weekday CSVs do contain average speed/travel-time/congestion summaries, but they are city/urban summaries rather than segment-hour targets. The `congestion_level` field in annual JSON has no documented scale (for example, values 147 and 123 coexist with separate average percentages 33 and 29).", "",
            "## Temporal and segment structure", "",
            f"Date files span {dates[0].isoformat()} through {dates[-1].isoformat()} ({len(dates)} calendar days). Time buckets are hourly by `timeSet`, labeled as intervals in Asia/Kolkata; exact sample instant/start-vs-end convention is not specified. Expected segment-hour cells for the segments present on each date: {expected_unique_cells:,}; unique bucket entries found: {present_cells:,}; missing buckets: {missing_expected_buckets:,} ({100*missing_expected_buckets/max(expected_unique_cells,1):.4f}%). Duplicate segment-ID rows: {duplicate_feature_rows:,}; duplicate segment-hour occurrences: {duplicate_cell_occurrences:,}.", "",
            f"Unique segment IDs: {len(segment):,}; segment-days: {total_segment_days:,}; IDs present all {len(dates)} days: {present_all_days:,}; IDs reappearing after a day-level absence: {reappearing_segments:,}. ID and geometry stability counts are in `summary.json` and `segment_persistence.csv`.", "",
            "| Persistence category | Segment IDs |", "|---|---:|",
            *[f"| {k} | {v} |" for k, v in sorted(categories.items())], "",
            "## Probe-count quality", "",
            f"Across stored `probeCount` values: {json.dumps(all_count_values, ensure_ascii=False)}. Zero is retained as a recorded count, but it cannot be interpreted as no traffic or free-flow absent semantics. Negative values: {negative_counts}; non-integer values: {non_integer_counts}; expected cells missing or ambiguous: {missing_probe_values:,}; explicit null entries: {null_probe_value_entries:,}.", "",
            f"Probe-count means by hour show morning 07:00-10:00 average {morning_mean:.4f} and evening 16:00-20:00 average {evening_mean:.4f} (count units unresolved). Weekday daily-mean distribution: {json.dumps(stats_of(weekday_vals))}; weekend daily-mean distribution: {json.dumps(stats_of(weekend_vals))}.", "",
            f"Segments with constant nonmissing probeCount: {constant_segments:,}; all-zero segments: {all_zero_segments:,}. Spike candidates use a screening rule of above the global 99.9th percentile and at least 10x the previous valid hour; this is not proof of an error. Top candidates are in `spike_candidates_top100.csv`.", "",
            "## Temporal signal (not model results)", "",
            f"Per-segment autocorrelation summaries (minimum 30 valid pairs per lag): `{json.dumps(acf_summary, ensure_ascii=False)}`. Lag 24 is same-hour next-day association. These statistics concern probe counts only and cannot establish predictable speed or routing cost.", "",
            "## Important limitations", "",
            "The README claim of over 4,000,000 entries/day is kept separate from the observed feature and segment-hour counts in the report. `frc`, `speedLimit`, distance-field semantics, probe unit, and exact bucket timestamp convention lack a field-level codebook. The annual aggregate and weekday tables are not substitutes for segment-level observed speed/travel-time labels. No values were imputed or altered.", ""
        ]
        (OUT / "audit_report.md").write_text("\n".join(report_lines), encoding="utf-8")
        print(f"Delhi dataset audit complete: {OUT}")


if __name__ == "__main__":
    main()
