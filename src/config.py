"""Central paths for Phase 1. Raw data is read-only; never written to."""
from pathlib import Path
import os

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Raw data location (override with env var GEOPULSE_DATA_DIR)
DATA_DIR = Path(os.environ.get("GEOPULSE_DATA_DIR", r"C:\Users\nidhe\Downloads\archive (1)"))
CSV_PATH = DATA_DIR / "traffic_bhubaneswar.csv"
PARQUET_PATH = DATA_DIR / "traffic_structured_v1.parquet"
DUCKDB_PATH = DATA_DIR / "traffic_v1.duckdb"

OUT_DIR = PROJECT_ROOT / "outputs" / "phase1"
FIG_DIR = OUT_DIR / "figures"
REPORT_DIR = OUT_DIR / "reports"
METRIC_DIR = OUT_DIR / "metrics"
INTERIM_DIR = PROJECT_ROOT / "data" / "interim"

for d in (FIG_DIR, REPORT_DIR, METRIC_DIR, INTERIM_DIR):
    d.mkdir(parents=True, exist_ok=True)
