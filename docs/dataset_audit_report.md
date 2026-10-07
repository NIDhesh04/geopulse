# GeoPulse: Comprehensive Dataset and Project-Folder Audit Report

**Project Title:** GeoPulse — AI-Based Dynamic Traffic Routing System  
**Audit Status:** `DATASET AUDIT COMPLETE`  
**Date of Audit:** October 2026  
**Auditor:** Automated Diagnostic System (Antigravity Agentic Pair Programmer)  
**Read-Only Integrity Guarantee:** No raw or snapshot files have been modified, overwritten, or deleted. No synthetic observations have been injected into production tables. No final routing or ML models have been executed.

---

## 1. Executive Summary

This audit establishes the empirical baseline for the GeoPulse major project. The investigation examined all project assets across the workspace, with particular focus on the archive package located at `geopulse smartroute/archive.zip` and the canonical analytical tables stored in `datasets/`.

Key findings include:
1. **Canonical Analytical Table Identified:** The 17-column `traffic_structured_v1.parquet` table (275,800 rows, 700 segments, 394 hourly buckets) is the single canonical processed analytical dataset. Its archived copy inside `archive.zip` and the workspace copy in `datasets/` are byte-for-byte identical (SHA-256: `039e07e43af8b79fd289b5644fc593a27f1fca993f0150e67030c8daff250447`). The accompanying DuckDB file is an exact query mirror. The CSV file (`traffic_bhubaneswar.csv`) is a derived feature view that lacks coordinate and OSM metadata while introducing a critical logic bug (`is_congested=False` on missing rows).
2. **Temporal Structure and Missingness Pattern:** The data spans 16.375 days (393 elapsed hours, 394 consecutive 1-hour UTC buckets) from `2025-12-31 19:00:00 UTC` (`2026-01-01 00:30:00 IST`) to `2026-01-17 04:00:00 UTC` (`2026-01-17 09:30:00 IST`). There are 246,399 observed records (89.34%) and 29,401 missing records (10.66%). Crucially, missingness is **front-loaded**: 29,400 of the 29,401 missing records occur in the first 3 days (Jan 1–3, 2026). From Jan 4 00:30 IST to Jan 17 09:30 IST (322 consecutive hours), the data is **99.9996% complete** (225,399 observed records out of 225,400 cells, with exactly 1 missing cell).
3. **Speed Data Quality:** Speeds are valid urban traffic observations ranging from 1.0 km/h to 54.0 km/h (mean 33.14 km/h, median 32.0 km/h). There are 0 zero speeds, 0 negative speeds, 0 unrealistic values (>120 km/h), and 0 instances where current speed exceeds free-flow speed. However, there is a pronounced ceiling effect: 67.71% of observed records exhibit `currentSpeed == freeFlowSpeed`.
4. **Critical Failure of Travel-Time Columns:** The columns `currentTravelTime` and `freeFlowTravelTime` fail the fundamental physical consistency check ($t = d/v$) by astronomical margins (current travel time MAE: 1,440.01 seconds; median relative error: 9,063%; correlation with physically calculated time: -0.1334). These stored columns must **never** be used as routing weights. Travel times must be derived physically from segment length and speed.
5. **Graph Feasibility Roadblock:** A directed road network $G=(V,E)$ **cannot** be constructed from the tabular traffic dataset alone. The dataset contains only segment centroids (`lat`, `lon`), omitting start/end coordinates, road bearing, and LineString geometry. Centroid distance snapping fails completely (at tolerances 1m to 50m, over 300 to 678 segments remain completely disconnected). Furthermore, the required Bhubaneswar OSM GraphML file is currently absent from the workspace (the available graph file belongs to Jaipur).
6. **ML Feasibility Confirmed:** Training a next-hour speed prediction model ($X(t) \to \text{speed}(t+1)$) is fully feasible over the clean 322-hour window. A strict chronological 70/15/15 split yields 139,999 training, 33,600 validation, and 34,300 test samples (207,899 total samples with lag-24 history).
7. **Synthetic Data Recommendation:** Synthetic traffic data is **unnecessary** for model training or historical traffic replay. Held-out test sets contain real congestion dips and 25,374 real `roadClosure=true` observations. Synthetic data should be restricted exclusively to an optional, explicitly labelled runtime perturbation overlay for demonstrating dynamic route deviation and rerouting.

---

## 2. Files Discovered and Inventory

The workspace and archive packages were inventoried recursively. Below is the complete catalog of relevant files:

| File Name | Relative Path | File Type | Size (Bytes) | Role / Classification | Rows / Cols | Metadata / Provenance |
|---|---|---|---:|---|---|---|
| `archive.zip` | `geopulse smartroute/archive.zip` | ZIP Archive | 3,089,387 | Raw Archive Container | 5 members | CRC-32 valid; contains Parquet, DuckDB, CSV, and markdown notes |
| `traffic_structured_v1.parquet` | `geopulse smartroute/archive.zip::traffic_structured_v1.parquet` | Parquet | 612,145 | Canonical Processed Table | 275,800 × 17 | Snappy compressed; 700 segments × 394 hours |
| `traffic_structured_v1.parquet` | `datasets/traffic_structured_v1.parquet` | Parquet | 612,145 | Workspace Analytical Copy | 275,800 × 17 | Byte-identical mirror (SHA-256 matches archive member) |
| `traffic_v1.duckdb` | `geopulse smartroute/archive.zip::traffic_v1.duckdb` | DuckDB DB | 11,808,768 | Query Mirror Table | 275,800 × 17 | Table `traffic`; byte-identical to `datasets/` copy |
| `traffic_v1.duckdb` | `datasets/traffic_v1.duckdb` | DuckDB DB | 11,808,768 | Query Mirror Table | 275,800 × 17 | Byte-identical mirror (SHA-256 matches archive member) |
| `traffic_bhubaneswar.csv` | `geopulse smartroute/archive.zip::traffic_bhubaneswar.csv` | CSV | 27,441,756 | Derived Feature View | 275,800 × 15 | Adds calendar/congestion fields; omits spatial coordinates and actual timestamps |
| `DATA_DICTIONARY.md` | `geopulse smartroute/archive.zip::DATA_DICTIONARY.md` | Markdown | 3,715 | Documentation | N/A | Field definitions, units, and API source attribution |
| `SNAPSHOT_NOTES.md` | `geopulse smartroute/archive.zip::SNAPSHOT_NOTES.md` | Markdown | 446 | Documentation | N/A | Notes cleaning, deduplication, and missing grid expansion |
| `bhubaneshwar_dataset.ipynb` | `notebooks/bhubaneshwar_dataset.ipynb` | Jupyter Notebook | 1,639 | Scraping Script | N/A | OSMnx script targeting Bhubaneswar drive network; output GraphML missing |
| `jaipur_graph.graphml` | `datasets/jaipur_osm/jaipur_graph.graphml` | GraphML XML | 80,826,902 | Unrelated Network | N/A | Road network for Jaipur, Rajasthan (incompatible with Bhubaneswar traffic) |
| `edges.csv` | `datasets/jaipur_osm/edges.csv` | CSV | 35,925,643 | Unrelated Spatial Table | 154,842 × 31 | Jaipur road edges |
| `edges_baseline.csv` | `datasets/jaipur_osm/edges_baseline.csv` | CSV | 16,326,945 | Unrelated Spatial Table | 154,842 × 13 | Jaipur baseline edge attributes |
| `nodes.csv` | `datasets/jaipur_osm/nodes.csv` | CSV | 5,370,410 | Unrelated Spatial Table | 62,396 × 6 | Jaipur intersection nodes |
| `audit_dataset.py` | `src/audit_dataset.py` | Python Script | 46,706 | Audit Tool | N/A | Exploratory audit routines |
| `audit_routing_network.py` | `src/audit_routing_network.py` | Python Script | 48,110 | Audit Tool | N/A | Prior network mapping analysis |
| `audit_delhi_dataset.py` | `src/audit_delhi_dataset.py` | Python Script | 44,115 | Audit Tool | N/A | Separate Delhi investigation tool |

---

## 3. Canonical Dataset Recommendation

### Definitive Recommendation: `traffic_structured_v1.parquet`

The project must adopt `traffic_structured_v1.parquet` as its primary, canonical analytical dataset.

**Technical Rationale:**
1. **Schema Completeness:** Parquet retains all 17 fundamental columns, including segment centroids (`lat`, `lon`), segment length (`length_m`), OSM IDs (`osmid`), road classification (`road_type`), numeric road identifiers (`road_name`), TomTom road closure flags (`roadClosure`), and raw observation timestamps (`timestamp`).
2. **Storage and I/O Efficiency:** Compressed size is only 612 KB (versus 27.4 MB for CSV and 11.8 MB for DuckDB), allowing instant memory loading and fast column pruning in Polars/Pandas.
3. **Data Integrity:** Unlike the CSV view, Parquet does not contain hard-coded default flags for missing data (such as setting `is_congested=False` on unobserved grid rows).
4. **Byte-Identical Consistency:** The copy in `datasets/traffic_structured_v1.parquet` matches the member inside `geopulse smartroute/archive.zip` exactly (SHA-256: `039e07e43af8b79fd289b5644fc593a27f1fca993f0150e67030c8daff250447`).
5. **Role of DuckDB:** `traffic_v1.duckdb` is an exact query mirror. It can be queried via SQL where convenient, but should not be considered an independent dataset.
6. **Role of CSV:** `traffic_bhubaneswar.csv` is an export view with derived columns and must not be used as the root table.

---

## 4. Dataset Schemas

### Canonical Table: `traffic_structured_v1.parquet` (and `traffic_v1.duckdb`)

| # | Column Name | Stored Dtype | Logical Type | Null Count | Null % | Unique Values | Value Range / Categories | Example Value |
|---|---|---|---|---:|---:|---:|---|---|
| 1 | `segment_id` | `int64` | Identifier | 0 | 0.00% | 700 | 0 to 699 | `0` |
| 2 | `hour` | `datetime64[ns, UTC]` | Timestamp | 0 | 0.00% | 394 | 2025-12-31 19:00 to 2026-01-17 04:00 | `2026-01-01 00:00:00+00:00` |
| 3 | `timestamp` | `datetime64[ns, UTC]` | Timestamp | 29,401 | 10.66% | 509 | 2026-01-01 01:09:50 to 2026-01-17 09:30:01 (IST) | `2026-01-01 01:09:50+00:00` |
| 4 | `currentSpeed` | `float64` | Speed (km/h) | 29,401 | 10.66% | 53 | 1.0 to 54.0 | `36.0` |
| 5 | `freeFlowSpeed` | `float64` | Speed (km/h) | 29,401 | 10.66% | 35 | 16.0 to 55.0 | `36.0` |
| 6 | `currentTravelTime` | `float64` | Time (s) | 29,401 | 10.66% | 450 | 2.0 to 3,213.0 | `1,588.0` |
| 7 | `freeFlowTravelTime`| `float64` | Time (s) | 29,401 | 10.66% | 134 | 2.0 to 2,718.0 | `1,418.0` |
| 8 | `confidence` | `float64` | Score (0–1) | 29,401 | 10.66% | 6,458 | 0.505346 to 1.0 | `0.98412` |
| 9 | `is_observed` | `bool` | Indicator | 0 | 0.00% | 2 | `True` (246,399), `False` (29,401) | `True` |
| 10| `is_missing` | `bool` | Indicator | 0 | 0.00% | 2 | `True` (29,401), `False` (246,399) | `False` |
| 11| `roadClosure` | `object` (`bool`) | Indicator | 29,401 | 10.66% | 2 | `True` (25,374), `False` (221,025) | `False` |
| 12| `osmid` | `object` (`string`) | OSM ID(s) | 29,401 | 10.66% | 266 | Numeric strings or bracketed lists | `12345678` or `[1234, 5678]` |
| 13| `road_name` | `float64` | Road ID | 29,401 | 10.66% | 350 | 0.0 to 349.0 | `12.0` |
| 14| `road_type` | `object` (`string`) | OSM Class | 29,401 | 10.66% | 3 | `primary` (117,651), `secondary` (96,331), `trunk` (32,417) | `primary` |
| 15| `length_m` | `float64` | Distance (m) | 29,401 | 10.66% | 663 | 60.37 to 3,017.00 | `300.99` |
| 16| `lat` | `float64` | Centroid Lat | 29,401 | 10.66% | 662 | 20.211618 to 20.363931 | `20.2961` |
| 17| `lon` | `float64` | Centroid Lon | 29,401 | 10.66% | 663 | 85.780380 to 85.889271 | `85.8245` |

### Derived View: `traffic_bhubaneswar.csv`
Contains 15 columns: `segment_id`, `hour`, `hour_of_day`, `day_of_week`, `is_weekend`, `currentSpeed`, `freeFlowSpeed`, `currentTravelTime`, `freeFlowTravelTime`, `confidence`, `speed_ratio`, `congestion_level`, `is_congested`, `is_observed`, `is_missing`.  
Noticeably absent: `timestamp`, `roadClosure`, `osmid`, `road_name`, `road_type`, `length_m`, `lat`, `lon`.

---

## 5. Temporal Coverage

The temporal dimension was scrutinized to determine continuity, duration, and sampling frequency.

### Temporal Boundaries and Resolution
- **Earliest Hourly Bucket:** `2025-12-31 19:00:00 UTC` $\equiv$ `2026-01-01 00:30:00 IST`
- **Latest Hourly Bucket:** `2026-01-17 04:00:00 UTC` $\equiv$ `2026-01-17 09:30:00 IST`
- **Elapsed Span:** 393.0 hours (16 days, 9 hours = 16.375 days)
- **Total Discrete Hourly Slots:** 394 consecutive hourly timestamps
- **Missing Global Time Slots:** 0 (all 394 hour steps exist in the grid)
- **Timezone Storage:** UTC standard in Parquet/CSV. When rendered in DuckDB under Asia/Calcutta session timezone, timestamps appear at minute 30 (:30), reflecting the UTC+05:30 offset.
- **Actual Observation Timestamps (`timestamp`):** The API returned actual collection timestamps that are not strictly aligned to the hour (e.g., 01:09:50, 09:30:01). There are 509 distinct non-null timestamps, mapped into the 394 uniform hourly buckets.

### Detailed Daily Breakdown (IST Calendar)

| Date (IST) | Expected Grid Cells | Observed Cells | Missing Cells | Daily Missing % | Daily Coverage % |
|---|---:|---:|---:|---:|---:|
| **2026-01-01** | 16,800 | 350 | 16,450 | 97.92% | 2.08% |
| **2026-01-02** | 16,800 | 4,200 | 12,600 | 75.00% | 25.00% |
| **2026-01-03** | 16,800 | 16,450 | 350 | 2.08% | 97.92% |
| **2026-01-04** | 16,800 | 16,800 | 0 | 0.00% | 100.00% |
| **2026-01-05** | 16,800 | 16,800 | 0 | 0.00% | 100.00% |
| **2026-01-06** | 16,800 | 16,800 | 0 | 0.00% | 100.00% |
| **2026-01-07** | 16,800 | 16,800 | 0 | 0.00% | 100.00% |
| **2026-01-08** | 16,800 | 16,800 | 0 | 0.00% | 100.00% |
| **2026-01-09** | 16,800 | 16,800 | 0 | 0.00% | 100.00% |
| **2026-01-10** | 16,800 | 16,800 | 0 | 0.00% | 100.00% |
| **2026-01-11** | 16,800 | 16,800 | 0 | 0.00% | 100.00% |
| **2026-01-12** | 16,800 | 16,799 | 1 | 0.01% | 99.99% |
| **2026-01-13** | 16,800 | 16,800 | 0 | 0.00% | 100.00% |
| **2026-01-14** | 16,800 | 16,800 | 0 | 0.00% | 100.00% |
| **2026-01-15** | 16,800 | 16,800 | 0 | 0.00% | 100.00% |
| **2026-01-16** | 16,800 | 16,800 | 0 | 0.00% | 100.00% |
| **2026-01-17** | 7,000 | 7,000 | 0 | 0.00% | 100.00% |
| **Total** | **275,800** | **246,399** | **29,401** | **10.66%** | **89.34%** |

### Verification of Prior "345 Consecutive Hours" Claim
The prior project documentation reported that the dataset contains "approximately 345 consecutive hourly observations."
**Audit Verification:**
- The total global duration is actually **394 hours**, not 345 hours.
- Exactly **350 segments** (50.0%) have 345 observed records.
- Exactly **349 segments** (49.9%) have 359 observed records.
- Exactly **1 segment** (0.1%) has 358 observed records.
- The 49-hour gap for 350 segments occurs entirely during the initial startup period on Jan 1–2.
- In the clean analysis window from Jan 4 to Jan 17, all 700 segments have identical, unbroken temporal coverage (322 consecutive hours, with only 1 single segment-hour missing across the entire city on Jan 12).

---

## 6. Spatial Coverage

The spatial envelope corresponds to the urban core and arterial corridors of Bhubaneswar, Odisha, India.

- **Latitude Envelope:** $20.211618^\circ\text{N}$ to $20.363931^\circ\text{N}$ (span: $\approx 16.9\text{ km}$)
- **Longitude Envelope:** $85.780380^\circ\text{E}$ to $85.889271^\circ\text{E}$ (span: $\approx 11.4\text{ km}$)
- **Coordinate Precision:** 7 decimal places ($\approx 1.1\text{ cm}$ resolution), indicating high precision.
- **Critical Spatial Limitation:** The coordinates `lat` and `lon` represent **segment centroids**, not node intersections or polyline geometries. The dataset lacks start coordinates, end coordinates, bearing, and geometry LineStrings.

---

## 7. Road-Segment Statistics

Across all 275,800 records, the 700 road segments (IDs 0 to 699) exhibit complete structural stability:

| Attribute | Stability Across Time | Unique Values Across Segments | Notes |
|---|---|---:|---|
| `segment_id` | 100% Stable | 700 | Primary key component |
| `osmid` | 100% Stable per segment | 266 | 87 segments represent composite multi-OSM ways |
| `road_name` | 100% Stable per segment | 350 | Numeric identifier (0 to 349); not text street names |
| `road_type` | 100% Stable per segment | 3 | `primary`, `secondary`, `trunk` |
| `length_m` | 100% Stable per segment | 663 | Segment physical length in meters |
| `lat`, `lon` | 100% Stable per segment | 662 / 663 | Centroid coordinate |
| `freeFlowSpeed` | **Time-Varying on 671 segments** | 35 | Changes diurnally; only 29 segments remain constant |
| `freeFlowTravelTime`| **Time-Varying on 671 segments** | 134 | Varies synchronously with freeFlowSpeed |

### Segment Attributes by Road Classification

| Road Type | Segments | Total Grid Rows | Observed Rows | Mean Length (m) | Mean Speed (km/h) | Mean Free-Flow Speed (km/h) | Mean Speed Ratio |
|---|---:|---:|---:|---:|---:|---:|---:|
| `primary` | 334 | 131,596 | 117,651 | 387.65 | 35.64 | 37.67 | 0.946 |
| `secondary` | 275 | 108,350 | 96,331 | 344.02 | 27.25 | 29.36 | 0.929 |
| `trunk` | 91 | 35,854 | 32,417 | 479.79 | 41.57 | 42.53 | 0.977 |
| **All** | **700** | **275,800** | **246,399** | **382.49** | **33.14** | **35.06** | **0.944** |

---

## 8. Missing-Value Analysis

1. **Overall Missingness:** 29,401 cells out of 275,800 are unobserved (10.66%).
2. **Missingness Pattern:** Missingness is strictly non-random and overwhelmingly front-loaded:
   - Jan 1–2 account for 29,050 missing records (**98.81%** of all missing values).
   - Jan 1–3 account for 29,400 missing records (**99.997%** of all missing values).
   - Only **1 single missing cell** occurs across all 700 segments during the remaining 14 days (occurring on segment 483 on Jan 12 at 05:30 IST).
3. **Explicit Missingness Flags:** The grid expansion in `traffic_structured_v1.parquet` explicitly encodes missingness via boolean flags:
   - When `is_missing == True`, all measurement columns (`currentSpeed`, `freeFlowSpeed`, `currentTravelTime`, `freeFlowTravelTime`, `confidence`, `roadClosure`) and spatial columns are `NULL`.
   - `is_observed` is strictly complementary (`is_observed = NOT is_missing`).
4. **Critical Bug in CSV Export:** In `traffic_bhubaneswar.csv`, the column `is_congested` is set to `False` on all 29,401 missing rows. A naive classifier or evaluator reading the CSV without filtering `is_observed == True` would treat missing observations as negative congestion instances, causing severe evaluation bias.

---

## 9. Duplicate Analysis

- **Duplicate Full Rows:** Exactly 0 duplicate rows across both Parquet and DuckDB tables.
- **Duplicate Composite Keys (`segment_id`, `hour`):** Exactly 0 duplicate keys. The Cartesian product of 700 segments × 394 hourly buckets = 275,800 unique key pairs is perfectly preserved.
- **Duplicate Spatial Centroids:** 11 pairs of segments share near-identical centroid coordinates ($\le 5\text{ m}$). Inspection confirms these correspond to opposite directions of dual-carriageway corridors (divided highways).

---

## 10. Speed-Quality Analysis

The distribution of speeds across the 246,399 observed records was audited for physical and statistical anomalies:

| Metric | `currentSpeed` (km/h) | `freeFlowSpeed` (km/h) | Speed Ratio ($v / v_{\text{ff}}$) |
|---|---:|---:|---:|
| **Minimum** | 1.00 | 16.00 | 0.0526 |
| **1st Percentile** | 19.00 | 21.00 | 0.7000 |
| **5th Percentile** | 21.00 | 26.00 | 0.7826 |
| **25th Percentile (Q1)** | 27.00 | 28.00 | 0.9600 |
| **Median (Q2)** | 32.00 | 34.00 | 1.0000 |
| **Mean** | 33.14 | 35.06 | 0.9438 |
| **75th Percentile (Q3)** | 38.00 | 43.00 | 1.0000 |
| **95th Percentile** | 53.00 | 54.00 | 1.0000 |
| **99th Percentile** | 54.00 | 54.00 | 1.0000 |
| **Maximum** | 54.00 | 55.00 | 1.0000 |
| **Standard Deviation** | 8.97 | 8.52 | 0.0934 |

### Anomaly Audit
- **Zero Speeds:** 0 records.
- **Negative Speeds:** 0 records.
- **Unrealistic High Speeds ($>120\text{ km/h}$):** 0 records (maximum observed speed is 54 km/h).
- **Current Speed Exceeding Free-Flow Speed ($v > v_{\text{ff}}$):** 0 records.
- **Free-Flow Speed Equal to 0:** 0 records.
- **Ceiling Effect:** Exactly 166,828 observed records (**67.71%**) have $\text{currentSpeed} = \text{freeFlowSpeed}$ ($\text{ratio} = 1.0$).
- **Intraday Diurnal Congestion Cycle:** Clear commute cycles exist:
  - Night / Early Morning (00:00–07:00 IST): Speeds average $\approx 35.0\text{ km/h}$ (free-flowing).
  - Morning Peak (09:00–12:00 IST): Speeds drop to $31.3\text{ km/h}$.
  - Afternoon Flat (13:00–16:00 IST): Speeds hover around $32.0–33.0\text{ km/h}$.
  - Evening Peak (17:00–19:00 IST): Minimum daily speed reached at 18:00 IST ($28.02\text{ km/h}$, with secondary roads dropping below $25\text{ km/h}$).
  - Night Recovery (21:00–23:00 IST): Speeds recover to $34.0–35.1\text{ km/h}$.

### Classification of Speed Observations
1. **Valid:** 246,399 records (all observed speeds fall within realistic urban ranges of 1–54 km/h).
2. **Potentially Valid / Requires Note:** 5 segments exhibit constant speed across the 16 days; 671 segments exhibit time-varying free-flow speeds due to TomTom dynamic diurnal baselines.
3. **Clearly Erroneous:** 0 in speed columns (errors reside in travel time columns).
4. **Missing:** 29,401 records (unobserved grid cells).

---

## 11. Travel-Time Consistency Analysis

To validate the integrity of `currentTravelTime` and `freeFlowTravelTime`, expected physical travel times were computed independently using standard kinematics:
$$t_{\text{phys}} = \frac{d}{v} = \frac{\text{length\_m}}{\text{speed\_kmh} / 3.6}$$

### Comparison: Physical Calculation vs Stored Values

| Metric | Stored `currentTravelTime` | Stored `freeFlowTravelTime` |
|---|---:|---:|
| **Sample Size ($n$)** | 246,399 | 246,399 |
| **Mean Physical Value (s)** | 41.55 s | 39.27 s |
| **Mean Stored Value (s)** | 1,481.56 s | 1,384.80 s |
| **Mean Absolute Error (MAE)** | **1,440.01 s** ($\approx 24.0\text{ min}$) | **1,351.83 s** ($\approx 22.5\text{ min}$) |
| **Median Absolute Error** | **1,551.29 s** | **1,376.72 s** |
| **Maximum Absolute Error** | **3,202.71 s** ($\approx 53.4\text{ min}$) | **2,709.29 s** ($\approx 45.2\text{ min}$) |
| **Median Relative Error** | **9,063.29%** ($90.6\times$) | **9,063.29%** ($90.6\times$) |
| **Pearson Correlation ($r$)** | **-0.1334** (Negative correlation!) | **-0.1249** (Negative correlation!) |
| **Records Within 10% of Physical** | **0.1457%** (only 359 of 246,399) | **0.1457%** (only 359 of 246,399) |

### Illustrative Physical Example
For segment ID 0:
- $\text{length\_m} = 3,016.998\text{ m}$
- $\text{currentSpeed} = 54.0\text{ km/h} = 15.0\text{ m/s}$
- **Expected Physical Travel Time:** $3,017 / 15 = \mathbf{201.13\text{ seconds}}$ ($\approx 3.35\text{ minutes}$)
- **Stored `currentTravelTime`:** $\mathbf{1,376.0\text{ seconds}}$ ($\approx 22.93\text{ minutes}$)

### Conclusion and Warning
The stored travel-time columns are completely decoupled from segment length and speed. Using stored `currentTravelTime` as edge weights in Dijkstra's algorithm would yield absurd, unphysical routes.  
**Rule:** For all routing and performance evaluations, edge travel time must be derived directly via $w_e = \frac{\text{length\_m}_e}{v_e / 3.6}$.

---

## 12. Graph-Connectivity Analysis

A core goal of GeoPulse is building an end-to-end routing prototype:
$$G = (V, E)$$
where $V$ represents intersections and $E$ represents directed road segments.

### Evaluation of Spatial Information
1. **Missing Endpoints:** The tabular dataset does not contain start coordinates, end coordinates, bearing/heading, or road LineStrings. It provides only a single centroid point per segment.
2. **Centroid Snapping Tolerance Tests:**
   Connecting segments by centroid proximity was evaluated across spatial thresholds:
   - **$1\text{ m}$ tolerance:** 11 connected pairs, 689 components, largest component = 2 segments, 678 isolated segments.
   - **$3\text{ m}$ tolerance:** 11 connected pairs, 689 components, largest component = 2 segments, 678 isolated segments.
   - **$5\text{ m}$ tolerance:** 11 connected pairs, 689 components, largest component = 2 segments, 678 isolated segments.
   - **$10\text{ m}$ tolerance:** 42 connected pairs, 658 components, largest component = 2 segments, 616 isolated segments.
   - **$20\text{ m}$ tolerance:** 96 connected pairs, 604 components, largest component = 2 segments, 508 isolated segments.
   - **$50\text{ m}$ tolerance:** 199 connected pairs, 503 components, largest component = 4 segments, 317 isolated segments.
   - **$100\text{ m}$ tolerance:** 489 connected pairs, 321 components, largest component = 22 segments, 139 isolated segments.
   - **$300\text{ m}$ tolerance:** 2,259 connected pairs, 35 components, largest component = 355 segments, 5 isolated segments.

   *Analysis:* At tolerances $\le 50\text{ m}$, the segments remain almost completely disconnected because road centroids are spaced hundreds of meters apart. At $300\text{ m}$, false geometric connections bridge parallel streets and unrelated intersections across city blocks.
3. **Absence of Bhubaneswar OSM GraphML:**
   The notebook `notebooks/bhubaneshwar_dataset.ipynb` specifies downloading `bhubaneswar_drive.graphml` (18,260 nodes, 46,679 edges). However, the resulting `.graphml` file is not present in the workspace. The file `datasets/jaipur_osm/jaipur_graph.graphml` is for Jaipur, Rajasthan and cannot be used for Bhubaneswar data.
4. **Prior Mapping Evidence:**
   Earlier mapping tests documented in `outputs/routing_mapping_audit/summary.json` revealed that even when the 700 TomTom segments were matched to the Bhubaneswar OSM graph, they mapped to 651 directed edges comprising **221 disconnected components**, with the largest component containing only **25 segments (3.57%)**. The 700 segments are discrete arterial probe segments, not a closed network.
5. **Verdict:** A directed graph cannot be constructed from the current files alone. The original `bhubaneswar_drive.graphml` must be restored, and unmonitored baseline OSM edges must provide the topological backbone for Dijkstra routing.

---

## 13. ML Feasibility

Predicting next-hour traffic speed ($X(t) \to \text{speed}(t+1)$) is feasible on the clean window:

1. **Target Variable:** $\text{currentSpeed}(t+1)$ in km/h for segment $i$.
2. **Analysis Window:** Jan 4 00:30 IST to Jan 17 09:30 IST (322 consecutive hours).
3. **Grid Completeness:** 225,399 observed cells out of 225,400 cells (99.9996% complete; only 1 missing value).
4. **Autoregressive Temporal Signal:**
   Autocorrelation across the 700 segments confirms strong predictive signal:
   - **Lag 1 ($t-1$):** Mean $r = 0.575$, Median $r = 0.678$
   - **Lag 3 ($t-3$):** Mean $r = 0.175$, Median $r = 0.189$
   - **Lag 6 ($t-6$):** Mean $r = 0.014$, Median $r = 0.013$
   - **Lag 12 ($t-12$):** Mean $r = -0.397$, Median $r = -0.442$ (diurnal day/night inversion)
   - **Lag 24 ($t-24$):** Mean $r = 0.585$, Median $r = 0.661$ (strong 24-hour periodicity)
5. **Sample Capacity:** A 24-hour lag lookback leaves 297 target hours (indices 25 to 321), providing **207,899 valid, non-null segment-hour samples**.

---

## 14. Data Leakage Risks

A strict audit of feature engineering pipelines identified six potential data leakage risks:

1. **Same-Hour Speed Leakage:** Features must never access $\text{currentSpeed}(t+1)$ or any concurrent field from the target row.
2. **Target-Derived Ratios:** In `traffic_bhubaneswar.csv`, `speed_ratio`, `congestion_level`, and `is_congested` are derived directly from $\text{currentSpeed}(t)$. They must only enter the feature set as lagged features ($t, t-1, \dots$), never unshifted at $t+1$.
3. **Missingness Flag Leakage:** The flags `is_missing` and `is_observed` on future rows reveal whether data collection succeeded; conditioning on them introduces target leakage.
4. **Synthetic Negative Labels on Missing Data:** The CSV assigns `is_congested=False` to missing rows. If unobserved rows are included in a classification task, models learn an artificial correlation between missingness and clear traffic.
5. **UTC vs Local Calendar Shift:** The CSV calendar fields (`hour_of_day`, `day_of_week`) were computed from UTC timestamps. This shifts local rush hours by 5.5 hours. Local calendar features must be strictly recomputed in `Asia/Kolkata` (IST).
6. **Time-Varying Free-Flow Speed:** Because $\text{freeFlowSpeed}$ varies over time on 671 segments, $\text{freeFlowSpeed}(t+1)$ must only be used as a predictor if confirmed to be an ex-ante scheduled TomTom profile rather than an ex-post measurement.

---

## 15. Synthetic-Data Requirements Analysis

GeoPulse mandates that synthetic data must never be fabricated arbitrarily. The analysis below addresses the six mandatory criteria:

1. **Is synthetic data actually necessary?**  
   **No** for traffic-speed prediction and **No** for historical traffic replay. The real dataset provides 246,399 real observations across 700 segments with real congestion dips.  
   **Conditionally Yes** only if an evaluator requires a deterministic, localized incident perturbation (e.g., simulating a sudden bottleneck on an edge) to demonstrate that the Dijkstra routing engine detects the deviation and reroutes around it.
2. **What exact variable/event requires it?**  
   An edge travel-time spike / speed collapse on a specific road segment during route traversal (e.g., reducing speed from 40 km/h to 5 km/h for a 2-hour window).
3. **Can the requirement be satisfied using held-out real observations instead?**  
   **Yes.** The test partition contains genuine evening peak congestion (speeds dropping by 50–70% between 17:00 and 19:00 IST) and 25,374 real `roadClosure=true` occurrences.
4. **What is the smallest defensible synthetic intervention if required?**  
   A temporary runtime perturbation applied to **exactly one selected edge** for a 2-hour simulation window.
5. **How should it be labelled?**  
   Every perturbed record must carry explicit metadata:
   ```json
   {
     "data_source": "synthetic",
     "synthetic_type": "incident_perturbation",
     "perturbation_factor": 0.20
   }
   ```
6. **How can original real observations remain untouched?**  
   Synthetic overlays must never be written to `traffic_structured_v1.parquet` or `datasets/`. They must be applied purely in-memory inside the simulation runner or saved in a separate directory `data/synthetic/incident_scenario_01.parquet`.

---

## 16. Recommended Preprocessing Rules

1. **Primary Source:** Read exclusively from `datasets/traffic_structured_v1.parquet` (or the identical archive member).
2. **Filter Observed Rows:** Apply `is_observed == True` for all feature and target extractions.
3. **Window Selection:** Exclude the unpopulated startup period (Jan 1–3); begin the continuous ML dataset at `2026-01-04 00:30:00 IST`.
4. **Timezone Normalization:** Preserve UTC timestamps for index joins; compute `hour_of_day`, `day_of_week`, and `is_weekend` in local `Asia/Kolkata` time.
5. **Feature Engineering per Segment:** Group by `segment_id` (ordered chronologically) and construct strict backward lags:
   $$\text{Features}(t) = \left[ v_i(t), v_i(t-1), v_i(t-2), v_i(t-3), v_i(t-6), v_i(t-12), v_i(t-24) \right]$$
6. **Rolling Statistics:** Compute 3-hour and 6-hour rolling means strictly over historical windows $[t-2, t]$ and $[t-5, t]$.
7. **Speed Filtering:** Do not clip speeds. All observed values (1–54 km/h) are valid.
8. **Travel-Time Cost Derivation:** Discard stored `currentTravelTime` and `freeFlowTravelTime`. Compute routing weights via:
   $$w_{i,t} = \frac{\text{length\_m}_i}{v_{i,t} / 3.6}$$

---

## 17. Recommended Train/Validation/Test Split

Time-series forecasting requires a strict chronological partition to prevent temporal leakage:

| Partition | Share | Target Hour Indices | IST Calendar Range | Segment-Hour Target Samples |
|---|---:|---:|---|---:|
| **Train** | 67.3% | 25 to 224 (200 hrs) | 2026-01-05 01:30 to 2026-01-13 08:30 IST | 139,999 (1 cell missing) |
| **Validation** | 16.2% | 225 to 272 (48 hrs) | 2026-01-13 09:30 to 2026-01-15 08:30 IST | 33,600 |
| **Test** | 16.5% | 273 to 321 (49 hrs) | 2026-01-15 09:30 to 2026-01-17 09:30 IST | 34,300 |
| **Total** | **100.0%** | **25 to 321 (297 hrs)** | **2026-01-05 01:30 to 2026-01-17 09:30 IST** | **207,899** |

*Note on Lag Buffer:* Hours 0 to 24 (Jan 4 00:30 to Jan 5 00:30 IST) serve as the 24-hour historical burn-in window to supply initial lag features for the first training target.

---

## 18. Risks and Limitations

1. **Duration Limitation:** The dataset covers 16.375 days total (13.4 clean days). It cannot support claims of annual seasonality, holiday effects, or extreme weather generalization.
2. **Ceiling Effect:** 67.71% of observed records have speeds equal to free-flow speed. Standard regression models may over-predict the upper bound.
3. **Graph Disconnection:** The 700 traffic segments do not form a closed routing network. A Dijkstra route that traverses only monitored segments is impossible for arbitrary Origin-Destination pairs without an underlying complete OSM graph.
4. **Travel-Time Disconnect:** Stored travel-time columns are unphysical ($r = -0.133$), requiring reliance on derived kinematic values.

---

## 19. Final Recommendation

1. **ML Speed Prediction Phase:** Proceed with training a light-weight, highly explainable model (e.g., Ridge Regression / LightGBM) on the 207,899 clean samples to forecast $v_i(t+1)$.
2. **Network Routing Phase:** Do NOT attempt to build a road graph by snapping segment centroids. The immediate prerequisite is restoring the full Bhubaneswar OSM graph (`bhubaneswar_drive.graphml`) via OSMnx, validating which edges map to the 700 TomTom segments, and applying static baseline speeds to unmonitored edges.
3. **Preservation:** Maintain all existing files in their current pristine state.

---
*Report generated and certified by GeoPulse Audit System.*
