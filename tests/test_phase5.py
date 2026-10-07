"""Automated Validation Tests for Phase 5: Microscopic SUMO Simulation Integration.

Tests:
  Test A: Network & Artifact Integrity (net.xml, rou.xml, sumocfg generated and valid)
  Test B: Route Mapping & Vehicle Definition Sanity (vType, routes, and vehicles defined)
  Test C: Simulation Execution & Result Verification (arrival times, durations, distances)
"""
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import INTERIM_DIR, PROJECT_ROOT

PHASE5_DIR = PROJECT_ROOT / "outputs" / "phase5"
NET_FILE = PHASE5_DIR / "bhubaneswar.net.xml"
ROU_FILE = PHASE5_DIR / "benchmark.rou.xml"
CFG_FILE = PHASE5_DIR / "simulation.sumocfg"
RES_FILE = PHASE5_DIR / "sumo_results.json"


def test_a_artifact_integrity():
    """Test A: Verify all required SUMO configuration and network files exist and are well-formed."""
    print("\n" + "=" * 60)
    print("RUNNING TEST A: Artifact & XML Integrity")
    print("=" * 60)

    assert NET_FILE.exists(), f"Missing network file: {NET_FILE}"
    assert NET_FILE.stat().st_size > 1_000_000, f"Network file too small: {NET_FILE.stat().st_size} bytes"
    print(f"[PASS] Network file exists ({NET_FILE.stat().st_size / (1024*1024):.2f} MB)")

    assert ROU_FILE.exists(), f"Missing route file: {ROU_FILE}"
    assert ROU_FILE.stat().st_size > 500, f"Route file too small: {ROU_FILE.stat().st_size} bytes"
    print(f"[PASS] Route file exists ({ROU_FILE.stat().st_size} bytes)")

    assert CFG_FILE.exists(), f"Missing config file: {CFG_FILE}"
    cfg_tree = ET.parse(CFG_FILE)
    cfg_root = cfg_tree.getroot()
    assert cfg_root.tag == "configuration", f"Config root must be 'configuration', got: {cfg_root.tag}"
    print(f"[PASS] SUMO config XML is valid")


def test_b_route_definitions():
    """Test B: Verify route file defines car vType, valid vehicle routes, and depart times."""
    print("\n" + "=" * 60)
    print("RUNNING TEST B: Route & Vehicle Definitions")
    print("=" * 60)

    tree = ET.parse(ROU_FILE)
    root = tree.getroot()

    vtypes = {}
    routes = {}
    vehicles = {}

    for elem in root:
        tag = elem.tag.split("}")[-1]
        if tag == "vType":
            vtypes[elem.get("id")] = elem.attrib
        elif tag == "route":
            routes[elem.get("id")] = elem.get("edges").split()
        elif tag == "vehicle":
            vehicles[elem.get("id")] = elem.attrib

    assert "car" in vtypes, "vType 'car' must be defined in routes"
    print(f"[PASS] Vehicle type 'car' defined: maxSpeed={vtypes['car'].get('maxSpeed')}m/s, accel={vtypes['car'].get('accel')}m/s²")

    expected_vehicles = ["veh_static", "veh_predictive", "veh_dynamic"]
    for vid in expected_vehicles:
        assert vid in vehicles, f"Vehicle '{vid}' not defined in route file"
        v_attr = vehicles[vid]
        assert float(v_attr.get("depart", -1)) == 0.0, f"Vehicle '{vid}' depart time must be 0"
        route_id = v_attr.get("route")
        assert route_id in routes, f"Route '{route_id}' for vehicle '{vid}' not found"
        assert len(routes[route_id]) > 0, f"Route '{route_id}' has no edges"
        print(f"[PASS] Vehicle '{vid}' bound to route '{route_id}' with {len(routes[route_id])} edges")


def test_c_simulation_results():
    """Test C: Verify simulation execution results record arrival times and positive travel durations."""
    print("\n" + "=" * 60)
    print("RUNNING TEST C: Simulation Execution & Results")
    print("=" * 60)

    assert RES_FILE.exists(), f"Missing results JSON: {RES_FILE}"
    with open(RES_FILE, "r", encoding="utf-8") as f:
        results = json.load(f)

    expected_vehicles = ["veh_static", "veh_predictive", "veh_dynamic"]
    for vid in expected_vehicles:
        assert vid in results, f"Result for '{vid}' missing from simulation output"
        r = results[vid]
        assert r["depart_time"] == 0.0, f"'{vid}' depart_time must be 0"
        assert r["arrival_time"] > 0.0, f"'{vid}' arrival_time must be > 0"
        assert r["travel_duration_seconds"] > 0.0, f"'{vid}' travel duration must be > 0"
        assert r["total_distance_km"] > 0.0, f"'{vid}' distance must be > 0"
        print(f"[PASS] '{vid}': Duration = {r['travel_duration_minutes']} min, Distance = {r['total_distance_km']} km")


def main():
    print("=" * 60)
    print("STARTING PHASE 5 VALIDATION SUITE")
    print("=" * 60)

    test_a_artifact_integrity()
    test_b_route_definitions()
    test_c_simulation_results()

    print("\n" + "=" * 60)
    print("ALL PHASE 5 TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    main()
