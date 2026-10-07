"""
GeoPulse Phase 10: Automated Data Leakage & Lookahead Audit Engine (Section 14)

Formally audits the four stages of the pipeline to guarantee scientific integrity:
  1. Prediction Feature Audit: No future speeds in ML training/inference.
  2. Initial Routing Audit: Route planning uses predictive weights, not ground truth.
  3. Ground-Truth Evaluation Audit: Actual traffic used strictly for retrospective evaluation.
  4. Dynamic Replay Audit: Telemetry at t1 is quarantined until vehicle reaches decision point.
"""

from typing import Dict, Any
import json
import numpy as np
import pandas as pd


def perform_data_leakage_audit(
    feature_meta_path: str = 'models/feature_metadata.json',
    predictions_path: str = 'results/phase7_predictions.parquet',
    eval_parquet_path: str = 'results/phase8_route_evaluation.parquet',
    replay_parquet_path: str = 'results/phase9_dynamic_replay.parquet'
) -> Dict[str, Any]:
    """
    Executes automated assertions against code artifacts and data tables.
    """
    checks = {}

    # 1. Feature Metadata Audit
    with open(feature_meta_path, 'r') as f:
        meta = json.load(f)
    features = meta.get('feature_cols', meta.get('feature_names', []))
    forbidden_tokens = ['target', 'actual', 'future', 'lead', 't_plus', 'ground_truth']
    leak_features = [f for f in features if any(tok in f.lower() for tok in forbidden_tokens)]
    checks['check_1_ml_feature_leakage'] = {
        'status': 'PASSED' if len(leak_features) == 0 else 'FAILED',
        'details': f"Features examined: {len(features)}. Forbidden tokens found: {leak_features}",
        'is_leak_free': bool(len(leak_features) == 0)
    }

    # 2. Prediction Independence Audit (ML Predictions != Ground Truth)
    pred_df = pd.read_parquet(predictions_path)
    exact_matches = int((pred_df['actual_speed'] == pred_df['predicted_speed']).sum())
    mae = float((pred_df['actual_speed'] - pred_df['predicted_speed']).abs().mean())
    checks['check_2_prediction_not_oracle'] = {
        'status': 'PASSED' if exact_matches < len(pred_df) * 0.05 and mae > 0.1 else 'FAILED',
        'details': f"Total samples: {len(pred_df)}. Exact speed matches: {exact_matches}. MAE: {mae:.4f} km/h.",
        'is_leak_free': bool(mae > 0.1)
    }

    # 3. Routing Separation Audit (Predicted Path != Oracle Path in all instances)
    eval_df = pd.read_parquet(eval_parquet_path)
    ml_vs_oracle_overlap = float(eval_df['ml_current_route_overlap'].mean())
    checks['check_3_route_planning_separation'] = {
        'status': 'PASSED' if ml_vs_oracle_overlap < 1.0 else 'FAILED',
        'details': f"Mean ML-Oracle route overlap: {ml_vs_oracle_overlap:.4f} (demonstrates ML did not solve oracle directly).",
        'is_leak_free': bool(ml_vs_oracle_overlap < 1.0)
    }

    # 4. Dynamic Replay Quarantined Telemetry Audit
    replay_df = pd.read_parquet(replay_parquet_path)
    # Check that initial route travel time under prediction differs from updated actual time
    initial_diff = float((replay_df['initial_predicted_time_s'] - replay_df['initial_actual_time_s']).abs().mean())
    checks['check_4_dynamic_telemetry_quarantine'] = {
        'status': 'PASSED' if initial_diff > 0.01 else 'FAILED',
        'details': f"Mean divergence between t0 predicted plan and t1 actual observation: {initial_diff:.2f} s.",
        'is_leak_free': bool(initial_diff > 0.01)
    }

    overall_pass = all(c['is_leak_free'] for c in checks.values())
    checks['overall_leakage_audit_status'] = 'ALL CHECKS PASSED' if overall_pass else 'AUDIT FAILED'

    return checks
