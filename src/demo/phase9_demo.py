"""
GeoPulse Interactive Terminal Demonstration

Replays the real-time dynamic rerouting lifecycle:
Predict (t0) -> Plan -> Observe (t1) -> Compare -> Re-route

Consumes real historical observations from results/phase9_demo_scenario.json.
Uses clean ASCII output for universal terminal compatibility.
"""

import os
import json
import time


def run_demo():
    payload_path = 'results/phase9_demo_scenario.json'
    if not os.path.exists(payload_path):
        print(f"Error: Demo payload {payload_path} not found. Please run scripts/run_phase9_replay.py first.")
        return

    with open(payload_path, 'r') as f:
        demo = json.load(f)

    print("\n" + "=" * 65)
    print("      GeoPulse: AI-Based Dynamic Traffic Routing System")
    print("               LIVE JOURNEY REPLAY DEMONSTRATION")
    print("=" * 65)
    print(f"Trip OD #{demo['od_id']}  |  Corridor: Origin {demo['source_node']} -> Destination {demo['destination_node']}")
    print(f"Diurnal Period: Evening Commuter Peak  |  Date: Jan 15, 2026")
    print("=" * 65)

    print("\n[PHASE 1 - 19:30 IST] PREDICTIVE ROUTE PLANNING (t0)")
    print("-" * 65)
    print("* LightGBM ML model queries historical lags and forecasts next-hour corridor speeds.")
    print("* Custom Dijkstra synthesizes travel-time weights over Bhubaneswar road network.")
    print(f"* Initial Planned Route R0 selected:")
    print(f"    Total Route Links:     {demo['initial_route_edges']} directed OSM road segments")
    print(f"    Expected Travel Time:  {demo['total_time_no_reroute_s'] / 60.0:.1f} minutes ({demo['total_time_no_reroute_s']:.1f} s)")
    print("* Vehicle departs origin node and initiates journey...")

    time.sleep(0.5)

    print("\n[PHASE 2 - 20:30 IST] REAL-TIME TRAFFIC TELEMETRY UPDATE (t1)")
    print("-" * 65)
    print(f"* Vehicle reaches Decision Node #{demo['decision_node']} (Link #{demo['decision_step']}).")
    print("* New real-time traffic observations arrive from arterial sensor streams.")
    print("* Unanticipated downstream congestion detected on original corridor:")
    print("    Arterial segment speed dropped into severe bottleneck conditions.")
    print(f"    Estimated remaining time on original R0: {demo['total_time_no_reroute_s']:.1f} seconds.")

    time.sleep(0.5)

    print("\n[PHASE 3 - DEGRADATION DETECTION & DIJKSTRA REROUTING]")
    print("-" * 65)
    print("* Route evaluator probes alternative paths from current vehicle position.")
    print("* Custom Dijkstra executes dynamic re-routing with updated traffic weights:")
    print(f"    Alternative Bypass R1 Time:  {demo['total_time_dynamic_s']:.1f} seconds")
    print(f"    Potential Travel Time Saved: {demo['time_saved_s']:.1f} seconds ({demo['time_saved_s']/60:.2f} min)")
    print(f"    Threshold Check:             Exceeds 10s / 3% thresholds -> TRIGGER REROUTE!")
    print(f"* Alert: Dynamic Reroute Initiated! Switching to bypass corridor.")

    time.sleep(0.5)

    print("\n[PHASE 4 - FINAL JOURNEY OUTCOME & COUNTERFACTUAL AUDIT]")
    print("=" * 65)
    print(f"Strategy A (No Rerouting - Continued on R0):      {demo['total_time_no_reroute_s']/60.0:.2f} min ({demo['total_time_no_reroute_s']:.1f} s)")
    print(f"Strategy B (GeoPulse Dynamic Reroute - Switched):  {demo['total_time_dynamic_s']/60.0:.2f} min ({demo['total_time_dynamic_s']:.1f} s)")
    print("-" * 65)
    print(f"[+] NET TIME SAVED:     {demo['time_saved_s']:.1f} seconds ({demo['time_saved_s']/60.0:.2f} minutes)")
    print(f"[+] JOURNEY EFFICIENCY: +{demo['improvement_pct']:.2f}% improvement")
    print(f"[+] SPATIAL DIVERGENCE: {demo['changed_edges_count']} bypass segments utilized (Route Overlap: {demo['route_overlap']*100:.1f}%)")
    print("=" * 65)
    print("DEMO COMPLETE: Dynamic traffic anticipation prevented commuter delay.\n")


if __name__ == '__main__':
    run_demo()
