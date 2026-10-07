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
    
    .decision-card-reroute {
        background: #f0fdf4;
        border: 2px solid #22c55e;
        border-radius: 10px;
        padding: 18px 22px;
        margin: 14px 0;
        box-shadow: 0 4px 12px rgba(34, 197, 94, 0.12);
    }
    .decision-card-suppressed {
        background: #f8fafc;
        border: 2px solid #94a3b8;
        border-radius: 10px;
        padding: 18px 22px;
        margin: 14px 0;
        box-shadow: 0 2px 8px rgba(148, 163, 184, 0.1);
    }
    .gate-badge-pass {
        background: #dcfce7;
        color: #15803d;
        font-weight: 800;
        padding: 3px 8px;
        border-radius: 4px;
        border: 1px solid #86efac;
        font-size: 12px;
    }
    .gate-badge-fail {
        background: #fee2e2;
        color: #b91c1c;
        font-weight: 800;
        padding: 3px 8px;
        border-radius: 4px;
        border: 1px solid #fca5a5;
        font-size: 12px;
    }
    .scenario-summary-banner {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-left: 6px solid #0284c7;
        border-radius: 8px;
        padding: 16px 20px;
        margin-bottom: 20px;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04);
    }
    .shared-pattern-banner {
        background: #eff6ff;
        border: 1px solid #bfdbfe;
        border-left: 5px solid #2563eb;
        border-radius: 8px;
        padding: 14px 18px;
        margin-bottom: 20px;
        color: #1e40af;
        font-size: 13px;
        line-height: 1.5;
    }
    .bottleneck-banner {
        background: #fff7ed;
        border: 1px solid #fed7aa;
        border-left: 5px solid #f97316;
        border-radius: 8px;
        padding: 14px 18px;
        margin: 14px 0;
        color: #9a3412;
        font-size: 13px;
    }
    .flow-step {
        display: inline-block;
        background: #f1f5f9;
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        padding: 6px 12px;
        font-size: 11px;
        font-weight: 600;
        color: #334155;
        margin: 2px 4px;
    }
    .flow-arrow {
        color: #94a3b8;
        font-weight: 800;
        margin: 0 2px;
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
    
    run_btn = st.button("▶ RE-RUN PIPELINE", type="primary", use_container_width=True)


# -----------------------------------------------------------------------------
# 3. HEADER & ARCHITECTURE STATUS
# -----------------------------------------------------------------------------
st.markdown("""
<div class="main-header">
    <h1>GEOPULSE — AI-Based Dynamic Traffic Routing System</h1>
    <p>Predictive ML Speed Forecasting • Scratch-Built Custom Dijkstra • Real-Time Edge Degradation Rerouting</p>
</div>
""", unsafe_allow_html=True)


# Detect parameter change to trigger auto-execution on scenario selection
current_exec_params = (
    selected_scenario_id,
    st.session_state.reroute_mode,
    st.session_state.threshold_seconds,
    st.session_state.threshold_percent
)

should_run = (
    run_btn or 
    st.session_state.current_run is None or 
    st.session_state.get('last_executed_params') != current_exec_params
)

if should_run:
    progress_bar = st.progress(0.0)
    status_text = st.empty()

    def update_prog(msg: str, frac: float):
        status_text.markdown(f"**Pipeline Execution:** `{msg}`")
        progress_bar.progress(frac)

    try:
        run_res = run_geopulse_pipeline(
            scenario_id=selected_scenario_id,
            threshold_seconds=st.session_state.threshold_seconds,
            threshold_percent=st.session_state.threshold_percent,
            reroute_mode=st.session_state.reroute_mode,
            progress_callback=update_prog
        )
        set_current_run(run_res)
        st.session_state.last_executed_params = current_exec_params
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
# 3B. SCENARIO SUMMARY & SYSTEM ARCHITECTURE OVERVIEW
# -----------------------------------------------------------------------------
scen_id = run_result['scenario_id']
is_reroute = run_result['reroute_triggered']
status_badge = '<span class="status-badge-reroute">REROUTE TRIGGERED</span>' if is_reroute else '<span class="status-badge-maintain">REROUTE SUPPRESSED</span>'
saving_str = f"Saves {run_result['time_saved_s']:.1f}s (+{run_result['improvement_pct']:.2f}%)" if is_reroute else "Planned Route Maintained (0.0s)"

st.markdown(f"""
<div class="scenario-summary-banner">
    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
        <div>
            <div style="font-size: 18px; font-weight: 800; color: #0f172a;">Scenario #{scen_id:02d} — {run_result['origin_name']} → {run_result['destination_name']}</div>
            <div style="font-size: 13px; color: #475569; margin-top: 5px;">
                <b>Origin:</b> Node {run_result['origin_node']} • <b>Destination:</b> Node {run_result['destination_node']} • 
                <b>Departure:</b> {run_result['departure_timestamp']} ({run_result['period']}) • 
                <b>Decision Point:</b> Node {run_result['decision_node']} (Step {run_result['decision_step']})
            </div>
        </div>
        <div style="text-align: right;">
            {status_badge}
            <div style="font-size: 13px; font-weight: 700; color: #0369a1; margin-top: 4px;">{saving_str}</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# Shared Bottleneck Pattern Banner (Explaining legitimate identical savings across OD #0 and OD #2)
if run_result.get('shared_bottleneck_info', {}).get('detected'):
    st.markdown(f"""
    <div class="shared-pattern-banner">
        <b>ℹ️ SHARED CONGESTION PATTERN DETECTED</b><br/>
        {run_result['shared_bottleneck_info']['explanation']}
    </div>
    """, unsafe_allow_html=True)

# System Architecture Flow Visual
st.markdown("""
<div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 14px; margin-bottom: 20px; text-align: center;">
    <div style="font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 1px; margin-bottom: 6px;">GEOPULSE CLOSED-LOOP ARCHITECTURE PIPELINE</div>
    <span class="flow-step">1. Historical Traffic</span><span class="flow-arrow">→</span>
    <span class="flow-step">2. LightGBM Prediction</span><span class="flow-arrow">→</span>
    <span class="flow-step">3. Dynamic Edge Weights</span><span class="flow-arrow">→</span>
    <span class="flow-step">4. Custom Dijkstra</span><span class="flow-arrow">→</span>
    <span class="flow-step">5. Vehicle Traversal</span><span class="flow-arrow">→</span>
    <span class="flow-step">6. Real-Time Update</span><span class="flow-arrow">→</span>
    <span class="flow-step">7. Dual-Gate Gating</span><span class="flow-arrow">→</span>
    <span class="flow-step">8. Dynamic Reroute / Maintain</span>
</div>
""", unsafe_allow_html=True)

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

    # Visual Legend for Red vs Green Routes (Requirement 3)
    if run_result['reroute_triggered']:
        st.markdown("""
        <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:6px; padding:8px 12px; margin-top:8px; font-size:12px; display:flex; justify-content:space-around; flex-wrap:wrap; gap:8px;">
            <span>🔴 <b style="color:#dc2626;">Original Route / No-Reroute Path</b> (Congested)</span>
            <span>🟢 <b style="color:#16a34a;">GeoPulse Dynamic Route</b> (Optimal Bypass)</span>
            <span>🔵 <b style="color:#0284c7;">Traversed Path</b> (Active Progress)</span>
            <span>⭐ <b style="color:#d97706;">Reroute Decision Point</b></span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:6px; padding:8px 12px; margin-top:8px; font-size:12px; display:flex; justify-content:space-around; flex-wrap:wrap; gap:8px;">
            <span>🛣️ <b style="color:#475569;">Planned Route (Maintained Optimal)</b></span>
            <span>🔵 <b style="color:#0284c7;">Traversed Path</b> (Active Progress)</span>
            <span>⭐ <b style="color:#d97706;">Traffic Evaluation Point</b></span>
        </div>
        """, unsafe_allow_html=True)

    # Congested bottleneck highlight callout (Requirement 4)
    if run_result.get('bottleneck_analysis', {}).get('detected'):
        b_info = run_result['bottleneck_analysis']
        st.markdown(f"""
        <div class="bottleneck-banner">
            <b>⚠️ CONGESTED BOTTLENECK DETECTED: {b_info['corridor_name']}</b><br/>
            Observed Speed: <b>{b_info['observed_speed_kmh']} km/h</b> vs Predicted: <b>{b_info['predicted_speed_kmh']} km/h</b> 
            (Speed Drop: <b>-{b_info['speed_drop_kmh']} km/h / -{b_info['speed_drop_pct']}%</b>) • Traversal Delay Added: <b>+{b_info['delay_added_s']}s</b>.
        </div>
        """, unsafe_allow_html=True)

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
# 6. REROUTING DECISION & OPERATIONAL GATE AUDIT (REQUIREMENTS 5, 6, 8, 9)
# -----------------------------------------------------------------------------
st.markdown("---")
st.markdown("### 🎯 Rerouting Decision & Operational Gate Audit")

gate_data = run_result.get('gate_evaluation', {})
time_pass = gate_data.get('time_gate_pass', False)
pct_pass = gate_data.get('percent_gate_pass', False)
time_badge = '<span class="gate-badge-pass">PASS</span>' if time_pass else '<span class="gate-badge-fail">FAIL</span>'
pct_badge = '<span class="gate-badge-pass">PASS</span>' if pct_pass else '<span class="gate-badge-fail">FAIL</span>'

if run_result['reroute_triggered']:
    st.markdown(f"""
    <div class="decision-card-reroute">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
            <div style="font-size: 14px; font-weight: 800; color: #15803d; text-transform: uppercase; letter-spacing: 0.5px;">
                ✅ REROUTE TRIGGERED — OPERATIONAL GATES SATISFIED
            </div>
            <span class="status-badge-reroute" style="background:#dcfce7; color:#15803d; border-color:#86efac;">
                TIME SAVED: {run_result['time_saved_s']:.2f} s (+{run_result['improvement_pct']:.2f}%)
            </span>
        </div>
        <div style="font-size: 13px; color: #166534; margin: 12px 0 14px 0; line-height: 1.6;">
            <b>Why Did GeoPulse Reroute?</b><br/>
            {run_result.get('reroute_explanation', '')}
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; background: #ffffff; border: 1px solid #bbf7d0; border-radius: 8px; padding: 12px 16px;">
            <div>
                <span style="font-size: 11px; color: #64748b; font-weight: 700;">GATE 1: ABSOLUTE DELAY (ΔT)</span><br/>
                <span style="font-size: 16px; font-weight: 800; color: #0f172a;">{run_result['delta_T_s']:.2f}s</span> 
                <span style="font-size: 12px; color: #475569;">(Req ≥ {run_result['threshold_seconds']:.0f}s)</span> → {time_badge}
            </div>
            <div>
                <span style="font-size: 11px; color: #64748b; font-weight: 700;">GATE 2: RELATIVE GAIN (ΔT%)</span><br/>
                <span style="font-size: 16px; font-weight: 800; color: #0f172a;">{run_result['delta_T_pct']:.2f}%</span> 
                <span style="font-size: 12px; color: #475569;">(Req ≥ {run_result['threshold_percent']:.1f}%)</span> → {pct_badge}
            </div>
            <div>
                <span style="font-size: 11px; color: #64748b; font-weight: 700;">FINAL OPERATIONAL OUTCOME</span><br/>
                <span style="font-size: 16px; font-weight: 800; color: #15803d;">DYNAMIC BYPASS ACTIVE</span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown(f"""
    <div class="decision-card-suppressed">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
            <div style="font-size: 14px; font-weight: 800; color: #334155; text-transform: uppercase; letter-spacing: 0.5px;">
                🛡️ REROUTE SUPPRESSED — PLANNED ROUTE RETAINED
            </div>
            <span class="status-badge-maintain">
                MAINTAIN CURRENT ROUTE
            </span>
        </div>
        <div style="font-size: 13px; color: #475569; margin: 12px 0 14px 0; line-height: 1.6;">
            <b>Why Did GeoPulse Not Reroute?</b><br/>
            {run_result.get('reroute_explanation', '')}
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px 16px;">
            <div>
                <span style="font-size: 11px; color: #64748b; font-weight: 700;">GATE 1: ABSOLUTE DELAY (ΔT)</span><br/>
                <span style="font-size: 16px; font-weight: 800; color: #0f172a;">{run_result['delta_T_s']:.2f}s</span> 
                <span style="font-size: 12px; color: #475569;">(Req ≥ {run_result['threshold_seconds']:.0f}s)</span> → {time_badge}
            </div>
            <div>
                <span style="font-size: 11px; color: #64748b; font-weight: 700;">GATE 2: RELATIVE GAIN (ΔT%)</span><br/>
                <span style="font-size: 16px; font-weight: 800; color: #0f172a;">{run_result['delta_T_pct']:.2f}%</span> 
                <span style="font-size: 12px; color: #475569;">(Req ≥ {run_result['threshold_percent']:.1f}%)</span> → {pct_badge}
            </div>
            <div>
                <span style="font-size: 11px; color: #64748b; font-weight: 700;">FINAL OPERATIONAL OUTCOME</span><br/>
                <span style="font-size: 16px; font-weight: 800; color: #475569;">ROUTE RETENTION (STABLE)</span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 6B. ROUTE COMPARISON TABLE (REQUIREMENT 14)
# -----------------------------------------------------------------------------
if run_result['reroute_triggered']:
    st.markdown("#### 🛣️ Route Comparison Table")
    init_dep_dt = pd.to_datetime(run_result['departure_timestamp'])
    eta_no_reroute = (init_dep_dt + pd.Timedelta(seconds=run_result['no_reroute_total_time_s'])).strftime('%H:%M:%S')
    eta_dynamic = (init_dep_dt + pd.Timedelta(seconds=run_result['dynamic_reroute_total_time_s'])).strftime('%H:%M:%S')

    route_table = pd.DataFrame([
        {
            "Performance Metric": "Directed Route Edges",
            "Original Route (No Reroute)": f"{run_result['initial_route_edges_count']} links",
            "GeoPulse Dynamic Route": f"{run_result['final_route_edges_count']} links",
            "Operational Difference": f"{run_result['final_route_edges_count'] - run_result['initial_route_edges_count']:+d} links"
        },
        {
            "Performance Metric": "Total Distance Traversed",
            "Original Route (No Reroute)": f"{run_result['initial_route_distance_m']:.1f} m ({run_result['initial_route_distance_m']/1000:.2f} km)",
            "GeoPulse Dynamic Route": f"{run_result['final_route_distance_m']:.1f} m ({run_result['final_route_distance_m']/1000:.2f} km)",
            "Operational Difference": f"{run_result['final_route_distance_m'] - run_result['initial_route_distance_m']:+.1f} m"
        },
        {
            "Performance Metric": "Total Travel Time",
            "Original Route (No Reroute)": f"{run_result['no_reroute_total_time_s']:.2f} s ({run_result['no_reroute_total_time_s']/60:.2f} min)",
            "GeoPulse Dynamic Route": f"{run_result['dynamic_reroute_total_time_s']:.2f} s ({run_result['dynamic_reroute_total_time_s']/60:.2f} min)",
            "Operational Difference": f"Time Saved: {run_result['time_saved_s']:.2f} s ({run_result['improvement_pct']:.2f}%)"
        },
        {
            "Performance Metric": "Destination Arrival ETA",
            "Original Route (No Reroute)": eta_no_reroute,
            "GeoPulse Dynamic Route": eta_dynamic,
            "Operational Difference": f"Arrives {run_result['time_saved_s']:.1f}s earlier"
        }
    ])
    st.table(route_table.set_index("Performance Metric"))

# -----------------------------------------------------------------------------
# 6C. RESEARCH-ORIENTED KPI PERFORMANCE SECTION (REQUIREMENT 7)
# -----------------------------------------------------------------------------
st.markdown("---")
st.markdown("### 📊 Research-Oriented KPI Performance Metrics")

kpi_c1, kpi_c2, kpi_c3, kpi_c4 = st.columns(4)

with kpi_c1:
    st.markdown("**Route Performance**")
    st.metric(
        label="No-Reroute Travel Time",
        value=f"{run_result['no_reroute_total_time_s']:.1f} s",
        help="Counterfactual travel time if vehicle continued on initial planned route"
    )
    st.metric(
        label="GeoPulse Travel Time",
        value=f"{run_result['dynamic_reroute_total_time_s']:.1f} s",
        delta=f"-{run_result['time_saved_s']:.1f} s ({run_result['improvement_pct']:.2f}%)" if run_result['reroute_triggered'] else "0.0s (Maintained)",
        delta_color="normal"
    )

with kpi_c2:
    st.markdown("**Spatial Route Metrics**")
    st.metric(
        label="Initial Route Distance",
        value=f"{run_result['initial_route_distance_m']/1000:.2f} km",
        help=f"{run_result['initial_route_edges_count']} directed road links"
    )
    st.metric(
        label="Final Route Distance",
        value=f"{run_result['final_route_distance_m']/1000:.2f} km",
        delta=f"Overlap: {run_result['route_overlap']*100:.1f}%",
        delta_color="off"
    )

with kpi_c3:
    st.markdown("**ML Model & Speeds**")
    st.metric(
        label="Predicted Corridor Speed",
        value=f"{run_result['speed_metrics']['predicted_speed_kmh']} km/h",
        help="Pre-trip speed forecasted by LightGBM model"
    )
    st.metric(
        label="Observed Sensor Speed",
        value=f"{run_result['speed_metrics']['observed_speed_kmh']} km/h",
        delta=f"-{run_result['speed_metrics']['speed_drop_pct']}% Drop",
        delta_color="inverse"
    )

with kpi_c4:
    st.markdown("**Software Execution Latency**")
    exec_dict = run_result['execution_times_ms']
    st.metric(
        label="Total Pipeline Decision",
        value=f"{exec_dict['total_edge_decision_ms']:.2f} ms",
        help="Includes traffic ingest, custom Dijkstra reroute, and gate checks"
    )
    st.metric(
        label="Reroute Dijkstra Latency",
        value=f"{exec_dict['edge_reroute_dijkstra_ms']:.2f} ms",
        delta=f"Initial: {exec_dict['edge_initial_dijkstra_ms']:.1f} ms",
        delta_color="off"
    )

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
