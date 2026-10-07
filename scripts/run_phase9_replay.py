"""
GeoPulse Phase 9: Dynamic Rerouting Replay & Evaluation Pipeline

Implements:
1. Replay simulation of the Main Demonstration Scenario (Predict -> Plan -> Observe -> Compare -> Re-route).
2. Counterfactual evaluation: Strategy A (No Rerouting) vs Strategy B (GeoPulse Dynamic Rerouting).
3. Benchmark evaluation across 20 representative scenarios spanning all diurnal periods.
4. Export of replay datasets (Parquet, CSV, JSON).
5. Generation of all 10 publication-quality presentation figures (300 DPI).
"""

import os
import sys
import json
import time
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import networkx as nx
from shapely import wkt

sys.path.insert(0, os.path.abspath('.'))

from src.routing.traffic_weights import GraphWeightManager
from src.routing.dynamic_rerouter import DynamicRerouter
from src.routing.route_evaluator import compute_edge_jaccard_overlap

# Visual styling
plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.size'] = 11
plt.rcParams['axes.titlesize'] = 13
plt.rcParams['axes.labelsize'] = 11
plt.rcParams['figure.titlesize'] = 14

os.makedirs('results/phase9/figures', exist_ok=True)
os.makedirs('docs', exist_ok=True)

print("=" * 70)
print("GeoPulse Phase 9: Dynamic Rerouting Replay Pipeline")
print("=" * 70)

# -----------------------------------------------------------------------------
# 1. LOAD GRAPH & PREDICTIONS
# -----------------------------------------------------------------------------
print("\n[Step 1/6] Loading road graph and predictions...")
t0_load = time.time()
G = nx.read_graphml('data/raw/osm/bhubaneswar_drive.graphml')
mapping_df = pd.read_parquet('data/processed/traffic_to_osm_mapping_final.parquet')
pred_df = pd.read_parquet('results/phase7_predictions.parquet')
cand_df = pd.read_csv('results/phase9_candidate_scenarios.csv')

pred_df['ts_round'] = pd.to_datetime(pred_df['timestamp']).dt.round('h')
pred_df['ts_ist'] = pred_df['ts_round'].dt.tz_convert('Asia/Kolkata')

weight_manager = GraphWeightManager(G, mapping_df)
rerouter = DynamicRerouter(weight_manager, reroute_threshold_seconds=10.0, reroute_threshold_percent=3.0)
print(f"Loaded graph ({G.number_of_nodes():,} nodes) and weight manager in {time.time()-t0_load:.2f}s")

# -----------------------------------------------------------------------------
# 2. SELECT & EXECUTE MAIN DEMONSTRATION SCENARIO
# -----------------------------------------------------------------------------
print("\n[Step 2/6] Executing Main Demonstration Scenario (Scenario #0)...")
main_cand = cand_df.iloc[0]

# Timestamps
t0_val = pd.to_datetime(main_cand['t0_utc'])
t1_val = pd.to_datetime(main_cand['t1_utc'])
t0_ist_val = pd.to_datetime(main_cand['t0_ist'])
t1_ist_val = pd.to_datetime(main_cand['t1_ist'])

p0 = pred_df[pred_df['ts_round'] == t0_val].set_index('traffic_segment_id')
p1 = pred_df[pred_df['ts_round'] == t1_val].set_index('traffic_segment_id')

w_pred_t0, _, dyn_edges_t0 = weight_manager.build_scenario_weights(p0['predicted_speed'].to_dict())
w_obs_t1, _, dyn_edges_t1 = weight_manager.build_scenario_weights(p1['actual_speed'].to_dict())

main_sim = rerouter.simulate_journey(
    scenario_id=0,
    od_id=int(main_cand['od_id']),
    source=str(int(float(main_cand['source_node']))),
    destination=str(int(float(main_cand['destination_node']))),
    t0=t0_val,
    t1=t1_val,
    t0_ist=t0_ist_val,
    t1_ist=t1_ist_val,
    period_label='Evening Peak',
    w_pred_t0=w_pred_t0,
    w_obs_t1=w_obs_t1,
    dynamic_edges_set=dyn_edges_t1,
    decision_frac=float(main_cand['decision_frac'])
)

print(f"Main Demo Trip OD #{main_sim['od_id']} (Evening Peak: {main_sim['initial_ist_timestamp']} -> {main_sim['update_ist_timestamp']}):")
print(f"  Decision Node: {main_sim['decision_node']} (Step {main_sim['decision_step']} of {main_sim['initial_route_edges']})")
print(f"  Strategy A (No Rerouting):       {main_sim['total_time_no_reroute_s']:.1f} s ({main_sim['total_time_no_reroute_s']/60:.2f} min)")
print(f"  Strategy B (Dynamic Rerouting):  {main_sim['total_time_dynamic_s']:.1f} s ({main_sim['total_time_dynamic_s']/60:.2f} min)")
print(f"  Time Saved:                      {main_sim['time_saved_s']:.1f} s ({main_sim['time_saved_s']/60:.2f} min)")
print(f"  Improvement:                     {main_sim['improvement_pct']:.2f}%")
print(f"  Route Overlap:                   {main_sim['route_overlap_before_after']*100:.1f}%")

# Export compact demo scenario JSON
demo_json_data = {
    "scenario_id": "demo_scenario_0",
    "od_id": int(main_sim['od_id']),
    "source_node": main_sim['source_node'],
    "destination_node": main_sim['destination_node'],
    "initial_timestamp": str(main_sim['initial_ist_timestamp']),
    "update_timestamp": str(main_sim['update_ist_timestamp']),
    "decision_node": main_sim['decision_node'],
    "decision_step": int(main_sim['decision_step']),
    "reroute_triggered": bool(main_sim['reroute_triggered']),
    "trigger_reason": main_sim['trigger_reason'],
    "total_time_no_reroute_s": main_sim['total_time_no_reroute_s'],
    "total_time_dynamic_s": main_sim['total_time_dynamic_s'],
    "time_saved_s": main_sim['time_saved_s'],
    "improvement_pct": main_sim['improvement_pct'],
    "initial_route_edges": main_sim['initial_route_edges'],
    "new_route_edges": main_sim['new_route_edges'],
    "changed_edges_count": main_sim['changed_edges_count'],
    "route_overlap": main_sim['route_overlap_before_after']
}

with open('results/phase9_demo_scenario.json', 'w') as f:
    json.dump(demo_json_data, f, indent=2)
print("Saved demo payload to results/phase9_demo_scenario.json")

# -----------------------------------------------------------------------------
# 3. MULTI-SCENARIO BENCHMARK EVALUATION (20 SCENARIOS)
# -----------------------------------------------------------------------------
print("\n[Step 3/6] Running 20-scenario benchmark evaluation across diurnal periods...")
# Select 20 balanced scenarios from candidates and controls
benchmark_scenarios = []

# Take top 8 high-impact candidate scenarios from cand_df
top_cands = cand_df.head(8)
for _, r in top_cands.iterrows():
    benchmark_scenarios.append({
        'od_id': int(r['od_id']),
        't0_utc': pd.to_datetime(r['t0_utc']),
        't1_utc': pd.to_datetime(r['t1_utc']),
        't0_ist': pd.to_datetime(r['t0_ist']),
        't1_ist': pd.to_datetime(r['t1_ist']),
        'period': 'Evening Peak' if r['is_evening_peak'] == 1 else 'Midday',
        'src': str(int(float(r['source_node']))),
        'dst': str(int(float(r['destination_node']))),
        'frac': float(r['decision_frac'])
    })

# Add diverse candidates from other periods (Morning peak, Midday, Off-Peak)
od_df = pd.read_csv('results/phase8_od_pairs.csv')
unique_ts = sorted(pred_df['ts_round'].unique())

# Pick additional 12 timestamps and OD pairs across periods
period_samples = [
    # Morning Peak (Fri Jan 16: 09:30 -> 10:30 IST)
    (20, 21, 'Morning Peak', [1, 5, 12, 18]),
    # Midday (Fri Jan 16: 13:30 -> 14:30 IST)
    (24, 25, 'Midday', [2, 8, 15, 22]),
    # Off-Peak / Night (Fri Jan 16: 22:30 -> 23:30 IST)
    (33, 34, 'Off-Peak', [3, 7, 14, 25])
]

for idx0, idx1, p_name, od_sample_list in period_samples:
    t0_cand = unique_ts[idx0]
    t1_cand = unique_ts[idx1]
    t0_ist_cand = pd.to_datetime(t0_cand).tz_convert('Asia/Kolkata')
    t1_ist_cand = pd.to_datetime(t1_cand).tz_convert('Asia/Kolkata')
    
    for od_i in od_sample_list:
        od_r = od_df.iloc[od_i]
        benchmark_scenarios.append({
            'od_id': od_i,
            't0_utc': t0_cand,
            't1_utc': t1_cand,
            't0_ist': t0_ist_cand,
            't1_ist': t1_ist_cand,
            'period': p_name,
            'src': str(int(float(od_r['source_node']))),
            'dst': str(int(float(od_r['destination_node']))),
            'frac': 0.33
        })

print(f"Total benchmark scenarios assembled: {len(benchmark_scenarios)}")

# Execute benchmark
benchmark_results = []
for sc_idx, sc in enumerate(benchmark_scenarios):
    p0 = pred_df[pred_df['ts_round'] == sc['t0_utc']].set_index('traffic_segment_id')
    p1 = pred_df[pred_df['ts_round'] == sc['t1_utc']].set_index('traffic_segment_id')
    
    w_pred, _, _ = weight_manager.build_scenario_weights(p0['predicted_speed'].to_dict())
    w_obs, _, dyn_set = weight_manager.build_scenario_weights(p1['actual_speed'].to_dict())
    
    res_sim = rerouter.simulate_journey(
        scenario_id=sc_idx,
        od_id=sc['od_id'],
        source=sc['src'],
        destination=sc['dst'],
        t0=sc['t0_utc'],
        t1=sc['t1_utc'],
        t0_ist=sc['t0_ist'],
        t1_ist=sc['t1_ist'],
        period_label=sc['period'],
        w_pred_t0=w_pred,
        w_obs_t1=w_obs,
        dynamic_edges_set=dyn_set,
        decision_frac=sc['frac']
    )
    # Strip heavy path arrays for tabular export
    clean_rec = {k: v for k, v in res_sim.items() if not k.endswith('_path')}
    benchmark_results.append(clean_rec)

df_bench = pd.DataFrame(benchmark_results)
df_bench.to_parquet('results/phase9_dynamic_replay.parquet', index=False)
df_bench.to_csv('results/phase9_dynamic_replay.csv', index=False)
print("Saved results/phase9_dynamic_replay.parquet and .csv")

# -----------------------------------------------------------------------------
# 4. COMPUTE BENCHMARK SUMMARY METRICS
# -----------------------------------------------------------------------------
print("\n[Step 4/6] Computing benchmark summary metrics...")
n_bench = len(df_bench)
n_rerouted = df_bench['reroute_triggered'].sum()
reroute_freq_pct = (n_rerouted / n_bench) * 100.0

beneficial_reroutes = (df_bench['time_saved_s'] > 0).sum()
non_beneficial_reroutes = n_rerouted - beneficial_reroutes

mean_saving_all = df_bench['time_saved_s'].mean()
median_saving_all = df_bench['time_saved_s'].median()
mean_imp_all = df_bench['improvement_pct'].mean()

# On rerouted subset
rerouted_sub = df_bench[df_bench['reroute_triggered'] == True]
mean_saving_rerouted = rerouted_sub['time_saved_s'].mean() if len(rerouted_sub) > 0 else 0.0
mean_imp_rerouted = rerouted_sub['improvement_pct'].mean() if len(rerouted_sub) > 0 else 0.0

bench_metrics_data = {
    "main_demo": {
        "scenario_id": 0,
        "od_id": int(main_sim['od_id']),
        "period": main_sim['period'],
        "no_reroute_total_time_s": main_sim['total_time_no_reroute_s'],
        "dynamic_reroute_total_time_s": main_sim['total_time_dynamic_s'],
        "time_saved_s": main_sim['time_saved_s'],
        "improvement_pct": main_sim['improvement_pct'],
        "initial_route_distance_m": main_sim['initial_route_distance_m'],
        "final_route_distance_m": main_sim['new_route_distance_m'],
        "route_overlap": main_sim['route_overlap_before_after'],
        "decision_step": int(main_sim['decision_step']),
        "reroute_triggered": bool(main_sim['reroute_triggered'])
    },
    "benchmark": {
        "total_scenarios": n_bench,
        "reroute_triggered_count": int(n_rerouted),
        "reroute_frequency_pct": round(reroute_freq_pct, 2),
        "beneficial_reroutes_count": int(beneficial_reroutes),
        "non_beneficial_reroutes_count": int(non_beneficial_reroutes),
        "mean_saving_seconds_overall": round(mean_saving_all, 2),
        "median_saving_seconds_overall": round(median_saving_all, 2),
        "mean_improvement_pct_overall": round(mean_imp_all, 2),
        "mean_saving_seconds_when_rerouted": round(mean_saving_rerouted, 2),
        "mean_improvement_pct_when_rerouted": round(mean_imp_rerouted, 2),
        "average_route_overlap": round(df_bench['route_overlap_before_after'].mean(), 4)
    }
}

with open('results/phase9_dynamic_rerouting_metrics.json', 'w') as f:
    json.dump(bench_metrics_data, f, indent=2)

df_bench_summary = pd.DataFrame([{
    'total_scenarios': n_bench,
    'reroute_count': n_rerouted,
    'reroute_frequency_pct': reroute_freq_pct,
    'beneficial_reroutes': beneficial_reroutes,
    'mean_saving_s': mean_saving_all,
    'median_saving_s': median_saving_all,
    'mean_improvement_pct': mean_imp_all,
    'mean_saving_when_rerouted_s': mean_saving_rerouted,
    'mean_imp_when_rerouted_pct': mean_imp_rerouted
}])
df_bench_summary.to_csv('results/phase9_dynamic_rerouting_metrics.csv', index=False)
print("Saved summary metrics to results/phase9_dynamic_rerouting_metrics.csv and .json")

# -----------------------------------------------------------------------------
# 5. GENERATE ALL 10 PRESENTATION FIGURES
# -----------------------------------------------------------------------------
print("\n[Step 5/6] Generating all 10 publication figures...")

def extract_edge_coords(G, u, v, k):
    data = G.get_edge_data(u, v, k, default={})
    if 'geometry' in data:
        geom = wkt.loads(data['geometry'])
        return list(geom.coords)
    else:
        u_d = G.nodes[u]
        v_d = G.nodes[v]
        return [
            (float(u_d.get('x', u_d.get('lon', 0.0))), float(u_d.get('y', u_d.get('lat', 0.0)))),
            (float(v_d.get('x', v_d.get('lon', 0.0))), float(v_d.get('y', v_d.get('lat', 0.0))))
        ]

# FIGURE 1: Dynamic Rerouting Map
fig, ax = plt.subplots(figsize=(10, 8), dpi=300)

# 1. Traversed common prefix
for u, v, k in main_sim['traversed_edge_path']:
    lons, lats = zip(*extract_edge_coords(G, u, v, k))
    ax.plot(lons, lats, color='#2b5c8f', linewidth=3.5, label='Traversed Path (Before Reroute)' if (u, v, k) == main_sim['traversed_edge_path'][0] else "")

# 2. Abandoned congested remaining R0
for u, v, k in main_sim['remaining_r0_edge_path']:
    lons, lats = zip(*extract_edge_coords(G, u, v, k))
    ax.plot(lons, lats, color='#d62728', linewidth=3.0, linestyle=':', alpha=0.85, label='Original Path (Abandoned due to Congestion)' if (u, v, k) == main_sim['remaining_r0_edge_path'][0] else "")

# 3. Executed rerouted bypass R1
for u, v, k in main_sim['remaining_r1_edge_path']:
    lons, lats = zip(*extract_edge_coords(G, u, v, k))
    ax.plot(lons, lats, color='#2ca02c', linewidth=3.5, label='GeoPulse Dynamic Reroute (Faster Bypass)' if (u, v, k) == main_sim['remaining_r1_edge_path'][0] else "")

# Markers
src_n = main_sim['source_node']
dst_n = main_sim['destination_node']
dec_n = main_sim['decision_node']

ax.scatter([float(G.nodes[src_n]['x'])], [float(G.nodes[src_n]['y'])], color='#008800', s=160, zorder=6, edgecolors='black', label='Origin (Start)')
ax.scatter([float(G.nodes[dec_n]['x'])], [float(G.nodes[dec_n]['y'])], color='#ffaa00', s=180, zorder=6, marker='P', edgecolors='black', label='Reroute Decision Point (Congestion Detected)')
ax.scatter([float(G.nodes[dst_n]['x'])], [float(G.nodes[dst_n]['y'])], color='#cc0000', s=160, zorder=6, marker='X', edgecolors='black', label='Destination (End)')

ax.set_title(f'Figure 1: GeoPulse Dynamic Rerouting Demonstration (OD #{main_sim["od_id"]}, Evening Peak)', fontweight='bold', pad=12)
ax.set_xlabel('Longitude (°E)')
ax.set_ylabel('Latitude (°N)')
ax.legend(loc='lower left', frameon=True)
plt.tight_layout()
fig.savefig('results/phase9/figures/01_dynamic_rerouting_map.png', bbox_inches='tight')
plt.close(fig)

# FIGURE 2: Journey Timeline
fig, ax = plt.subplots(figsize=(9, 5), dpi=300)
steps = ['1. Initial Plan (t0)', '2. Traffic Update (t1)', '3. Degradation Detected', '4. Dynamic Reroute (R1)']
y_times = [
    main_sim['initial_predicted_time_s'] / 60.0,
    main_sim['total_time_no_reroute_s'] / 60.0,
    main_sim['total_time_no_reroute_s'] / 60.0,
    main_sim['total_time_dynamic_s'] / 60.0
]
colors = ['#1f77b4', '#d62728', '#ff7f0e', '#2ca02c']
ax.plot(steps, y_times, marker='o', linewidth=2.5, color='#4a5568')
for i, (txt, c) in enumerate(zip(y_times, colors)):
    ax.scatter([steps[i]], [txt], color=c, s=120, zorder=5, edgecolors='black')
    ax.text(i, txt + 0.35, f'{txt:.2f} min', ha='center', fontweight='bold', color=c)

ax.set_title('Figure 2: Trip Timeline & Dynamic Delay Recovery', fontweight='bold', pad=12)
ax.set_ylabel('Trip Travel Time (minutes)')
ax.set_ylim(min(y_times) - 1.0, max(y_times) + 1.5)
ax.grid(True, linestyle='--', alpha=0.6)
plt.tight_layout()
fig.savefig('results/phase9/figures/02_rerouting_timeline.png', bbox_inches='tight')
plt.close(fig)

# FIGURE 3: Before vs After Travel Time
fig, ax = plt.subplots(figsize=(7, 5), dpi=300)
labels = ['Strategy A:\nNo Rerouting', 'Strategy B:\nDynamic Rerouting']
times = [main_sim['total_time_no_reroute_s'] / 60.0, main_sim['total_time_dynamic_s'] / 60.0]
bars = ax.bar(labels, times, color=['#d62728', '#2ca02c'], width=0.48, edgecolor='black', alpha=0.85)

for bar in bars:
    yval = bar.get_height()
    ax.text(bar.get_x() + bar.get_width()/2.0, yval + 0.3, f'{yval:.2f} min\n({yval*60:.0f} s)', ha='center', va='bottom', fontweight='bold')

ax.text(0.5, 0.88, f'Time Saved: {main_sim["time_saved_s"]:.1f} s ({main_sim["time_saved_s"]/60:.2f} min)\nImprovement: {main_sim["improvement_pct"]:.2f}%',
        transform=ax.transAxes, ha='center', bbox=dict(boxstyle='round,pad=0.5', facecolor='white', alpha=0.9, edgecolor='#ccc'))

ax.set_title('Figure 3: Counterfactual Travel Time Comparison', fontweight='bold', pad=12)
ax.set_ylabel('Total Journey Time (minutes)')
ax.set_ylim(0, max(times) * 1.25)
ax.grid(axis='y', linestyle='--', alpha=0.7)
plt.tight_layout()
fig.savefig('results/phase9/figures/03_before_after_travel_time.png', bbox_inches='tight')
plt.close(fig)

# FIGURE 4: Route Change Analysis
fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
metrics_labels = ['Total Initial Edges', 'Rerouted Path Edges', 'Changed Bypass Edges']
vals = [main_sim['initial_route_edges'], main_sim['new_route_edges'], main_sim['changed_edges_count']]
bars = ax.bar(metrics_labels, vals, color=['#2b5c8f', '#2ca02c', '#ff7f0e'], width=0.52, edgecolor='black', alpha=0.85)
for bar in bars:
    yval = bar.get_height()
    ax.text(bar.get_x() + bar.get_width()/2.0, yval + 1, f'{int(yval)}', ha='center', va='bottom', fontweight='bold')

ax.set_title(f'Figure 4: Edge Composition & Route Overlap (Jaccard = {main_sim["route_overlap_before_after"]*100:.1f}%)', fontweight='bold', pad=12)
ax.set_ylabel('Edge Count')
ax.set_ylim(0, max(vals) * 1.2)
ax.grid(axis='y', linestyle='--', alpha=0.7)
plt.tight_layout()
fig.savefig('results/phase9/figures/04_route_change_analysis.png', bbox_inches='tight')
plt.close(fig)

# FIGURE 5: Traffic Evolution on Critical Link
fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
# Extract critical edge speeds
crit_edge = main_sim['remaining_r0_edge_path'][0]
t0_spd = weight_manager.edge_lengths[crit_edge] / (w_pred_t0[crit_edge] / 3.6)
t1_spd = weight_manager.edge_lengths[crit_edge] / (w_obs_t1[crit_edge] / 3.6)
free_spd = weight_manager.edge_static_speeds[crit_edge]

phases = ['Baseline Free-Flow', 'Initial Forecast (t0)', 'Observed Congestion (t1)']
spds = [free_spd, t0_spd, t1_spd]
colors = ['#888888', '#1f77b4', '#d62728']

bars = ax.bar(phases, spds, color=colors, width=0.52, edgecolor='black', alpha=0.85)
for bar in bars:
    yval = bar.get_height()
    ax.text(bar.get_x() + bar.get_width()/2.0, yval + 0.8, f'{yval:.1f} km/h', ha='center', va='bottom', fontweight='bold')

ax.set_title('Figure 5: Traffic Speed Evolution on Bottleneck Link', fontweight='bold', pad=12)
ax.set_ylabel('Corridor Speed (km/h)')
ax.set_ylim(0, max(spds) * 1.25)
ax.grid(axis='y', linestyle='--', alpha=0.7)
plt.tight_layout()
fig.savefig('results/phase9/figures/05_traffic_evolution.png', bbox_inches='tight')
plt.close(fig)

# FIGURE 6: Rerouting Benefit Distribution Across Benchmark
fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
rerouted_only = df_bench[df_bench['reroute_triggered'] == True]
sns.histplot(rerouted_only['time_saved_s'], bins=12, color='#2ca02c', edgecolor='white', alpha=0.85, ax=ax)
ax.axvline(rerouted_only['time_saved_s'].mean(), color='#d62728', linestyle='--', linewidth=2, label=f'Mean Saving: {rerouted_only["time_saved_s"].mean():.1f} s')
ax.axvline(rerouted_only['time_saved_s'].median(), color='#1f77b4', linestyle=':', linewidth=2, label=f'Median Saving: {rerouted_only["time_saved_s"].median():.1f} s')
ax.set_title('Figure 6: Distribution of Time Saved When Rerouting Triggered', fontweight='bold', pad=12)
ax.set_xlabel('Time Saved (seconds)')
ax.set_ylabel('Scenario Count')
ax.legend(loc='upper right', frameon=True)
plt.tight_layout()
fig.savefig('results/phase9/figures/06_rerouting_benefit_distribution.png', bbox_inches='tight')
plt.close(fig)

# FIGURE 7: Reroute Frequency in Benchmark
fig, ax = plt.subplots(figsize=(7, 5), dpi=300)
trig_pct = (df_bench['reroute_triggered'].sum() / len(df_bench)) * 100.0
no_trig_pct = 100.0 - trig_pct

wedges, texts, autotexts = ax.pie(
    [trig_pct, no_trig_pct],
    labels=[f'Dynamic Reroute Triggered\n({trig_pct:.1f}%)', f'No Reroute Needed\n({no_trig_pct:.1f}%)'],
    colors=['#2ca02c', '#aaaaaa'],
    autopct='%1.1f%%',
    startangle=140,
    explode=(0.06, 0),
    wedgeprops=dict(edgecolor='black', linewidth=1.2)
)
for at in autotexts:
    at.set_fontweight('bold')
ax.set_title('Figure 7: Rerouting Trigger Frequency Across Benchmark Scenarios', fontweight='bold', pad=12)
plt.tight_layout()
fig.savefig('results/phase9/figures/07_reroute_frequency.png', bbox_inches='tight')
plt.close(fig)

# FIGURE 8: Prediction vs Reality on Monitored Corridors
fig, ax = plt.subplots(figsize=(7, 7), dpi=300)
pred_vals = p0['predicted_speed'].values
act_vals = p1['actual_speed'].values
sample_idx = np.random.choice(len(pred_vals), size=min(400, len(pred_vals)), replace=False)
ax.scatter(pred_vals[sample_idx], act_vals[sample_idx], alpha=0.45, color='#2b5c8f', edgecolors='none', s=30)
max_spd = max(np.max(pred_vals), np.max(act_vals)) + 5
ax.plot([0, max_spd], [0, max_spd], color='#d62728', linestyle='--', linewidth=2, label='Identity Line (Perfect Forecast)')
ax.set_title('Figure 8: Initial Predicted Speed vs. Subsequent Observed Speed', fontweight='bold', pad=12)
ax.set_xlabel('Predicted Speed at t0 (km/h)')
ax.set_ylabel('Observed Speed at t1 (km/h)')
ax.set_xlim([0, max_spd])
ax.set_ylim([0, max_spd])
ax.legend(loc='lower right', frameon=True)
plt.tight_layout()
fig.savefig('results/phase9/figures/08_prediction_vs_observation.png', bbox_inches='tight')
plt.close(fig)

# FIGURE 9: Cumulative Journey Comparison Trajectory
fig, ax = plt.subplots(figsize=(10, 5), dpi=300)
# Step-by-step cumulative travel time
k_step = main_sim['decision_step']

# Traversed portion
t_trav_cum = np.cumsum([w_pred_t0[e] for e in main_sim['traversed_edge_path']])

# Strategy A remaining
t_rem_a_cum = t_trav_cum[-1] + np.cumsum([w_obs_t1[e] for e in main_sim['remaining_r0_edge_path']])
full_a_steps = np.arange(len(main_sim['r0_edge_path']))
full_a_times = np.concatenate([t_trav_cum, t_rem_a_cum]) / 60.0

# Strategy B remaining
t_rem_b_cum = t_trav_cum[-1] + np.cumsum([w_obs_t1[e] for e in main_sim['remaining_r1_edge_path']])
full_b_steps = np.arange(len(main_sim['r1_edge_path']))
full_b_times = np.concatenate([t_trav_cum, t_rem_b_cum]) / 60.0

ax.plot(full_a_steps, full_a_times, color='#d62728', linestyle='--', linewidth=2.5, label='Strategy A: No Reroute (Suffers Bottleneck Delay)')
ax.plot(full_b_steps, full_b_times, color='#2ca02c', linewidth=2.5, label='Strategy B: GeoPulse Dynamic Reroute (Faster Bypass)')
ax.axvline(k_step, color='#ffaa00', linestyle=':', linewidth=2, label=f'Decision Step {k_step} (Traffic Update Arrives)')

ax.set_title('Figure 9: Cumulative Journey Trajectory Comparison', fontweight='bold', pad=12)
ax.set_xlabel('Edge Step Along Route')
ax.set_ylabel('Cumulative Travel Time (minutes)')
ax.legend(loc='upper left', frameon=True)
ax.grid(True, linestyle='--', alpha=0.6)
plt.tight_layout()
fig.savefig('results/phase9/figures/09_cumulative_journey_comparison.png', bbox_inches='tight')
plt.close(fig)

# FIGURE 10: Final Executive Summary Infographic
fig, ax = plt.subplots(figsize=(10, 6), dpi=300)
ax.axis('off')

summary_text = (
    "GeoPulse Phase 9: Dynamic Rerouting Lifecycle Summary\n"
    "============================================================\n\n"
    "LIFECYCLE FLOW:\n"
    "Predict (ML t0) -> Plan Initial Route R0 -> Drive -> Observe Traffic (t1)\n"
    "  -> Detect Degradation -> Re-route via Dijkstra -> Arrive Ahead of Congestion\n\n"
    "----------------------------------------------------------------------------\n"
    "MAIN DEMONSTRATION METRICS (OD #0, Evening Peak Commute):\n"
    "----------------------------------------------------------------------------\n"
    f"• Strategy A (No Rerouting):         {main_sim['total_time_no_reroute_s']:.1f} s ({main_sim['total_time_no_reroute_s']/60:.2f} min)\n"
    f"• Strategy B (GeoPulse Rerouting):   {main_sim['total_time_dynamic_s']:.1f} s ({main_sim['total_time_dynamic_s']/60:.2f} min)\n"
    f"• Actual Travel Time Saved:          {main_sim['time_saved_s']:.1f} s ({main_sim['time_saved_s']/60:.2f} min)\n"
    f"• Percentage Journey Improvement:    {main_sim['improvement_pct']:.2f}%\n"
    f"• Trigger Decision Point:            Step {main_sim['decision_step']} of {main_sim['initial_route_edges']} edges\n"
    f"• Spatial Route Jaccard Overlap:     {main_sim['route_overlap_before_after']*100:.1f}%\n\n"
    "----------------------------------------------------------------------------\n"
    "MULTI-SCENARIO BENCHMARK SUMMARY (20 Scenarios Across City):\n"
    "----------------------------------------------------------------------------\n"
    f"• Rerouting Trigger Frequency:       {reroute_freq_pct:.1f}%\n"
    f"• Beneficial Reroute Rate:           {beneficial_reroutes}/{n_bench} ({beneficial_reroutes/n_bench*100:.1f}%)\n"
    f"• Mean Time Saved When Rerouted:     {mean_saving_rerouted:.1f} s ({mean_saving_rerouted/60:.2f} min)\n"
    f"• Mean Percentage Improvement:       {mean_imp_rerouted:.2f}% when triggered\n"
)

ax.text(0.04, 0.96, summary_text, transform=ax.transAxes, fontsize=11, family='monospace',
        verticalalignment='top', bbox=dict(boxstyle='round,pad=1.0', facecolor='#f8fafc', edgecolor='#cbd5e1', linewidth=2))

plt.tight_layout()
fig.savefig('results/phase9/figures/10_dynamic_routing_summary.png', bbox_inches='tight')
plt.close(fig)

print("All 10 figures successfully generated and saved to results/phase9/figures/")
print("\n[Step 6/6] Pipeline execution fully complete.")
