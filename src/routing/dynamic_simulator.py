"""Dynamic Edge Simulation Engine for GeoPulse Bhubaneswar.

Implements the VehicleSimulation class that simulates vehicle movement across the
embedded road network, advances physical time, evaluates real-time traffic speeds,
and executes three comparative routing strategies:
  1. Static Baseline (fixed pre-planned free-flow route)
  2. Predictive Pre-Planned (fixed pre-planned route based on ML departure forecast)
  3. Dynamic Edge-Rerouting (live re-evaluation with hysteresis threshold)
"""
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import time

import networkx as nx
import numpy as np
import pandas as pd
import xgboost as xgb

from src.routing.custom_dijkstra import custom_dijkstra

FEATURE_COLS = [
    "hour_sin",
    "hour_cos",
    "day_sin",
    "day_cos",
    "is_weekend_num",
    "freeFlowSpeed",
    "speed_t-1",
    "speed_t-2",
    "speed_t-3",
]


class VehicleSimulation:
    """Simulates vehicle traversal on G_embedded with real-time dynamic rerouting."""

    def __init__(
        self,
        G: Union[nx.MultiDiGraph, nx.DiGraph],
        model: Optional[xgb.XGBRegressor] = None,
        model_path: Optional[Union[str, Path]] = None,
        features_df: Optional[pd.DataFrame] = None,
        features_path: Optional[Union[str, Path]] = None,
        epsilon: float = 60.0,
        alpha: float = 0.0,
        beta: float = 1.0,
    ):
        """Initializes the vehicle simulation environment.

        Parameters
        ----------
        G : nx.MultiDiGraph
            The embedded road graph with is_monitored and segment_id attributes.
        model : xgb.XGBRegressor, optional
            Loaded XGBoost regression model.
        model_path : str or Path, optional
            Path to xgb_speed_model.json if model not provided.
        features_df : pd.DataFrame, optional
            Engineered feature dataframe (ml_features.parquet).
        features_path : str or Path, optional
            Path to ml_features.parquet if features_df not provided.
        epsilon : float, optional
            Hysteresis threshold in seconds to prevent route oscillation (default 60s).
        alpha : float, optional
            Distance cost multiplier (default 0.0 for pure travel-time minimization).
        beta : float, optional
            Travel time cost multiplier (default 1.0).
        """
        self.G = G
        self.epsilon = epsilon
        self.alpha = alpha
        self.beta = beta

        # Load XGBoost Model
        if model is not None:
            self.model = model
        elif model_path is not None:
            self.model = xgb.XGBRegressor()
            self.model.load_model(str(model_path))
        else:
            raise ValueError("Either model or model_path must be provided.")

        # Load Features Data
        if features_df is not None:
            self.feat_df = features_df
        elif features_path is not None:
            self.feat_df = pd.read_parquet(features_path)
            self.feat_df["hour"] = pd.to_datetime(self.feat_df["hour"], utc=True)
        else:
            raise ValueError("Either features_df or features_path must be provided.")

        # Build fast O(1) lookup tables
        print("Indexing features and ground-truth speed lookup table...")
        self.actual_speeds = {}
        for row in self.feat_df[["hour", "segment_id", "currentSpeed"]].itertuples(index=False):
            self.actual_speeds[(row.hour, int(row.segment_id))] = float(row.currentSpeed)

        # Cache for predicted speeds by hour bucket: hour -> {segment_id: predicted_speed}
        self.prediction_cache: Dict[pd.Timestamp, Dict[int, float]] = {}

    def get_predictions_for_hour(self, timestamp: pd.Timestamp) -> Dict[int, float]:
        """Returns predicted speeds for all monitored segments at a specific hour."""
        hour_bucket = timestamp.floor("h")

        if hour_bucket in self.prediction_cache:
            return self.prediction_cache[hour_bucket]

        # Filter feature rows for this hour
        sub = self.feat_df[self.feat_df["hour"] == hour_bucket]
        if not sub.empty:
            X = sub[FEATURE_COLS]
            preds = self.model.predict(X)
            pred_dict = {
                int(sid): max(float(p), 1.0) for sid, p in zip(sub["segment_id"], preds)
            }
        else:
            # Fallback to nearest available hour
            nearest_hours = (self.feat_df["hour"] - hour_bucket).abs().sort_values()
            nearest_hour = self.feat_df.loc[nearest_hours.index[0], "hour"]
            sub = self.feat_df[self.feat_df["hour"] == nearest_hour]
            X = sub[FEATURE_COLS]
            preds = self.model.predict(X)
            pred_dict = {
                int(sid): max(float(p), 1.0) for sid, p in zip(sub["segment_id"], preds)
            }

        self.prediction_cache[hour_bucket] = pred_dict
        return pred_dict

    def get_ground_truth_speed(self, segment_id: int, timestamp: pd.Timestamp) -> float:
        """Returns the actual ground-truth velocity (km/h) for a segment at time t."""
        hour_bucket = timestamp.floor("h")
        key = (hour_bucket, segment_id)
        if key in self.actual_speeds:
            return max(self.actual_speeds[key], 1.0)
        # Fallback to model prediction or free-flow speed
        preds = self.get_predictions_for_hour(timestamp)
        return preds.get(segment_id, 35.0)

    def _get_edge_data(self, u: Any, v: Any) -> Dict[str, Any]:
        """Retrieves best edge data between u and v."""
        if self.G.is_multigraph():
            edge_dict = self.G[u][v]
            # Select edge with smallest length or free_flow_time
            best_k = min(edge_dict.keys(), key=lambda k: edge_dict[k].get("free_flow_time", 9999))
            return edge_dict[best_k]
        return self.G[u][v]

    def _traverse_edge(
        self, u: Any, v: Any, current_time: pd.Timestamp
    ) -> Tuple[float, float, pd.Timestamp]:
        """Calculates actual traversal time and distance, advancing vehicle clock."""
        edge_data = self._get_edge_data(u, v)
        length_m = float(edge_data.get("length", 10.0))

        is_mon = edge_data.get("is_monitored") is True or str(edge_data.get("is_monitored")).lower() == "true"
        sid = edge_data.get("segment_id")

        if is_mon and sid is not None and sid != -1 and sid != "-1":
            actual_speed = self.get_ground_truth_speed(int(sid), current_time)
        else:
            actual_speed = float(edge_data.get("free_flow_speed", 30.0))

        actual_speed = max(actual_speed, 1.0)  # strict floor
        traversal_time_s = length_m / (actual_speed / 3.6)
        new_time = current_time + pd.Timedelta(seconds=traversal_time_s)

        return traversal_time_s, length_m, new_time

    def _compute_remaining_path_cost(
        self, path: List[Any], current_time: pd.Timestamp, speed_dict: Dict[int, float]
    ) -> float:
        """Estimates expected remaining travel time along path using speed_dict."""
        cost = 0.0
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            edge_data = self._get_edge_data(u, v)
            length = float(edge_data.get("length", 10.0))
            is_mon = edge_data.get("is_monitored") is True or str(edge_data.get("is_monitored")).lower() == "true"
            sid = edge_data.get("segment_id")

            if is_mon and sid is not None and int(sid) in speed_dict:
                sp = max(speed_dict[int(sid)], 1.0)
                t = length / (sp / 3.6)
            else:
                t = float(edge_data.get("free_flow_time", length / (30.0 / 3.6)))
            cost += self.alpha * length + self.beta * t
        return cost

    def run_static_baseline(
        self, source: Any, target: Any, departure_time: pd.Timestamp
    ) -> Dict[str, Any]:
        """Strategy 1: Static Dijkstra using static free-flow edge weights."""
        t_start = time.perf_counter()

        # Route once using static free-flow times (no dynamic speeds dict)
        path, _ = custom_dijkstra(self.G, source, target, alpha=self.alpha, beta=self.beta)
        if not path:
            return {"strategy": "static", "success": False, "error": "No path found"}

        current_time = departure_time
        total_time_s = 0.0
        total_distance_m = 0.0

        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            dt, dist, current_time = self._traverse_edge(u, v, current_time)
            total_time_s += dt
            total_distance_m += dist

        latency_ms = (time.perf_counter() - t_start) * 1000.0

        return {
            "strategy": "static",
            "success": True,
            "total_travel_time_seconds": total_time_s,
            "total_distance_meters": total_distance_m,
            "reroute_count": 0,
            "departure_time": departure_time,
            "arrival_time": current_time,
            "compute_latency_ms": latency_ms,
            "path": path,
        }

    def run_predictive_preplanned(
        self, source: Any, target: Any, departure_time: pd.Timestamp
    ) -> Dict[str, Any]:
        """Strategy 2: Pre-planned route using ML forecast at departure hour."""
        t_start = time.perf_counter()

        # Query ML forecast at departure time
        predicted_speeds = self.get_predictions_for_hour(departure_time)

        # Route once at departure using predicted speeds
        path, _ = custom_dijkstra(
            self.G, source, target, alpha=self.alpha, beta=self.beta, edge_speeds_dict=predicted_speeds
        )
        if not path:
            return {"strategy": "predictive", "success": False, "error": "No path found"}

        current_time = departure_time
        total_time_s = 0.0
        total_distance_m = 0.0

        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            dt, dist, current_time = self._traverse_edge(u, v, current_time)
            total_time_s += dt
            total_distance_m += dist

        latency_ms = (time.perf_counter() - t_start) * 1000.0

        return {
            "strategy": "predictive",
            "success": True,
            "total_travel_time_seconds": total_time_s,
            "total_distance_meters": total_distance_m,
            "reroute_count": 0,
            "departure_time": departure_time,
            "arrival_time": current_time,
            "compute_latency_ms": latency_ms,
            "path": path,
        }

    def run_dynamic_edge_rerouting(
        self, source: Any, target: Any, departure_time: pd.Timestamp
    ) -> Dict[str, Any]:
        """Strategy 3: Dynamic Edge-Rerouting with ML updates and hysteresis."""
        t_start = time.perf_counter()

        # Initial route at departure
        predicted_speeds = self.get_predictions_for_hour(departure_time)
        planned_path, _ = custom_dijkstra(
            self.G, source, target, alpha=self.alpha, beta=self.beta, edge_speeds_dict=predicted_speeds
        )
        if not planned_path:
            return {"strategy": "dynamic", "success": False, "error": "No path found"}

        current_time = departure_time
        total_time_s = 0.0
        total_distance_m = 0.0
        reroute_count = 0
        traversed_path = [source]
        curr_node = source
        last_hour_evaluated = departure_time.floor("h")

        # Step node-by-node along planned_path
        while curr_node != target:
            # Check if vehicle entered a new hourly bucket
            curr_hour = current_time.floor("h")
            hour_changed = curr_hour != last_hour_evaluated

            if hour_changed:
                last_hour_evaluated = curr_hour
                latest_speeds = self.get_predictions_for_hour(current_time)

                # Compute remaining cost on current planned path
                remaining_cost = self._compute_remaining_path_cost(
                    planned_path, current_time, latest_speeds
                )

                # Re-run Dijkstra from current_node to target
                new_path, new_cost = custom_dijkstra(
                    self.G, curr_node, target, alpha=self.alpha, beta=self.beta, edge_speeds_dict=latest_speeds
                )

                # Hysteresis check: only reroute if savings exceed epsilon
                if new_path and (new_cost < remaining_cost - self.epsilon):
                    planned_path = new_path
                    reroute_count += 1

            # Advance vehicle to next node in planned_path
            next_node = planned_path[1]
            dt, dist, current_time = self._traverse_edge(curr_node, next_node, current_time)
            total_time_s += dt
            total_distance_m += dist

            traversed_path.append(next_node)
            curr_node = next_node
            planned_path = planned_path[1:]

        latency_ms = (time.perf_counter() - t_start) * 1000.0

        return {
            "strategy": "dynamic",
            "success": True,
            "total_travel_time_seconds": total_time_s,
            "total_distance_meters": total_distance_m,
            "reroute_count": reroute_count,
            "departure_time": departure_time,
            "arrival_time": current_time,
            "compute_latency_ms": latency_ms,
            "path": traversed_path,
        }
