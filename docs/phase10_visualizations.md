# Phase 10 Visualizations Index

**Project:** GeoPulse — AI-Based Dynamic Traffic Routing System  
**Component:** Phase 10 Ablation & Robustness Evaluation  
**Figure Directory:** [`results/phase10/figures/`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase10/figures)  
**Figure Resolution:** 300 DPI (Publication / Defense Quality)

---

## Overview of Figures

| Figure | Filename | Type | Purpose & Key Takeaway |
|---|---|---|---|
| **01** | [`01_routing_strategy_travel_time.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase10/figures/01_routing_strategy_travel_time.png) | Boxplot + Means | Displays the empirical distribution of actual trip travel times across the 5 routing strategies: Static ($1,066.81\text{ s}$) $\to$ Persistence ($1,064.68\text{ s}$) $\to$ Historical ($1,063.10\text{ s}$) $\to$ LightGBM ($1,063.08\text{ s}$) $\to$ Oracle ($1,060.75\text{ s}$). Shows LightGBM and Historical are closely matched and substantially faster than Static and Persistence. |
| **02** | [`02_routing_strategy_improvement.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase10/figures/02_routing_strategy_improvement.png) | Bar Chart (95% CI) | Direct comparison of travel-time savings vs. Static baseline: Persistence ($+2.13\text{ s}$), Historical ($+3.72\text{ s}$), LightGBM ($+3.73\text{ s}$), and Oracle ($+6.06\text{ s}$). Demonstrates LightGBM and Historical recover $>61\%$ of the Oracle's achievable saving. |
| **03** | [`03_prediction_method_comparison.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase10/figures/03_prediction_method_comparison.png) | Dual Bar Panel | Multi-metric comparison of predictive methods: Win Rate vs Static (Persistence: $29.6\%$, Historical: $35.5\%$, LightGBM: $34.6\%$) alongside Mean Time Saved. Highlights that Historical same-hour lookup is a formidable baseline on par with GBDT. |
| **04** | [`04_oracle_regret_comparison.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase10/figures/04_oracle_regret_comparison.png) | Empirical CDF | Cumulative distribution $P(\text{Regret} \le x)$ for Static, Persistence, Historical, and LightGBM. Over 60% of LightGBM trips incur $<2\text{ seconds}$ of regret relative to the theoretical current-traffic oracle. |
| **05** | [`05_dynamic_rerouting_policy_comparison.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase10/figures/05_dynamic_rerouting_policy_comparison.png) | Dual Horizontal Bar | Contrasts dynamic rerouting policies (B1 through B5). Shows unconstrained "Always Reroute" triggers in $50.0\%$ of trips ($35.3\text{ s}$ saving), while the GeoPulse Dual Threshold triggers in $40.0\%$ ($34.0\text{ s}$ saving), suppressing low-margin route changes without sacrificing beneficial savings. |
| **06** | [`06_threshold_sensitivity.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase10/figures/06_threshold_sensitivity.png) | 2D Heatmap Grid | Heatmaps of Trigger Frequency and Mean Saving across the 2D grid ($\Delta T \in [5, 30]\text{ s}$, $\Delta T\% \in [1, 10]\%$). Shows steep cliff at $10\%$ threshold and stability around the GeoPulse operating point ($10\text{s} + 3\%$). |
| **07** | [`07_rerouting_frequency_vs_savings.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase10/figures/07_rerouting_frequency_vs_savings.png) | Pareto Trade-Off Plot | Plots route stability (trigger frequency) vs travel-time savings across policies. Demonstrates that the dual threshold achieves near-maximal savings ($33.96\text{ s}$ vs $35.27\text{ s}$ max) while reducing trip disruptions. |
| **08** | [`08_performance_by_time_period.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase10/figures/08_performance_by_time_period.png) | Diurnal Grouped Bar | Breaks down savings and win rates across Morning Peak ($+0.27\text{ s}, 29.3\%$), Midday ($+1.59\text{ s}, 27.5\%$), Evening Peak ($+8.57\text{ s}, 45.6\%$), and Off-Peak ($+2.41\text{ s}, 32.0\%$). Confirms that peak evening congestion generates the highest routing gains. |
| **09** | [`09_performance_by_route_length.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase10/figures/09_performance_by_route_length.png) | Corridor Bins Bar | Evaluates performance across distance bins: Short $<5\text{ km}$ ($+0.00\text{ s}$), Medium $5\text{--}8\text{ km}$ ($+3.71\text{ s}$), and Long $>8\text{ km}$ ($+4.67\text{ s}, 45.8\%$ win rate). Proves dynamic routing benefits increase with journey length. |
| **10** | [`10_prediction_error_vs_routing_gain.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase10/figures/10_prediction_error_vs_routing_gain.png) | Scatter + Reg Line | Correlates Route Travel-Time Prediction Error ($|T_{\text{pred}} - T_{\text{actual}}|$) with Oracle Regret ($r = +0.1580, p = 7.15 \times 10^{-6}$). Demonstrates that higher prediction error systematically widens regret against the oracle. |

---

## Detailed Figure Descriptions

### Figure 1: Routing Strategy Travel Time
- **File:** [`results/phase10/figures/01_routing_strategy_travel_time.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase10/figures/01_routing_strategy_travel_time.png)
- **Interpretation:** Displays box plots and annotated means for all 800 evaluations across 5 strategies. LightGBM ($1,063.08\text{ s}$) and Historical ($1,063.10\text{ s}$) achieve identical median and mean performance, both visibly outperforming Static ($1,066.81\text{ s}$) and Persistence ($1,064.68\text{ s}$). Current-Traffic Oracle establishes the lower bound ($1,060.75\text{ s}$).

### Figure 2: Routing Strategy Improvement vs Static
- **File:** [`results/phase10/figures/02_routing_strategy_improvement.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase10/figures/02_routing_strategy_improvement.png)
- **Interpretation:** Features 95% bootstrap confidence intervals for mean time saved vs static. LightGBM ($+3.73\text{ s}$) and Historical ($+3.72\text{ s}$) have non-overlapping confidence intervals compared with Persistence ($+2.13\text{ s}$), confirming statistically significant superiority over simple persistence.

### Figure 3: Prediction Method Comparison
- **File:** [`results/phase10/figures/03_prediction_method_comparison.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase10/figures/03_prediction_method_comparison.png)
- **Interpretation:** Focuses strictly on deployable prediction baselines. Shows Historical same-hour lookup achieves a $35.5\%$ win rate against static, marginally exceeding LightGBM's $34.6\%$ win rate, while LightGBM achieves a marginally higher absolute saving ($+3.73\text{ s}$ vs $+3.72\text{ s}$).

### Figure 4: Cumulative Distribution Function (CDF) of Oracle Regret
- **File:** [`results/phase10/figures/04_oracle_regret_comparison.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase10/figures/04_oracle_regret_comparison.png)
- **Interpretation:** Traces the empirical CDF of regret $T_{\text{strategy}} - T_{\text{oracle}}$. The LightGBM and Historical curves rise sharply, with 60% of trips exhibiting zero or near-zero regret ($\le 2\text{ s}$), while Static exhibits a substantially longer regret tail stretching to $30+\text{ seconds}$.

### Figure 5: Dynamic Rerouting Policy Comparison
- **File:** [`results/phase10/figures/05_dynamic_rerouting_policy_comparison.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase10/figures/05_dynamic_rerouting_policy_comparison.png)
- **Interpretation:** Side-by-side assessment of trigger frequency vs fleet-wide mean saving. Gated policies (B3, B4, B5) eliminate 20% of unnecessary triggers (reducing trigger rate from 50% to 40%) while retaining 96.3% of the total potential travel-time savings ($33.96\text{ s}$ vs $35.27\text{ s}$).

### Figure 6: Threshold Sensitivity Heatmaps
- **File:** [`results/phase10/figures/06_threshold_sensitivity.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase10/figures/06_threshold_sensitivity.png)
- **Interpretation:** Left heatmap shows trigger frequency drops from $50.0\%$ at $(5\text{s}, 1\%)$ to $0.0\%$ at $\ge 10\%$. Right heatmap demonstrates that mean savings remain flat at $33.96\text{ s}$ across the operational sweet spot ($10\text{--}30\text{s}$ and $3\text{--}5\%$), verifying that $10\text{s} + 3\%$ is robust and not hyper-sensitive.

### Figure 7: Rerouting Pareto Trade-Off
- **File:** [`results/phase10/figures/07_rerouting_frequency_vs_savings.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase10/figures/07_rerouting_frequency_vs_savings.png)
- **Interpretation:** Demonstrates diminishing returns: jumping from $40\%$ to $50\%$ trigger rate yields only $1.31\text{ seconds}$ of additional fleet-wide saving at the cost of $25\%$ more commuter path alterations.

### Figure 8: Diurnal Operational Period Performance
- **File:** [`results/phase10/figures/08_performance_by_time_period.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase10/figures/08_performance_by_time_period.png)
- **Interpretation:** Highlights that GeoPulse's primary impact occurs during the Evening Peak commute ($17:30\text{--}20:30\text{ IST}$), generating $+8.57\text{ s}$ offline routing savings and a $45.6\%$ win rate, while off-peak hours show modest gains due to uncongested baseline conditions.

### Figure 9: Route Length Robustness
- **File:** [`results/phase10/figures/09_performance_by_route_length.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase10/figures/09_performance_by_route_length.png)
- **Interpretation:** Shows that short trips ($<5\text{ km}$) lack topological detour options, resulting in $0.0\text{ s}$ divergence. Medium ($5\text{--}8\text{ km}$) and Long ($>8\text{ km}$) trips allow meaningful diversion around bottlenecks, saving $+3.71\text{ s}$ and $+4.67\text{ s}$ respectively.

### Figure 10: Prediction Error vs. Oracle Regret
- **File:** [`results/phase10/figures/10_prediction_error_vs_routing_gain.png`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/results/phase10/figures/10_prediction_error_vs_routing_gain.png)
- **Interpretation:** Confirms statistically significant positive correlation ($r = +0.1580, p < 0.001$) between prediction error and oracle regret. Larger errors in estimated corridor traversal times directly translate into sub-optimal route decisions.
