# Phase 11 Visualizations Index

**Project:** GeoPulse — AI-Based Dynamic Traffic Routing System  
**Component:** Phase 11 Final Integrated Prototype & Architecture Simulation  
**Figure Directory:** [`results/phase11/figures/`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase11/figures)  
**Figure Resolution:** 300 DPI (Publication / Defense Quality)

---

## Overview of Figures

| Figure | Filename | Type | Purpose & Key Takeaway |
|---|---|---|---|
| **01** | [`01_end_to_end_route.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase11/figures/01_end_to_end_route.png) | Bhubaneswar Street Map | Renders the complete journey on physical OpenStreetMap road geometry for the Canonical Demo Trip (OD #0, Evening Peak). Depicts: Traversed prefix before update (blue), Abandoned congested corridor (red dashed), GeoPulse dynamic bypass (green), and Reroute decision point (orange star). |
| **02** | [`02_end_to_end_timeline.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase11/figures/02_end_to_end_timeline.png) | Lifecycle Milestone Timeline | Traces the chronological journey progression across 5 milestones: Planning at t0 (19:30 IST) $\to$ En route traversal $\to$ Telemetry arrival at t1 (20:30 IST) $\to$ Degradation detection ($\Delta T = 84.9\text{s}$) $\to$ Dynamic rerouting and arrival ($20.04\text{ min}$ vs $21.45\text{ min}$). |
| **03** | [`03_edge_cloud_architecture.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase11/figures/03_edge_cloud_architecture.png) | Architectural Block Diagram | Publication-grade diagram illustrating the logical separation between Cloud, Edge Server, and Vehicle tiers. Details message protocols (MODEL_UPDATE, TRAFFIC_UPDATE, POSITION_UPDATE, ROUTE_UPDATE) and prototype software execution times. |

---

## Detailed Figure Descriptions

### Figure 1: End-to-End Dynamic Rerouting Map
- **File:** [`results/phase11/figures/01_end_to_end_route.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase11/figures/01_end_to_end_route.png)
- **Description:** Features the actual geometry of Bhubaneswar's road network for OD #0 during the Evening Peak commute. Highlights how the vehicle departs Node `3722327026`, traverses the initial prefix (blue), encounters downstream bottleneck conditions at Node `3320289784`, abandons the congested path (red dashed), and safely deflects onto a faster parallel bypass (green), saving $84.9\text{ seconds}$ ($6.60\%$).

### Figure 2: End-to-End Timeline
- **File:** [`results/phase11/figures/02_end_to_end_timeline.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase11/figures/02_end_to_end_timeline.png)
- **Description:** Visualizes the chronological lifecycle of the trip, illustrating how predictive planning provides an initial baseline ($1,310.3\text{ s}$ expected) and how real-time reactive detour logic restores trip duration to $1,202.2\text{ s}$ when downstream conditions collapse.

### Figure 3: Simulated Edge-Cloud Architecture
- **File:** [`results/phase11/figures/03_edge_cloud_architecture.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase11/figures/03_edge_cloud_architecture.png)
- **Description:** Illustrates the architectural relationship between the centralized Cloud Model Service, the regional Edge Server, and the connected Vehicle simulator. Annotates each operational interface with prototype software execution times ($1.03\text{ ms}$ prediction packaging, $12.65\text{ ms}$ weight update, $20.33\text{ ms}$ Dijkstra recomputation).
