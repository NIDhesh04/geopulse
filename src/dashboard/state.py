"""
GeoPulse Phase 11B: Dashboard Session State Management

Manages simulation playback state, active scenario selection,
presentation mode, and UI toggles across Streamlit reruns.
"""

from typing import Dict, Any, Optional
import streamlit as st


def init_session_state():
    """Initializes all necessary session state variables with sensible defaults."""
    if 'current_run' not in st.session_state:
        st.session_state.current_run = None

    if 'vehicle_step' not in st.session_state:
        st.session_state.vehicle_step = 0

    if 'auto_play' not in st.session_state:
        st.session_state.auto_play = False

    if 'presentation_mode' not in st.session_state:
        st.session_state.presentation_mode = False

    if 'selected_mode' not in st.session_state:
        st.session_state.selected_mode = "Mode A — Guided Demo"

    if 'selected_scenario_id' not in st.session_state:
        st.session_state.selected_scenario_id = 0

    if 'reroute_mode' not in st.session_state:
        st.session_state.reroute_mode = "GeoPulse Dual Threshold"

    if 'threshold_seconds' not in st.session_state:
        st.session_state.threshold_seconds = 10.0

    if 'threshold_percent' not in st.session_state:
        st.session_state.threshold_percent = 3.0

    if 'map_renderer' not in st.session_state:
        st.session_state.map_renderer = "Matplotlib High-Res Road Network"

    if 'last_executed_params' not in st.session_state:
        st.session_state.last_executed_params = None


def set_current_run(run_result: Dict[str, Any], params: Optional[Any] = None, *args, **kwargs):
    """Stores a newly executed run result, synchronizes executed parameters, and resets playback to step 0."""
    st.session_state.current_run = run_result
    st.session_state.vehicle_step = 0
    st.session_state.auto_play = False
    if params is not None:
        st.session_state.last_executed_params = params
    elif 'params' in kwargs:
        st.session_state.last_executed_params = kwargs['params']
    elif len(args) > 0:
        st.session_state.last_executed_params = args[0]
    elif run_result is not None:
        st.session_state.last_executed_params = (
            run_result.get('scenario_id', 0),
            run_result.get('reroute_mode', 'GeoPulse Dual Threshold'),
            run_result.get('threshold_seconds', 10.0),
            run_result.get('threshold_percent', 3.0)
        )


def step_forward():
    """Advances vehicle simulation by 1 edge step."""
    if st.session_state.current_run is not None:
        edges = st.session_state.current_run['final_route_edges'] if st.session_state.current_run['reroute_triggered'] else st.session_state.current_run['initial_route_edges']
        max_step = len(edges)
        if st.session_state.vehicle_step < max_step:
            st.session_state.vehicle_step += 1


def step_backward():
    """Moves vehicle simulation backward by 1 edge step."""
    if st.session_state.vehicle_step > 0:
        st.session_state.vehicle_step -= 1


def reset_playback():
    """Resets vehicle simulation back to origin (Step 0)."""
    st.session_state.vehicle_step = 0
    st.session_state.auto_play = False


def jump_to_decision():
    """Jumps simulation directly to the traffic update decision step."""
    if st.session_state.current_run is not None:
        st.session_state.vehicle_step = st.session_state.current_run['decision_step']


def jump_to_destination():
    """Jumps simulation to the final trip destination."""
    if st.session_state.current_run is not None:
        edges = st.session_state.current_run['final_route_edges'] if st.session_state.current_run['reroute_triggered'] else st.session_state.current_run['initial_route_edges']
        st.session_state.vehicle_step = len(edges)
