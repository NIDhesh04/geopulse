"""Dummy Roadside Edge Server for GeoPulse Bhubaneswar.

Simulates a local roadside Edge Computing unit providing real-time traffic speeds
for individual road segments with hardware latency simulation.

To run this server in the background:
    .\\.venv\\Scripts\\python.exe -m uvicorn src.routing.dummy_edge_server:app --host 127.0.0.1 --port 8000
Or on Linux/macOS:
    uvicorn src.routing.dummy_edge_server:app --host 127.0.0.1 --port 8000 &
"""
import asyncio
from pathlib import Path
import sys
from typing import Dict, Optional

from fastapi import FastAPI, Query
import pandas as pd
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.config import INTERIM_DIR, PROJECT_ROOT

app = FastAPI(title="GeoPulse Bhubaneswar Roadside Edge Server")

# In-memory database of actual ground-truth speeds: (hour_timestamp, segment_id) -> speed
ACTUAL_SPEEDS: Dict[tuple, float] = {}
# Dynamic test overrides: segment_id -> overridden_speed
OVERRIDES: Dict[int, float] = {}


def load_ground_truth_data():
    """Loads feature parquet into in-memory dictionary for fast O(1) edge retrieval."""
    global ACTUAL_SPEEDS
    feat_path = INTERIM_DIR / "ml_features.parquet"
    if not feat_path.exists():
        print(f"[EdgeServer Warning] {feat_path} not found. Running with empty database.")
        return

    print("[EdgeServer] Loading ground truth traffic observations into memory...")
    df = pd.read_parquet(feat_path)
    df["hour"] = pd.to_datetime(df["hour"], utc=True)
    
    for row in df[["hour", "segment_id", "currentSpeed"]].itertuples(index=False):
        ACTUAL_SPEEDS[(row.hour, int(row.segment_id))] = float(row.currentSpeed)
    print(f"[EdgeServer] Loaded {len(ACTUAL_SPEEDS):,} ground truth edge observations.")


@app.on_event("startup")
def startup_event():
    load_ground_truth_data()


@app.get("/health")
def health():
    return {"status": "ok", "loaded_records": len(ACTUAL_SPEEDS), "active_overrides": len(OVERRIDES)}


@app.get("/get_speed")
async def get_speed(
    segment_id: int = Query(..., description="The TomTom / OSM segment ID"),
    current_simulated_time: str = Query(..., description="Current vehicle simulated timestamp (ISO format)"),
):
    """Returns actual real-time ground-truth speed for the requested segment at simulated time.
    
    Injects 20ms (0.02s) artificial hardware/network latency to simulate roadside edge communication.
    """
    # 1. Hardware network communication delay simulation
    await asyncio.sleep(0.02)

    # 2. Check for manual test overrides (e.g. Test B simulated severe jam)
    if segment_id in OVERRIDES:
        return {
            "segment_id": segment_id,
            "speed": float(OVERRIDES[segment_id]),
            "source": "override",
            "simulated_time": current_simulated_time,
        }

    # 3. Parse timestamp to hour bucket
    try:
        ts = pd.to_datetime(current_simulated_time, utc=True)
        hour_bucket = ts.floor("h")
    except Exception:
        hour_bucket = None

    # 4. Lookup ground truth speed
    key = (hour_bucket, segment_id)
    if key in ACTUAL_SPEEDS:
        speed = ACTUAL_SPEEDS[key]
        src = "ground_truth"
    else:
        # Fallback speed if timestamp outside monitored range
        speed = 35.0
        src = "default_fallback"

    return {
        "segment_id": segment_id,
        "speed": float(speed),
        "source": src,
        "simulated_time": current_simulated_time,
    }


class OverrideRequest(BaseModel):
    segment_id: int
    speed: float


@app.post("/set_override")
def set_override(req: OverrideRequest):
    """Forces the edge server to return a specific speed for a segment (used for dynamic tests)."""
    OVERRIDES[req.segment_id] = float(req.speed)
    return {"status": "success", "overrides": OVERRIDES}


@app.post("/reset_overrides")
def reset_overrides():
    """Clears all dynamic speed overrides."""
    OVERRIDES.clear()
    return {"status": "success", "message": "Overrides reset"}
