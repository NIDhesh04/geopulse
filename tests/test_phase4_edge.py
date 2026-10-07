"""Automated Validation Tests for Phase 4: Hybrid Edge Computing & ML Routing.

Tests:
  Test A: Edge Server Connectivity & API Contract (Port 8000 responds with valid speed)
  Test B: Hybrid Logic Trigger (Severe 5 km/h jam forces Edge API intercept & Dijkstra replan)
  Test C: Hysteresis Guard (Minor 5s delay ignored; route remains stable without chattering)
"""
import sys
from pathlib import Path
import networkx as nx
import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import INTERIM_DIR, PROJECT_ROOT
from src.routing.custom_dijkstra import custom_dijkstra
from src.routing.hybrid_simulator import HybridVehicleSimulation

MODEL_PATH = PROJECT_ROOT / "outputs" / "phase3" / "xgb_speed_model.json"
GRAPH_PATH = INTERIM_DIR / "G_embedded.graphml"
FEAT_PATH = INTERIM_DIR / "ml_features.parquet"
EDGE_SERVER_URL = "http://127.0.0.1:8000"


def setup_simulation(delay_threshold=45.0):
    G = nx.read_graphml(GRAPH_PATH, force_multigraph=True)
    sim = HybridVehicleSimulation(
        G=G,
        model_path=MODEL_PATH,
        features_path=FEAT_PATH,
        edge_server_url=EDGE_SERVER_URL,
        delay_threshold_seconds=delay_threshold,
        alpha=0.0,
        beta=1.0,
    )
    return sim, G


def test_a_server_connectivity():
    """Test A: Assert Dummy Edge Server is online on port 8000 and returns valid float speeds."""
    print("\n" + "=" * 65)
    print("RUNNING TEST A: Edge Server Connectivity & API Verification")
    print("=" * 65)

    # 1. Health check
    try:
        r = requests.get(f"{EDGE_SERVER_URL}/health", timeout=3.0)
        assert r.status_code == 200, f"Expected HTTP 200, got {r.status_code}"
        health_data = r.json()
        assert health_data.get("status") == "ok", f"Health status not ok: {health_data}"
        print(f"[PASS] Edge Server is reachable on port 8000: {health_data}")
    except requests.exceptions.ConnectionError:
        raise AssertionError(
            "Dummy Edge Server is not running on http://127.0.0.1:8000! "
            "Start it with: python -m uvicorn src.routing.dummy_edge_server:app --port 8000"
        )

    # 2. Query /get_speed for segment_id=10
    sample_time = "2026-01-14T13:00:00Z"
    resp = requests.get(
        f"{EDGE_SERVER_URL}/get_speed",
        params={"segment_id": 10, "current_simulated_time": sample_time},
        timeout=3.0,
    )
    assert resp.status_code == 200, f"Expected HTTP 200, got {resp.status_code}"
    data = resp.json()
    assert "speed" in data, f"Key 'speed' missing from response: {data}"
    speed = float(data["speed"])
    assert speed > 0.0, f"Speed must be positive float, got {speed}"
    assert data["segment_id"] == 10, f"Segment ID mismatch: {data['segment_id']}"
    print(f"[PASS] API returned valid speed: {speed} km/h for segment 10 (source: {data['source']})")


def test_b_hybrid_logic_trigger(sim, source, target, dep_time):
    """Test B: Force Edge Server to report 5 km/h jam; assert vehicle intercepts and replans."""
    print("\n" + "=" * 65)
    print("RUNNING TEST B: Hybrid Edge-ML Dynamic Replan Trigger")
    print("=" * 65)

    # Reset any previous test overrides
    requests.post(f"{EDGE_SERVER_URL}/reset_overrides", timeout=2.0)

    # 1. Obtain baseline pre-planned route (without edge congestion)
    baseline_res = sim.run_predictive_preplanned(source, target, dep_time)
    assert baseline_res["success"], "Baseline path planning failed"
    baseline_path = baseline_res["path"]

    # 2. Identify a monitored segment along the baseline route that has an alternative bypass path
    jammed_sid = None
    jam_u, jam_v = None, None
    preds_base = sim.get_predictions_for_hour(dep_time)

    for i in range(len(baseline_path) - 1):
        u, v = baseline_path[i], baseline_path[i + 1]
        edata = sim._get_edge_data(u, v)
        is_mon = edata.get("is_monitored") is True or str(edata.get("is_monitored")).lower() == "true"
        sid = edata.get("segment_id")
        if is_mon and sid is not None and sid != -1 and sid != "-1":
            sid_int = int(sid)
            # Test if a 5 km/h jam forces divergence from this point
            test_preds = dict(preds_base)
            test_preds[sid_int] = 5.0
            test_path, _ = custom_dijkstra(sim.G, u, target, alpha=sim.alpha, beta=sim.beta, edge_speeds_dict=test_preds)
            if test_path != baseline_path[i:]:
                jammed_sid = sid_int
                jam_u, jam_v = u, v
                break

    assert jammed_sid is not None, "No divertable monitored segment found along baseline path!"
    print(f"Target monitored segment for edge jam: ID={jammed_sid} on edge ({jam_u} -> {jam_v})")

    # 3. Force the Edge Server to report 5.0 km/h for this segment
    ov_resp = requests.post(
        f"{EDGE_SERVER_URL}/set_override",
        json={"segment_id": jammed_sid, "speed": 5.0},
        timeout=2.0,
    )
    assert ov_resp.status_code == 200
    print(f"Injected roadside edge override: segment {jammed_sid} speed = 5.0 km/h (severe jam).")

    # 4. Execute Hybrid Edge-ML simulation
    hybrid_res = sim.run_hybrid_edge_ml(source, target, dep_time)
    assert hybrid_res["success"], f"Hybrid simulation failed: {hybrid_res.get('error')}"

    print(f"Baseline Path ({len(baseline_path)} nodes): {baseline_path}")
    print(f"Hybrid Path   ({len(hybrid_res['path'])} nodes): {hybrid_res['path']}")
    print(f"Reroute Count: {hybrid_res['reroute_count']}")

    # 5. Assertions: Route must divert around jammed segment and increment reroute count
    assert hybrid_res["reroute_count"] >= 1, (
        f"Hybrid replan failed to trigger! reroute_count={hybrid_res['reroute_count']}"
    )
    assert hybrid_res["path"] != baseline_path, "Hybrid path did not alter despite 5 km/h jam!"

    # Verify that the jammed edge was bypassed
    bypassed = True
    for i in range(len(hybrid_res["path"]) - 1):
        if hybrid_res["path"][i] == jam_u and hybrid_res["path"][i + 1] == jam_v:
            bypassed = False
            break

    assert bypassed, f"Vehicle failed to avoid jammed edge ({jam_u} -> {jam_v})!"
    print(f"[PASS] Hybrid architecture successfully detected roadside jam via API and bypassed it!")
    print(f"[PASS] Reroute count correctly incremented: {hybrid_res['reroute_count']}.")

    # Clean up override
    requests.post(f"{EDGE_SERVER_URL}/reset_overrides", timeout=2.0)


def test_c_hysteresis_guard(sim, source, target, dep_time):
    """Test C: Force a slight 5-second delay; assert simulation ignores it to prevent chattering."""
    print("\n" + "=" * 65)
    print("RUNNING TEST C: Hysteresis Guard Against Route Chattering")
    print("=" * 65)

    # Reset overrides
    requests.post(f"{EDGE_SERVER_URL}/reset_overrides", timeout=2.0)

    # 1. Baseline predictive plan
    baseline_res = sim.run_predictive_preplanned(source, target, dep_time)
    baseline_path = baseline_res["path"]

    # 2. Find monitored segment
    mon_sid = None
    mon_u, mon_v = None, None
    for i in range(len(baseline_path) - 1):
        u, v = baseline_path[i], baseline_path[i + 1]
        edata = sim._get_edge_data(u, v)
        is_mon = edata.get("is_monitored") is True or str(edata.get("is_monitored")).lower() == "true"
        sid = edata.get("segment_id")
        if is_mon and sid is not None and sid != -1 and sid != "-1":
            mon_sid = int(sid)
            mon_u, mon_v = u, v
            edge_len = float(edata.get("length", 100.0))
            break

    assert mon_sid is not None, "No monitored segment found along baseline path!"

    # 3. Calculate speed that causes only a tiny 5-second delay (well under the 45s threshold)
    pred_speeds = sim.get_predictions_for_hour(dep_time)
    pred_sp = pred_speeds.get(mon_sid, 40.0)
    pred_time = edge_len / (pred_sp / 3.6)
    target_time = pred_time + 5.0  # +5 seconds delay
    slight_delay_speed = (edge_len / target_time) * 3.6

    print(f"Segment {mon_sid} length={edge_len:.1f}m: Predicted Speed={pred_sp:.1f} km/h ({pred_time:.1f}s)")
    print(f"Setting Edge Server speed={slight_delay_speed:.1f} km/h (+5.0s delay, threshold=45.0s)...")

    # Override with slight delay speed
    requests.post(
        f"{EDGE_SERVER_URL}/set_override",
        json={"segment_id": mon_sid, "speed": max(slight_delay_speed, 1.0)},
        timeout=2.0,
    )

    # 4. Run Hybrid simulation
    res_sub = sim.run_hybrid_edge_ml(source, target, dep_time)

    # 5. Assert: Reroute count must be 0 and path must remain identical
    assert res_sub["reroute_count"] == 0, (
        f"Hysteresis failed! Expected 0 reroutes for 5s delay, got {res_sub['reroute_count']}"
    )
    assert res_sub["path"] == baseline_path, "Path changed despite sub-threshold delay!"
    print(f"[PASS] Minor delay (+5s) correctly ignored by hysteresis guard (reroute_count=0).")
    print(f"[PASS] Route maintained original trajectory without chatter.")

    # Clean up
    requests.post(f"{EDGE_SERVER_URL}/reset_overrides", timeout=2.0)


def main():
    print("=" * 65)
    print("STARTING PHASE 4 HYBRID EDGE-ML AUTOMATED VALIDATION SUITE")
    print("=" * 65)

    test_a_server_connectivity()

    sim, G = setup_simulation(delay_threshold=45.0)

    # Select representative OD pair spanning ~6 km across Bhubaneswar
    source = "8065163006"
    target = "4714739238"
    dep_time = pd.Timestamp("2026-01-14 13:00:00+00:00")

    test_b_hybrid_logic_trigger(sim, source, target, dep_time)
    test_c_hysteresis_guard(sim, source, target, dep_time)

    print("\n" + "=" * 65)
    print("ALL PHASE 4 HYBRID EDGE-ML TESTS PASSED SUCCESSFULLY! (3/3)")
    print("=" * 65)


if __name__ == "__main__":
    main()
