# Metrics and strategy comparison — approved Topic 9

**Fact:** Consolidated on 2026-11-23 from Topic 9 approvals. This is an evaluation design, not measured evidence or a requirement to implement the whole benchmark before the first demo.

## Keep the explanation simple

- **Decision:** Separate routing information benefit from emergency-signal-priority benefit. Present ambulance outcomes and ordinary-traffic consequences together.
- **Decision:** The presentation can show a few understandable side-by-side comparisons. The full scenario/seed suite runs headlessly behind the results; it is not a 980-screen UI feature.
- **Decision:** Build the evaluation incrementally after the engine works. Keep scientific claims within the comparisons actually executed.

## Core comparison matrix

| Routing information | Priority disabled | Priority enabled |
|---|---|---|
| **Decision:** Historical only, LIVE_HORIZON=0 | Run | Run |
| **Decision:** Professor's hybrid, LIVE_HORIZON=2 | Run | Run |
| **Decision:** All-live snapshot, LIVE_HORIZON=all | Run | Run |

- **Decision:** Hold movement-aware Dijkstra, junction forecasting, normal signal service, and re-planning rules constant. Change information horizon and priority enablement only.
- **Decision:** All-live is an information-rich reference, not an oracle or guaranteed winner. Explicit reports remain visible according to the approved reporting rules in every mode.
- **Decision:** Static routing is an additional demonstration baseline, not part of the six core configurations. Greedy/blended variants are deferred.
- **Assumption (static-demo follow-up):** Specify static initial weights and blocked-route behavior before implementing that optional demonstration; do not silently invent a different fallback policy.

## Paired inputs and reproducibility

- **Decision:** Pair network, initial world, signal settings, historical profiles, arrival demand, ambulance missions, incidents, explicit reports, and observation windows by scenario/seed.
- **Decision:** Pre-generate external schedules or use independently keyed RNG streams so strategy-dependent code paths cannot change demand or event schedules. Freeze schedules before benchmark execution.
- **Decision:** Local discovery times, queues, signal actions, and route outcomes may diverge as consequences of policies; do not force them to match.
- **Decision:** Calibrate historical profiles on separate incident-free baseline runs, then freeze profiles/configuration/seed lists before final results. No tuning against favorable benchmark outcomes.
- **Decision:** Record fixture/version, engine/configuration/profile version, seed, schedule identity, and exact policies with each result so a headless run can be reproduced.

## Scenario suite and scale

| Core scenario | Question |
|---|---|
| **Decision:** Ordinary demand without incidents | Is the historical expectation sufficient? |
| **Decision:** Predictable distant congestion | Does long-range information explain a useful route choice? |
| **Decision:** Unexpected local obstruction | Does observation produce a useful reroute or honest stop? |
| **Decision:** Unexpected distant obstruction | Where do historical estimates fail and wider live coverage help? |
| **Decision:** Congested receiving road | Is ineffective priority refused and blockage exposed? |
| **Decision:** Conflicting ambulances | Do arbitration, commitment, and recovery work under contention? |
| **Decision:** Temporary disconnection | Does the ambulance stop/alert and resume after reopening? |

- **Decision:** Use 5x5 fixtures for core cases, an 8x8/10-ambulance fixture for conflicts, and a separate 10x10/30-ambulance scale experiment.
- **Decision:** Include one ordinary-traffic-only reference per core scenario/seed. It provides context, not a replacement for priority-on/off comparisons with the same ambulance missions.
- **Decision:** Include conditions where hybrid gains little or loses. The predictable-congestion scenario need not show hybrid outperforming historical-only, since both have historical information.
- **Decision:** The scale experiment reports execution speed and forecast workload alongside traffic outcomes. Completion alone does not prove that requested accelerated playback is sustainable.
- **Decision:** Use one named demo seed per scenario, 20 predeclared benchmark seeds per core scenario, and five seeds for the scale experiment. The core matrix is 7 x 20 x 6 = 840 runs; ordinary-only references add 140 runs, for 980 before optional/static and scale experiments.
- **Assumption (fixture preparation):** Choose actual seed IDs, road/demand/incident parameter values, station capacities, and documented variation ranges before implementation of the benchmark. Seeds must not mean arbitrary parameter changes chosen after observing results.

## Time windows and completion

- **Decision:** Warm up ordinary traffic for 600 seconds without ambulances or surprise incidents. Clone the same warm state into all configurations, retaining populations/controller state but resetting evaluation counters.
- **Decision:** Evaluate for 1800 seconds after warm-up; schedule missions within the first 600 evaluation seconds. Continue for a 600-second follow-up with no new missions and ordinary demand still active.
- **Decision:** The common measurement window is 2400 seconds; total run length including warm-up is 3000 seconds. Use the same external schedules through the whole window.
- **Decision:** Arrival by evaluation end is on-time completion. Arrival during follow-up is late completion. Still present at the end is unfinished. Keep incomplete ambulances physically present and their policies active; do not delete them to simplify recovery.
- **Decision:** If completion is late or absent, call the final period follow-up, not a guaranteed full post-arrival recovery period. Report evaluation and follow-up delay separately as well as their combined total.
- **Decision:** Rejected activations are reported as such against the scheduled mission set; do not hide them by counting only activated missions. Actual journey time begins only at successful activation, as specified earlier.

## Ambulance outcomes

- **Decision:** Report individual mission outcomes, actual activation-to-arrival time, on-time/late/unfinished/rejected counts, stopped time by reason, re-plan and reroute counts, initial ETA error, and requests/grants/unsuccessful grants.
- **Decision:** Keep Displayed ETA distinct from measured journey time. ETA error is only defined when an initial estimate exists and actual arrival is observed; report missing cases separately.
- **Decision:** For paired travel-time differences, use matched missions completed in both runs and show coverage/full outcome counts alongside. Never make completion failures disappear from a successful-only average or replace them with zero travel time.
- **Decision:** Summarize seed-level results and paired differences with medians and interquartile ranges. Ambulances sharing one traffic run are not independent experimental replicates.
- **Decision:** Stopped-time categories must distinguish ordinary signal waiting, queue/receiving-space waiting, physical impassability, and unavailable route/estimate; do not count one second twice in summed categories.

## Civilian accounting

- **Decision:** Total measured civilian delay is boundary waiting + junction waiting + running-time excess, in vehicle-seconds (displayable as vehicle-minutes). Exclude ambulances from civilian populations.
- **Decision:** Accrue boundary and junction waiting from beginning-of-movement civilian populations times the one-second step. Include vehicles still waiting at measurement end.
- **Decision:** Implement running-time excess for each civilian travelling cohort as quantity * max(0, step_seconds - actual_distance_advanced / free_flow_speed) for its travelling step. Cap distance at the actual remaining road distance. This accounts for partial progress, impassability, and the model's step-boundary discretization without assuming eventual completion.
- **Decision:** Newly entering cohorts start accrual from their next eligible movement step; newly queued cohorts begin queue accrual next step. This matches the approved beginning-of-movement accounting. Do not add running and queue time for the same cohort during the same step.
- **Decision:** Report exited vehicle-equivalents, remaining travelling/queued populations, boundary backlog, peak queues, and full-road duration beside delay. A lower delay number with unfinished/backlogged demand is not automatically a better traffic outcome.
- **Decision:** Do not claim distinct civilian vehicles delayed. Fractional batches can wait at multiple junctions; queue-entry volume is not a unique-vehicle count.

## Priority cost and recovery

- **Decision:** For each information policy, priority cost is signed delta D = civilian delay with priority - civilian delay without priority over the identical 2400-second window with the same scheduled missions. Do not clamp beneficial negative differences to zero.
- **Decision:** Interpret delta D as a network-wide policy effect, not automatically a particular ambulance's attributable delay. Ordinary-only references change more than signal priority and cannot substitute for this estimate.
- **Decision:** Recovery starts after the last emergency grant ends. It is the time until network civilian queue population remains within max(0.05 * matched priority-disabled queue population, 1 vehicle-equivalent) for 60 consecutive simulation seconds, comparing equal timestamps. Use absolute queue difference for 'within'.
- **Decision:** Report boundary backlog alongside queue recovery; queue recovery does not undo accumulated delay. If there is no ended last grant within observation, or no qualifying interval, report recovery not observed/not recovered within observation window, not zero.
- **Decision:** Compute recovery from one-second aggregate queue measurements in benchmark runs, rather than infer 60 consecutive seconds from five-second dashboard samples. A qualifying interval's start is the recovery time, confirmed after its 60th consecutive second; a later grant restarts this assessment.

## Presentation claims and validation

- **Decision:** State comparator, scenario/seed coverage, change in completed-trip time, completion outcomes, and civilian impact together. Publish actual completed benchmark coverage, not planned coverage.
- **Decision:** No superiority claim against CoSiCoSt (its implementation is not tested), no real-world accuracy/lives-saved claim, no all-live optimality claim, and no cherry-picked best seed presented as typical performance.
- **Decision:** Include neutral/negative results and separate software-usability demonstrations from algorithm evidence.
- **Decision:** Verify identical external schedules/warm starts, policy isolation, partial-progress accounting, retained unfinished populations, rejected activations, missing ETA cases, signed deltas, and exact one-second recovery detection.
- **Decision:** Keep benchmark runners headless and use existing engine/configuration contracts; do not introduce a new service or UI requirement solely to execute the suite.
