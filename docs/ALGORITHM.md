# Routing algorithm — approved Topics 3 and 5

**Fact:** Consolidated from user approvals on 2026-11-22. This specifies routing behavior with the movement-aware update approved in Topic 5. See SIMULATION.md for world dynamics and SIGNALS.md for signal service. No application code is implemented by this document.

## Purpose and boundaries

- **Decision:** Use the professor's hybrid routing loop: nearby live estimates, distant current-clock predictions, a shortest-path search, and re-planning at each junction.
- **Decision:** Keep the routing loop behind an interface so policies can be extended later. Road travel-time providers accept `(edge, time)`; junction delay is estimated separately for the outgoing movement.
- **Decision:** Design for per-ambulance routes and live sets. The first end-to-end milestone uses one ambulance; the complete project targets multiple ambulances. Shared-signal arbitration is specified in SIGNALS.md.
- **Decision:** Backtracking is deferred. Do not introduce a two-node retreat cap, U-turn rules, or a BACKTRACKING state.

## Graph and information access

- **Decision:** Junctions are nodes; directed road segments are edges. Compute live neighborhoods using directed connectivity before congestion-based blocking.
- **Decision:** `LIVE_HORIZON` is configurable: 0 means predictions everywhere, 2 is the default, and `all` exposes live estimates for every edge reachable from the current junction. A finite horizon h exposes an edge if its source can be reached in at most h-1 directed hops.
- **Decision:** Include every branch in that neighborhood, not just the previously selected route. Compute the set independently for each ambulance and recalculate it when that ambulance reaches a junction.
- **Decision:** This is a routing information-access policy. Hidden simulator state must not leak into route selection. A simulator-wide ground-truth visualization must be distinguished from router-visible information.
- **Decision:** Local observations can reveal blockages. Explicitly reported closures are available to all routing modes regardless of horizon; unreported distant blockages remain unknown until observed.
- **Fact:** The `all` mode is an upper bound on live-information coverage, not a guarantee of minimum actual journey time or knowledge of future conditions.

## Cost snapshot and providers

- **Decision:** Estimated segment cost, in seconds, equals estimated road traversal time plus estimated junction waiting time.
- **Decision:** Attribute waiting to the outgoing movement at the segment's starting junction. Destination arrival incurs no additional departure wait.
- **Decision:** Retain `(edge, time)` for road traversal. Use a separate junction-delay estimator under the currently established signal policy; do not assume automatic preemption for every candidate path.
- **Decision:** Topic 5 replaces the outgoing-edge-only assumption. Search states are `(junction, incoming_edge)` and junction-delay estimates accept `(incoming_edge, outgoing_edge, time)`, with frozen snapshot/ambulance queue context. A transition costs the outgoing road estimate plus this movement-specific wait and leads to `(outgoing_edge.destination, outgoing_edge)`.
- **Decision:** Activation uses an explicit hospital/station departure entry as incoming context, including initial queue waiting. Any state at the destination junction is a goal without further departure service.
- **Decision:** Expanded search states do not change base-road-graph hop distances or displayed route edge sequences.
- **Decision:** Junction waits use isolated deterministic forecasts of at most 300 seconds under known established policy, respecting the same live/history boundary as road estimates. Candidate probes do not request priority. Horizon-exceeded is unknown/excluded with a disclosed reason, not a known physical closure. Cache identical complete forecast inputs within each frozen routing snapshot only.
- **Decision:** At a routing decision at time t, select live or predicted road providers according to the live set, evaluate all estimates against the same current clock t and consistent signal state, and freeze costs for the whole search.
- **Decision:** Baseline predictions describe conditions at t, not estimated arrival times at downstream edges. Run ordinary Dijkstra on this frozen snapshot; costs change between searches, not within a search.
- **Decision:** Finite usable costs must be nonnegative. Negative, missing, or NaN estimates are data-quality failures, never zero-cost shortcuts.
- **Decision:** If a live estimate is unavailable or invalid, use a valid current-clock predicted estimate and identify the fallback in explanations. A live report of a known blockage is not missing data and must not be replaced with a finite predicted value.
- **Decision:** If no valid road estimate exists, exclude the edge from this search as unknown and surface a data-quality warning. Invalid junction-delay estimates similarly make the movement unknown; never substitute zero waiting.
- **Decision:** Confirmed closures override estimates with infinite cost until explicitly reopened. Distinguish known blocked edges from edges excluded because their cost is unknown.
- **Decision:** A red signal is waiting, not a road blockage.

## Routing and movement loop

1. **Decision:** On activation, start the journey clock. If already at the destination, record immediate arrival without a search.
2. **Decision:** At the current junction, construct the information set and frozen cost snapshot, then search for a feasible path to the destination.
3. **Decision:** Use stable junction and edge ordering for equal costs, retaining the first equal-cost predecessor. This must yield deterministic choices for repeated identical inputs.
4. **Decision:** If a path exists, select its first edge, wait for a feasible departure, and enter that edge. Signal waiting itself does not invalidate the selected route.
5. **Decision:** If the planned departure becomes unavailable while waiting at the junction, allow immediate re-planning before entering the road.
6. **Decision:** Once on an edge, commit to completing that segment. Progress follows simulated ground-truth conditions, separately from the estimates used to choose the route. Do not change direction mid-segment.
7. **Decision:** If the current edge becomes impassable, stop in place and raise an operator alert. Resume only when passage becomes possible; do not teleport or introduce backtracking.
8. **Decision:** Information about other roads may update while moving, but the next routing decision occurs at the next junction. On arrival, complete the journey if at the destination; otherwise refresh and repeat.

## No-route behavior and recovery

- **Decision:** If all outgoing edges are known blocked, stop at the junction and raise an operator alert.
- **Decision:** If some outgoing edges remain open but no complete feasible path exists, stop and alert that the destination is unreachable under current information. Do not move aimlessly.
- **Decision:** Preserve unknown-data reasons when excluded edges prevent route discovery; do not misreport all exclusions as physical blockages.
- **Decision:** Retry a stopped route search on a relevant information update or operator retry. Clear the active no-route alert when a feasible route becomes available. Exact event subscriptions belong to later architecture design.

## Metrics

- **Decision:** Displayed ETA is based on estimated remaining route costs and is explicitly an estimate. Update it after route calculations and preserve the initial activation-time estimate for evaluation when one exists.
- **Decision:** Actual journey time runs from activation at the starting junction to arrival, including initial waiting, later signal waits, and stops. It is measured from the simulation clock, not by summing route estimates.
- **Decision:** Re-plan count is the number of searches after the initial search, including failed searches.
- **Decision:** Reroute count increments only when a new feasible edge sequence differs from the untraversed remainder of the previously selected route. Normal removal of already traversed edges does not count. A failed search alone does not increment this count; the first feasible route is an initial selection, not a change of route.

## Required verification scenarios

- **Decision:** Verify horizon 0, horizon 2 across competing branches, and all-live mode; prove neighborhood discovery is independent of blockages and isolated per ambulance.
- **Decision:** Verify every provider call within a search uses the same t, live fallback is disclosed, confirmed closure dominates estimates, and unknown data never creates a zero-cost path.
- **Decision:** Verify deterministic equal-cost choices, immediate arrival, all-outgoing-blocked stopping, and unreachable destinations despite open local edges.
- **Decision:** Verify red-light waiting does not masquerade as blockage, infeasible departures trigger re-planning, and mid-edge impassability stops without reverse movement.
- **Decision:** Verify initial waiting is included in actual journey time, initial ETA is retained, ordinary progress is not a reroute, and failed searches count as re-plans only.
- **Decision:** Verify the router cannot access hidden distant incidents through cost or closure inputs. Shared scenario seeds support repeatable runs using the fixed-step world model in SIMULATION.md.

- **Decision:** Verify that alternate incoming roads can produce different waits at the same junction, dedicated-entry activation includes waiting, base-graph live sets are unchanged, and forecast caching does not mix different queue positions or visibility contexts.
