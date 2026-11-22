"""Deterministic replay of the saved Phase 7 speed-prediction artifact.

This service reads historical predictions. It does not run the model or claim
live inference. Source timestamps carry small per-segment capture offsets, so
artifact rows are assigned to their nearest UTC hour only when within five
minutes; callers must request an exact UTC hour and missing hours raise clearly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Set

import numpy as np
import pandas as pd


class MissingReplayTimestampError(KeyError):
    """Raised when the requested exact hour has no stored prediction frame."""


@dataclass(frozen=True)
class TrafficReplayFrame:
    """One hourly prediction frame with explicit forecast timing."""
    origin_timestamp: pd.Timestamp
    target_valid_timestamp: pd.Timestamp
    predicted_speeds: Mapping[int, float]
    source_origin_timestamps: Mapping[int, pd.Timestamp]
    missing_segment_ids: frozenset[int]
    invalid_segment_ids: frozenset[int]

    @property
    def missing_prediction_count(self) -> int:
        return len(self.missing_segment_ids)

    @property
    def invalid_prediction_count(self) -> int:
        return len(self.invalid_segment_ids)


class HistoricalTrafficReplay:
    """Load and replay stored predictions at deterministic hourly intervals."""

    REQUIRED_COLUMNS = {"timestamp", "traffic_segment_id", "predicted_speed"}
    HOUR = pd.Timedelta(hours=1)
    SOURCE_OFFSET_TOLERANCE = pd.Timedelta(minutes=5)

    def __init__(
        self,
        predictions: Any = "results/phase7_predictions.parquet",
        expected_segment_ids: Optional[Iterable[int]] = None,
    ):
        if isinstance(predictions, pd.DataFrame):
            frame = predictions.copy()
        else:
            path = Path(predictions)
            if not path.is_absolute():
                path = Path(__file__).resolve().parents[2] / path
            if not path.exists():
                raise FileNotFoundError(f"Prediction artifact not found: {path}")
            frame = pd.read_parquet(path)

        missing = self.REQUIRED_COLUMNS - set(frame.columns)
        if missing:
            raise ValueError(f"Prediction artifact lacks required columns: {sorted(missing)}")
        if frame.empty:
            raise ValueError("Prediction artifact contains no rows")

        timestamps = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
        if timestamps.isna().any():
            raise ValueError("Prediction artifact has missing or invalid origin timestamps")
        origin_hours = timestamps.dt.round("h")
        offsets = (timestamps - origin_hours).abs()
        if (offsets > self.SOURCE_OFFSET_TOLERANCE).any():
            bad = timestamps.loc[offsets > self.SOURCE_OFFSET_TOLERANCE].iloc[0]
            raise ValueError(
                f"Prediction origin {bad.isoformat()} is not close to an hourly bucket; "
                "refusing to assign it to an unrelated replay hour"
            )

        segment_ids = pd.to_numeric(frame["traffic_segment_id"], errors="coerce")
        if segment_ids.isna().any() or ((segment_ids % 1) != 0).any():
            raise ValueError("Prediction artifact has missing or non-integer segment IDs")

        frame = frame.assign(
            _origin_hour=origin_hours,
            _source_origin=timestamps,
            _segment_id=segment_ids.astype("int64"),
            _speed=pd.to_numeric(frame["predicted_speed"], errors="coerce"),
        )
        duplicate_keys = frame.duplicated(["_origin_hour", "_segment_id"], keep=False)
        if duplicate_keys.any():
            example = frame.loc[duplicate_keys, ["_origin_hour", "_segment_id"]].iloc[0]
            raise ValueError(
                "Duplicate prediction rows for origin hour/segment: "
                f"{example['_origin_hour'].isoformat()} / {int(example['_segment_id'])}"
            )

        all_ids: Set[int] = set(frame["_segment_id"].astype(int))
        if expected_segment_ids is None:
            self.expected_segment_ids = frozenset(all_ids)
        else:
            try:
                expected = {int(segment_id) for segment_id in expected_segment_ids}
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("expected_segment_ids must contain integer IDs") from exc
            self.expected_segment_ids = frozenset(expected)

        self._frames: Dict[pd.Timestamp, pd.DataFrame] = {
            pd.Timestamp(origin): group.sort_values("_segment_id").reset_index(drop=True)
            for origin, group in frame.groupby("_origin_hour", sort=True)
        }
        self.available_timestamps = tuple(sorted(self._frames))
        self._current_timestamp: Optional[pd.Timestamp] = None

    @staticmethod
    def _normalize_requested_hour(value: Any) -> pd.Timestamp:
        timestamp = pd.Timestamp(value)
        if pd.isna(timestamp):
            raise ValueError("Replay timestamp is missing or invalid")
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize("UTC")
        else:
            timestamp = timestamp.tz_convert("UTC")
        if timestamp != timestamp.floor("h"):
            raise ValueError(
                "Replay timestamps must be exact hourly UTC boundaries; "
                f"got {timestamp.isoformat()}"
            )
        return timestamp

    def get_frame(self, origin_timestamp: Any) -> TrafficReplayFrame:
        """Fetch exactly one stored origin hour; never substitute a nearby hour."""
        origin = self._normalize_requested_hour(origin_timestamp)
        source = self._frames.get(origin)
        if source is None:
            first, last = self.available_timestamps[0], self.available_timestamps[-1]
            raise MissingReplayTimestampError(
                f"No prediction frame at {origin.isoformat()}; available range is "
                f"{first.isoformat()} through {last.isoformat()} "
                f"({len(self.available_timestamps)} stored hours)"
            )

        speeds: Dict[int, float] = {}
        source_timestamps: Dict[int, pd.Timestamp] = {}
        invalid_ids = set()
        rows = source[["_segment_id", "_speed", "_source_origin"]].itertuples(
            index=False, name=None
        )
        for raw_segment_id, raw_speed, raw_origin in rows:
            segment_id = int(raw_segment_id)
            speed = float(raw_speed) if pd.notna(raw_speed) else float("nan")
            speeds[segment_id] = speed
            source_timestamps[segment_id] = pd.Timestamp(raw_origin)
            if not np.isfinite(speed) or speed <= 0:
                invalid_ids.add(segment_id)

        missing_ids = self.expected_segment_ids - set(speeds)
        return TrafficReplayFrame(
            origin_timestamp=origin,
            target_valid_timestamp=origin + self.HOUR,
            predicted_speeds=speeds,
            source_origin_timestamps=source_timestamps,
            missing_segment_ids=frozenset(missing_ids),
            invalid_segment_ids=frozenset(invalid_ids),
        )

    def start(self, origin_timestamp: Any) -> TrafficReplayFrame:
        """Select a replay start hour and return its exact prediction frame."""
        frame = self.get_frame(origin_timestamp)
        self._current_timestamp = frame.origin_timestamp
        return frame

    def advance(self) -> Optional[TrafficReplayFrame]:
        """Advance exactly one hour, raising on a gap and returning None at EOF."""
        if self._current_timestamp is None:
            raise RuntimeError("Replay has not started; call start(timestamp) first")
        next_timestamp = self._current_timestamp + self.HOUR
        if next_timestamp > self.available_timestamps[-1]:
            return None
        frame = self.get_frame(next_timestamp)
        self._current_timestamp = frame.origin_timestamp
        return frame

    def iter_from(self, origin_timestamp: Any):
        """Yield frames chronologically from an exact start through the artifact."""
        frame = self.start(origin_timestamp)
        while frame is not None:
            yield frame
            frame = self.advance()
