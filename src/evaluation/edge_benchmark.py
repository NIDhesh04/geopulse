"""Edge-Benchmarking: Evaluating Hybrid Edge-ML vs. Predictive & Static Strategies.

Runs a city-wide comparative benchmark across 20 long-distance OD pairs (>= 5 km)
during peak evening rush hour (January 14, 2026 18:30 IST / 13:00 UTC).

Strategies:
  1. Static Baseline: Free-flow speeds only (blind to ML and Edge).
  2. Predictive Pre-Planned: XGBoost initial plan (blind to real-time Edge).
  3. Hybrid Edge-ML: Global XGBoost plan + Node-by-node Edge API pings + Dynamic Replanning.

Outputs:
  outputs/phase4/edge_benchmark_results.csv
"""
import sys
from pathlib import Path
import networkx as nx
import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.config import INTERIM_DIR, PROJECT_ROOT
from src.routing.hybrid_simulator import HybridVehicleSimulation

PHASE4_OUT = PROJECT_ROOT / "outputs" / "phase4"
PHASE4_OUT.mkdir(parents=True, exist_ok=True)

MODEL_PATH = PROJECT_ROOT / "outputs" / "phase3" / "xgb_speed_model.json"
GRAPH_PATH = INTERIM_DIR / "G_embedded.graphml"
FEAT_PATH = INTERIM_DIR / "ml_features.parquet"
EDGE_SERVER_URL = "http://127.0.0.1:8000"


def main():
    print("=" * 70)
    print("GeoPulse Bhubaneswar: Hybrid Edge-ML Benchmark Evaluation (Phase 4)")
    print("=" * 70)

    # 1. Health check for Dummy Edge Server
    print(f"\nStep 1: Checking Edge Server at {EDGE_SERVER_URL}...")
    try:
        r = requests.get(f"{EDGE_SERVER_URL}/health", timeout=2.0)
        if r.status_code == 200:
            print(f"[EdgeServer ONLINE] Server status: {r.json()}")
        else:
            print(f"[EdgeServer WARNING] Non-200 status: {r.status_code}")
    except Exception as e:
        print(f"[EdgeServer ERROR] Could not connect to edge server: {e}")
        print("Please start the server with: python -m uvicorn src.routing.dummy_edge_server:app --port 8000")
        sys.exit(1)

    # 2. Reset any test overrides on edge server before benchmarking
    requests.post(f"{EDGE_SERVER_URL}/reset_overrides", timeout=2.0)

    # 3. Load simulation environment
    print("\nStep 2: Loading road network graph, XGBoost model, and features...")
    G = nx.read_graphml(GRAPH_PATH, force_multigraph=True)
    sim = HybridVehicleSimulation(
        G=G,
        model_path=MODEL_PATH,
        features_path=FEAT_PATH,
        edge_server_url=EDGE_SERVER_URL,
        delay_threshold_seconds=45.0,  # 45s unexpected delay triggers replan
        alpha=0.0,
        beta=1.0,
    )

    # Peak rush hour: Jan 14, 2026 13:00 UTC (18:30 IST)
    departure_time = pd.Timestamp("2026-01-14 13:00:00+00:00")
    print(f"Departure Time: {departure_time} ({departure_time.tz_convert('Asia/Kolkata')} IST Peak Congestion)")

    # 4. Sample 20 valid OD pairs (>= 5 km apart)
    print("\nStep 3: Sampling 20 valid city-scale OD pairs (>= 5.0 km apart)...")
    nodes = list(G.nodes)
    rng = np.random.default_rng(42)
    od_pairs = []

    while len(od_pairs) < 20:
        s, t = rng.choice(nodes, 2, replace=False)
        xs, ys = float(G.nodes[s]["x"]), float(G.nodes[s]["y"])
        xt, yt = float(G.nodes[t]["x"]), float(G.nodes[t]["y"])
        dist_m = np.hypot(xt - xs, yt - ys)
        if dist_m >= 5000.0:
            od_pairs.append((s, t, dist_m / 1000.0))

    print(f"Sampled {len(od_pairs)} OD pairs spanning across Bhubaneswar.")

    # 5. Execute 3 strategies across all OD pairs
    print("\nStep 4: Executing multi-strategy simulation across all OD pairs...")
    records = []

    for idx, (source, target, direct_dist_km) in enumerate(od_pairs, start=1):
        od_label = f"OD_{idx:02d} ({source} -> {target})"
        print(f"Evaluating [{idx:02d}/20] {od_label} (Crow-fly distance: {direct_dist_km:.2f} km)...")

        # 1. Static Baseline
        res_static = sim.run_static_baseline(source, target, departure_time)

        # 2. Predictive Pre-Planned
        res_pred = sim.run_predictive_preplanned(source, target, departure_time)

        # 3. Hybrid Edge-ML
        res_hyb = sim.run_hybrid_edge_ml(source, target, departure_time)

        if not (res_static["success"] and res_pred["success"] and res_hyb["success"]):
            print(f"  Warning: OD pair {idx} failed reachability check. Skipping.")
            continue

        records.append({
            "OD_pair": od_label,
            "Strategy": "Static Baseline",
            "Travel_Time_Seconds": res_static["total_travel_time_seconds"],
            "Travel_Time_Minutes": res_static["total_travel_time_seconds"] / 60.0,
            "Distance_km": res_static["total_distance_meters"] / 1000.0,
            "Compute_Latency_ms": res_static["compute_latency_ms"],
            "Reroute_Count": 0,
        })

        records.append({
            "OD_pair": od_label,
            "Strategy": "Predictive Pre-Planned",
            "Travel_Time_Seconds": res_pred["total_travel_time_seconds"],
            "Travel_Time_Minutes": res_pred["total_travel_time_seconds"] / 60.0,
            "Distance_km": res_pred["total_distance_meters"] / 1000.0,
            "Compute_Latency_ms": res_pred["compute_latency_ms"],
            "Reroute_Count": 0,
        })

        records.append({
            "OD_pair": od_label,
            "Strategy": "Hybrid Edge-ML",
            "Travel_Time_Seconds": res_hyb["total_travel_time_seconds"],
            "Travel_Time_Minutes": res_hyb["total_travel_time_seconds"] / 60.0,
            "Distance_km": res_hyb["total_distance_meters"] / 1000.0,
            "Compute_Latency_ms": res_hyb["compute_latency_ms"],
            "Reroute_Count": res_hyb["reroute_count"],
        })

    df_results = pd.DataFrame(records)

    # 6. Save benchmark table
    out_csv = PHASE4_OUT / "edge_benchmark_results.csv"
    df_results.to_csv(out_csv, index=False)
    print(f"\nSaved benchmark results to {out_csv} ({len(df_results)} rows).")

    # 7. Print summary table
    print("\n" + "=" * 70)
    print("HYBRID EDGE-ML BENCHMARK COMPARATIVE SUMMARY")
    print("=" * 70)

    summary = df_results.groupby("Strategy").agg({
        "Travel_Time_Minutes": ["mean", "median", "std"],
        "Distance_km": ["mean"],
        "Compute_Latency_ms": ["mean"],
        "Reroute_Count": ["mean", "sum"],
    })
    print(summary.round(3).to_string())

    # Comparison metrics
    pivot_time = df_results.pivot(index="OD_pair", columns="Strategy", values="Travel_Time_Seconds")
    pivot_lat = df_results.pivot(index="OD_pair", columns="Strategy", values="Compute_Latency_ms")

    time_static = pivot_time["Static Baseline"].mean() / 60.0
    time_pred = pivot_time["Predictive Pre-Planned"].mean() / 60.0
    time_hyb = pivot_time["Hybrid Edge-ML"].mean() / 60.0

    lat_static = pivot_lat["Static Baseline"].mean()
    lat_pred = pivot_lat["Predictive Pre-Planned"].mean()
    lat_hyb = pivot_lat["Hybrid Edge-ML"].mean()

    print("\n" + "-" * 70)
    print("KEY PERFORMANCE & LATENCY HIGHLIGHTS:")
    print(f"  * Mean Travel Time (Static Baseline):     {time_static:.2f} mins (Latency: {lat_static:.1f} ms)")
    print(f"  * Mean Travel Time (Predictive Route):    {time_pred:.2f} mins (Latency: {lat_pred:.1f} ms)")
    print(f"  * Mean Travel Time (Hybrid Edge-ML):      {time_hyb:.2f} mins (Latency: {lat_hyb:.1f} ms)")
    print(f"  * Edge Communication Overhead:            +{lat_hyb - lat_pred:.1f} ms across entire trip")
    print("-" * 70)


if __name__ == "__main__":
    main()
