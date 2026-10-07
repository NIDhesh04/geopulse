# Phase 1 Evaluation Guide & Artifact Catalog

**GeoPulse Bhubaneswar — Dataset & Road-Network Validation Report**  
*Location:* `outputs/phase1/`

---

## 📊 Overview of Phase 1 Outputs

This folder houses the empirical evidence, statistical summaries, generated network figures, and the formal technical report for **Phase 1: Dataset & Road-Network Validation**.

---

## 📑 Directory Contents

### 1. Reports (`outputs/phase1/reports/`)
- **[PHASE1_REPORT.md](file:///c:/users/nidhe/Projects/geopulse_bhu/outputs/phase1/reports/PHASE1_REPORT.md)**:  
  The full, 15-section technical specification and validation report. It details:
  - Theoretical grid alignment & dimensions
  - DuckDB/Parquet schema vs. CSV differences
  - Missingness run lengths and temporal distributions
  - Travel time semantics ($19\text{ km}$ macro-corridor vs. $129\text{ m}$ road segment)
  - Geometric mapping to OpenStreetMap ways (0.13m median offset)
  - Full graph topology ($888$ nodes, $760$ edges, $264$ components)
  - Proof that $\mu = 0$ (Forest) and alternative path availability is $0.0\%$
  - Formal suitability scorecard ($46.25 / 100$)
  - Explicit Go / Go with Modifications / No-Go recommendations

---

### 2. Figures Catalog (`outputs/phase1/figures/`)

All figures are rendered as publication-grade PNGs (130–140 DPI):

| Filename | Description | Key Insight for Presentations |
|---|---|---|
| **[network_overview.png](file:///c:/users/nidhe/Projects/geopulse_bhu/outputs/phase1/figures/network_overview.png)** | Full spatial layout of the 700 traffic segments mapped onto physical coordinates, color-coded by OSM road classification (trunk, primary, secondary). | Demonstrates that the dataset covers major arterial avenues across Bhubaneswar, from NH-16 to master road corridors. |
| **[network_segment_graph_lcc.png](file:///c:/users/nidhe/Projects/geopulse_bhu/outputs/phase1/figures/network_segment_graph_lcc.png)** | Visual breakdown of connected components. The Largest Connected Component (15 nodes) is highlighted in bold red against other disconnected components in grey. | Visually proves that segments are disjoint corridors rather than a connected mesh. |
| **[degree_distribution.png](file:///c:/users/nidhe/Projects/geopulse_bhu/outputs/phase1/figures/degree_distribution.png)** | Histogram of undirected node degrees in $G_{seg}$. | Mean degree is 1.41; 60.6% of nodes are degree 1 (dead ends). |
| **[example_reroute.png](file:///c:/users/nidhe/Projects/geopulse_bhu/outputs/phase1/figures/example_reroute.png)** | Route selection on the largest connected component under free-flow vs. heavy congestion. | Proves that because $\mu = 0$, the shortest path is the *only* path—no alternative exists to divert traffic. |
| **[route_change_rate_over_time.png](file:///c:/users/nidhe/Projects/geopulse_bhu/outputs/phase1/figures/route_change_rate_over_time.png)** | Rerouting trigger rate evaluated over time across 100 consecutive hours. | A completely flat 0.0% line demonstrating zero dynamic route shifts on $G_{seg}$ alone. |
| **[coverage_over_time.png](file:///c:/users/nidhe/Projects/geopulse_bhu/outputs/phase1/figures/coverage_over_time.png)** | Hourly timeline showing the number of actively observed road segments (out of 700). | Shows high continuous uptime (~700 segments/hour) except for the initial 35–48h polling outage. |
| **[missingness_by_segment.png](file:///c:/users/nidhe/Projects/geopulse_bhu/outputs/phase1/figures/missingness_by_segment.png)** | Missing percentage sorted across all 700 segments. | Missingness is remarkably uniform (8.88% to 12.44%), with zero catastrophic sensor dropouts. |
| **[missingness_hour_of_day.png](file:///c:/users/nidhe/Projects/geopulse_bhu/outputs/phase1/figures/missingness_hour_of_day.png)** | Missingness distributed by Indian Standard Time (IST) hour-of-day. | Proves that missingness is not concentrated during peak hours (uniformly distributed around 9–12%). |
| **[gap_length_hist.png](file:///c:/users/nidhe/Projects/geopulse_bhu/outputs/phase1/figures/gap_length_hist.png)** | Frequency histogram of consecutive missing gap lengths (in hours). | Missingness occurs as single systemic outage blocks (35h and 49h) rather than erratic dropouts. |
| **[traffic_distributions.png](file:///c:/users/nidhe/Projects/geopulse_bhu/outputs/phase1/figures/traffic_distributions.png)** | Log-scaled distribution histograms for speed, travel time, and confidence. | Confirms clean, physically valid distributions without negative or zero values. |

---

### 3. Metrics & Machine-Readable Data (`outputs/phase1/metrics/`)

| Metric File | Key Contents & Purpose |
|---|---|
| **`dataset_structure.json`** | Total rows ($275,800$), grid dimensions, min/max timestamps, IST conversion verification, observed counts. |
| **`numeric_summary.csv`** | Summary statistics (mean, std, percentiles $1\%, 5\%, 25\%, 50\%, 75\%, 95\%, 99\%$, zero counts) for all traffic fields. |
| **`semantic_checks.json`** | Verification of physical laws (`currentSpeed <= freeFlowSpeed`, `speed_ratio == cs / ffs`, length CVs). |
| **`missingness_summary.json`** | Quantiles of missingness by segment, timestamp outages, and gap length run statistics. |
| **`duckdb_inventory.json`** | Complete schemas, row counts, and column types across DuckDB tables, views, and Parquet metadata. |
| **`metadata_checks.json`** | Inspection of static attributes, OSM IDs, bounding boxes, road type distributions, and TomTom signatures. |
| **`topology.json`** | Graph metrics for $G_{seg}$: nodes, directed/undirected edges, WCC/SCC distributions, degree distribution, cyclomatic complexity. |
| **`route_diversity.json`** | Detailed results of Yen k-shortest paths, simple path enumeration, and congestion scenarios on $G_{seg}$. |
| **`segment_missingness.csv`** | Per-segment missingness percentages and total observation counts. |
| **`timestamp_missingness.csv`** | Per-hour observation percentages across the 394 hours. |
| **`gap_runs.csv`** | Detailed log of every single consecutive missing data run per segment. |
| **`tomtom_signature_groups.csv`** | Grouping of segments that share identical speed profiles and TomTom flow identifiers. |

---

## 🎓 Viva & Presentation Talking Points

1. **Why we didn't jump directly into ML:**  
   *"In intelligent transportation research, data must be verified against physical network topology. Training an ML model on speeds without validating network connectivity would have led to a system that predicts traffic accurately but cannot route vehicles."*

2. **The physical travel time discovery:**  
   *"We verified that TomTom API travel times represent a 19 km probe corridor rather than the 129 m road edge. Using raw travel times would have produced nonsensical route costs; our formulation properly scales cost to edge length: $T_e = D_e / (v_e / 3.6)$."*

3. **How we solved the 0% alternative path blocker:**  
   *"Because the 700 monitored segments form an acyclic forest ($\mu=0$), we formulated the **Hierarchical Network Embedding Architecture**: dynamic ML traffic predictions are injected onto the arterial links of Bhubaneswar's complete OpenStreetMap road network, enabling true dynamic rerouting."*
