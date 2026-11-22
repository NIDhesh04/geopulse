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
import joblib

from src.edge.messages import ModelUpdateMessage
from src.traffic.replay import HistoricalTrafficReplay


class CloudModelService:
    """
    Compatibility wrapper for model metadata and saved historical predictions.

    The current Phase 7 Parquet is a historical prediction artifact. This class
    replays it; loading the model here does not perform live inference.
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

        # Replay exact stored hours; never substitute a nearby timestamp.
        self.replay = HistoricalTrafficReplay(self.predictions_path)

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
        Replays saved predictions for one exact origin hour and packages MODEL_UPDATE.

        `target_timestamp` is retained as the existing parameter name for caller
        compatibility; it identifies the frame's origin hour. The forecast applies
        at the separate target-valid timestamp.

        Returns
        -------
        message : ModelUpdateMessage
        execution_time_ms : float (Prototype software execution time in milliseconds)
        """
        t0 = time.perf_counter()
        frame = self.replay.get_frame(target_timestamp)
        pred_dict = dict(frame.predicted_speeds)
        execution_time_ms = (time.perf_counter() - t0) * 1000.0

        message = ModelUpdateMessage(
            model_version=self.model_version,
            feature_metadata=self.get_metadata(),
            prediction_timestamp=frame.origin_timestamp.isoformat(),
            predicted_speeds=pred_dict,
            total_segments=len(pred_dict),
            origin_timestamp=frame.origin_timestamp.isoformat(),
            target_valid_timestamp=frame.target_valid_timestamp.isoformat(),
        )

        return message, execution_time_ms
