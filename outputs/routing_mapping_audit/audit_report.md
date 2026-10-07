# GeoPulse routing network mapping audit

Read-only audit. The raw DuckDB and GraphML were not modified, and no ML models were trained. Route feasibility costs use only projected OSM geometry lengths, never the traffic travel-time columns.

## A. Mapping summary

| Metric | Value |
| --- | ---: |
| Traffic segments | 700 |
| OSM graph nodes | 18260 |
| OSM graph directed edges | 46679 |
| Previous unique mapped directed endpoint pairs | 645 |
| Duplicate mapping groups / segment pairs | 55 / 55 |
| Multi-ID segments | 87 |
| ID-expanded weak components | 44 |
| ID-expanded largest component nodes | 101 |
| ID-expanded largest component edges | 100 |
| Improved mapped segments in largest mapped component | 25 (3.57%) |
| Improved mapped largest component nodes / edges | 20 / 19 |

## 1. Reproduced previous method

The previous script uses EPSG:4326 traffic points, projects points and graph edge LineStrings into EPSG:32645 (UTM zone 45N), queries actual edge geometries within 500 m, and selects minimum score `distance/50 + road_type_mismatch + 0.25*abs(log(dataset_length/projected_edge_geometry_length))`. It compares directed edges independently; it does not collapse reciprocal directions. OSM IDs are parsed for existence but are not used in the score. Multi-ID segments are not treated as bundles. Length is the projected geometry length, not GraphML's `length` attribute. Road type is a coarse exact-class comparison, with unknown `other` treated as compatible. The previous CSV omits the graph edge key, so parallel edges sharing `(u,v)` cannot be distinguished from that CSV alone.

## 2. Duplicate mapping pairs

The 700 previous assignments collapse to 645 unique directed endpoint pairs: 55 pairs of segments share one best `(u,v)` edge, producing 55 repeated assignments. Of the 55 pairs, 31 have identical coordinates, length, road type, and source OSM ID; 19 have identical complete hourly currentSpeed arrays (including missing positions), and 10 satisfy both tests. Pair classification counts: {"B. Same edge but potentially different traffic measurement": 21, "C. Mapping ambiguity": 23, "A. Clearly duplicate physical segment": 10, "D. Probably legitimate separate observations": 1}. These are mapping collisions and likely physical duplicates, but do not delete either row without establishing whether they are duplicate API records or distinct measurements of one physical edge.

Full requested per-pair fields, correlations, overlapping-observation counts, and classifications are in `duplicate_mapping_pairs.csv`.

## 3. Multi-OSM-ID segments

There are 87 multi-ID segments. 87 have every parsed ID represented in the GraphML; 85 have connected graph topology, but only 0 have both one graph component and one combined geometry component; 2 are disconnected or ambiguous. Their component/length/point results are in `multi_osm_id_segments.csv`; ten largest combined-length mismatches are in `multi_osm_id_examples_10.csv`. Combined OSM geometry length / traffic length median/min/max: 2.570 / 0.995 / 31.986. The per-ID JSON lists individual directed edge counts, unique physical geometry-piece counts, lengths, and highway tags. Geometry union deduplicates exact reciprocal/reverse lines; it cannot prove the API's own segment geometry because that polyline is not stored.

| segment_id | osmid_list | traffic_length_m | combined_geometry_length_m | combined_over_traffic_length_ratio | point_to_combined_geometry_m | relationship_assessment |
| --- | --- | --- | --- | --- | --- | --- |
| 441 | 1210277736;870242503;870242504 | 101.59319729986645 | 3249.6034825067413 | 31.986427919136013 | 0.023806152245818543 | topologically connected but geometry has multiple parts |
| 341 | 26754491;876134933 | 131.27828741015398 | 2817.054529403546 | 21.458647770154073 | 0.06490471013629262 | topologically connected but geometry has multiple parts |
| 549 | 1141889032;1141889036 | 83.41449494471067 | 1553.7387899964133 | 18.626724180566846 | 0.16712154662586842 | topologically connected but geometry has multiple parts |
| 255 | 1393752821;742084229;44947109 | 165.30941993060364 | 3051.056944132325 | 18.456642975416337 | 0.6563780106834032 | topologically connected but geometry has multiple parts |
| 406 | 279088748;456959531;1208986540;264753949 | 113.67030006572054 | 1954.362739129002 | 17.193257499971864 | 1.0521391472893618 | topologically connected but geometry has multiple parts |
| 288 | 874459840;40016878;874459839 | 153.32855012754362 | 2241.3000993374953 | 14.617630555256081 | 0.13688000875842785 | topologically connected but geometry has multiple parts |
| 311 | 746487578;746487579;879562788 | 144.40599390338113 | 1984.129894696405 | 13.739941404537145 | 0.05334564261034204 | topologically connected but geometry has multiple parts |
| 265 | 874459841;874459842;466615091 | 160.7785741574832 | 2112.030498920006 | 13.136268373989088 | 0.8146613827216161 | topologically connected but geometry has multiple parts |
| 432 | 219116708;478371821 | 104.18472459641404 | 1343.3453532286426 | 12.893880157887171 | 0.0006708689071292324 | topologically connected but geometry has multiple parts |
| 87 | 865024248;869997541 | 356.9228028032657 | 4371.947561246733 | 12.24900041944513 | 1.560929121521543 | topologically connected but geometry has multiple parts |

## 4. Directed and undirected connectivity

| representation | nodes | edges | weak_components | largest_component_nodes | largest_component_edges | strongly_connected_components | largest_scc_nodes | largest_scc_node_pct | traffic_segments_in_largest | traffic_segment_pct_in_largest | observations_in_largest | observation_pct_in_largest |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full OSM directed graph | 18260 | 46679 | 1 | 18260 | 46679 | 15.0 | 18230.0 | 99.83570646221249 |  |  |  |  |
| full OSM undirected physical graph | 18260 | 24503 | 1 | 18260 | 24503 |  |  |  |  |  |  |  |
| previous best edge | 867 | 645 | 227 | 20 | 19 | 862.0 | 2.0 | 0.2306805074971165 | 25.0 | 3.5714285714285716 | 8835.0 | 3.5856476690246306 |
| previous best edge (undirected) | 867 | 640 | 227 | 20 | 19 |  |  |  | 25.0 | 3.5714285714285716 | 8835.0 | 3.5856476690246306 |
| improved best edge | 869 | 651 | 221 | 20 | 19 | 866.0 | 2.0 | 0.23014959723820483 | 25.0 | 3.5714285714285716 | 8835.0 | 3.5856476690246306 |
| improved best edge (undirected) | 869 | 648 | 221 | 20 | 19 |  |  |  | 25.0 | 3.5714285714285716 | 8835.0 | 3.5856476690246306 |
| all graph edges for supplied OSM IDs | 1041 | 1102 | 44 | 101 | 100 | 889.0 | 50.0 | 4.803073967339097 | 59.0 | 8.428571428571429 | 20845.0 | 8.459855762401633 |
| all graph edges for supplied OSM IDs (undirected) | 1041 | 1002 | 44 | 101 | 100 |  |  |  | 59.0 | 8.428571428571429 | 20845.0 | 8.459855762401633 |

The full graph has 15 strongly connected components; its largest has 18230 nodes (99.8% of nodes). 692/700 selected traffic-edge assignments have both endpoints in that largest SCC. Weak-component results are unchanged after collapsing reciprocal directions; directionality is not the main cause of the mapped-subnetwork fragmentation. The mapped subset remains highly fragmented in its undirected physical projection. Thus the dominant issue is sparse/disconnected mapped coverage, not simply counting each road direction separately.

## 5. Improved matching method

Each candidate edge is scored with visible components: distance score `exp(-d/50m)` (30%); length similarity `exp(-abs(log(traffic_length/effective_way_length)))` (20%); road class (20%); exact OSM-ID evidence (30%). For ID-supported candidates, effective OSM length is the union length of the supplied OSM way geometry, deduplicating reverse copies; otherwise it is the candidate way's union length. Candidates are restricted to actual edge geometries within 500 m. Top five per traffic segment, including score components, edge key and OSM ID evidence, are in `improved_candidate_rankings_top5.csv`; selected assignments are in `improved_best_matches.csv`.

Improved match coverage: 700/700; OSM-ID-supported best candidates: 700; median/p95/max distance 0.135/6.435/87.490 m; broad class match 100.00%. This is a reproducible ranking, not ground-truth validation; direction remains unresolved for candidates with reciprocal identical geometry.

## 6. Largest connected traffic subset

Improved best-edge mapping: 25/700 segments (3.57%) in its largest weak component, with 20 nodes and 19 edges; that is **Unusable** by the project thresholds. Expanding each traffic segment to all supplied OSM IDs increases the largest mapped component to 59/700 (8.43%). Full component metrics, including observation share, are in `summary.json`.

## 7. Segment geometry overlap screen

There are 525 segment-centroid pairs within 100 m. Using best-matched OSM edge lines as inferred geometries (traffic polylines are unavailable), pair counts are {"unrelated": 341, "adjacent": 137, "duplicate": 47}. This is a proxy screen: it can identify duplicate/overlapping OSM assignments but cannot establish overlap of the traffic provider's original polylines. Full pair details are in `close_segment_geometry_pairs.csv`.

## 8. Why 700 assignments became 645

Reconciliation on the previous CSV's `(u,v)` identity: 700 segment assignments = 645 unique directed endpoint pairs + 55 repeated assignments. The repeated portion is exactly 55 two-segment groups. Collapsing directed endpoint pairs to unordered physical endpoint pairs gives 640 pairs; the difference is reciprocal directions sharing physical endpoints. Multi-ID status (87 segments) overlaps this accounting and is not an additional subtraction. The previous output has 0 unmatched traffic segments. The CSV did not preserve GraphML edge `key`, so “645 unique graph multiedges” was not proven; it is 645 unique directed endpoint pairs.

## 9-10. Routing feasibility and dynamic coverage

Sampled 100 reproducible ordered OD pairs from the largest weak component (seed 20261006, minimum straight-line OD separation 2000 m). Shortest paths use projected OSM geometry length; 100 routes succeeded, 0 failed (100.0% success). Median route distance: 7658.3 m.

Dynamic physical-edge coverage uses unique mapped undirected endpoint pairs because traffic direction is not fully established. Mean/median/min/max/Q25/Q75 coverage: 14.07% / 11.52% / 0.00% / 58.33% / 3.38% / 19.67%. Routes above 25/50/75/90% coverage: 17.0% / 3.0% / 0.0% / 0.0%. Each route is in `routing_od_feasibility_100.csv`.

## 11. Architecture comparison

| Architecture | Feasible? | Scientific quality | Recommendation |
|---|---|---|---|
| A. Route directly on 700 traffic segments | No, not as-is | Weak: disconnected and duplicate mappings | Reject |
| B. Full OSM graph, predictions only on matched edges | Yes | Conditional; needs explicit static fallback and verified edge map | Viable baseline design |
| C. Largest traffic-mapped component | Yes, but limited | Use only if measured component is large enough; current output provides measured share | Not preferred unless scope is explicitly limited |
| D. Aggregate traffic segments onto physical OSM roads | Yes as preprocessing | Necessary for repeated assignments, but does not fix connectivity alone | Apply as mapping cleanup |
| E. Full OSM graph + validated dynamic costs + static costs elsewhere | Yes, conditional | Best preserves topology while making sparse coverage explicit | **Recommend** |

A is simple but cannot route reliably on the disconnected traffic-only graph. B and E preserve OSM connectivity, but route results depend on transparent static fallback and validated direction-aware mapping; E makes that fallback explicit. C permits claims only within the measured connected traffic subset, which is small here. D is necessary to handle repeated traffic-to-road assignments cleanly, but aggregation alone does not join disconnected components. Do not treat routes with low dynamic coverage as evidence of citywide dynamic-routing benefit.

## Limitations

No traffic segment polylines are stored, so overlap is inferred from matched OSM edge geometry and centroids. `candidate_u/v` in the old spatial CSV did not include GraphML multiedge key. Exact OSM-ID geometry is strong evidence but not proof of API segment boundaries. Traffic time fields were not used as costs. Directed speed assignment is uncertain where a traffic record cannot be tied to one travel direction. The OD sample is a feasibility screen, not a route-benefit experiment.
