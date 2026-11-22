"""Replay saved hourly speed predictions and update OSM edge costs in memory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import networkx as nx
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.routing.traffic_weights import GraphWeightManager, TrafficEdgeCostUpdater
from src.traffic.replay import HistoricalTrafficReplay

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, help="Exact hourly UTC origin, e.g. 2026-01-15T08:00:00Z")
    parser.add_argument("--steps", type=int, default=1, help="Number of consecutive hourly frames to apply")
    parser.add_argument("--graph", default="data/raw/osm/bhubaneswar_drive.graphml")
    parser.add_argument("--mapping", default="data/processed/traffic_to_osm_mapping_final.parquet")
    parser.add_argument("--predictions", default="results/phase7_predictions.parquet")
    args = parser.parse_args()
    if args.steps <= 0:
        parser.error("--steps must be positive")

    graph_path = ROOT / args.graph
    mapping_path = ROOT / args.mapping
    predictions_path = ROOT / args.predictions
    original_graph = nx.read_graphml(graph_path)
    mapping = pd.read_parquet(mapping_path)
    replay = HistoricalTrafficReplay(
        predictions_path,
        expected_segment_ids=mapping["traffic_segment_id"].astype(int),
    )
    updater = TrafficEdgeCostUpdater(GraphWeightManager(original_graph, mapping))

    frame = replay.start(args.start)
    for step in range(args.steps):
        result = updater.update_working_copy(
            frame.predicted_speeds,
            origin_timestamp=frame.origin_timestamp,
            target_valid_timestamp=frame.target_valid_timestamp,
        )
        report = result.diagnostics.to_dict()
        report["replay_step"] = step + 1
        report["missing_segment_ids"] = sorted(frame.missing_segment_ids)
        report["invalid_segment_ids"] = sorted(frame.invalid_segment_ids)
        report["working_graph_edges"] = result.working_graph.number_of_edges()
        print(json.dumps(report, sort_keys=True))

        if step + 1 < args.steps:
            next_frame = replay.advance()
            if next_frame is None:
                break
            frame = next_frame


if __name__ == "__main__":
    main()
