# Phase 8 Visualizations Index

**Project:** GeoPulse — AI-Based Dynamic Traffic Routing System  
**Component:** Custom Dynamic Routing Engine & Multi-Scenario Evaluation  
**Figure Directory:** [`results/phase8/figures/`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase8/figures)  
**Figure Resolution:** 300 DPI (Publication / Defense Quality)

---

## Overview of Figures

| Figure | Filename | Type | Purpose & Key Takeaway |
|---|---|---|---|
| **01** | [`01_example_route_comparison.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase8/figures/01_example_route_comparison.png) | Bhubaneswar Street Map | Renders the actual OpenStreetMap road geometries comparing Static baseline (gray), ML-predicted dynamic (blue), and Current-optimal oracle (green) paths across Bhubaneswar for OD #14 during the Friday Evening Peak. Demonstrates real dynamic corridor deflection around arterial bottlenecks. |
| **02** | [`02_route_travel_time_comparison.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase8/figures/02_route_travel_time_comparison.png) | Bar Chart | Directly compares mean actual traversal times across the 800 evaluations: Static (1,066.8 s / 17.8 min) vs. ML-Predicted (1,063.1 s / 17.7 min) vs. Current-Optimal Oracle (1,060.8 s / 17.7 min). |
| **03** | [`03_improvement_over_static.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase8/figures/03_improvement_over_static.png) | Histogram + KDE | Shows the distribution of percentage travel-time improvements achieved by ML dynamic routing relative to static baseline across all 800 evaluations, with peak improvements exceeding 4–8%. |
| **04** | [`04_predicted_vs_actual_route_time.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase8/figures/04_predicted_vs_actual_route_time.png) | Scatter Plot | Plots ML-predicted trip duration against ground-truth actual trip duration under observed traffic. Points tightly cluster along the ideal $y=x$ reference line ($R^2 = 0.9984$), verifying route-level kinematic consistency. |
| **05** | [`05_route_regret_distribution.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase8/figures/05_route_regret_distribution.png) | Histogram | Depicts oracle regret ($T_{\text{ML}} - T_{\text{oracle}}$). The distribution is heavily zero-skewed (median regret: 0.0 s, mean regret: 2.3 s), proving the ML route matches the theoretical oracle benchmark in the vast majority of scenarios. |
| **06** | [`06_route_distance_comparison.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase8/figures/06_route_distance_comparison.png) | Bar Chart | Compares physical network distance across routing modes: Static (9.28 km) vs. ML (9.28 km) vs. Current-Optimal (9.28 km), showing that travel-time savings are achieved through intelligent speed-corridor routing without excessive path detours. |
| **07** | [`07_dynamic_route_coverage.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase8/figures/07_dynamic_route_coverage.png) | Histogram + KDE | Shows the percentage of route edges monitored by dynamic traffic sensors (Mean: 35.3%, spanning up to 75% on major arterial cross-city trips). |
| **08** | [`08_improvement_by_period.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase8/figures/08_improvement_by_period.png) | Grouped Bar Chart | Contrasts travel-time improvements across traffic periods: Evening Peak (0.69% mean, 45.6% win rate), Morning Peak (0.05%), Midday (0.16%), and Off-Peak (0.25%). |
| **09** | [`09_route_change_statistics.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase8/figures/09_route_change_statistics.png) | Donut / Pie Chart | Quantifies the frequency of dynamic rerouting: ML selects an alternate dynamic corridor in 28.6% of evaluations while retaining the static path when free-flow prevails (71.4%). |
| **10** | [`10_edge_weight_comparison.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase8/figures/10_edge_weight_comparison.png) | KDE Density Plot | Compares the probability distributions of edge travel times across Static, Observed, and ML-Predicted states across all 46,679 road links in Bhubaneswar. |
| **11** | [`11_route_congestion_profile.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase8/figures/11_route_congestion_profile.png) | Step / Line Profile | Traces link-by-link speed along the selected route for OD #14, contrasting static assumed speeds against actual observed and ML-predicted speeds. |
| **12** | [`12_routing_summary.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase8/figures/12_routing_summary.png) | Executive Infographic | Defense-ready summary card presenting the core project conclusions: Static $\to$ ML Predicted $\to$ Current Optimal travel times, win rates, and regret bounds. |

---

## Detailed Figure Descriptions

### Figure 1: Example Route Comparison Map
- **File:** [`results/phase8/figures/01_example_route_comparison.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase8/figures/01_example_route_comparison.png)
- **Description:** Uses the exact WKT curved road geometry from OpenStreetMap to plot trip OD #14 during the Friday Evening Peak. The static baseline blindly navigates congested inner corridors, whereas both ML-predicted and Current-optimal routes intelligently deflect along higher-speed bypass corridors to avoid gridlock.

### Figure 2: Route Travel Time Comparison
- **File:** [`results/phase8/figures/02_route_travel_time_comparison.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase8/figures/02_route_travel_time_comparison.png)
- **Description:** Establishes the core empirical hierarchy: Static baseline ($1,066.8\text{ s}$) requires more time than ML-Predicted dynamic routing ($1,063.1\text{ s}$), which closely approaches the theoretical current-optimal oracle benchmark ($1,060.8\text{ s}$).

### Figure 3: Improvement Over Static Routing
- **File:** [`results/phase8/figures/03_improvement_over_static.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase8/figures/03_improvement_over_static.png)
- **Description:** Frequency distribution of percentage time savings. Trips through congested arterial corridors achieve substantial travel-time reductions.

### Figure 4: ML Predicted vs. Actual Route Time
- **File:** [`results/phase8/figures/04_predicted_vs_actual_route_time.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase8/figures/04_predicted_vs_actual_route_time.png)
- **Description:** Verifies that route-level travel time predictions computed from individual edge kinematics match actual vehicle travel times with an $R^2$ of $0.9984$.

### Figure 5: Oracle Regret Distribution
- **File:** [`results/phase8/figures/05_route_regret_distribution.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase8/figures/05_route_regret_distribution.png)
- **Description:** Shows that in over $93.25\%$ of evaluations, the ML route comes within $5.0\text{ seconds}$ of the theoretical oracle optimum, with median regret equal to $0.0\text{ seconds}$.

### Figure 6: Route Distance Comparison
- **File:** [`results/phase8/figures/06_route_distance_comparison.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase8/figures/06_route_distance_comparison.png)
- **Description:** Confirms that dynamic time savings do not introduce circuitous detour mileage, maintaining mean physical route distance at $9.28\text{ km}$.

### Figure 7: Dynamic Route Coverage
- **File:** [`results/phase8/figures/07_dynamic_route_coverage.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase8/figures/07_dynamic_route_coverage.png)
- **Description:** Evaluates the degree to which routes utilize monitored arterial roads ($35.3\%$ average coverage), confirming that the 2-tier static fallback architecture seamlessly bridges monitored arterials and local streets.

### Figure 8: Improvement by Traffic Period
- **File:** [`results/phase8/figures/08_improvement_by_period.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase8/figures/08_improvement_by_period.png)
- **Description:** Shows that dynamic routing advantages are highest during the Evening Peak ($45.6\%$ win rate), when commuter congestion creates the greatest travel-time disparities.

### Figure 9: Route Change Statistics
- **File:** [`results/phase8/figures/09_route_change_statistics.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase8/figures/09_route_change_statistics.png)
- **Description:** Demonstrates selective rerouting: GeoPulse only alters the route when traffic conditions justify deflection ($28.6\%$ of evaluations), preserving the baseline path otherwise.

### Figure 10: Edge Weight Distribution Comparison
- **File:** [`results/phase8/figures/10_edge_weight_comparison.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase8/figures/10_edge_weight_comparison.png)
- **Description:** Density curves illustrating how dynamic edge weights shift towards higher traversal times during congestion relative to the rigid static baseline.

### Figure 11: Route Congestion Profile
- **File:** [`results/phase8/figures/11_route_congestion_profile.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase8/figures/11_route_congestion_profile.png)
- **Description:** Detailed step-by-step corridor speed diagnostics along OD #14, demonstrating the accuracy of ML speed forecasting across individual road segments.

### Figure 12: Routing Executive Summary Graphic
- **File:** [`results/phase8/figures/12_routing_summary.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase8/figures/12_routing_summary.png)
- **Description:** High-impact executive briefing card summarizing sample size, network scale, scenario travel times, win rates, and oracle convergence bounds.
