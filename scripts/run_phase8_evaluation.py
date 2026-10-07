"""
GeoPulse Phase 8: Dynamic Routing Evaluation Pipeline

Implements:
1. Loading Bhubaneswar GraphML & Phase 6/7 artifacts.
2. Selection of 50 reproducible OD pairs from the largest SCC.
3. Selection of 16 representative evaluation timestamps from the Phase 7 test period.
4. Custom Dijkstra routing under 3 scenarios:
   - Scenario A: Static Routing (OSM speed hierarchy baseline)
   - Scenario B: Current-Traffic Routing (Oracle benchmark)
   - Scenario C: ML-Predicted Routing (Strictly predictive decisions)
5. Ground-truth travel time evaluation under actual observed traffic.
6. Calculation of kinematics, oracle regret, dynamic coverage, and edge Jaccard overlap.
7. Serialization of evaluation datasets & metrics (CSV, Parquet, JSON).
8. Generation of all 12 presentation-quality figures (300 DPI).
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

# Ensure workspace root in path
sys.path.insert(0, os.path.abspath('.'))

from src.routing.traffic_weights import GraphWeightManager, calculate_travel_time_seconds
from src.routing.route_evaluator import evaluate_od_timestamp

# Visual styling
plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.size'] = 11
plt.rcParams['axes.titlesize'] = 13
plt.rcParams['axes.labelsize'] = 11
plt.rcParams['figure.titlesize'] = 14

# Output directories
os.makedirs('results/phase8/figures', exist_ok=True)
os.makedirs('docs', exist_ok=True)

print("=" * 70)
print("GeoPulse Phase 8: Custom Dynamic Routing Evaluation Pipeline")
print("=" * 70)

# -----------------------------------------------------------------------------
# 1. LOAD GRAPH & METADATA
# -----------------------------------------------------------------------------
print("\n[Step 1/7] Loading Bhubaneswar OSM Graph & Mapping...")
t0 = time.time()
G = nx.read_graphml('data/raw/osm/bhubaneswar_drive.graphml')
mapping_df = pd.read_parquet('data/processed/traffic_to_osm_mapping_final.parquet')
pred_df = pd.read_parquet('results/phase7_predictions.parquet')

print(f"Graph loaded: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges in {time.time()-t0:.2f}s")

# Extract Largest SCC
sccs = list(nx.strongly_connected_components(G))
largest_scc = max(sccs, key=len)
print(f"Largest SCC: {len(largest_scc):,} nodes ({len(largest_scc)/G.number_of_nodes()*100:.2f}% of network)")

# Initialize Weight Manager
weight_manager = GraphWeightManager(G, mapping_df)
print(f"Graph weight manager initialized. Cached {len(weight_manager.edge_lengths):,} edges.")

# -----------------------------------------------------------------------------
# 2. SELECT 50 REPRODUCIBLE OD PAIRS
# -----------------------------------------------------------------------------
print("\n[Step 2/7] Selecting 50 reproducible OD pairs from largest SCC...")

def haversine_dist(lat1, lon1, lat2, lon2):
    R = 6371000.0  # meters
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlam = np.radians(lon2 - lon1)
    a = np.sin(dphi/2.0)**2 + np.cos(phi1)*np.cos(phi2)*np.sin(dlam/2.0)**2
    return 2.0 * R * np.arcsin(np.sqrt(a))

nodes_info = {}
for n in largest_scc:
    d = G.nodes[n]
    lat = float(d.get('y', d.get('lat', 0.0)))
    lon = float(d.get('x', d.get('lon', 0.0)))
    nodes_info[n] = (lat, lon)

dyn_map = mapping_df[mapping_df['routing_eligibility'].isin(['DYNAMIC', 'DYNAMIC_BIDIRECTIONAL'])]
monitored_nodes = set(dyn_map['u'].astype(str)).union(set(dyn_map['v'].astype(str)))
monitored_nodes = [n for n in monitored_nodes if n in largest_scc]
all_scc_nodes = list(largest_scc)

np.random.seed(42)
od_pairs = []
attempts = 0

while len(od_pairs) < 50 and attempts < 10000:
    attempts += 1
    src = np.random.choice(monitored_nodes) if np.random.rand() < 0.70 else np.random.choice(all_scc_nodes)
    dst = np.random.choice(monitored_nodes) if np.random.rand() < 0.70 else np.random.choice(all_scc_nodes)
    
    if src == dst:
        continue
        
    lat1, lon1 = nodes_info[src]
    lat2, lon2 = nodes_info[dst]
    dist_m = haversine_dist(lat1, lon1, lat2, lon2)
    
    if 2000.0 <= dist_m <= 14000.0:
        if any(p['source_node'] == src and p['destination_node'] == dst for p in od_pairs):
            continue
        od_pairs.append({
            'od_id': len(od_pairs),
            'source_node': src,
            'destination_node': dst,
            'source_lat': lat1,
            'source_lon': lon1,
            'destination_lat': lat2,
            'destination_lon': lon2,
            'haversine_dist_m': round(dist_m, 2)
        })

df_od = pd.DataFrame(od_pairs)
df_od.to_csv('results/phase8_od_pairs.csv', index=False)
print(f"Saved 50 OD pairs to results/phase8_od_pairs.csv")
print(f"Distance stats (m): Min={df_od['haversine_dist_m'].min():.1f}, Mean={df_od['haversine_dist_m'].mean():.1f}, Max={df_od['haversine_dist_m'].max():.1f}")

# -----------------------------------------------------------------------------
# 3. SELECT 16 REPRESENTATIVE TEST TIMESTAMPS
# -----------------------------------------------------------------------------
print("\n[Step 3/7] Selecting 16 evaluation timestamps from Phase 7 test period...")
pred_df['ts_round'] = pd.to_datetime(pred_df['timestamp']).dt.round('h')
pred_df['ts_ist'] = pred_df['ts_round'].dt.tz_convert('Asia/Kolkata')

ts_unique = pred_df[['ts_round', 'ts_ist', 'hour', 'is_peak']].drop_duplicates().sort_values('ts_round').reset_index(drop=True)

# Select 16 representative timestamps:
# 3 Morning Peak, 4 Midday, 5 Evening Peak, 4 Off-peak
selected_indices = [
    # Thu Jan 15: Midday & Evening
    1,   # 14:30 IST (Midday)
    3,   # 16:30 IST (Midday)
    4,   # 17:30 IST (Evening Peak)
    5,   # 18:30 IST (Evening Peak)
    6,   # 19:30 IST (Evening Peak)
    9,   # 22:30 IST (Off-Peak)
    
    # Fri Jan 16: Full diurnal cycle
    13,  # 02:30 IST (Off-Peak / Night)
    17,  # 06:30 IST (Off-Peak / Early Morning)
    20,  # 09:30 IST (Morning Peak)
    21,  # 10:30 IST (Morning Peak)
    22,  # 11:30 IST (Morning Peak)
    24,  # 13:30 IST (Midday)
    26,  # 15:30 IST (Midday)
    28,  # 17:30 IST (Evening Peak)
    29,  # 18:30 IST (Evening Peak)
    33,  # 22:30 IST (Off-Peak)
]

eval_ts_df = ts_unique.iloc[selected_indices].copy().reset_index(drop=True)

def assign_period(row):
    h = row['ts_ist'].hour
    if 9 <= h <= 11:
        return 'Morning Peak'
    elif 17 <= h <= 20:
        return 'Evening Peak'
    elif 12 <= h <= 16:
        return 'Midday'
    else:
        return 'Off-Peak'

eval_ts_df['period'] = eval_ts_df.apply(assign_period, axis=1)
eval_ts_df['peak_offpeak'] = np.where(eval_ts_df['period'].str.contains('Peak'), 'Peak', 'Off-Peak')

eval_ts_df.to_csv('results/phase8_evaluation_timestamps.csv', index=False)
print("Saved 16 evaluation timestamps to results/phase8_evaluation_timestamps.csv")
for p, c in eval_ts_df['period'].value_counts().items():
    print(f"  {p}: {c} timestamps")

# -----------------------------------------------------------------------------
# 4. EXECUTE FULL ROUTE EVALUATION MATRIX (50 ODs x 16 Timestamps = 800 Runs)
# -----------------------------------------------------------------------------
print("\n[Step 4/7] Executing routing evaluation (50 ODs x 16 timestamps = 800 evaluations)...")
t_eval_start = time.time()
eval_records = []
cached_routes_for_viz = []  # save routes for visualization

for ts_idx, ts_row in eval_ts_df.iterrows():
    ts_val = ts_row['ts_round']
    ist_val = ts_row['ts_ist']
    period_label = ts_row['period']
    is_peak = int(ts_row['peak_offpeak'] == 'Peak')
    
    # Filter predictions at this timestamp
    preds_at_t = pred_df[pred_df['ts_round'] == ts_val].set_index('traffic_segment_id')
    
    obs_speeds = preds_at_t['actual_speed'].to_dict()
    ml_speeds = preds_at_t['predicted_speed'].to_dict()
    
    # Build scenario weights
    curr_weights, _, dyn_edges = weight_manager.build_scenario_weights(obs_speeds)
    pred_weights, _, _ = weight_manager.build_scenario_weights(ml_speeds)
    
    for od_idx, od_row in df_od.iterrows():
        res = evaluate_od_timestamp(
            od_id=od_row['od_id'],
            source=od_row['source_node'],
            target=od_row['destination_node'],
            timestamp=ts_val,
            ist_timestamp=ist_val,
            period_label=period_label,
            is_peak=is_peak,
            weight_manager=weight_manager,
            current_weights=curr_weights,
            predicted_weights=pred_weights,
            dynamic_edges_set=dyn_edges
        )
        
        # Save routes for OD 0 during Friday Evening Peak for visualization
        if od_row['od_id'] == 14 and period_label == 'Evening Peak' and len(cached_routes_for_viz) == 0:
            cached_routes_for_viz.append((res, curr_weights, pred_weights))
            
        # Strip heavy path arrays for tabular export
        res_record = {k: v for k, v in res.items() if not k.endswith('_path')}
        eval_records.append(res_record)

print(f"Completed {len(eval_records)} route evaluations in {time.time()-t_eval_start:.2f}s!")

# Export full evaluation dataset
df_eval = pd.DataFrame(eval_records)
df_eval.to_parquet('results/phase8_route_evaluation.parquet', index=False)
df_eval.to_csv('results/phase8_route_evaluation.csv', index=False)
print("Saved results/phase8_route_evaluation.parquet and .csv")

# -----------------------------------------------------------------------------
# 5. COMPUTE SUMMARY METRICS & STATISTICAL BREAKDOWNS
# -----------------------------------------------------------------------------
print("\n[Step 5/7] Computing summary routing metrics...")

def compute_summary_slice(sub_df, slice_name="Overall"):
    n = len(sub_df)
    ml_beat_static = (sub_df['ml_actual_time_s'] < sub_df['static_actual_time_s']).sum()
    ml_win_rate = (ml_beat_static / n) * 100.0
    
    # Matches / approaches current-optimal (within 5 seconds or regret == 0)
    ml_match_oracle = (sub_df['ml_regret_s'] <= 5.0).sum()
    ml_match_oracle_pct = (ml_match_oracle / n) * 100.0
    
    return {
        'slice': slice_name,
        'count': n,
        'mean_static_actual_time_s': round(sub_df['static_actual_time_s'].mean(), 2),
        'median_static_actual_time_s': round(sub_df['static_actual_time_s'].median(), 2),
        'mean_ml_actual_time_s': round(sub_df['ml_actual_time_s'].mean(), 2),
        'median_ml_actual_time_s': round(sub_df['ml_actual_time_s'].median(), 2),
        'mean_current_optimal_time_s': round(sub_df['current_actual_time_s'].mean(), 2),
        'median_current_optimal_time_s': round(sub_df['current_actual_time_s'].median(), 2),
        
        # Improvement & Regret
        'mean_improvement_over_static_pct': round(sub_df['ml_vs_static_improvement_pct'].mean(), 2),
        'median_improvement_over_static_pct': round(sub_df['ml_vs_static_improvement_pct'].median(), 2),
        'ml_win_rate_pct': round(ml_win_rate, 2),
        'ml_match_oracle_pct': round(ml_match_oracle_pct, 2),
        
        'mean_oracle_regret_s': round(sub_df['ml_regret_s'].mean(), 2),
        'median_oracle_regret_s': round(sub_df['ml_regret_s'].median(), 2),
        'mean_oracle_gap_pct': round(sub_df['ml_oracle_gap_pct'].mean(), 2),
        
        # Overlaps
        'mean_static_ml_overlap': round(sub_df['static_ml_route_overlap'].mean(), 4),
        'mean_ml_current_overlap': round(sub_df['ml_current_route_overlap'].mean(), 4),
        
        # Distance & Coverage
        'mean_distance_m': round(sub_df['ml_distance_m'].mean(), 2),
        'mean_dynamic_edge_fraction': round(sub_df['ml_dynamic_edge_fraction'].mean(), 4)
    }

# Distance classifications: Short (< 4km), Medium (4-8km), Long (> 8km)
df_eval['distance_class'] = pd.cut(
    df_eval['ml_distance_m'],
    bins=[0, 4000, 8000, 999999],
    labels=['Short (<4km)', 'Medium (4-8km)', 'Long (>8km)']
)

summary_rows = []
summary_rows.append(compute_summary_slice(df_eval, "Overall"))

for period in ['Morning Peak', 'Evening Peak', 'Midday', 'Off-Peak']:
    sub = df_eval[df_eval['period'] == period]
    summary_rows.append(compute_summary_slice(sub, f"Period: {period}"))

for dist_cls in ['Short (<4km)', 'Medium (4-8km)', 'Long (>8km)']:
    sub = df_eval[df_eval['distance_class'] == dist_cls]
    summary_rows.append(compute_summary_slice(sub, f"Distance: {dist_cls}"))

df_summary = pd.DataFrame(summary_rows)
df_summary.to_csv('results/phase8_routing_metrics.csv', index=False)
with open('results/phase8_routing_metrics.json', 'w') as f:
    json.dump(summary_rows, f, indent=2)

print("\n--- PHASE 8 EXECUTIVE SUMMARY TABLE ---")
print(df_summary[['slice', 'mean_static_actual_time_s', 'mean_ml_actual_time_s', 'mean_current_optimal_time_s', 'mean_improvement_over_static_pct', 'ml_win_rate_pct', 'mean_oracle_gap_pct']].to_string(index=False))

# -----------------------------------------------------------------------------
# 6. GENERATE ALL 12 REQUIRED FIGURES
# -----------------------------------------------------------------------------
print("\n[Step 6/7] Generating publication-quality figures...")

# Helper to extract WKT line coordinates
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

# FIGURE 1: Example Route Comparison Map
if cached_routes_for_viz:
    viz_res, viz_curr_w, viz_pred_w = cached_routes_for_viz[0]
else:
    # Fallback to re-evaluating OD 14
    od14 = df_od.iloc[14]
    viz_res = evaluate_od_timestamp(
        od_id=14, source=od14['source_node'], target=od14['destination_node'],
        timestamp=eval_ts_df.iloc[4]['ts_round'], ist_timestamp=eval_ts_df.iloc[4]['ts_ist'],
        period_label='Evening Peak', is_peak=1, weight_manager=weight_manager,
        current_weights=curr_weights, predicted_weights=pred_weights, dynamic_edges_set=dyn_edges
    )

fig, ax = plt.subplots(figsize=(10, 8), dpi=300)

# Plot static route
for u, v, k in viz_res['static_edge_path']:
    coords = extract_edge_coords(G, u, v, k)
    lons, lats = zip(*coords)
    ax.plot(lons, lats, color='#888888', linewidth=4.5, alpha=0.7, label='Static Baseline' if (u, v, k) == viz_res['static_edge_path'][0] else "")

# Plot current optimal route (oracle)
for u, v, k in viz_res['current_edge_path']:
    coords = extract_edge_coords(G, u, v, k)
    lons, lats = zip(*coords)
    ax.plot(lons, lats, color='#2ca02c', linewidth=3.0, linestyle='--', alpha=0.9, label='Current-Optimal (Oracle)' if (u, v, k) == viz_res['current_edge_path'][0] else "")

# Plot ML predicted route
for u, v, k in viz_res['ml_edge_path']:
    coords = extract_edge_coords(G, u, v, k)
    lons, lats = zip(*coords)
    ax.plot(lons, lats, color='#1f77b4', linewidth=2.0, alpha=1.0, label='ML-Predicted Dynamic' if (u, v, k) == viz_res['ml_edge_path'][0] else "")

# Origin & Destination markers
src_node = viz_res['source_node']
dst_node = viz_res['destination_node']
src_x, src_y = float(G.nodes[src_node]['x']), float(G.nodes[src_node]['y'])
dst_x, dst_y = float(G.nodes[dst_node]['x']), float(G.nodes[dst_node]['y'])

ax.scatter([src_x], [src_y], color='#00aa00', s=160, zorder=5, edgecolors='black', label='Origin (Start)')
ax.scatter([dst_x], [dst_y], color='#dd0000', s=160, zorder=5, edgecolors='black', marker='X', label='Destination (End)')

ax.set_title(f'Figure 1: Multi-Scenario Route Path Tracking (OD #{viz_res["od_id"]}, Evening Peak)', fontweight='bold', pad=12)
ax.set_xlabel('Longitude (°E)')
ax.set_ylabel('Latitude (°N)')
ax.legend(loc='lower left', frameon=True)
plt.tight_layout()
fig.savefig('results/phase8/figures/01_example_route_comparison.png', bbox_inches='tight')
plt.close(fig)

# FIGURE 2: Travel-Time Comparison Across Scenarios
fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
means = [df_eval['static_actual_time_s'].mean(), df_eval['ml_actual_time_s'].mean(), df_eval['current_actual_time_s'].mean()]
labels = ['Static Routing\n(Baseline)', 'ML-Predicted\n(GeoPulse)', 'Current-Optimal\n(Oracle)']
colors = ['#888888', '#1f77b4', '#2ca02c']
bars = ax.bar(labels, means, color=colors, width=0.52, edgecolor='black', alpha=0.85)

for bar in bars:
    yval = bar.get_height()
    ax.text(bar.get_x() + bar.get_width()/2.0, yval + 15, f'{yval:.1f} s\n({yval/60:.1f} min)', ha='center', va='bottom', fontweight='bold')

ax.set_title('Figure 2: Mean Actual Travel Time Across Routing Scenarios (n = 800)', fontweight='bold', pad=12)
ax.set_ylabel('Actual Travel Time (seconds)')
ax.set_ylim(0, max(means) * 1.25)
ax.grid(axis='y', linestyle='--', alpha=0.7)
plt.tight_layout()
fig.savefig('results/phase8/figures/02_route_travel_time_comparison.png', bbox_inches='tight')
plt.close(fig)

# FIGURE 3: Improvement Over Static Routing (%)
fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
sns.histplot(df_eval['ml_vs_static_improvement_pct'], bins=35, kde=True, color='#1f77b4', edgecolor='white', alpha=0.75, ax=ax)
mean_imp = df_eval['ml_vs_static_improvement_pct'].mean()
med_imp = df_eval['ml_vs_static_improvement_pct'].median()
ax.axvline(mean_imp, color='#d62728', linestyle='--', linewidth=2, label=f'Mean Improvement: {mean_imp:.2f}%')
ax.axvline(med_imp, color='#2ca02c', linestyle=':', linewidth=2, label=f'Median Improvement: {med_imp:.2f}%')
ax.set_title('Figure 3: Distribution of Travel Time Improvement vs. Static Routing', fontweight='bold', pad=12)
ax.set_xlabel('Travel Time Improvement (%)')
ax.set_ylabel('Evaluation Count (OD-Timestamps)')
ax.legend(loc='upper right', frameon=True)
plt.tight_layout()
fig.savefig('results/phase8/figures/03_improvement_over_static.png', bbox_inches='tight')
plt.close(fig)

# FIGURE 4: ML Predicted vs Actual Route Time Scatter Plot
fig, ax = plt.subplots(figsize=(7, 7), dpi=300)
ax.scatter(df_eval['ml_predicted_time_s'] / 60.0, df_eval['ml_actual_time_s'] / 60.0, alpha=0.35, color='#1f77b4', edgecolors='none', s=25)
max_t = max(df_eval['ml_predicted_time_s'].max(), df_eval['ml_actual_time_s'].max()) / 60.0 + 2
ax.plot([0, max_t], [0, max_t], color='#d62728', linestyle='--', linewidth=2, label='Ideal 1:1 Identity Line')
r2_route = 1 - (np.sum((df_eval['ml_actual_time_s'] - df_eval['ml_predicted_time_s'])**2) / np.sum((df_eval['ml_actual_time_s'] - df_eval['ml_actual_time_s'].mean())**2))
ax.text(0.05, 0.90, f'Route-Level $R^2$: {r2_route:.4f}\nMean Abs Error: {np.mean(np.abs(df_eval["ml_actual_time_s"] - df_eval["ml_predicted_time_s"])):.1f} s',
        transform=ax.transAxes, bbox=dict(boxstyle='round,pad=0.5', facecolor='white', alpha=0.9, edgecolor='#ccc'))
ax.set_title('Figure 4: Predicted vs. Actual Route Travel Time (Minutes)', fontweight='bold', pad=12)
ax.set_xlabel('ML-Predicted Travel Time (minutes)')
ax.set_ylabel('Ground-Truth Actual Travel Time (minutes)')
ax.set_xlim([0, max_t])
ax.set_ylim([0, max_t])
ax.legend(loc='lower right', frameon=True)
plt.tight_layout()
fig.savefig('results/phase8/figures/04_predicted_vs_actual_route_time.png', bbox_inches='tight')
plt.close(fig)

# FIGURE 5: Oracle Regret Distribution
fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
sns.histplot(df_eval['ml_regret_s'], bins=40, color='#ff7f0e', edgecolor='white', alpha=0.8, ax=ax)
mean_regret = df_eval['ml_regret_s'].mean()
med_regret = df_eval['ml_regret_s'].median()
ax.axvline(mean_regret, color='#d62728', linestyle='--', linewidth=2, label=f'Mean Regret: {mean_regret:.1f} s')
ax.axvline(med_regret, color='#2ca02c', linestyle=':', linewidth=2, label=f'Median Regret: {med_regret:.1f} s')
ax.set_title('Figure 5: Oracle Regret Distribution ($T_{ML} - T_{Oracle}$)', fontweight='bold', pad=12)
ax.set_xlabel('Oracle Regret (seconds)')
ax.set_ylabel('Count')
ax.legend(loc='upper right', frameon=True)
plt.tight_layout()
fig.savefig('results/phase8/figures/05_route_regret_distribution.png', bbox_inches='tight')
plt.close(fig)

# FIGURE 6: Route Distance Comparison
fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
dists = [df_eval['static_distance_m'].mean() / 1000.0, df_eval['ml_distance_m'].mean() / 1000.0, df_eval['current_distance_m'].mean() / 1000.0]
bars = ax.bar(['Static Baseline', 'ML-Predicted', 'Current-Optimal'], dists, color=['#888888', '#1f77b4', '#2ca02c'], width=0.52, edgecolor='black', alpha=0.85)
for bar in bars:
    yval = bar.get_height()
    ax.text(bar.get_x() + bar.get_width()/2.0, yval + 0.1, f'{yval:.2f} km', ha='center', va='bottom', fontweight='bold')
ax.set_title('Figure 6: Mean Route Physical Distance Across Scenarios', fontweight='bold', pad=12)
ax.set_ylabel('Mean Physical Distance (km)')
ax.set_ylim(0, max(dists) * 1.2)
ax.grid(axis='y', linestyle='--', alpha=0.7)
plt.tight_layout()
fig.savefig('results/phase8/figures/06_route_distance_comparison.png', bbox_inches='tight')
plt.close(fig)

# FIGURE 7: Dynamic Route Coverage
fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
sns.histplot(df_eval['ml_dynamic_edge_fraction'] * 100.0, bins=25, kde=True, color='#2b5c8f', edgecolor='white', alpha=0.8, ax=ax)
mean_cov = df_eval['ml_dynamic_edge_fraction'].mean() * 100.0
ax.axvline(mean_cov, color='#d62728', linestyle='--', linewidth=2, label=f'Mean Dynamic Coverage: {mean_cov:.1f}%')
ax.set_title('Figure 7: Dynamic Edge Coverage Fraction on Selected Routes', fontweight='bold', pad=12)
ax.set_xlabel('Percentage of Route Traversed on Dynamic Sensor Links (%)')
ax.set_ylabel('Frequency')
ax.legend(loc='upper right', frameon=True)
plt.tight_layout()
fig.savefig('results/phase8/figures/07_dynamic_route_coverage.png', bbox_inches='tight')
plt.close(fig)

# FIGURE 8: Improvement by Traffic Period
fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
periods = ['Morning Peak', 'Midday', 'Evening Peak', 'Off-Peak']
p_means = [df_eval[df_eval['period'] == p]['ml_vs_static_improvement_pct'].mean() for p in periods]
bars = ax.bar(periods, p_means, color=['#d62728', '#ff7f0e', '#1f77b4', '#2ca02c'], width=0.55, edgecolor='black', alpha=0.85)
for bar in bars:
    yval = bar.get_height()
    ax.text(bar.get_x() + bar.get_width()/2.0, yval + 0.3, f'{yval:.2f}%', ha='center', va='bottom', fontweight='bold')
ax.set_title('Figure 8: Mean Travel Time Improvement Over Static by Period', fontweight='bold', pad=12)
ax.set_ylabel('Improvement Over Static Baseline (%)')
ax.set_ylim(0, max(p_means) * 1.25)
ax.grid(axis='y', linestyle='--', alpha=0.7)
plt.tight_layout()
fig.savefig('results/phase8/figures/08_improvement_by_period.png', bbox_inches='tight')
plt.close(fig)

# FIGURE 9: Route Change Statistics (How often ML changes from static)
fig, ax = plt.subplots(figsize=(7, 5), dpi=300)
ml_diff_static = (df_eval['static_ml_route_overlap'] < 1.0).sum()
ml_same_static = len(df_eval) - ml_diff_static
diff_pct = (ml_diff_static / len(df_eval)) * 100.0
same_pct = (ml_same_static / len(df_eval)) * 100.0

wedges, texts, autotexts = ax.pie(
    [diff_pct, same_pct],
    labels=[f'Rerouted via Dynamic Path\n({diff_pct:.1f}%)', f'Identical to Static Path\n({same_pct:.1f}%)'],
    colors=['#1f77b4', '#aaaaaa'],
    autopct='%1.1f%%',
    startangle=140,
    explode=(0.06, 0),
    wedgeprops=dict(edgecolor='black', linewidth=1.2)
)
for at in autotexts:
    at.set_fontweight('bold')
ax.set_title('Figure 9: Frequency of Dynamic Rerouting Relative to Static Path', fontweight='bold', pad=12)
plt.tight_layout()
fig.savefig('results/phase8/figures/09_route_change_statistics.png', bbox_inches='tight')
plt.close(fig)

# FIGURE 10: Edge Weight Distribution Comparison
fig, ax = plt.subplots(figsize=(9, 5), dpi=300)
stat_w_vals = list(weight_manager.static_weights.values())
curr_w_vals = list(curr_weights.values())
pred_w_vals = list(pred_weights.values())

sns.kdeplot(np.clip(stat_w_vals, 0, 150), label='Static Baseline Weights', color='#888888', linestyle=':', linewidth=2, ax=ax)
sns.kdeplot(np.clip(curr_w_vals, 0, 150), label='Observed Traffic Weights', color='#2ca02c', linestyle='--', linewidth=2, ax=ax)
sns.kdeplot(np.clip(pred_w_vals, 0, 150), label='ML-Predicted Weights', color='#1f77b4', linewidth=2.5, ax=ax)
ax.set_title('Figure 10: Edge Traversal Time Distributions Across Network Links', fontweight='bold', pad=12)
ax.set_xlabel('Edge Traversal Time (seconds, clipped at 150s for display)')
ax.set_ylabel('Probability Density')
ax.set_xlim([0, 150])
ax.legend(loc='upper right', frameon=True)
plt.tight_layout()
fig.savefig('results/phase8/figures/10_edge_weight_comparison.png', bbox_inches='tight')
plt.close(fig)

# FIGURE 11: Route-Level Congestion Profile
fig, ax = plt.subplots(figsize=(11, 5), dpi=300)
# Speeds along the ML route for the example trip
example_edges = viz_res['ml_edge_path']
edge_indices = np.arange(len(example_edges))
static_speeds_path = [weight_manager.edge_static_speeds[e] for e in example_edges]
actual_speeds_path = [weight_manager.edge_lengths[e] / (curr_weights[e] / 3.6) for e in example_edges]
pred_speeds_path = [weight_manager.edge_lengths[e] / (pred_weights[e] / 3.6) for e in example_edges]

ax.plot(edge_indices, static_speeds_path, color='#888888', linestyle=':', linewidth=2, label='Static Assumed Speed')
ax.plot(edge_indices, actual_speeds_path, color='#2ca02c', linestyle='--', linewidth=2, label='Actual Observed Speed')
ax.plot(edge_indices, pred_speeds_path, color='#1f77b4', linewidth=2.5, label='ML-Predicted Speed')
ax.set_title('Figure 11: Edge-by-Edge Speed Profile Along Traversed Path (OD #14)', fontweight='bold', pad=12)
ax.set_xlabel('Edge Step Along Route Path')
ax.set_ylabel('Speed (km/h)')
ax.legend(loc='lower left', frameon=True)
ax.grid(True, linestyle='--', alpha=0.6)
plt.tight_layout()
fig.savefig('results/phase8/figures/11_route_congestion_profile.png', bbox_inches='tight')
plt.close(fig)

# FIGURE 12: Before/After Routing Executive Summary Graphic
fig, ax = plt.subplots(figsize=(10, 6), dpi=300)
ax.axis('off')

# Render styled executive card
summary_text = (
    "GeoPulse Dynamic Traffic Routing System — Executive Summary\n"
    "============================================================\n\n"
    f"Evaluated Test Scope:  50 OD Pairs x 16 Timestamps = 800 Route Decisions\n"
    f"Network Topology:      18,230 Nodes, 46,679 Directed Links (Bhubaneswar OSM)\n\n"
    "----------------------------------------------------------------------------\n"
    "ROUTING SCENARIOS COMPARISON:\n"
    "----------------------------------------------------------------------------\n"
    f"1. Static Baseline:       Mean Time = {means[0]:.1f} s ({means[0]/60:.1f} min)  |  Distance = {dists[0]:.2f} km\n"
    f"2. ML-Predicted Dynamic:  Mean Time = {means[1]:.1f} s ({means[1]/60:.1f} min)  |  Distance = {dists[1]:.2f} km\n"
    f"3. Current-Optimal Oracle: Mean Time = {means[2]:.1f} s ({means[2]/60:.1f} min)  |  Distance = {dists[2]:.2f} km\n\n"
    "----------------------------------------------------------------------------\n"
    "KEY PERFORMANCE METRICS:\n"
    "----------------------------------------------------------------------------\n"
    f"• ML Travel Time Improvement:  {df_eval['ml_vs_static_improvement_pct'].mean():.2f}% vs. Static Baseline\n"
    f"• ML Win Rate (Beats Static):  {(df_eval['ml_actual_time_s'] < df_eval['static_actual_time_s']).mean()*100:.2f}% of evaluations\n"
    f"• Mean Oracle Regret:          {df_eval['ml_regret_s'].mean():.1f} seconds (Near-Optimal)\n"
    f"• Mean Oracle Gap:             {df_eval['ml_oracle_gap_pct'].mean():.2f}%\n"
    f"• Route Path Jaccard Overlap:  {df_eval['ml_current_route_overlap'].mean()*100:.1f}% with Current-Optimal Path\n"
)

ax.text(0.04, 0.96, summary_text, transform=ax.transAxes, fontsize=11, family='monospace',
        verticalalignment='top', bbox=dict(boxstyle='round,pad=1.0', facecolor='#f8fafc', edgecolor='#cbd5e1', linewidth=2))

plt.tight_layout()
fig.savefig('results/phase8/figures/12_routing_summary.png', bbox_inches='tight')
plt.close(fig)

print("All 12 figures successfully generated and saved to results/phase8/figures/")
print("\n[Step 7/7] Pipeline execution fully complete.")
