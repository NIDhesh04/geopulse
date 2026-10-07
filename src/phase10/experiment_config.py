"""
GeoPulse Phase 10: Experiment Configuration & Constants

Defines standard paths, parameters, thresholds, and period definitions
to ensure fully reproducible ablation and robustness experiments.
"""

import os
from typing import Dict, List, Tuple

# -----------------------------------------------------------------------------
# DIRECTORY PATHS
# -----------------------------------------------------------------------------
RESULTS_DIR = 'results/phase10'
FIGURES_DIR = 'results/phase10/figures'
DOCS_DIR = 'docs'

# Source input paths (Phase 1-9 canonical artifacts)
GRAPH_PATH = 'data/raw/osm/bhubaneswar_drive.graphml'
MAPPING_PARQUET = 'data/processed/traffic_to_osm_mapping_final.parquet'
FEATURE_META_JSON = 'models/feature_metadata.json'
SPEED_MODEL_JOBLIB = 'models/speed_predictor.joblib'
PHASE7_PREDICTIONS_PARQUET = 'results/phase7_predictions.parquet'
PHASE8_OD_PAIRS_CSV = 'results/phase8_od_pairs.csv'
PHASE8_TIMESTAMPS_CSV = 'results/phase8_evaluation_timestamps.csv'
PHASE8_EVAL_PARQUET = 'results/phase8_route_evaluation.parquet'
PHASE9_REPLAY_PARQUET = 'results/phase9_dynamic_replay.parquet'
PHASE9_CANDIDATES_CSV = 'results/phase9_candidate_scenarios.csv'

# Random seed
RANDOM_SEED = 42

# -----------------------------------------------------------------------------
# EXPERIMENT A: STRATEGY DEFINITIONS
# -----------------------------------------------------------------------------
STRATEGIES = [
    'Static Baseline',
    'Persistence Prediction',
    'Historical Baseline',
    'LightGBM Prediction',
    'Current-Traffic Oracle'
]

# -----------------------------------------------------------------------------
# EXPERIMENT B & C: REROUTING POLICIES & THRESHOLDS
# -----------------------------------------------------------------------------
# Baseline dual threshold (GeoPulse Phase 9 standard)
DEFAULT_THRESHOLD_SECONDS = 10.0
DEFAULT_THRESHOLD_PERCENT = 3.0

# Threshold Sensitivity Grid
GRID_ABS_THRESHOLDS_S = [5.0, 10.0, 20.0, 30.0]
GRID_PCT_THRESHOLDS = [1.0, 2.0, 3.0, 5.0, 10.0]

# -----------------------------------------------------------------------------
# EXPERIMENT D: DIURNAL TIME PERIODS
# -----------------------------------------------------------------------------
PERIOD_DEFINITIONS = {
    'Morning Peak': (9, 11),
    'Midday': (12, 16),
    'Evening Peak': (17, 20),
    'Off-Peak': (21, 8)
}

# -----------------------------------------------------------------------------
# EXPERIMENT E: ROUTE LENGTH BINS (km)
# -----------------------------------------------------------------------------
ROUTE_LENGTH_BINS = [0.0, 5000.0, 8000.0, 50000.0]
ROUTE_LENGTH_LABELS = ['Short (<5 km)', 'Medium (5-8 km)', 'Long (>8 km)']

# -----------------------------------------------------------------------------
# EXPERIMENT F: CONGESTION TERTILES
# -----------------------------------------------------------------------------
CONGESTION_LABELS = ['Low Congestion', 'Medium Congestion', 'High Congestion']
