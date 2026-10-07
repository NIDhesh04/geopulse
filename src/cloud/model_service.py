"""
GeoPulse Phase 11: Cloud Model Service Component

Simulates the centralized cloud environment responsible for:
  - Model lifecycle management (LightGBM regressor artifact & metadata)
  - Next-hour feature generation and batch speed inference
  - Dispatching MODEL_UPDATE messages to regional Edge Servers
"""

import os
import json
import time
from typing import Dict, Any, Optional, Tuple
import pandas as pd
import joblib

from src.edge.messages import ModelUpdateMessage


class CloudModelService:
    """
    Centralized Cloud Service managing training artifacts, feature schemas,
    and batch traffic prediction inference.
    """

    def __init__(
        self,
        model_path: str = 'models/speed_predictor.joblib',
        metadata_path: str = 'models/feature_metadata.json',
        predictions_path: str = 'results/phase7_predictions.parquet'
    ):
        self.model_path = model_path
        self.metadata_path = metadata_path
        self.predictions_path = predictions_path

        # Load metadata
        with open(self.metadata_path, 'r') as f:
            self.metadata = json.load(f)

        self.model_version = f"LightGBM-v1.0 (Iteration {self.metadata.get('best_iteration', 112)})"
        self.model = None
        self._load_model()

        # Cache predictions table for efficient real-time broadcast simulation
        self._pred_df = pd.read_parquet(self.predictions_path)
        if 'ts_round' not in self._pred_df.columns:
            self._pred_df['ts_round'] = pd.to_datetime(self._pred_df['timestamp']).dt.round('h')
        else:
            self._pred_df['ts_round'] = pd.to_datetime(self._pred_df['ts_round'])

    def _load_model(self):
        """Loads serialized model artifact from persistent storage."""
        if os.path.exists(self.model_path):
            self.model = joblib.load(self.model_path)
        else:
            raise FileNotFoundError(f"Model artifact not found at {self.model_path}")

    def get_metadata(self) -> Dict[str, Any]:
        """Exposes model versioning and training provenance."""
        return {
            'model_version': self.model_version,
            'model_type': self.metadata.get('model_type', 'LightGBMRegressor'),
            'feature_count': len(self.metadata.get('feature_cols', [])),
            'feature_cols': self.metadata.get('feature_cols', []),
            'training_samples': self.metadata.get('train_samples', 0),
            'validation_samples': self.metadata.get('val_samples', 0),
            'test_samples': self.metadata.get('test_samples', 0),
            'speed_clipping': self.metadata.get('speed_clipping', [3.0, 120.0])
        }

    def generate_predictions_broadcast(self, target_timestamp: Any) -> Tuple[ModelUpdateMessage, float]:
        """
        Executes prediction generation for a given timestamp and packages a MODEL_UPDATE broadcast.

        Returns
        -------
        message : ModelUpdateMessage
        execution_time_ms : float (Prototype software execution time in milliseconds)
        """
        t0 = time.perf_counter()
        ts_val = pd.to_datetime(target_timestamp)

        # Retrieve predictions for all 700 monitored segments at target_timestamp
        sub = self._pred_df[self._pred_df['ts_round'] == ts_val]
        if len(sub) == 0:
            # Fallback to closest timestamp
            closest_ts = min(self._pred_df['ts_round'], key=lambda x: abs(x - ts_val))
            sub = self._pred_df[self._pred_df['ts_round'] == closest_ts]

        pred_dict = dict(zip(sub['traffic_segment_id'], sub['predicted_speed']))
        execution_time_ms = (time.perf_counter() - t0) * 1000.0

        message = ModelUpdateMessage(
            model_version=self.model_version,
            feature_metadata=self.get_metadata(),
            prediction_timestamp=str(target_timestamp),
            predicted_speeds=pred_dict,
            total_segments=len(pred_dict)
        )

        return message, execution_time_ms
