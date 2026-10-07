"""Inspect traffic_v1.duckdb and traffic_structured_v1.parquet (read-only).

Writes: outputs/phase1/metrics/duckdb_inventory.json and a text dump.
"""
import json
import sys
from pathlib import Path

import duckdb
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.config import DUCKDB_PATH, PARQUET_PATH, CSV_PATH, METRIC_DIR  # noqa: E402


def main():
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    inv = {"duckdb": {}, "parquet": {}}
    lines = []

    objs = con.execute(
        "SELECT table_schema, table_name, table_type FROM information_schema.tables ORDER BY 1,2"
    ).fetchall()
    lines.append(f"== DuckDB objects in {DUCKDB_PATH.name} ==")
    for schema, name, ttype in objs:
        fq = f'"{schema}"."{name}"'
        cols = con.execute(f"DESCRIBE {fq}").fetchall()
        n = con.execute(f"SELECT COUNT(*) FROM {fq}").fetchone()[0]
        sample = con.execute(f"SELECT * FROM {fq} LIMIT 5").fetchdf()
        inv["duckdb"][f"{schema}.{name}"] = {
            "type": ttype,
            "rows": n,
            "columns": [{"name": c[0], "dtype": c[1]} for c in cols],
        }
        lines.append(f"\n--- {schema}.{name} ({ttype}) rows={n}")
        for c in cols:
            lines.append(f"   {c[0]:<25} {c[1]}")
        lines.append(sample.to_string())

    # Any views' SQL definitions (may reveal provenance)
    try:
        views = con.execute("SELECT view_name, sql FROM duckdb_views() WHERE NOT internal").fetchall()
        for v, sql in views:
            lines.append(f"\nVIEW {v}: {sql}")
            inv["duckdb"].setdefault("_views", {})[v] = sql
    except Exception as e:  # pragma: no cover
        lines.append(f"view listing failed: {e}")

    # Parquet
    pf = pq.ParquetFile(PARQUET_PATH)
    inv["parquet"] = {
        "rows": pf.metadata.num_rows,
        "columns": [{"name": f.name, "dtype": str(f.type)} for f in pf.schema_arrow],
        "key_value_metadata": {
            (k.decode() if isinstance(k, bytes) else k): (v.decode()[:500] if isinstance(v, bytes) else str(v)[:500])
            for k, v in (pf.schema_arrow.metadata or {}).items()
        },
    }
    lines.append(f"\n== Parquet {PARQUET_PATH.name}: rows={pf.metadata.num_rows}")
    for f in pf.schema_arrow:
        lines.append(f"   {f.name:<25} {f.type}")
    lines.append(pq.read_table(PARQUET_PATH).slice(0, 5).to_pandas().to_string())

    # CSV header for comparison
    with open(CSV_PATH) as fh:
        csv_cols = fh.readline().strip().split(",")
    inv["csv_columns"] = csv_cols
    all_db_cols = {c["name"] for t in inv["duckdb"].values() if isinstance(t, dict) and "columns" in t for c in t["columns"]}
    inv["columns_in_duckdb_not_csv"] = sorted(all_db_cols - set(csv_cols))
    inv["columns_in_parquet_not_csv"] = sorted({c["name"] for c in inv["parquet"]["columns"]} - set(csv_cols))
    lines.append(f"\nColumns in DuckDB but not CSV: {inv['columns_in_duckdb_not_csv']}")
    lines.append(f"Columns in Parquet but not CSV: {inv['columns_in_parquet_not_csv']}")

    (METRIC_DIR / "duckdb_inventory.json").write_text(json.dumps(inv, indent=2, default=str))
    (METRIC_DIR / "duckdb_inventory.txt").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
