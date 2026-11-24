# Signal control — approved Topic 5

**Fact:** Consolidated from user approvals on 2026-11-22. This is a synthetic signal controller, not a field-deployment specification or reproduction of the complete CoSiCoSt implementation.

## Responsibilities and normal service

- **Decision:** Separate ordinary queue service, emergency-priority arbitration, and transition rules. Emergency priority cannot bypass transitions or receiving capacity.
- **Fact:** C-DAC's [CoSiCoSt-W brochure](https://www.intranse.in/sites/default/files/products/CoSiCoSt-Brochure.pdf) describes queue exhaustion and green-time limits as functional blocks.
- **Decision:** Describe the controller as CoSiCoSt-inspired bounded queue-exhaustion service, not an implementation of unpublished CoSiCoSt functions.
- **Decision:** Permit movements from one incoming approach at a time. Other approaches remain red. Serve at least minimum green, extend while queued traffic can discharge up to normal maximum, and yield after minimum green when empty or downstream-blocked.
- **Decision:** Select ordinary approaches in stable cyclic order, skipping approaches with no traffic able to discharge. Preserve the cyclic cursor through emergency interventions.
- **Decision:** Use Green -> Amber -> All-Red -> Next Green. No new junction admissions occur during amber or all-red. A new request cannot interrupt a transition; select the next approach at the end of clearance using current valid requests.
- **Decision:** A four-road junction can display a one-hot vector such as [0,0,1,0]. During amber/all-red all entries are zero and a separate phase-state field identifies the transition. Dedicated station/hospital entries have explicit additional approach slots; vectors must not assume every junction has four approaches.
- **Assumption:** This simplified approach-at-a-time arrangement sacrifices potential throughput and does not model spatial turn conflicts or lane interference. It is not a claim of optimal real-world intersection operation.

## Configurable timing defaults

| Parameter | Approved value |
|---|---:|
| **Decision:** Minimum green | 10 seconds |
| **Decision:** Normal maximum green | 30 seconds |
| **Decision:** Amber | 3 seconds |
| **Decision:** All-red clearance | 2 seconds |
| **Decision:** Emergency maximum continuous green | 45 seconds |
| **Decision:** Recovery service opportunity | Up to 10 seconds |

- **Decision:** Emergency maximum is measured from the original start of continuous green. New requests never reset that timer. Preemption respects the minimum green of an already served approach.
- **Assumption:** These are simulation experiment defaults, not validated operational timings.

## Priority requests and arbitration

- **Decision:** Each ambulance maintains at most one request, for its next junction or the junction where it is waiting. It does not reserve the whole route.
- **Decision:** Activate the request when ETA to road end <= estimated queue-clearance time + 15 seconds. Use the road end because spatial queue tails are not represented. The allowance does not guarantee passage within that interval.
- **Decision:** Requests identify the ambulance, incoming approach, intended outgoing road, and route version. Re-planning updates or cancels obsolete requests.
- **Decision:** If the needed approach is already green, extend as needed within the emergency maximum. Otherwise finish the active approach's minimum green and required clearance before switching.
- **Decision:** Do not grant an unproductive green solely for an ambulance whose receiving road is full. Keep the request pending and surface 'priority requested, downstream blocked'. If other movements on that approach can discharge, their usefulness remains relevant to ordinary service.
- **Decision:** Ambulances have equal emergency priority. Order eligible competing requests by earliest predicted junction arrival (actual arrival time for waiting ambulances), then request creation time, then stable ambulance ID.
- **Decision:** Once a grant starts, commit until the selected ambulance passes, the grant becomes unproductive, or emergency maximum expires. New requests do not continuously reshuffle an active grant.
- **Decision:** Requests sharing the served approach may benefit together but retain queue positions and cannot reset the timer.
- **Decision:** Release requests on passage, journey completion, or when the movement is no longer needed. A grant reaching maximum without passage is logged as unsuccessful; its request remains pending for later service.

## Recovery

- **Decision:** After an emergency grant, provide the next eligible ordinary approach in cyclic order up to 10 seconds of recovery service before another conflicting emergency grant. Skip approaches with nothing able to discharge; preserve the cyclic cursor.
- **Decision:** After recovery, serve the next eligible emergency request, or resume ordinary cyclic service if none exists.
- **Fact:** This trades some emergency waiting for ordinary traffic service; it does not guarantee bounded civilian waiting under oversaturation.
- **Decision:** Topic 7 resolves recovery timing: skip an ineligible opportunity before starting; once recovery green starts, retain the 10-second minimum even if it becomes empty/blocked, then transition normally. See ARCHITECTURE.md.

## Ambulance accounting and ordered queues

- **Decision:** Each ambulance occupies one indivisible vehicle-equivalent. For a road: civilian travelling + civilian queued + all ambulances on the road <= storage capacity. Travelling ambulances contribute to running-speed occupancy; waiting ambulances consume storage but not travelling occupancy.
- **Decision:** Each movement queue retains civilian batches and individual ambulances in arrival order, for example 3.4 civilian equivalents, ambulance A, 1.2 civilian equivalents, ambulance B. Partial civilian batches may discharge; ambulances cannot bypass traffic ahead in their movement.
- **Decision:** Crossing requires one complete unit of discharge service and one complete unit of receiving space. Transfer atomically from incoming to outgoing road; never duplicate or fractionally transfer an ambulance.
- **Decision:** A head-of-queue ambulance may accumulate at most one unit of discharge-service credit during continuously permitted service. Credit consumes its allocated discharge budget. Retain it while permission continues; clear unused credit on phase end. Credit neither reserves downstream space nor authorizes passage on red.
- **Decision:** Individual crossings may consume service earned across several steps. This is an explicit refinement of the original per-step aggregate-flow bound; accumulated service remains bounded by earned allocations.
- **Decision:** Allocate feasible whole ambulance receiving slots deterministically using the approved request ordering before allocating remaining space proportionally among civilian requests. This is the approved discrete exception to proportional receiving allocation.
- **Decision:** Station/hospital activation joins a dedicated departure-entry queue and starts the journey clock immediately. The ambulance consumes entry storage until admitted to its first road. Destination arrival removes it without requiring another outgoing signal movement.
- **Decision:** ARCHITECTURE.md resolves shared discharge allocation, ordering for contenders without active requests, station-entry validation, and clearing credit/appending to the new queue when a waiting ambulance changes movement.

## Junction-delay forecasts

- **Decision:** The junction estimator accepts (incoming_edge, outgoing_edge, time), with ambulance queue context and the frozen information snapshot supplied as estimator context.
- **Decision:** Reuse signal-service rules in a deterministic isolated forecast. Estimate admission of a hypothetical ambulance in the candidate movement: estimated waiting = forecast admission time - current snapshot time.
- **Decision:** Include traffic ahead, signal/clearance waits, and discharge service; exclude outgoing-road traversal. A waiting ambulance uses its existing position rather than a duplicated queue entry. Downstream candidate movements place a hypothetical ambulance behind the currently estimated queue.
- **Decision:** Use observed queue/receiving occupancy only where permitted by the ambulance's live set. Elsewhere use historical expectations. Use observable or historical arrival/discharge expectations, never the hidden future event schedule.
- **Decision:** Known established signal policy and committed grants may affect the forecast. The hypothetical candidate does not create a new priority grant.
- **Decision:** Each candidate forecast starts at the same current-clock snapshot time, not the path's projected arrival time. Internal forecast advancement estimates waiting under that snapshot; the outer Dijkstra remains a frozen-cost search, not arrival-time-dependent routing.
- **Decision:** Limit forecasts to 300 simulation seconds by default. If admission does not occur within the horizon, return explicit unknown/horizon-exceeded. Exclude that movement under the approved unknown-cost rule, disclose the reason, and do not claim permanent physical blockage.
- **Decision:** Cache identical forecast inputs only within the frozen routing snapshot. Include all relevant forecast context, including queue position, information visibility, and committed policy, so unlike cases cannot share results.
- **Decision:** ARCHITECTURE.md specifies historical expected downstream flows with observable restrictions, a separate nonrecursive queue-clearance estimate, and conservative unknown-trigger behavior. Forecasts reuse service primitives without invoking request generation or themselves recursively.

## Routing integration

- **Decision:** Search states are (junction, incoming_edge). A transition to outgoing edge e costs junction_delay(incoming_edge, e, t) + road_traversal(e, t), and arrives in state (destination_of_e, e).
- **Decision:** Activation uses its dedicated departure entry as incoming context. Any destination-junction state is a goal, without an extra departure wait.
- **Decision:** Keep the physical graph and displayed routes as junctions and roads. Compute the configurable live neighborhood on the base road graph, never by counting expanded search states.
- **Decision:** Preserve current-clock predictions, frozen nonnegative costs, deterministic ties, stop/alert behavior, and deferred backtracking from ALGORITHM.md.

## Required checks

- **Decision:** Verify minimum/maximum greens, no timer resets, no admissions during amber/all-red, one permitted approach, and correct vectors at additional departure entries.
- **Decision:** Verify request triggering/version changes, deterministic arbitration, grant commitment, downstream-blocked messaging, unsuccessful grants, and cyclic recovery.
- **Decision:** Verify fractional batches ahead of ambulances, one-unit capacity, atomic transfers, credit accumulation/reset, whole-slot allocation, and ordinary flow conservation.
- **Decision:** Verify initial station waiting, destination exit, differing movement waits for different incoming roads, and unchanged base-graph live neighborhoods.
- **Decision:** Verify forecast isolation, live/history boundaries, no hypothetical preemption, 300-second unknown outcomes, and cached versus uncached equivalence.
- **Decision:** Test accounting and behavior with multiple simultaneous ambulances even if the first integration milestone activates only one.
