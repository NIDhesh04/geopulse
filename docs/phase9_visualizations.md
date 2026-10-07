# Phase 9 Visualizations Index

**Project:** GeoPulse — AI-Based Dynamic Traffic Routing System  
**Component:** Phase 9 Dynamic Rerouting Replay & End-to-End Demonstration  
**Figure Directory:** [`results/phase9/figures/`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase9/figures)  
**Figure Resolution:** 300 DPI (Publication / Defense Quality)

---

## Overview of Figures

| Figure | Filename | Type | Purpose & Key Takeaway |
|---|---|---|---|
| **01** | [`01_dynamic_rerouting_map.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase9/figures/01_dynamic_rerouting_map.png) | Bhubaneswar Street Map | Renders the real curved OpenStreetMap road network geometry for the Main Demonstration Trip (OD #0, Evening Peak). Visually displays: Traversed path prior to update (blue), Abandoned congested corridor (red dotted), GeoPulse dynamic rerouted bypass (green), and Reroute decision point (orange marker). |
| **02** | [`02_rerouting_timeline.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase9/figures/02_rerouting_timeline.png) | Step Timeline | Traces the chronological journey progression across four distinct states: Initial Plan at t0 (21.45 min expected) $\to$ Traffic update at t1 $\to$ Degradation detected $\to$ Dynamic rerouting to R1 (recovering trip time to 20.04 min). |
| **03** | [`03_before_after_travel_time.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase9/figures/03_before_after_travel_time.png) | Bar Chart | Direct counterfactual comparison: Strategy A without rerouting (1,287.1 s / 21.45 min) vs. Strategy B with GeoPulse dynamic rerouting (1,202.2 s / 20.04 min), highlighting the net 84.9 s (1.42 min, 6.60%) time saving. |
| **04** | [`04_route_change_analysis.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase9/figures/04_route_change_analysis.png) | Bar Chart | Edge composition breakdown showing initial path links (74), rerouted path links (46), bypass segments utilized (1), and overall route Jaccard overlap (60.0%). |
| **05** | [`05_traffic_evolution.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase9/figures/05_traffic_evolution.png) | Bar Chart | Explains the physical cause of route degradation by charting speed evolution on the critical bottleneck link: Free-flow baseline (50.0 km/h) $\to$ Initial forecast (31.7 km/h) $\to$ Observed congestion drop (14.0 km/h). |
| **06** | [`06_rerouting_benefit_distribution.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase9/figures/06_rerouting_benefit_distribution.png) | Histogram + KDE | Distribution of travel time saved across benchmark scenarios where rerouting was triggered (Mean saving: 84.9 s / 1.42 min; Mean improvement: 5.88%). |
| **07** | [`07_reroute_frequency.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase9/figures/07_reroute_frequency.png) | Pie Chart | Quantifies rerouting decision discipline across the 20 benchmark journeys: Dynamic reroute triggered in 40.0% of trips; No reroute necessary in 60.0% of trips (preventing unnecessary path oscillation). |
| **08** | [`08_prediction_vs_observation.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase9/figures/08_prediction_vs_observation.png) | Scatter Plot | Contrasts initial predicted corridor speeds at t0 against actual observed speeds at t1 across monitored road segments, demonstrating where unexpected congestion surges occur. |
| **09** | [`09_cumulative_journey_comparison.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase9/figures/09_cumulative_journey_comparison.png) | Cumulative Trajectory Plot | Traces cumulative journey travel time step-by-step. Shows both strategies traveling together until Step 15 (decision point), after which Strategy A escalates steeply due to bottleneck delays while Strategy B remains on a flatter, faster slope. |
| **10** | [`10_dynamic_routing_summary.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase9/figures/10_dynamic_routing_summary.png) | Executive Infographic | Defense-ready summary graphic illustrating the full closed-loop architecture: Predict $\to$ Plan $\to$ Drive $\to$ Observe $\to$ Detect $\to$ Re-route, annotated with exact measured empirical gains. |

---

## Detailed Figure Descriptions

### Figure 1: Dynamic Rerouting Map
- **File:** [`results/phase9/figures/01_dynamic_rerouting_map.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase9/figures/01_dynamic_rerouting_map.png)
- **Description:** Features the actual geometry of Bhubaneswar's road network for OD #0 during the Evening Peak commute. The blue line depicts the shared initial trajectory up to the decision node (Step 15). At this point, the original planned corridor (red dotted line) experiences severe congestion. GeoPulse computes an alternative path (green line) that deflects onto an open bypass corridor, safely avoiding the bottleneck.

### Figure 2: Journey Timeline
- **File:** [`results/phase9/figures/02_rerouting_timeline.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase9/figures/02_rerouting_timeline.png)
- **Description:** Depicts the dynamic state progression of the journey over time. Highlights how real-time degradation detection identifies a pending delay increase to $21.45\text{ min}$ and how Dijkstra re-routing successfully restores trip duration to $20.04\text{ min}$.

### Figure 3: Before vs After Travel Time
- **File:** [`results/phase9/figures/03_before_after_travel_time.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase9/figures/03_before_after_travel_time.png)
- **Description:** Side-by-side comparison illustrating Strategy A ($1,287.1\text{ s}$) versus Strategy B ($1,202.2\text{ s}$), achieving an absolute saving of $84.9\text{ seconds}$ ($6.60\%$ improvement).

### Figure 4: Route Change Analysis
- **File:** [`results/phase9/figures/04_route_change_analysis.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase9/figures/04_route_change_analysis.png)
- **Description:** Quantifies the structural route transformation: the vehicle retains the initial 15 links, diverts onto a streamlined bypass link, and rejoins the final approach corridor, resulting in a 60.0% spatial overlap.

### Figure 5: Traffic Evolution on Critical Link
- **File:** [`results/phase9/figures/05_traffic_evolution.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase9/figures/05_traffic_evolution.png)
- **Description:** Shows how speed on the abandoned link dropped from an expected $31.7\text{ km/h}$ down to $14.0\text{ km/h}$ under observed congestion, triggering the rerouting threshold.

### Figure 6: Rerouting Benefit Distribution
- **File:** [`results/phase9/figures/06_rerouting_benefit_distribution.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase9/figures/06_rerouting_benefit_distribution.png)
- **Description:** Shows the distribution of time savings across the benchmark scenarios where rerouting was triggered, consistently delivering meaningful benefits of $84.9\text{ seconds}$ per affected journey.

### Figure 7: Reroute Frequency
- **File:** [`results/phase9/figures/07_reroute_frequency.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase9/figures/07_reroute_frequency.png)
- **Description:** Illustrates system stability: $60.0\%$ of trips do not trigger rerouting because existing paths remain optimal, avoiding erratic route switching.

### Figure 8: Prediction vs. Reality
- **File:** [`results/phase9/figures/08_prediction_vs_observation.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase9/figures/08_prediction_vs_observation.png)
- **Description:** Scatter plot highlighting the physical discrepancy between initial predictions and evolving traffic observations that necessitates real-time reactive rerouting.

### Figure 9: Cumulative Journey Trajectory Comparison
- **File:** [`results/phase9/figures/09_cumulative_journey_comparison.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase9/figures/09_cumulative_journey_comparison.png)
- **Description:** Plots cumulative trip minutes as a function of edge steps. After Step 15, the two curves visibly diverge as Strategy A encounters congestion delay while Strategy B maintains higher speeds along the bypass.

### Figure 10: Dynamic Routing Executive Summary Graphic
- **File:** [`results/phase9/figures/10_dynamic_routing_summary.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase9/figures/10_dynamic_routing_summary.png)
- **Description:** Presentation card summarizing the end-to-end GeoPulse closed loop, key numerical savings, and benchmark metrics for final evaluation.
