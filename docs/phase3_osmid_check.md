# Phase 3: Traffic Segment OSM ID Existence Verification Report

**Project:** GeoPulse — AI-Based Dynamic Traffic Routing System  
**Phase:** 3 — Traffic Segment OSM ID Existence Check  
**Status:** `PHASE 3 COMPLETE`  
**Execution Timestamp:** 2026-10-07 15:05:00 IST (UTC+05:30)  
**Input Datasets:**
- Traffic Table: [`datasets/traffic_structured_v1.parquet`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/datasets/traffic_structured_v1.parquet) (observed rows)
- OSM Graph: [`data/raw/osm/bhubaneswar_drive.graphml`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/data/raw/osm/bhubaneswar_drive.graphml)

---

## 1. Summary Metrics

| Metric | Count | Percentage |
|---|---:|---:|
| **Total Traffic Segments** | **700** | 100.0% |
| **Segments with Usable OSM IDs** | **700** | 100.0% |
| **Unique OSM IDs in Traffic Dataset** | **344** | — |
| **Unique OSM IDs in Downloaded OSM Graph** | **11,337** | — |
| **Traffic OSM IDs Found in Graph** | **344** | **100.0%** |
| **Traffic OSM IDs NOT Found in Graph** | **0** | **0.0%** |
| **Segments with ALL IDs Found** | **700** | **100.0%** |
| **Segments with SOME IDs Found** | **0** | 0.0% |
| **Segments with NO IDs Found** | **0** | 0.0% |
| **Single-ID Segments** | **613** | 87.57% |
| **Multi-ID Segments** | **87** | 12.43% |

---

## 2. Key Findings & Structural Observations

1. **Perfect ID Existence:** Every single OpenStreetMap identifier associated with the 700 TomTom traffic segments exists within the downloaded Bhubaneswar drive network graph. There are zero unmapped or orphaned OSM identifiers.
2. **Multi-Way Composite Segments:** Exactly 87 traffic segments (12.43%) contain a list of multiple OSM IDs (ranging from 2 to 6 OSM ways per segment). This occurs because TomTom traffic aggregation slices can span multiple shorter contiguous OSM ways along an arterial corridor.
3. **Shared OSM Identifiers Across Segments:** The 700 traffic segments map to 344 distinct OSM way IDs. This 2:1 ratio is standard for urban arterial monitoring: opposite travel directions of dual-carriageway corridors or segmented sensor probe windows reference the same underlying physical OSM way.
4. **Data Artifact Produced:** The segment-level lookup table has been saved to [`data/processed/osmid_existence_check.csv`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/data/processed/osmid_existence_check.csv) containing all 700 segment mappings.

---

## 3. Scope Safeguards Maintained

- No edge mapping or directional resolution performed.
- No distance or centroid approximations calculated.
- GraphML and raw traffic datasets preserved without modification.
