# GeoPulse Cleanup Manifest

**Audit date:** 22 November 2026  
**Repository:** GeoPulse  
**Cleanup performed:** safe removals, verified fixes, and readiness documentation. No commit or push.

## Summary

| Cleanup group | Files removed |
|---|---:|
| Python bytecode (.pyc) | 140 |
| Byte-for-byte duplicate dashboard timeline CSVs | 53 |
| Dashboard artifacts created during audit checks | 12 |
| Superseded audit notes and exact duplicate archived docs | 8 |
| Pytest cache files | 5 |
| **Total files removed** | **218** |

Removed 12 empty Python __pycache__ directories and the three pytest cache directories listed below. Dashboard timeline files were grouped by SHA-256 and one matching representative was retained for each identical content group. Nonduplicate JSON result records and experiment outputs were preserved. The final compile/test pass recreated bytecode and two Streamlit dashboard artifacts; these were removed again before the final Git check.

## Deleted files

### Python bytecode

Removed generated interpreter and pytest bytecode. These files are reproducible and are now covered by the root .gitignore.

- scripts/__pycache__/build_major_project_presentation.cpython-310.pyc
- scripts/__pycache__/build_major_project_presentation.cpython-313.pyc
- scripts/__pycache__/run_phase10_ablation.cpython-310.pyc
- scripts/__pycache__/run_phase10_ablation.cpython-313.pyc
- scripts/__pycache__/run_phase11_dashboard.cpython-310.pyc
- scripts/__pycache__/run_phase11_dashboard.cpython-313.pyc
- scripts/__pycache__/run_phase11_demo.cpython-310.pyc
- scripts/__pycache__/run_phase11_demo.cpython-313.pyc
- scripts/__pycache__/run_phase8_evaluation.cpython-310.pyc
- scripts/__pycache__/run_phase8_evaluation.cpython-313.pyc
- scripts/__pycache__/run_phase9_replay.cpython-310.pyc
- scripts/__pycache__/run_phase9_replay.cpython-313.pyc
- scripts/__pycache__/run_two_edge_experiments.cpython-310.pyc
- scripts/__pycache__/run_two_edge_experiments.cpython-313.pyc
- scripts/__pycache__/train_phase7_speed_predictor.cpython-310.pyc
- scripts/__pycache__/train_phase7_speed_predictor.cpython-313.pyc
- src/cloud/__pycache__/model_service.cpython-310.pyc
- src/cloud/__pycache__/model_service.cpython-313.pyc
- src/cloud/__pycache__/__init__.cpython-310.pyc
- src/cloud/__pycache__/__init__.cpython-313.pyc
- src/dashboard/__pycache__/backend.cpython-310.pyc
- src/dashboard/__pycache__/backend.cpython-313.pyc
- src/dashboard/__pycache__/state.cpython-310.pyc
- src/dashboard/__pycache__/state.cpython-313.pyc
- src/dashboard/__pycache__/visualization.cpython-310.pyc
- src/dashboard/__pycache__/visualization.cpython-313.pyc
- src/dashboard/__pycache__/__init__.cpython-310.pyc
- src/dashboard/__pycache__/__init__.cpython-313.pyc
- src/demo/__pycache__/phase9_demo.cpython-310.pyc
- src/demo/__pycache__/phase9_demo.cpython-313.pyc
- src/edge/__pycache__/edge_server.cpython-310.pyc
- src/edge/__pycache__/edge_server.cpython-313.pyc
- src/edge/__pycache__/messages.cpython-310.pyc
- src/edge/__pycache__/messages.cpython-313.pyc
- src/edge/__pycache__/visualizations.cpython-310.pyc
- src/edge/__pycache__/visualizations.cpython-313.pyc
- src/edge/__pycache__/__init__.cpython-310.pyc
- src/edge/__pycache__/__init__.cpython-313.pyc
- src/experiments/__pycache__/benchmark_runner.cpython-310.pyc
- src/experiments/__pycache__/benchmark_runner.cpython-313.pyc
- src/experiments/__pycache__/visualizations.cpython-310.pyc
- src/experiments/__pycache__/visualizations.cpython-313.pyc
- src/experiments/__pycache__/__init__.cpython-310.pyc
- src/experiments/__pycache__/__init__.cpython-313.pyc
- src/phase10/__pycache__/experiment_config.cpython-310.pyc
- src/phase10/__pycache__/experiment_config.cpython-313.pyc
- src/phase10/__pycache__/leakage_check.cpython-310.pyc
- src/phase10/__pycache__/leakage_check.cpython-313.pyc
- src/phase10/__pycache__/prediction_error_analysis.cpython-310.pyc
- src/phase10/__pycache__/prediction_error_analysis.cpython-313.pyc
- src/phase10/__pycache__/rerouting_ablation.cpython-310.pyc
- src/phase10/__pycache__/rerouting_ablation.cpython-313.pyc
- src/phase10/__pycache__/robustness.cpython-310.pyc
- src/phase10/__pycache__/robustness.cpython-313.pyc
- src/phase10/__pycache__/routing_ablation.cpython-310.pyc
- src/phase10/__pycache__/routing_ablation.cpython-313.pyc
- src/phase10/__pycache__/statistical_analysis.cpython-310.pyc
- src/phase10/__pycache__/statistical_analysis.cpython-313.pyc
- src/phase10/__pycache__/threshold_sensitivity.cpython-310.pyc
- src/phase10/__pycache__/threshold_sensitivity.cpython-313.pyc
- src/phase10/__pycache__/visualizations.cpython-310.pyc
- src/phase10/__pycache__/visualizations.cpython-313.pyc
- src/phase10/__pycache__/__init__.cpython-310.pyc
- src/phase10/__pycache__/__init__.cpython-313.pyc
- src/pygame_simulation/__pycache__/main.cpython-310.pyc
- src/pygame_simulation/__pycache__/main.cpython-313.pyc
- src/pygame_simulation/__pycache__/renderer.cpython-310.pyc
- src/pygame_simulation/__pycache__/renderer.cpython-313.pyc
- src/pygame_simulation/__pycache__/road_renderer.cpython-310.pyc
- src/pygame_simulation/__pycache__/road_renderer.cpython-313.pyc
- src/pygame_simulation/__pycache__/scenario_manager.cpython-310.pyc
- src/pygame_simulation/__pycache__/scenario_manager.cpython-313.pyc
- src/pygame_simulation/__pycache__/simulation_controller.cpython-310.pyc
- src/pygame_simulation/__pycache__/simulation_controller.cpython-313.pyc
- src/pygame_simulation/__pycache__/ui_components.cpython-310.pyc
- src/pygame_simulation/__pycache__/ui_components.cpython-313.pyc
- src/pygame_simulation/__pycache__/vehicle_sprite.cpython-310.pyc
- src/pygame_simulation/__pycache__/vehicle_sprite.cpython-313.pyc
- src/pygame_simulation/__pycache__/__init__.cpython-310.pyc
- src/pygame_simulation/__pycache__/__init__.cpython-313.pyc
- src/routing/__pycache__/astar.cpython-310.pyc
- src/routing/__pycache__/astar.cpython-313.pyc
- src/routing/__pycache__/candidate_generator.cpython-310.pyc
- src/routing/__pycache__/candidate_generator.cpython-313.pyc
- src/routing/__pycache__/decision_strategies.cpython-310.pyc
- src/routing/__pycache__/decision_strategies.cpython-313.pyc
- src/routing/__pycache__/dijkstra.cpython-310.pyc
- src/routing/__pycache__/dijkstra.cpython-313.pyc
- src/routing/__pycache__/dynamic_rerouter.cpython-310.pyc
- src/routing/__pycache__/dynamic_rerouter.cpython-313.pyc
- src/routing/__pycache__/lookahead.cpython-310.pyc
- src/routing/__pycache__/lookahead.cpython-313.pyc
- src/routing/__pycache__/route_controller.cpython-310.pyc
- src/routing/__pycache__/route_controller.cpython-313.pyc
- src/routing/__pycache__/route_evaluator.cpython-310.pyc
- src/routing/__pycache__/route_evaluator.cpython-313.pyc
- src/routing/__pycache__/traffic_weights.cpython-310.pyc
- src/routing/__pycache__/traffic_weights.cpython-313.pyc
- src/routing/__pycache__/two_edge_selector.cpython-310.pyc
- src/routing/__pycache__/two_edge_selector.cpython-313.pyc
- src/routing/__pycache__/__init__.cpython-310.pyc
- src/routing/__pycache__/__init__.cpython-313.pyc
- src/simulation/__pycache__/vehicle.cpython-310.pyc
- src/simulation/__pycache__/vehicle.cpython-313.pyc
- src/simulation/__pycache__/__init__.cpython-310.pyc
- src/simulation/__pycache__/__init__.cpython-313.pyc
- src/__pycache__/audit_dataset.cpython-310.pyc
- src/__pycache__/audit_dataset.cpython-313.pyc
- src/__pycache__/audit_delhi_dataset.cpython-310.pyc
- src/__pycache__/audit_delhi_dataset.cpython-313.pyc
- src/__pycache__/audit_routing_network.cpython-310.pyc
- src/__pycache__/audit_routing_network.cpython-313.pyc
- tests/__pycache__/test_phase10_ablation.cpython-310.pyc
- tests/__pycache__/test_phase10_ablation.cpython-313-pytest-8.4.2.pyc
- tests/__pycache__/test_phase10_ablation.cpython-313-pytest-9.1.1.pyc
- tests/__pycache__/test_phase10_ablation.cpython-313.pyc
- tests/__pycache__/test_phase11_dashboard.cpython-310.pyc
- tests/__pycache__/test_phase11_dashboard.cpython-313-pytest-8.4.2.pyc
- tests/__pycache__/test_phase11_dashboard.cpython-313-pytest-9.1.1.pyc
- tests/__pycache__/test_phase11_dashboard.cpython-313.pyc
- tests/__pycache__/test_phase11_integration.cpython-310.pyc
- tests/__pycache__/test_phase11_integration.cpython-313-pytest-8.4.2.pyc
- tests/__pycache__/test_phase11_integration.cpython-313-pytest-9.1.1.pyc
- tests/__pycache__/test_phase11_integration.cpython-313.pyc
- tests/__pycache__/test_phase8_routing.cpython-310.pyc
- tests/__pycache__/test_phase8_routing.cpython-313-pytest-8.4.2.pyc
- tests/__pycache__/test_phase8_routing.cpython-313-pytest-9.1.1.pyc
- tests/__pycache__/test_phase8_routing.cpython-313.pyc
- tests/__pycache__/test_phase9_rerouting.cpython-310.pyc
- tests/__pycache__/test_phase9_rerouting.cpython-313-pytest-8.4.2.pyc
- tests/__pycache__/test_phase9_rerouting.cpython-313-pytest-9.1.1.pyc
- tests/__pycache__/test_phase9_rerouting.cpython-313.pyc
- tests/__pycache__/test_pygame_simulation.cpython-310.pyc
- tests/__pycache__/test_pygame_simulation.cpython-313-pytest-8.4.2.pyc
- tests/__pycache__/test_pygame_simulation.cpython-313-pytest-9.1.1.pyc
- tests/__pycache__/test_pygame_simulation.cpython-313.pyc
- tests/__pycache__/test_two_edge_routing.cpython-310.pyc
- tests/__pycache__/test_two_edge_routing.cpython-313-pytest-8.4.2.pyc
- tests/__pycache__/test_two_edge_routing.cpython-313-pytest-9.1.1.pyc
- tests/__pycache__/test_two_edge_routing.cpython-313.pyc

### Duplicate dashboard timeline CSVs

Removed only exact SHA-256 duplicates. A matching timeline with the same content remains in results/dashboard_runs/.

- results/dashboard_runs/demo_timeline_scenario_0_20261118_152525.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261118_150120.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261118_144625.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261008_155611.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261008_111839.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261008_111738.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261007_231458.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261007_231436.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261007_230902.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261007_230823.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261007_230558.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261007_230509.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261007_230012.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261007_225659.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261007_225610.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261007_223350.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261007_221756.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261007_221649.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261007_221627.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261007_220735.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261007_210659.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261007_205806.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261007_205801.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261007_205137.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261007_204241.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261007_203724.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261007_203703.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261007_203532.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261007_203509.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261007_203334.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261007_202846.csv
- results/dashboard_runs/demo_timeline_scenario_11_20261008_112215.csv
- results/dashboard_runs/demo_timeline_scenario_11_20261007_223703.csv
- results/dashboard_runs/demo_timeline_scenario_11_20261007_223631.csv
- results/dashboard_runs/demo_timeline_scenario_11_20261007_223226.csv
- results/dashboard_runs/demo_timeline_scenario_11_20261007_205105.csv
- results/dashboard_runs/demo_timeline_scenario_14_20261007_231305.csv
- results/dashboard_runs/demo_timeline_scenario_14_20261007_222945.csv
- results/dashboard_runs/demo_timeline_scenario_14_20261007_222741.csv
- results/dashboard_runs/demo_timeline_scenario_14_20261007_222734.csv
- results/dashboard_runs/demo_timeline_scenario_3_20261007_205209.csv
- results/dashboard_runs/demo_timeline_scenario_3_20261007_204941.csv
- results/dashboard_runs/demo_timeline_scenario_3_20261007_204241.csv
- results/dashboard_runs/demo_timeline_scenario_5_20261007_203849.csv
- results/dashboard_runs/demo_timeline_scenario_5_20261007_203759.csv
- results/dashboard_runs/demo_timeline_scenario_6_20261007_231120.csv
- results/dashboard_runs/demo_timeline_scenario_6_20261007_222128.csv
- results/dashboard_runs/demo_timeline_scenario_6_20261007_222038.csv
- results/dashboard_runs/demo_timeline_scenario_6_20261007_221854.csv
- results/dashboard_runs/demo_timeline_scenario_8_20261007_231711.csv
- results/dashboard_runs/demo_timeline_scenario_8_20261007_231706.csv
- results/dashboard_runs/demo_timeline_scenario_8_20261007_231702.csv
- results/dashboard_runs/demo_timeline_scenario_8_20261007_204242.csv

### Audit-generated dashboard artifacts

These JSON/CSV files were created by this audit's Streamlit AppTest runs, were absent before the audit, and were removed after verification.

- results/dashboard_runs/demo_result_scenario_0_20261122_000748.json
- results/dashboard_runs/demo_result_scenario_0_20261122_000903.json
- results/dashboard_runs/demo_result_scenario_0_20261122_002322.json
- results/dashboard_runs/demo_result_scenario_0_20261122_003546.json
- results/dashboard_runs/demo_result_scenario_0_20261122_003620.json
- results/dashboard_runs/demo_timeline_scenario_0_20261122_000748.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261122_000903.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261122_002322.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261122_003546.csv
- results/dashboard_runs/demo_timeline_scenario_0_20261122_003620.csv
- results/dashboard_runs/demo_result_scenario_0_20261122_004334.json
- results/dashboard_runs/demo_timeline_scenario_0_20261122_004334.csv

### Superseded audit notes and exact archived documentation copies

Removed the older audit/implementation-status notes superseded by the complete audit report, and five archived documents confirmed byte-identical to copies retained at the repository root.

- GEOPULSE_AUDIT_VERIFICATION.md
- docs/PROJECT_AUDIT.md
- docs/IMPLEMENTATION_STATUS.md
- geopulse smartroute/docs/phase2_osm_download.md
- geopulse smartroute/docs/phase3_osmid_check.md
- geopulse smartroute/docs/phase4_10_segment_inspection.md
- geopulse smartroute/docs/phase5_full_mapping_audit.md
- geopulse smartroute/docs/routing_weight_policy.md

### Pytest cache

Removed these five files after an elevated inventory confirmed the exact workspace paths:

- .pytest_cache/.gitignore
- .pytest_cache/CACHEDIR.TAG
- .pytest_cache/README.md
- .pytest_cache/v/cache/lastfailed
- .pytest_cache/v/cache/nodeids

Removed the empty directories .pytest_cache/v/cache, .pytest_cache/v, and .pytest_cache.

## Empty bytecode directories removed

- tests/__pycache__
- src/simulation/__pycache__
- src/routing/__pycache__
- src/pygame_simulation/__pycache__
- src/phase10/__pycache__
- src/experiments/__pycache__
- src/edge/__pycache__
- src/demo/__pycache__
- src/dashboard/__pycache__
- src/cloud/__pycache__
- src/__pycache__
- scripts/__pycache__

## Files added or modified

| File | Change |
|---|---|
| .gitignore | Added ignore rules for Python bytecode, test/tool caches, virtual environments, temporary files, and logs. The OSM response cache under notebooks/cache/ remains tracked. |
| requirements.txt | Added pinned dependencies matching the verified Python 3.13 environment. |
| README.md | Replaced the stale project overview with current architecture, installation, run commands, limits, and report links. |
| src/routing/two_edge_selector.py | Fixed imports, lookahead destination propagation, and evaluator weight refresh; added adaptive evaluator handling. |
| src/routing/route_controller.py | Consolidated duplicated control flow and repaired update acceptance, reverse-edge backtracking, cycle recovery, and journey metrics. |
| scripts/run_phase11_dashboard.py | Updated deprecated Streamlit width arguments. |
| scripts/train_phase7_speed_predictor.py | Corrected a mathtext string escape warning. |
| tests/test_two_edge_routing.py | Corrected test assumptions and added multi-candidate lookahead/current-weight coverage. |
| GEOPULSE_COMPLETE_PROJECT_REPORT.md | Added the detailed repository, architecture, feature-status, verification, and Phase 2 readiness audit. |
| GEOPULSE_CLEANUP_MANIFEST.md | This file: exact cleanup and preservation record. |

The routing controller and selector already contained user edits before the audit. Those edits were inspected and carried forward in the resulting fixes.

## Important files and data preserved

- Canonical structured traffic data: datasets/traffic_structured_v1.parquet and datasets/traffic_v1.duckdb.
- Traffic-to-OSM mapping: data/processed/traffic_to_osm_mapping_final.parquet.
- Bhubaneswar and Jaipur OSM GraphML networks.
- LightGBM model and feature metadata under models/.
- Phase 7-11 predictions, metrics, experiment results, and figures under results/, except the exact duplicate CSVs and audit-generated files listed above.
- The three notebooks/cache/ OSMnx response-cache files; they reproduce graph topology and are not Python bytecode caches.
- geopulse smartroute/archive.zip, which contains canonical data plus unique data dictionary and snapshot notes.
- Distinct historical audit notes geopulse smartroute/docs/dataset_audit_report.md and geopulse smartroute/docs/dataset_audit_summary.json.

## Preserved for review

- src/audit_delhi_dataset.py and outputs/delhi_dataset_audit/: retained because they are not duplicates; check their dataset path assumptions before reuse.
- Historical phase/methodology reports: retained where they contain unique steps or results. Reconcile any completion or performance claims against the complete audit before citing them.
- Historical results/two_edge_experiments/master_algorithm_comparison.csv: retained as evidence of the pre-repair benchmark; it was not regenerated after the current route-controller fixes.

## Remaining cleanup recommendations

1. Re-run the Two-Edge multi-origin/destination benchmark after reducing real-network cycle fallback, and replace or date the historical comparison outputs.
2. Reconcile old phase reports against the audited feature status.
3. Review the Delhi audit's external path assumptions if that dataset is to be used.
4. Keep generated experiment output cleanup selective: preserve canonical results and remove only confirmed duplicates or disposable run artifacts.

## Git and verification record

The audit made no commit or push. Final Git status reports 131 changed paths, including the four new root files listed above; the tracked diff summary is 127 files changed, 476 insertions, and 5,336 deletions. git diff --check exited successfully. Git emitted only its LF-to-CRLF normalization notices for the README and modified Python files.

Final verification: Python compilation succeeded; the full suite passed **69 tests in 16.42 seconds**. Afterward, regenerated bytecode and two AppTest dashboard files were removed. A final inventory found zero .pyc files under src/, tests/, or scripts/, no .pytest_cache directory, and no dashboard run artifacts dated 20261122.

