"""
GeoPulse Phase 11: Edge-Cloud Logical Architecture Message Protocol

Defines the message schemas exchanged between the logical layers:
  Cloud  <--->  Edge Server  <--->  Vehicle Simulator
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Any, Optional


@dataclass
class ModelUpdateMessage:
    """Dispatched from Cloud to Edge to broadcast model metadata and predictions."""
    model_version: str
    feature_metadata: Dict[str, Any]
    prediction_timestamp: str
    predicted_speeds: Dict[int, float]
    total_segments: int


@dataclass
class PositionUpdateMessage:
    """Dispatched from Vehicle to Edge to report real-time telemetry and traversal status."""
    vehicle_id: str
    current_node: str
    current_edge: Optional[Tuple[str, str, int]]
    edge_index: int
    progress_pct: float
    elapsed_time_s: float
    timestamp: str


@dataclass
class TrafficUpdateMessage:
    """Dispatched from Traffic Sensor Ingestion to Edge to report actual observed road conditions."""
    timestamp: str
    observed_speeds: Dict[int, float]
    sensor_count: int


@dataclass
class RouteUpdateMessage:
    """Dispatched from Edge to Vehicle to deliver initial guidance or dynamic detour."""
    vehicle_id: str
    node_path: List[str]
    edge_path: List[Tuple[str, str, int]]
    total_cost_s: float
    is_reroute: bool
    saving_s: float
    saving_pct: float
    reason: str


@dataclass
class ArchitectureEvent:
    """Logs an inter-component transaction with software execution timing."""
    event_id: int
    timestamp: str
    source_component: str
    target_component: str
    message_type: str
    summary: str
    execution_time_ms: float
