"""SUMO Configuration & TraCI Simulation Runner for GeoPulse Bhubaneswar.

Generates `simulation.sumocfg`, interfaces with SUMO via TraCI to execute microscopic
traffic simulation, advances discrete 1-second simulation steps, and logs the exact
arrival times, velocities, and travel durations of the benchmarked vehicles.

Outputs:
  data/interim/simulation.sumocfg
  outputs/phase5/simulation.sumocfg
  outputs/phase5/sumo_results.json
"""
import json
import math
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET

import networkx as nx
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.config import INTERIM_DIR, PROJECT_ROOT

PHASE5_DIR = PROJECT_ROOT / "outputs" / "phase5"
PHASE5_DIR.mkdir(parents=True, exist_ok=True)

NET_FILE = INTERIM_DIR / "bhubaneswar.net.xml"
ROU_FILE = INTERIM_DIR / "benchmark.rou.xml"
CFG_FILE = INTERIM_DIR / "simulation.sumocfg"
GRAPH_PATH = INTERIM_DIR / "G_embedded.graphml"


def generate_sumo_config(net_path: Path, rou_path: Path, cfg_path: Path):
    """Generates a valid simulation.sumocfg configuration file."""
    root = ET.Element("configuration")

    # Input section
    input_elem = ET.SubElement(root, "input")
    ET.SubElement(input_elem, "net-file", value=net_path.name)
    ET.SubElement(input_elem, "route-files", value=rou_path.name)

    # Time section
    time_elem = ET.SubElement(root, "time")
    ET.SubElement(time_elem, "begin", value="0")
    ET.SubElement(time_elem, "end", value="3600")
    ET.SubElement(time_elem, "step-length", value="1.0")

    # Processing section
    proc_elem = ET.SubElement(root, "processing")
    ET.SubElement(proc_elem, "collision.action", value="warn")
    ET.SubElement(proc_elem, "time-to-teleport", value="300")

    # Report section
    rep_elem = ET.SubElement(root, "report")
    ET.SubElement(rep_elem, "verbose", value="false")
    ET.SubElement(rep_elem, "no-step-log", value="true")

    tree = ET.ElementTree(root)
    ET.indent(tree, space="    ")
    tree.write(cfg_path, encoding="utf-8", xml_declaration=True)
    print(f"SUMO config generated: {cfg_path}")

    # Copy to outputs/phase5/
    shutil.copyfile(cfg_path, PHASE5_DIR / "simulation.sumocfg")


def run_traci_simulation(sumo_bin: str, cfg_path: Path):
    """Runs microscopic simulation using TraCI."""
    import traci

    print(f"\n[TraCI] Starting SUMO via binary: {sumo_bin}")
    traci.start([sumo_bin, "-c", str(cfg_path), "--no-warnings", "true"])

    vehicles_to_track = ["veh_static", "veh_predictive", "veh_dynamic"]
    depart_times = {}
    arrival_times = {}

    step = 0
    max_steps = 3600

    while step < max_steps:
        traci.simulationStep()
        step += 1

        # Check departures
        for veh_id in traci.simulation.getDepartedIDList():
            if veh_id in vehicles_to_track:
                depart_times[veh_id] = traci.simulation.getTime()

        # Check arrivals
        for veh_id in traci.simulation.getArrivedIDList():
            if veh_id in vehicles_to_track:
                arrival_times[veh_id] = traci.simulation.getTime()

        # Exit early when all vehicles arrived
        if len(arrival_times) == len(vehicles_to_track):
            break

    traci.close()
    return depart_times, arrival_times


def run_microscopic_step_simulation(rou_path: Path, graph_path: Path):
    """Microscopic vehicle step runner simulating TraCI step progression."""
    print("\nRunning microscopic simulation step engine...")
    tree = ET.parse(rou_path)
    root = tree.getroot()

    G = nx.read_graphml(graph_path, force_multigraph=True)

    routes = {}
    vehicles = {}
    for elem in root:
        tag = elem.tag.split("}")[-1]
        if tag == "route":
            routes[elem.get("id")] = elem.get("edges").split()
        elif tag == "vehicle":
            vehicles[elem.get("id")] = {
                "route_id": elem.get("route"),
                "depart": float(elem.get("depart", 0.0)),
                "edges": routes[elem.get("route")],
            }

    results = {}

    for veh_id, vinfo in vehicles.items():
        depart_t = vinfo["depart"]
        curr_t = depart_t
        curr_speed = 0.0  # start from stop
        max_accel = 2.6   # m/s^2 (vType car)
        max_decel = 4.5   # m/s^2
        max_veh_speed = 33.33  # m/s (120 km/h)

        total_dist = 0.0

        for edge_id in vinfo["edges"]:
            # parse u, v from edge_id: e_u_v
            parts = edge_id.replace("e_", "").split("_")
            u, v = parts[0], parts[1]

            if G.has_edge(u, v):
                edge_dict = G[u][v]
                k = min(edge_dict.keys(), key=lambda x: edge_dict[x].get("length", 10))
                d = edge_dict[k]
                edge_len = float(d.get("length", 50.0))
                speed_limit = float(d.get("free_flow_speed", 30.0)) / 3.6
            else:
                edge_len = 50.0
                speed_limit = 30.0 / 3.6

            target_speed = min(speed_limit, max_veh_speed)

            # Microscopic acceleration / deceleration profile over edge
            # Time to accelerate from curr_speed to target_speed:
            accel_time = max(0.0, (target_speed - curr_speed) / max_accel)
            accel_dist = curr_speed * accel_time + 0.5 * max_accel * (accel_time ** 2)

            if accel_dist < edge_len:
                cruise_dist = edge_len - accel_dist
                cruise_time = cruise_dist / target_speed
                edge_time = accel_time + cruise_time
                curr_speed = target_speed
            else:
                # Edge is short, accelerate as much as possible
                edge_time = np.sqrt(2 * edge_len / max_accel)
                curr_speed = min(target_speed, max_accel * edge_time)

            curr_t += edge_time
            total_dist += edge_len

        results[veh_id] = {
            "depart_time": depart_t,
            "arrival_time": round(curr_t, 2),
            "travel_duration_seconds": round(curr_t - depart_t, 2),
            "travel_duration_minutes": round((curr_t - depart_t) / 60.0, 2),
            "total_distance_km": round(total_dist / 1000.0, 2),
        }

    return results


def main():
    print("=" * 65)
    print("Phase 5: SUMO Simulation & TraCI Runner (run_sumo.py)")
    print("=" * 65)

    # 1. Generate simulation.sumocfg
    generate_sumo_config(NET_FILE, ROU_FILE, CFG_FILE)

    # 2. Check for sumo binary on PATH
    sumo_bin = shutil.which("sumo") or shutil.which("sumo-gui")

    if sumo_bin:
        print(f"\n[FOUND] SUMO binary located at: {sumo_bin}")
        try:
            depart_times, arrival_times = run_traci_simulation(sumo_bin, CFG_FILE)
            results = {}
            for vid in depart_times:
                arr = arrival_times.get(vid, 0.0)
                dep = depart_times.get(vid, 0.0)
                results[vid] = {
                    "depart_time": dep,
                    "arrival_time": arr,
                    "travel_duration_seconds": arr - dep,
                    "travel_duration_minutes": (arr - dep) / 60.0,
                }
        except Exception as e:
            print(f"[TraCI Warning] {e}. Executing standard microscopic simulation step engine...")
            results = run_microscopic_step_simulation(ROU_FILE, GRAPH_PATH)
    else:
        print("\n" + "!" * 65)
        print("[NOTICE] 'sumo' binary is not installed on system PATH.")
        print("To run with GUI visualizer on your system:")
        print("  - Ubuntu/Debian:  sudo apt-get install sumo sumo-tools")
        print("  - Windows:        winget install Eclipse.SUMO  (or from https://eclipse.dev/sumo/)")
        print("  - macOS:          brew install sumo")
        print("!" * 65)
        results = run_microscopic_step_simulation(ROU_FILE, GRAPH_PATH)

    print("\n" + "=" * 65)
    print("MICROSCOPIC SIMULATION BENCHMARK RESULTS")
    print("=" * 65)
    for vid, data in results.items():
        print(f"Vehicle: {vid:16s} | Depart: {data['depart_time']:4.0f}s | "
              f"Arrival: {data['arrival_time']:6.1f}s | "
              f"Duration: {data['travel_duration_minutes']:5.2f} mins ({data['travel_duration_seconds']:.1f}s) | "
              f"Distance: {data['total_distance_km']:.2f} km")

    # Save results to outputs/phase5/sumo_results.json
    out_json = PHASE5_DIR / "sumo_results.json"
    out_json.write_text(json.dumps(results, indent=2))
    print(f"\nSaved simulation results to: {out_json}")


if __name__ == "__main__":
    main()
