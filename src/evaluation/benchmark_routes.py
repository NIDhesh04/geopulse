"""City-Wide Benchmark Evaluation of Route Planning Strategies.

Compares three routing strategies across 20 city-scale OD pairs (>= 5 km)
during peak evening congestion (January 14, 2026):
  1. Static Baseline (fixed pre-planned free-flow route)
  2. Predictive Pre-Planned (fixed ML forecast route at departure)
  3. Dynamic Edge-Rerouting (live re-evaluation with hysteresis)

Outputs:
  outputs/phase4/benchmark_results.csv
"""
import sys
from pathlib import Path
import networkx as nx
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.config import INTERIM_DIR, PROJECT_ROOT
from src.routing.dynamic_simulator import VehicleSimulation

PHASE4_OUT = PROJECT_ROOT / "outputs" / "phase4"
PHASE4_OUT.mkdir(parents=True, exist_ok=True)

MODEL_PATH = PROJECT_ROOT / "outputs" / "phase3" / "xgb_speed_model.json"
GRAPH_PATH = INTERIM_DIR / "G_embedded.graphml"
FEAT_PATH = INTERIM_DIR / "ml_features.parquet"


def main():
    print("=" * 65)
    print("GeoPulse Bhubaneswar: City-Scale Routing Benchmarking (Phase 4)")
    print("=" * 65)

    print("\nStep 1: Loading road graph, ML model, and feature dataset...")
    G = nx.read_graphml(GRAPH_PATH, force_multigraph=True)
    sim = VehicleSimulation(
        G=G,
        model_path=MODEL_PATH,
        features_path=FEAT_PATH,
        epsilon=45.0,  # 45-second savings hysteresis threshold
        alpha=0.0,     # pure travel-time minimization
        beta=1.0,
    )

    # Congested peak hour: Jan 14, 2026 13:00 UTC (18:30 IST Evening Rush Hour)
    departure_time = pd.Timestamp("2026-01-14 13:00:00+00:00")
    print(f"\nDeparture Time: {departure_time} ({departure_time.tz_convert('Asia/Kolkata')} IST Peak Hour)")

    print("\nStep 2: Sampling 20 valid city-scale OD pairs (>= 5.0 km apart)...")
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

    print("\nStep 3: Executing multi-strategy simulation across all OD pairs...")
    records = []

    for idx, (source, target, direct_dist_km) in enumerate(od_pairs, start=1):
        od_label = f"OD_{idx:02d} ({source} -> {target})"
        print(f"Running [{idx:02d}/20] {od_label} (Crow-fly distance: {direct_dist_km:.2f} km)...")

        # 1. Static Baseline
        res_static = sim.run_static_baseline(source, target, departure_time)

        # 2. Predictive Pre-Planned
        res_pred = sim.run_predictive_preplanned(source, target, departure_time)

        # 3. Dynamic Edge-Rerouting
        res_dyn = sim.run_dynamic_edge_rerouting(source, target, departure_time)

        if not (res_static["success"] and res_pred["success"] and res_dyn["success"]):
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
            "Strategy": "Dynamic Edge-Rerouting",
            "Travel_Time_Seconds": res_dyn["total_travel_time_seconds"],
            "Travel_Time_Minutes": res_dyn["total_travel_time_seconds"] / 60.0,
            "Distance_km": res_dyn["total_distance_meters"] / 1000.0,
            "Compute_Latency_ms": res_dyn["compute_latency_ms"],
            "Reroute_Count": res_dyn["reroute_count"],
        })

    df_results = pd.DataFrame(records)

    # Save benchmark table
    out_csv = PHASE4_OUT / "benchmark_results.csv"
    df_results.to_csv(out_csv, index=False)
    print(f"\nSaved benchmark results to {out_csv} ({len(df_results)} rows).")

    print("\n" + "=" * 65)
    print("BENCHMARK COMPARATIVE SUMMARY TABLE")
    print("=" * 65)

    summary = df_results.groupby("Strategy").agg({
        "Travel_Time_Minutes": ["mean", "median", "std"],
        "Compute_Latency_ms": ["mean"],
        "Reroute_Count": ["mean", "sum"],
    })
    print(summary.round(2).to_string())

    # Direct Comparison Calculations
    pivot_time = df_results.pivot(index="OD_pair", columns="Strategy", values="Travel_Time_Seconds")
    saved_pred_sec = (pivot_time["Static Baseline"] - pivot_time["Predictive Pre-Planned"]).mean()
    saved_dyn_sec = (pivot_time["Static Baseline"] - pivot_time["Dynamic Edge-Rerouting"]).mean()
    pct_saved_pred = (saved_pred_sec / pivot_time["Static Baseline"].mean()) * 100.0
    pct_saved_dyn = (saved_dyn_sec / pivot_time["Static Baseline"].mean()) * 100.0

    print("\n" + "-" * 65)
    print("KEY PERFORMANCE HIGHLIGHTS:")
    print(f"  * Average Travel Time (Static Baseline):     {pivot_time['Static Baseline'].mean()/60.0:.2f} mins")
    print(f"  * Average Travel Time (Predictive Route):    {pivot_time['Predictive Pre-Planned'].mean()/60.0:.2f} mins")
    print(f"  * Average Travel Time (Dynamic Rerouting):   {pivot_time['Dynamic Edge-Rerouting'].mean()/60.0:.2f} mins")
    print(f"  * Mean Savings (Predictive vs Static):       {saved_pred_sec/60.0:.2f} mins ({pct_saved_pred:.2f}%)")
    print(f"  * Mean Savings (Dynamic vs Static):          {saved_dyn_sec/60.0:.2f} mins ({pct_saved_dyn:.2f}%)")
    print("-" * 65)


if __name__ == "__main__":
    main()
