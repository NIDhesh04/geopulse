"""
GeoPulse Phase 11B: Interactive Demonstration Dashboard
Master Streamlit Application for Live Pipeline Demonstration

Usage:
    streamlit run scripts/run_phase11_dashboard.py
"""

import os
import sys
import json
import time
from datetime import datetime
import pandas as pd
import streamlit as st

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath('.'))

from src.dashboard.backend import (
    load_graph_and_mappings,
    get_scenario_catalog,
    run_geopulse_pipeline,
    export_run_results
)
from src.dashboard.visualization import (
    render_route_map_matplotlib,
    create_pydeck_map,
    render_journey_timeline_figure,
    get_step_simulation_status
)
from src.dashboard.state import (
    init_session_state,
    set_current_run,
    step_forward,
    step_backward,
    reset_playback,
    jump_to_decision,
    jump_to_destination
)


# -----------------------------------------------------------------------------
# 1. PAGE CONFIGURATION & STYLING
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="GeoPulse — Interactive Live Demonstration Dashboard",
    page_icon="🚦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for rich aesthetics and clean typography
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    .main-header {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0369a1 100%);
        color: white;
        padding: 24px 32px;
        border-radius: 12px;
        margin-bottom: 24px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
    }
    .main-header h1 {
        margin: 0;
        font-size: 28px;
        font-weight: 800;
        letter-spacing: -0.5px;
        color: #ffffff;
    }
    .main-header p {
        margin: 6px 0 0 0;
        font-size: 14px;
        color: #94a3b8;
        font-weight: 500;
    }
    
    .arch-card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 12px 16px;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .arch-card-active {
        background: #f0fdf4;
        border: 1px solid #86efac;
        border-radius: 8px;
        padding: 12px 16px;
        text-align: center;
        box-shadow: 0 2px 8px rgba(16, 185, 129, 0.15);
    }
    
    .metric-hero {
        background: #f0fdf4;
        border-left: 5px solid #10b981;
        padding: 16px 20px;
        border-radius: 6px;
        margin: 12px 0;
    }
    
    .status-badge-reroute {
        background: #fee2e2;
        color: #991b1b;
        font-weight: 700;
        padding: 4px 10px;
        border-radius: 6px;
        display: inline-block;
        border: 1px solid #f87171;
    }
    .status-badge-maintain {
        background: #dcfce7;
        color: #166534;
        font-weight: 700;
        padding: 4px 10px;
        border-radius: 6px;
        display: inline-block;
        border: 1px solid #86efac;
    }
    
    .stButton>button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.2s ease;
    }
    .stButton>button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    }
</style>
""", unsafe_allow_html=True)

init_session_state()

# -----------------------------------------------------------------------------
# 2. SIDEBAR: SCENARIO CONTROLS
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🚦 GeoPulse Navigation Engine")
    st.caption("AI-Based Dynamic Traffic Routing Prototype")
    st.markdown("---")

    catalog = get_scenario_catalog()
    
    demo_mode = st.radio(
        "Demonstration Mode",
        options=["Mode A — Guided Demo", "Mode B — Explore Scenarios"],
        index=0 if st.session_state.selected_mode == "Mode A — Guided Demo" else 1,
        help="Mode A runs the canonical Evening Peak scenario. Mode B allows selecting from 20 benchmark OD pairs & diurnal periods."
    )
    st.session_state.selected_mode = demo_mode

    if demo_mode == "Mode A — Guided Demo":
        st.info("⭐ **Guided Demo**: Canonical Evening Peak Scenario (OD #0: Khandagiri Square → Rasulgarh Square). Validated to reproduce 84.9s (6.60%) time saving.")
        selected_scenario_id = 0
    else:
        st.markdown("#### Scenario Selection")
        
        # Diurnal period filter
        periods = sorted(list(set(c['period'] for c in catalog)))
        selected_period = st.selectbox("Operational Period", ["All Periods"] + periods, index=0)
        
        filtered_catalog = catalog
        if selected_period != "All Periods":
            filtered_catalog = [c for c in catalog if c['period'] == selected_period]

        scenario_options = {c['scenario_id']: c['label'] for c in filtered_catalog}
        
        selected_scenario_id = st.selectbox(
            "Select Benchmark Scenario",
            options=list(scenario_options.keys()),
            format_func=lambda x: scenario_options[x],
            index=0
        )

    st.session_state.selected_scenario_id = selected_scenario_id
    scenario_info = next(c for c in catalog if c['scenario_id'] == selected_scenario_id)

    st.markdown("---")
    st.markdown("#### Routing Configuration")
    
    reroute_mode = st.selectbox(
        "Rerouting Policy",
        options=["GeoPulse Dual Threshold", "No Reroute"],
        index=0,
        help="Default GeoPulse Dual Threshold triggers rerouting only if ΔT ≥ 10s AND ΔT% ≥ 3%."
    )
    st.session_state.reroute_mode = reroute_mode

    # Advanced threshold configuration
    with st.expander("⚙️ Advanced / Experimental Settings", expanded=False):
        st.caption("Operational Gates (Validated default: 10s + 3%)")
        th_s = st.slider("Absolute Gate ΔT (seconds)", min_value=0.0, max_value=60.0, value=10.0, step=1.0)
        th_pct = st.slider("Relative Gate ΔT% (percent)", min_value=0.0, max_value=20.0, value=3.0, step=0.5)
        st.session_state.threshold_seconds = th_s
        st.session_state.threshold_percent = th_pct

    st.markdown("---")
    
    # Presentation Mode Toggle
    pres_mode = st.toggle("📺 Presentation Mode", value=st.session_state.presentation_mode,
                          help="Optimizes UI for projector screen defense: high contrast, enlarged key cards, cleaner layout.")
    st.session_state.presentation_mode = pres_mode

    # Map Rendering Toggle
    map_renderer = st.radio(
        "Map Display Engine",
        options=["Matplotlib High-Res Road Network", "Pydeck Interactive 3D/2D GIS Map"],
        index=0 if st.session_state.map_renderer == "Matplotlib High-Res Road Network" else 1
    )
    st.session_state.map_renderer = map_renderer

    st.markdown("---")
    
    run_btn = st.button("▶ RUN GEOPULSE", type="primary", use_container_width=True)


# -----------------------------------------------------------------------------
# 3. HEADER & ARCHITECTURE STATUS
# -----------------------------------------------------------------------------
st.markdown("""
<div class="main-header">
    <h1>GEOPULSE — AI-Based Dynamic Traffic Routing System</h1>
    <p>Predictive ML Speed Forecasting • Scratch-Built Custom Dijkstra • Real-Time Edge Degradation Rerouting</p>
</div>
""", unsafe_allow_html=True)


# Execute pipeline on Run button click
if run_btn or st.session_state.current_run is None:
    progress_bar = st.progress(0.0)
    status_text = st.empty()

    def update_prog(msg: str, frac: float):
        status_text.markdown(f"**Pipeline Execution:** `{msg}`")
        progress_bar.progress(frac)

    try:
        run_res = run_geopulse_pipeline(
            scenario_id=st.session_state.selected_scenario_id,
            threshold_seconds=st.session_state.threshold_seconds,
            threshold_percent=st.session_state.threshold_percent,
            reroute_mode=st.session_state.reroute_mode,
            progress_callback=update_prog
        )
        set_current_run(run_res)
        # Persist to disk
        json_p, csv_p = export_run_results(run_res)
        status_text.empty()
        progress_bar.empty()
    except Exception as e:
        st.error(f"Error running GeoPulse pipeline: {str(e)}")
        with st.expander("Technical Error Details"):
            st.exception(e)
        st.stop()

run_result = st.session_state.current_run

# -----------------------------------------------------------------------------
# 4. EDGE-CLOUD ARCHITECTURE STATUS STRIP
# -----------------------------------------------------------------------------
step_telemetry = get_step_simulation_status(run_result, st.session_state.vehicle_step)
current_step = step_telemetry['step']
decision_step = run_result['decision_step']
reroute_triggered = run_result['reroute_triggered']

arch_c1, arch_c2, arch_c3 = st.columns(3)

with arch_c1:
    st.markdown("""
    <div class="arch-card">
        <div style="font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 1px;">CENTRALIZED TIER</div>
        <div style="font-size: 16px; font-weight: 800; color: #0284c7; margin-top: 4px;">☁️ CLOUD MODEL SERVICE</div>
        <div style="font-size: 12px; color: #334155; margin-top: 4px;">LightGBM Regressor (25 Features)</div>
        <div style="font-size: 11px; color: #16a34a; font-weight: 600; margin-top: 2px;">● Broadcast Ready (700 Links)</div>
    </div>
    """, unsafe_allow_html=True)

with arch_c2:
    edge_active = (current_step == decision_step)
    cls = "arch-card-active" if edge_active else "arch-card"
    status_msg = "● Reroute Triggered & Dispatched" if (current_step >= decision_step and reroute_triggered) else "● Regional Monitoring Active"
    color_st = "#16a34a" if not edge_active else "#dc2626"
    st.markdown(f"""
    <div class="{cls}">
        <div style="font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 1px;">REGIONAL TIER</div>
        <div style="font-size: 16px; font-weight: 800; color: #0f172a; margin-top: 4px;">🏢 EDGE SERVER</div>
        <div style="font-size: 12px; color: #334155; margin-top: 4px;">Custom Dijkstra & Degradation Audit</div>
        <div style="font-size: 11px; color: {color_st}; font-weight: 600; margin-top: 2px;">{status_msg}</div>
    </div>
    """, unsafe_allow_html=True)

with arch_c3:
    veh_status = "Arrived at Destination" if current_step == step_telemetry['total_steps'] else f"Traversing Segment {current_step}/{step_telemetry['total_steps']}"
    st.markdown(f"""
    <div class="arch-card">
        <div style="font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 1px;">CLIENT TIER</div>
        <div style="font-size: 16px; font-weight: 800; color: #2563eb; margin-top: 4px;">🚗 CONNECTED VEHICLE</div>
        <div style="font-size: 12px; color: #334155; margin-top: 4px;">Telemetry & Dynamic Waypoint Navigation</div>
        <div style="font-size: 11px; color: #0284c7; font-weight: 600; margin-top: 2px;">● {veh_status}</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<div style='margin-bottom: 16px;'></div>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 5. MAIN ROUTE MAP & VEHICLE PLAYBACK CONTROLS
# -----------------------------------------------------------------------------
map_col, sim_col = st.columns([7, 3])

with map_col:
    st.markdown(f"#### 🗺️ Bhubaneswar Road Network Route Map")
    
    # Load graph once
    G, _, _ = load_graph_and_mappings()

    if st.session_state.map_renderer == "Matplotlib High-Res Road Network":
        fig_map = render_route_map_matplotlib(
            G=G,
            run_result=run_result,
            current_step=st.session_state.vehicle_step,
            dark_mode=False
        )
        st.pyplot(fig_map, use_container_width=True)
    else:
        deck = create_pydeck_map(
            G=G,
            run_result=run_result,
            current_step=st.session_state.vehicle_step
        )
        st.pydeck_chart(deck, use_container_width=True)

with sim_col:
    st.markdown("#### 🎮 Vehicle Simulation Controls")
    st.caption("Step through the vehicle's physical journey along the network links.")

    # Playback buttons
    b_c1, b_c2, b_c3 = st.columns(3)
    with b_c1:
        if st.button("⏪ Reset", use_container_width=True):
            reset_playback()
            st.rerun()
    with b_c2:
        if st.button("◀ Step", use_container_width=True):
            step_backward()
            st.rerun()
    with b_c3:
        if st.button("▶ Step", type="primary", use_container_width=True):
            step_forward()
            st.rerun()

    j_c1, j_c2 = st.columns(2)
    with j_c1:
        if st.button("⚡ Traffic Update", use_container_width=True, help="Jump directly to the traffic update decision point"):
            jump_to_decision()
            st.rerun()
    with j_c2:
        if st.button("🏁 Destination", use_container_width=True, help="Jump directly to trip completion"):
            jump_to_destination()
            st.rerun()

    # Scrubber slider
    max_steps = step_telemetry['total_steps']
    new_step = st.slider(
        "Journey Step Scrubber",
        min_value=0,
        max_value=max_steps,
        value=st.session_state.vehicle_step,
        help="Drag to inspect vehicle position and route state at any discrete step."
    )
    if new_step != st.session_state.vehicle_step:
        st.session_state.vehicle_step = new_step
        st.rerun()

    # Dynamic status alert container
    alert_lvl = step_telemetry['alert_level']
    banner = step_telemetry['status_banner']
    if alert_lvl == "warning":
        st.warning(banner)
    elif alert_lvl == "success":
        st.success(banner)
    else:
        st.info(banner)

    st.markdown(f"""
    **Current Node:** `{run_result['final_route_nodes'][min(current_step, len(run_result['final_route_nodes'])-1)]}`  
    **Traversed Distance:** `{round((run_result['final_route_distance_m'] * (current_step/max_steps if max_steps else 0))/1000, 2)} km`  
    **Journey Progress:** `{step_telemetry['progress_pct']}%`  
    **Decision Point:** `Node {run_result['decision_node']} (Step {decision_step})`  
    """)

    if current_step >= decision_step and reroute_triggered:
        st.markdown("""
        <div style="background:#fef2f2; border:1px solid #f87171; border-radius:6px; padding:10px; font-size:12px; color:#991b1b;">
            <b>Reroute Directive Active:</b> Vehicle abandoned the downstream congested corridor (red dashed) and transitioned into the dynamic bypass (emerald solid).
        </div>
        """, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 6. LIVE METRIC CARDS
# -----------------------------------------------------------------------------
st.markdown("---")
st.markdown("### 📊 Live Pipeline Performance Metrics")

m_c1, m_c2, m_c3, m_c4 = st.columns(4)

with m_c1:
    st.markdown("**ML Speed Prediction**")
    st.metric(
        label="Predicted Corridor Speed",
        value=f"{run_result['speed_metrics']['predicted_speed_kmh']} km/h",
        delta=None
    )
    st.metric(
        label="Observed Sensor Speed",
        value=f"{run_result['speed_metrics']['observed_speed_kmh']} km/h",
        delta=f"-{run_result['speed_metrics']['speed_drop_pct']}% Drop",
        delta_color="inverse"
    )

with m_c2:
    st.markdown("**Routing ETAs**")
    st.metric(
        label="Initial Planned ETA",
        value=f"{run_result['eta_metrics']['initial_route_eta_s']/60:.2f} min",
        help="ETA computed using LightGBM predicted link weights at departure"
    )
    st.metric(
        label="Current Path Remaining ETA",
        value=f"{run_result['eta_metrics']['current_remaining_eta_s']:.1f} s",
        help="Estimated time remaining on original route under observed congested speeds"
    )

with m_c3:
    st.markdown("**Alternative Route**")
    st.metric(
        label="Alternative Bypass ETA",
        value=f"{run_result['eta_metrics']['optimal_alternative_eta_s']:.1f} s",
        help="Optimal alternative route computed from decision point using custom Dijkstra"
    )
    st.metric(
        label="Absolute Saving (ΔT)",
        value=f"{run_result['delta_T_s']:.1f} s",
        delta=f"{run_result['delta_T_pct']:.1f}% relative",
        delta_color="normal"
    )

with m_c4:
    st.markdown("**Rerouting Decision**")
    st.markdown(f"**Dual Gate:** `ΔT ≥ {run_result['threshold_seconds']:.0f}s & ΔT% ≥ {run_result['threshold_percent']:.1f}%`")
    if run_result['reroute_triggered']:
        st.markdown('<div class="status-badge-reroute">TRIGGER DYNAMIC REROUTE</div>', unsafe_allow_html=True)
        st.caption(f"Reason: Potential saving ({run_result['delta_T_s']:.1f}s, {run_result['delta_T_pct']:.1f}%) crossed both operational thresholds.")
    else:
        st.markdown('<div class="status-badge-maintain">MAINTAIN ROUTE</div>', unsafe_allow_html=True)
        st.caption(f"Reason: Traffic degradation ({run_result['delta_T_s']:.1f}s, {run_result['delta_T_pct']:.1f}%) stayed below operational thresholds.")

# -----------------------------------------------------------------------------
# 7. FINAL COMPARATIVE RESULT PANEL
# -----------------------------------------------------------------------------
st.markdown("---")
st.markdown("### 🏆 Final Journey Outcome & Comparative Audit")

res_col1, res_col2 = st.columns([6, 4])

with res_col1:
    comp_df = pd.DataFrame([
        {
            "Performance Metric": "Total Travel Time",
            "Strategy A (No Reroute)": f"{run_result['no_reroute_total_time_s']:.1f} s ({run_result['no_reroute_total_time_s']/60:.2f} min)",
            "Strategy B (GeoPulse)": f"{run_result['dynamic_reroute_total_time_s']:.1f} s ({run_result['dynamic_reroute_total_time_s']/60:.2f} min)",
            "Net Benefit": f"-{run_result['time_saved_s']:.1f} s (-{run_result['time_saved_s']/60:.2f} min)" if run_result['reroute_triggered'] else "0.0 s"
        },
        {
            "Performance Metric": "Route Traversal Distance",
            "Strategy A (No Reroute)": f"{run_result['initial_route_distance_m']/1000:.2f} km",
            "Strategy B (GeoPulse)": f"{run_result['final_route_distance_m']/1000:.2f} km",
            "Net Benefit": f"{round((run_result['final_route_distance_m'] - run_result['initial_route_distance_m'])/1000, 2):+0.2f} km"
        },
        {
            "Performance Metric": "Road Network Segments",
            "Strategy A (No Reroute)": f"{run_result['initial_route_edges_count']} directed links",
            "Strategy B (GeoPulse)": f"{run_result['final_route_edges_count']} directed links",
            "Net Benefit": f"{run_result['final_route_edges_count'] - run_result['initial_route_edges_count']:+d} links"
        },
        {
            "Performance Metric": "Spatial Path Overlap",
            "Strategy A (No Reroute)": "100.0%",
            "Strategy B (GeoPulse)": f"{run_result['route_overlap']*100:.1f}%",
            "Net Benefit": f"{round((1.0 - run_result['route_overlap'])*100, 1):.1f}% Divergence"
        }
    ])
    st.table(comp_df.set_index("Performance Metric"))

with res_col2:
    if run_result['reroute_triggered']:
        st.markdown(f"""
        <div class="metric-hero">
            <div style="font-size: 13px; font-weight: 700; color: #166534; text-transform: uppercase;">Time Saved via Dynamic Rerouting</div>
            <div style="font-size: 34px; font-weight: 800; color: #15803d; margin-top: 4px;">{run_result['time_saved_s']:.2f} seconds</div>
            <div style="font-size: 16px; font-weight: 600; color: #166534; margin-top: 4px;">+{run_result['improvement_pct']:.2f}% Journey Improvement ({run_result['time_saved_s']/60:.2f} min)</div>
            <div style="font-size: 12px; color: #374151; margin-top: 8px;">
                Initial predictive route avoided downstream bottleneck, saving critical transit time in peak traffic.
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="background: #f8fafc; border-left: 5px solid #64748b; padding: 16px 20px; border-radius: 6px; margin: 12px 0;">
            <div style="font-size: 13px; font-weight: 700; color: #334155; text-transform: uppercase;">No Reroute Required</div>
            <div style="font-size: 24px; font-weight: 800; color: #1e293b; margin-top: 4px;">Route Retained</div>
            <div style="font-size: 13px; color: #475569; margin-top: 8px;">
                Traffic degradation (ΔT = {run_result['delta_T_s']:.1f}s) did not breach the dual threshold gates ({run_result['threshold_seconds']:.0f}s & {run_result['threshold_percent']:.1f}%). 
                Suppression prevented unnecessary route churn.
            </div>
        </div>
        """, unsafe_allow_html=True)

    # Canonical Validation Indicator
    if run_result['is_canonical']:
        if run_result['canonical_match']:
            st.success("✅ **Parity Verified**: Results match canonical Phase 11 benchmark (84.91s saving, +6.60% improvement).")
        else:
            st.warning(f"⚠️ **Discrepancy Detected**: {run_result['discrepancy_msg']}")

# -----------------------------------------------------------------------------
# 8. JOURNEY TIMELINE
# -----------------------------------------------------------------------------
st.markdown("---")
st.markdown("### ⏱️ Chronological Journey Milestone Timeline")
fig_tl = render_journey_timeline_figure(run_result)
st.pyplot(fig_tl, use_container_width=True)

# -----------------------------------------------------------------------------
# 9. PROTOTYPE SOFTWARE EXECUTION TIMES (EXPANDABLE)
# -----------------------------------------------------------------------------
with st.expander("⏱️ Prototype Software Execution Times (Measured Latency)", expanded=False):
    st.info("ℹ️ **Label**: Prototype software execution time on local test hardware. (Not real-world physical edge network transmission latency).")
    
    exec_dict = run_result['execution_times_ms']
    exec_df = pd.DataFrame([
        {"Pipeline Subsystem": "Cloud Model Broadcast Generation", "Software Execution Time (ms)": exec_dict['cloud_prediction_broadcast_ms'], "Architecture Tier": "Cloud"},
        {"Pipeline Subsystem": "Edge Weight Synthesis", "Software Execution Time (ms)": exec_dict['edge_weight_synthesis_ms'], "Architecture Tier": "Edge Server"},
        {"Pipeline Subsystem": "Edge Initial Dijkstra Computation", "Software Execution Time (ms)": exec_dict['edge_initial_dijkstra_ms'], "Architecture Tier": "Edge Server"},
        {"Pipeline Subsystem": "Edge Sensor Telemetry Ingestion", "Software Execution Time (ms)": exec_dict['edge_traffic_ingest_ms'], "Architecture Tier": "Edge Server"},
        {"Pipeline Subsystem": "Edge Re-routing Dijkstra Solver", "Software Execution Time (ms)": exec_dict['edge_reroute_dijkstra_ms'], "Architecture Tier": "Edge Server"},
        {"Pipeline Subsystem": "Edge Threshold Decision Logic", "Software Execution Time (ms)": exec_dict['edge_decision_evaluation_ms'], "Architecture Tier": "Edge Server"},
        {"Pipeline Subsystem": "Total Edge Server Decision Latency", "Software Execution Time (ms)": exec_dict['total_edge_decision_ms'], "Architecture Tier": "Edge Server"}
    ])
    st.dataframe(exec_df, use_container_width=True, hide_index=True)

# -----------------------------------------------------------------------------
# 10. RESULTS EXPORT & DOWNLOAD
# -----------------------------------------------------------------------------
st.markdown("---")
st.markdown("### 💾 Export & Download Demonstration Artifacts")

# Prepare export payloads
clean_export = dict(run_result)
clean_export['initial_route_edges'] = [list(e) for e in clean_export['initial_route_edges']]
clean_export['final_route_edges'] = [list(e) for e in clean_export['final_route_edges']]
json_str = json.dumps(clean_export, indent=2)

df_tl = pd.DataFrame(run_result.get('timeline', []))
csv_str = df_tl.to_csv(index=False)

d_c1, d_c2, d_c3 = st.columns([3, 3, 4])
with d_c1:
    st.download_button(
        label="📥 Download Run Results (JSON)",
        data=json_str,
        file_name=f"geopulse_run_scenario_{run_result['scenario_id']}.json",
        mime="application/json",
        use_container_width=True
    )
with d_c2:
    st.download_button(
        label="📥 Download Timeline (CSV)",
        data=csv_str,
        file_name=f"geopulse_timeline_scenario_{run_result['scenario_id']}.csv",
        mime="text/csv",
        use_container_width=True
    )
with d_c3:
    st.caption("All interactive runs are automatically saved to `results/dashboard_runs/` with unique execution timestamps.")
