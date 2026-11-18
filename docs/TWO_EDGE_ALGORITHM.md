# GeoPulse: Sequential Two-Edge Selection Algorithm
## Localized Sequential Routing Under Machine Learning Traffic Predictions

**Document:** `docs/TWO_EDGE_ALGORITHM.md`  
**System:** GeoPulse Major Project  
**Author:** GeoPulse Architecture & Core Engineering  
**Version:** 1.0  
**Status:** Approved & Implemented  

---

## 1. Introduction & Motivation

In traditional transportation routing algorithms (such as global Dijkstra or A*), a global shortest-path tree is solved end-to-end across the entire road network prior to departure. While mathematically optimal for static networks, this paradigm exhibits fundamental limitations in real-world urban deployments:
1. **Global Sensitivity to Local Distortions:** A minor traffic fluctuation or temporary signal phase on a distant link can invalidate the entire precomputed trajectory.
2. **Computational Inflexibility on Edge Devices:** Re-solving global shortest paths across networks with tens of thousands of links (e.g. 46,679 edges in Bhubaneswar) introduces significant computational and memory footprints for resource-constrained in-vehicle telematics units.
3. **Professor-Directed Research Focus:** To investigate whether a **sequential decision-making agent** evaluating localized binary choices (comparing exactly two candidate outgoing edges at every intersection) can achieve near-optimal travel times while maintaining sub-millisecond decision latency and dynamic agility.

GeoPulse integrates machine learning speed forecasts with a **Sequential Two-Edge Decision Engine**, enabling a vehicle to evaluate candidate branches at every intersection, select the preferred branch, advance forward, and repeat until the destination is reached.

---

## 2. Mathematical Formulation & Architecture

At any current intersection node $u \in V(G)$ with destination $D \in V(G)$ and active edge weights $w_e$:

```
                       Current Node u
                             │
            ┌────────────────┴────────────────┐
            │ Candidate Edge Generator        │
            │ (Reversal pruning, out-degree)  │
            └────────────────┬────────────────┘
                             │
                    Eligible Candidates
                             │
            ┌────────────────┴────────────────┐
            │ Candidate Selection Strategy    │
            │ (Reduces m > 2 to exactly 2)    │
            └───────┬─────────────────┬───────┘
                    │                 │
              Candidate A       Candidate B
             (u -> v_A, k_A)   (u -> v_B, k_B)
                    │                 │
            ┌───────┴─────────────────┴───────┐
            │ Two-Edge Decision Strategy      │
            │ Score(e_A) vs. Score(e_B)       │
            └────────────────┬────────────────┘
                             │
                      Winning Edge e*
                             │
                             ▼
                    Vehicle Advances to
                    Next Node v*
```

### 2.1 Out-Degree Cases at Intersections
Road networks exhibit varying out-degrees at different junctions:
1. **Dead End ($\text{out-degree} = 0$):**
   - The candidate generator returns an empty candidate set ($m=0$) and flags `is_dead_end=True`.
   - The `RouteController` catches this condition and invokes **Backtrack Recovery**, reversing to the previous intersection, blacklisting the dead-end edge, and routing along the alternate branch.
2. **Forced Continuation ($\text{out-degree} = 1$):**
   - When only one valid outgoing edge exists (e.g. mid-corridor waypoints or one-way continuations), the generator returns this single candidate with `is_forced=True`.
   - The decision strategy immediately selects this edge without fabricating a synthetic alternative.
3. **Natural Pair ($\text{out-degree} = 2$):**
   - Both outgoing edges form Candidate A and Candidate B directly.
4. **Branching Junction ($\text{out-degree} > 2$):**
   - Intersections with 3, 4, or 5 outgoing roads are filtered to remove immediate reversal back to the entering road ($v \ne p$), and then ranked to select exactly two candidates $\{e_A, e_B\}$ according to a candidate-generation policy.

---

## 3. Candidate Generation Strategies

When more than two eligible outgoing edges exist at an intersection, GeoPulse supports four candidate selection policies:

### 1. Random Candidate Selection (`random`)
- Uniformly samples two distinct edges from the eligible outgoing set:
  $$\{e_A, e_B\} \sim \text{Uniform}(\text{Eligible}(u), 2)$$
- Serves as the stochastic baseline to quantify the value of intelligent candidate filtering.

### 2. Lowest Immediate Cost (`lowest_immediate_cost`)
- Ranks eligible edges by immediate kinematic traversal travel time:
  $$w_e = \frac{L_e}{v_e / 3.6}$$
- Selects the two edges with the lowest traversal times.

### 3. Destination-Aware Candidate Selection (`destination_aware`)
- Ranks eligible edges by the sum of immediate travel time and optimistic straight-line remaining travel time to destination $D$:
  $$\tilde{f}(e) = w_e + h(v, D)$$
  where $h(v, D) = \frac{d_{\text{haversine}}(v, D)}{v_{\text{freeflow}}}$ is an admissible optimistic heuristic.
- Picks the two branches that best direct the vehicle toward the destination.

### 4. Lookahead-Based Candidate Selection (`lookahead`)
- Uses limited forward tree search to evaluate the best subpath continuation up to depth $k$ for each branch:
  $$\text{Cost}_{\text{lookahead}}(e) = w_e + \min_{P \in \text{Paths}(v, \text{depth}=k-1)} \left( \sum_{e' \in P} w_{e'} + h(\text{end}(P), D) \right)$$
- Selects the two branches with lowest cumulative lookahead costs.

---

## 4. Two-Edge Decision Strategies

Once Candidate A and Candidate B are identified, the **Two-Edge Selector** executes a comparative evaluation using a polymorphic strategy inheriting from `BaseDecisionStrategy`:

### Strategy 1: Greedy Selection (`GreedyDecisionStrategy`)
- Evaluates candidates solely on immediate edge traversal cost:
  $$\text{Score}(e) = w_e + \text{Penalty}_{\text{visited}}(v)$$
- Selects the candidate with the lower score.
- **Advantage:** Lowest possible computational complexity ($O(1)$).
- **Limitation:** Blind to destination direction and downstream bottlenecks; requires loop detection to avoid cyclic traps.

### Strategy 2: Destination-Aware Selection (`DestinationAwareDecisionStrategy`)
- Combines immediate edge cost with admissible destination heuristic:
  $$\text{Score}(e) = w_e + \alpha \cdot h(v, D) + \text{Penalty}_{\text{visited}}(v)$$
  where $\alpha \ge 1.0$ controls destination attraction (default $\alpha = 1.0$).
- **Advantage:** Prevents wandering away from destination while accounting for local edge speeds.

### Strategy 3: Limited Lookahead Selection (`LimitedLookaheadDecisionStrategy`)
- Explores forward consequences up to depth $k \in \{1, 2, 3, 5\}$ from the candidate endpoint nodes.
- Evaluates:
  $$\text{Score}(e) = w_e + \text{ContinuationCost}(v, \text{depth}=k-1) + \text{Penalty}_{\text{visited}}(v)$$
- Branch expansion is bounded by `max_expansions_per_node = 4` to prevent exponential expansion in dense urban grids.
- **Advantage:** Detects downstream bottlenecks that appear fast on the immediate edge but lead into gridlock.

### Strategy 4: Adaptive Selection (`AdaptiveDecisionStrategy`)
- Dynamically switches between Destination-Aware and Lookahead based on real-time traffic conditions:
  $$\text{Strategy} = \begin{cases} \text{Lookahead}(k=2), & \text{if } \min(v_{eA}, v_{eB}) < v_{\text{threshold}} \text{ (Congestion)} \\ \text{Destination-Aware}, & \text{otherwise (Free-Flow)} \end{cases}$$
- **Advantage:** Conserves computational resources in free-flowing traffic while applying lookahead scrutiny in congested bottlenecks.

---

## 5. Machine Learning Model Integration

The candidate edge travel times $w_e$ are computed using predicted traffic speeds from the Phase 7 trained **LightGBM Regressor** (`models/speed_predictor.joblib`):
1. **Feature Inputs ($n = 25$):**
   - Calendar & temporal features: `hour`, `day_of_week`, `is_weekend`, trigonometric hour/day encodings.
   - Speed lags: 1h, 2h, 3h, 6h, 12h, 24h historical speeds on mapped corridors.
   - Rolling statistics: 3h, 6h, 24h rolling means and standard deviations.
   - Road attributes: road type, segment length, free-flow speed, confidence code.
2. **Speed Conversion & Clamping:**
   $$\hat{v}_e = \text{clip}(\text{LightGBM}(X_e), 3.0, 120.0)\text{ km/h}$$
   $$w_e = \frac{L_e}{\hat{v}_e / 3.6}$$
3. **Static Fallback:**
   For unmonitored road segments (Tier 2 in [`docs/routing_weight_policy.md`](file:///c:/Users/Mohit%20sharma/Desktop/7th%20sem/new%20major%20project/geopulse/docs/routing_weight_policy.md)), speeds default to the OSM road hierarchy baseline ($15\text{--}50\text{ km/h}$).

---

## 6. Route Safety, Cycle Prevention & Failure Handling

Local decision policies on directed graphs can experience failure modes if unconstrained:
- **Immediate Reversal Pruning:** Prevents the vehicle from oscillating back and forth across two-way streets ($u \to v \to u$) by filtering $v == p$ from candidate generation.
- **Visited Node Loop Penalty:** Nodes already visited during the journey receive a severe score penalty ($+1000.0\text{ s}$), steering the selector toward unvisited corridors.
- **Cycle Breaker Recovery:** If a node is visited more than `max_node_visits` times (default 2), `RouteController` detects a cycle deadlock and invokes `custom_dijkstra` recovery from the current node to destination.
- **Dead-End Backtracking:** If a vehicle enters a cul-de-sac with 0 exits, the engine backtracks along the path to the previous node, blocks the dead-end edge, and resumes alternative pathing.
- **Maximum Hop Safeguard:** If hop count exceeds $3 \times \text{hops}(R_0)$, the engine terminates the search or invokes global Dijkstra recovery.
