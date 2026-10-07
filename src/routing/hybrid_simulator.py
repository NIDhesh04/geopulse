"""Hybrid Vehicle Simulation Engine (ML Pre-Planning + Roadside Edge Computing).

Implements the HybridVehicleSimulation class:
1. Global Prediction (ML): Uses trained XGBoost model to predict city-wide edge speeds
   and plans the initial optimal route from source to destination via Custom Dijkstra.
2. Local Reality Check (Edge Computing): As the vehicle approaches each node, it queries
   a roadside Edge Server (HTTP GET /get_speed on port 8000) for real-time traffic speeds
   on the immediate next road segment(s).
3. Compare-and-Adjust: If the edge server reports actual congestion significantly worse
   than predicted (delay > delay_threshold, e.g. 45s), triggers dynamic Dijkstra replanning.
4. Graceful Fails: Automatically falls back to ML predictions if the edge server drops.

Outputs:
  Travel time, distance, reroute count, compute latency, and final traversed node path.
"""
from datetime import datetime
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import networkx as nx
import numpy as np
import pandas as pd
import requests
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


class HybridVehicleSimulation:
    """Hybrid ML + Edge Computing Vehicle Simulation Engine."""

    def __init__(
        self,
        G: Union[nx.MultiDiGraph, nx.DiGraph],
        model: Optional[xgb.XGBRegressor] = None,
        model_path: Optional[Union[str, Path]] = None,
        features_df: Optional[pd.DataFrame] = None,
        features_path: Optional[Union[str, Path]] = None,
        edge_server_url: str = "http://127.0.0.1:8000",
        delay_threshold_seconds: float = 45.0,
        alpha: float = 0.0,
        beta: float = 1.0,
        api_timeout_seconds: float = 0.5,
    ):
        """Initializes the hybrid simulation environment.

        Parameters
        ----------
        G : nx.MultiDiGraph
            The embedded road graph with is_monitored and segment_id attributes.
        model : xgb.XGBRegressor, optional
            Trained XGBoost speed regression model.
        model_path : str or Path, optional
            Path to xgb_speed_model.json.
        features_df : pd.DataFrame, optional
            Supervised feature dataframe.
        features_path : str or Path, optional
            Path to ml_features.parquet.
        edge_server_url : str, optional
            Base URL for the roadside edge server (default http://127.0.0.1:8000).
        delay_threshold_seconds : float, optional
            Hysteresis threshold: replan triggered only if unexpected delay > this value.
        alpha : float, optional
            Distance weight in Dijkstra cost (default 0.0).
        beta : float, optional
            Travel time weight in Dijkstra cost (default 1.0).
        api_timeout_seconds : float, optional
            Timeout for Edge API requests before graceful fallback (default 0.5s).
        """
        self.G = G
        self.edge_server_url = edge_server_url.rstrip("/")
        self.delay_threshold_seconds = delay_threshold_seconds
        self.alpha = alpha
        self.beta = beta
        self.api_timeout = api_timeout_seconds

        # 1. Load ML Model
        if model is not None:
            self.model = model
        elif model_path is not None:
            self.model = xgb.XGBRegressor()
            self.model.load_model(str(model_path))
        else:
            raise ValueError("Either model or model_path must be provided.")

        # 2. Load Features Data
        if features_df is not None:
            self.feat_df = features_df
        elif features_path is not None:
            self.feat_df = pd.read_parquet(features_path)
            self.feat_df["hour"] = pd.to_datetime(self.feat_df["hour"], utc=True)
        else:
            raise ValueError("Either features_df or features_path must be provided.")

        # Fast O(1) in-memory table for fallback ground truth speeds: (hour, segment_id) -> speed
        self.actual_speeds = {}
        for row in self.feat_df[["hour", "segment_id", "currentSpeed"]].itertuples(index=False):
            self.actual_speeds[(row.hour, int(row.segment_id))] = float(row.currentSpeed)

        # Cache for predicted speeds by hour bucket
        self.prediction_cache: Dict[pd.Timestamp, Dict[int, float]] = {}

    def get_predictions_for_hour(self, timestamp: pd.Timestamp) -> Dict[int, float]:
        """Returns city-wide ML speed predictions for all 700 monitored segments at a specific hour."""
        hour_bucket = timestamp.floor("h")
        if hour_bucket in self.prediction_cache:
            return dict(self.prediction_cache[hour_bucket])

        sub = self.feat_df[self.feat_df["hour"] == hour_bucket]
        if not sub.empty:
            X = sub[FEATURE_COLS]
            preds = self.model.predict(X)
            pred_dict = {int(sid): max(float(p), 1.0) for sid, p in zip(sub["segment_id"], preds)}
        else:
            nearest_hours = (self.feat_df["hour"] - hour_bucket).abs().sort_values()
            nearest_hour = self.feat_df.loc[nearest_hours.index[0], "hour"]
            sub = self.feat_df[self.feat_df["hour"] == nearest_hour]
            X = sub[FEATURE_COLS]
            preds = self.model.predict(X)
            pred_dict = {int(sid): max(float(p), 1.0) for sid, p in zip(sub["segment_id"], preds)}

        self.prediction_cache[hour_bucket] = pred_dict
        return dict(pred_dict)

    def query_edge_server(self, segment_id: int, current_time: pd.Timestamp) -> Optional[float]:
        """Queries the roadside edge server for real-time speed on a segment.

        Graceful Fail: If server is offline or fails, returns None.
        """
        try:
            url = f"{self.edge_server_url}/get_speed"
            params = {
                "segment_id": int(segment_id),
                "current_simulated_time": current_time.isoformat(),
            }
            resp = requests.get(url, params=params, timeout=self.api_timeout)
            if resp.status_code == 200:
                data = resp.json()
                return max(float(data.get("speed", 30.0)), 1.0)
        except (requests.exceptions.RequestException, Exception):
            # Graceful fail: edge communication error -> default to None
            pass
        return None

    def _get_edge_data(self, u: Any, v: Any) -> Dict[str, Any]:
        """Retrieves best edge data between u and v."""
        if self.G.is_multigraph():
            edge_dict = self.G[u][v]
            best_k = min(edge_dict.keys(), key=lambda k: edge_dict[k].get("free_flow_time", 9999))
            return edge_dict[best_k]
        return self.G[u][v]

    def _traverse_edge(
        self, u: Any, v: Any, current_time: pd.Timestamp, speed_override: Optional[float] = None
    ) -> Tuple[float, float, pd.Timestamp]:
        """Calculates actual traversal time and distance, advancing vehicle clock."""
        edge_data = self._get_edge_data(u, v)
        length_m = float(edge_data.get("length", 10.0))

        if speed_override is not None:
            actual_speed = speed_override
        else:
            is_mon = edge_data.get("is_monitored") is True or str(edge_data.get("is_monitored")).lower() == "true"
            sid = edge_data.get("segment_id")

            if is_mon and sid is not None and sid != -1 and sid != "-1":
                # Ground truth speed from local table
                hour_bucket = current_time.floor("h")
                key = (hour_bucket, int(sid))
                actual_speed = self.actual_speeds.get(key, float(edge_data.get("free_flow_speed", 35.0)))
            else:
                actual_speed = float(edge_data.get("free_flow_speed", 30.0))

        actual_speed = max(actual_speed, 1.0)
        traversal_time_s = length_m / (actual_speed / 3.6)
        new_time = current_time + pd.Timedelta(seconds=traversal_time_s)

        return traversal_time_s, length_m, new_time

    # =========================================================================
    # Strategy 1: Static Baseline
    # =========================================================================
    def run_static_baseline(
        self, source: Any, target: Any, departure_time: pd.Timestamp
    ) -> Dict[str, Any]:
        """Fixed route using static free-flow speeds (no ML, no edge server)."""
        t_start = time.perf_counter()

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

    # =========================================================================
    # Strategy 2: Predictive Pre-Planned
    # =========================================================================
    def run_predictive_preplanned(
        self, source: Any, target: Any, departure_time: pd.Timestamp
    ) -> Dict[str, Any]:
        """Pre-planned route using global ML speed forecast at departure (blind to edge server)."""
        t_start = time.perf_counter()

        predicted_speeds = self.get_predictions_for_hour(departure_time)
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

    # =========================================================================
    # Strategy 3: Hybrid Edge-ML Architecture
    # =========================================================================
    def run_hybrid_edge_ml(
        self, source: Any, target: Any, departure_time: pd.Timestamp
    ) -> Dict[str, Any]:
        """Hybrid ML + Edge Computing dynamic navigation loop.
        
        1. Pre-Planning: Plans initial optimal route using city-wide XGBoost speed predictions.
        2. Edge Pinging: Before entering each upcoming segment, pings Edge Server (port 8000).
        3. Compare-and-Adjust: If unexpected delay > delay_threshold_seconds, triggers Dijkstra replan.
        4. Graceful Fallback: Defaults to ML if edge server drops.
        """
        t_start = time.perf_counter()

        # Phase A: Global Prediction (ML) Pre-Planning
        active_speeds = self.get_predictions_for_hour(departure_time)
        planned_route, _ = custom_dijkstra(
            self.G, source, target, alpha=self.alpha, beta=self.beta, edge_speeds_dict=active_speeds
        )
        if not planned_route:
            return {"strategy": "hybrid", "success": False, "error": "No path found"}

        current_time = departure_time
        total_time_s = 0.0
        total_distance_m = 0.0
        reroute_count = 0
        traversed_path = [source]
        curr_node = source

        # Phase B: Edge Pinging & Traversal Loop
        while curr_node != target:
            if len(planned_route) < 2:
                break

            # Local Reality Check: Query Edge Server for the immediate next 1-2 road segments
            replan_needed = False
            lookahead_limit = min(2, len(planned_route) - 1)
            for ahead_idx in range(lookahead_limit):
                u_ahead = planned_route[ahead_idx]
                v_ahead = planned_route[ahead_idx + 1]
                ed_ahead = self._get_edge_data(u_ahead, v_ahead)
                is_mon = ed_ahead.get("is_monitored") is True or str(ed_ahead.get("is_monitored")).lower() == "true"
                sid = ed_ahead.get("segment_id")

                if is_mon and sid is not None and sid != -1 and sid != "-1":
                    sid_int = int(sid)
                    length_m = float(ed_ahead.get("length", 10.0))
                    pred_speed = active_speeds.get(sid_int, float(ed_ahead.get("free_flow_speed", 35.0)))
                    pred_time_s = length_m / (max(pred_speed, 1.0) / 3.6)

                    # Query local roadside edge server
                    edge_speed = self.query_edge_server(sid_int, current_time)
                    if edge_speed is not None:
                        actual_time_s = length_m / (edge_speed / 3.6)
                        unexpected_delay = actual_time_s - pred_time_s

                        # Check hysteresis threshold
                        if unexpected_delay > self.delay_threshold_seconds:
                            active_speeds[sid_int] = edge_speed
                            replan_needed = True

            # Compare-and-Adjust: Trigger full replan if edge jam detected
            if replan_needed:
                new_path, _ = custom_dijkstra(
                    self.G, curr_node, target, alpha=self.alpha, beta=self.beta, edge_speeds_dict=active_speeds
                )
                if new_path and len(new_path) >= 2 and new_path != planned_route:
                    planned_route = new_path
                    reroute_count += 1

            next_node = planned_route[1]
            edge_data = self._get_edge_data(curr_node, next_node)
            is_mon = edge_data.get("is_monitored") is True or str(edge_data.get("is_monitored")).lower() == "true"
            sid = edge_data.get("segment_id")

            effective_speed = None
            if is_mon and sid is not None and sid != -1 and sid != "-1":
                sid_int = int(sid)
                effective_speed = active_speeds.get(sid_int)

            # Advance vehicle across edge (curr_node -> next_node)
            dt, dist, current_time = self._traverse_edge(
                curr_node, next_node, current_time, speed_override=effective_speed
            )
            total_time_s += dt
            total_distance_m += dist

            traversed_path.append(next_node)
            curr_node = next_node
            planned_route = planned_route[1:]

        latency_ms = (time.perf_counter() - t_start) * 1000.0

        return {
            "strategy": "hybrid",
            "success": True,
            "total_travel_time_seconds": total_time_s,
            "total_distance_meters": total_distance_m,
            "reroute_count": reroute_count,
            "departure_time": departure_time,
            "arrival_time": current_time,
            "compute_latency_ms": latency_ms,
            "path": traversed_path,
        }
