# Simulation world model — approved Topic 4

**Fact:** Consolidated from approvals through 2026-11-22. Topic 4 is closed at the world-model level. Approved signal service and ambulance priority are in SIGNALS.md; exact scenario fixtures and interface representations remain later design work.

## Representation and limitations

- **Decision:** Ordinary traffic uses aggregate travelling cohorts and movement queues with fractional vehicle-equivalents. Ambulances remain individual agents. No personal civilian route planning is required; configured turning proportions determine flow.
- **Decision:** Congestion emerges from external arrival demand, occupancy, incidents, capacity, and signal actions, never independent random congestion overwrites.
- **Decision:** Road storage is finite; downstream receiving limits cause spillback. Preserve vehicle conservation, including boundary backlogs.
- **Assumption:** Ordinary traffic is homogeneous. Vehicle size differences, lane changing, spatial queue geometry, and Indian mixed-traffic behavior are not modeled. CoSiCoSt inspiration does not establish mixed-traffic fidelity.

## Graph and units

- **Decision:** Use a configurable rectangular grid, default 5 by 5 junctions, represented as generic graph data so other generators or map importers can replace the grid generator.
- **Decision:** Neighboring junctions have separate directed road segments in each direction. Junctions include local (x, y) and optional latitude/longitude coordinates. Road lengths are explicit simulation attributes; map placement does not silently change them or imply real-world traffic accuracy.
- **Decision:** Roads have stable identifiers, length, free-flow speed, storage capacity, and maximum discharge rate. Hospitals and stations attach to junctions with explicit departure-entry queues and approach slots; their ambulances wait for admission rather than spawning past the signal.
- **Decision:** Boundary entry/exit points introduce and remove civilian traffic. For each incoming road, outgoing movement proportions and any exit proportion sum to one.
- **Decision:** Incidents modify attributes or availability, not graph connectivity or stable edge identities.
- **Decision:** Use metres, metres/second, seconds, vehicles/second for rates, fractional vehicle-equivalents for aggregate populations, and vehicle-seconds for accumulated waiting. Storage capacities represent vehicles under the homogeneous model.

## Clock and update order

- **Decision:** Use a deterministic fixed one-second step. Scenario weekday/time-of-day supports historical profiles. Playback speed changes wall-clock pacing only; pause stops simulation time.
- **Decision:** The same scenario, seed, and timestamped operator actions must reproduce the same evolution. The engine is headless; drawing is a client concern.
1. **Decision:** At a step boundary, apply scheduled incidents and operator actions.
2. **Decision:** Update observations, routing decisions, and signal decisions using that boundary's state.
3. **Decision:** Calculate movement and transfers over the next second from the beginning-of-movement state.
4. **Decision:** Commit transfers simultaneously and record measurements.
- **Decision:** ARCHITECTURE.md specifies phase 2: refresh observations and cancel invalid requests, freeze established-policy routing inputs, evaluate routes, then update requests/arbitrate signals once. New grants cannot change that same routing snapshot.
- **Fact:** Step boundaries discretize event timing. The chosen eligibility conventions add small discrete waiting effects; this is an acknowledged approximation.

## Running speed

- **Decision:** For travelling population M, total road storage K, and free-flow speed v_free, use rho = clamp(M / K, 0, 1), v_normal = v_free * max(0.2, 1 - 0.8 * rho).
- **Decision:** Effective speed is the minimum of v_normal and any active incident speed limit. Without a speed restriction, use v_normal. Complete impassability overrides speed to zero.
- **Assumption:** These coefficients are synthetic parameters, not calibrated traffic science. Travelling occupancy controls running slowdown; queued traffic separately consumes storage and incurs junction waiting.
- **Decision:** A positive running-speed floor does not override signal restrictions, queues, or unavailable downstream space.

## Cohort progression and movement queues

- **Decision:** A travelling cohort records a quantity and position along a road, without individual civilian identities or personal routes.
- **Decision:** Existing cohorts advance by the beginning-of-movement effective speed multiplied by one second. Cohorts reaching the road end join movement queues; new entrants begin at zero and move from the next step.
- **Decision:** Newly queued traffic becomes eligible for service next step. Traffic cannot enter and traverse another road in the same step.
- **Decision:** On reaching the end, split the cohort according to configured movement proportions. Queues are indexed by incoming road and intended outgoing road (or exit).
- **Decision:** Queued traffic continues to occupy its incoming road's storage until transfer or exit. For storage accounting, civilian travelling + civilian queued + all ambulances on the road must not exceed K_e. Travelling ambulances also count toward the running-speed travelling population.
- **Decision:** Ambulances advance individually at the same road-running speed initially. No assumed queue bypass or entry to a full road is allowed. Each ambulance occupies one unit, retains its position among fractional civilian batches, and uses the service-credit and atomic-transfer rules in SIGNALS.md.

## Receiving capacity and demand

- **Decision:** Civilian movement transfer is bounded by eligible queue population, discharge allocation, and receiving space. An indivisible ambulance may use up to one unit of service credit accumulated during continuously permitted service; its atomic crossing can use service earned across steps as specified in SIGNALS.md.
- **Decision:** Apply Topic 5's discrete exception: first allocate feasible whole receiving slots to eligible ambulances in deterministic order, then allocate remaining space proportionally among civilian transfer requests. All calculations precede simultaneous commit; processing order must not grant accidental priority.
- **Decision:** Use receiving space available at the beginning of the movement phase. Space freed by this step's departures is usable next step. This conservative convention avoids circular transfer dependencies.
- **Decision:** External demand unable to enter remains in a boundary backlog. Preserve and measure that population and its waiting; never silently discard it.
- **Decision:** Conservation includes in-network travelling/queued populations, boundary backlogs, arrivals, and completed exits. No incident may delete vehicles.

## Incident effects and reporting

- **Decision:** Support five physical effects: reduced traversal speed, reduced discharge rate, entry closure, complete impassability, and changed external arrival demand.
- **Decision:** Entry closure prevents new entrants but lets occupants clear; complete impassability prevents entry and stops occupants until passage is possible. Ambulances stopped on an impassable road raise operator alerts.
- **Decision:** Do not reduce storage capacity during incidents. Model a bottleneck using discharge/speed restrictions without making existing occupancy exceed a newly reduced capacity.
- **Decision:** Incident effects and reporting times are separate. Actual dynamics respond to physical onset; routers learn through permitted live observations or explicit reports.
- **Decision:** For overlapping restrictions, use the most restrictive active value for each attribute; complete impassability takes precedence. Removing an incident removes only its own restriction.
- **Assumption (unresolved fixture detail):** Overlapping demand changes require an explicit scenario composition rule; unlike speed/discharge restrictions, increased and decreased demand do not have a universal most-restrictive ordering. Avoid ambiguous overlapping demand overrides in initial fixtures.

## Live and historical estimates

- **Decision:** Fresh perfect live traversal observations are available only within the ambulance's approved live set. Noise and latency are deferred.
- **Decision:** Live estimated road traversal time is length / current effective speed, interpreted as the time if current conditions persist. Actual traversal can differ as conditions evolve. Exclude junction waiting from this quantity.
- **Decision:** Road availability is separate from speed. Locally observed or explicitly reported entry closures/impassability exclude entry. Existing occupants may continue clearing an entry-closed road.
- **Decision:** Historical traversal estimates use length / expected speed for road class, weekday/weekend, and time of day. Interpolate profile points; freeze profiles before comparison runs.
- **Decision:** Profiles represent ordinary expected conditions, not the current run's surprise incidents. They must not read hidden current queues, future incidents, or future signal decisions. Calibrate against incident-free baseline simulations.
- **Decision:** Call the initial implementation a historical-profile predictor, not trained ML. Keep the (edge, time) interface so a trained model can replace it later.
- **Decision:** Apply the same configurable live-horizon boundary to junction-delay estimation: observed queues locally, expected/historical queues or waits outside. Known established signal policies may inform estimates, but candidate routes get no assumed automatic preemption.
- **Decision:** Preserve approved routing fallback: invalid/unavailable live data falls back to valid historical estimates with disclosure; no valid estimate means unknown/excluded, not zero. A known closure overrides estimates until reopening.

## Measurements and verification

- **Decision:** Accrue queue waiting from beginning-of-movement queue population multiplied by one second. Track boundary-backlog waiting separately.
- **Decision:** Keep running-time excess separate from queue waiting. METRICS_AND_EVALUATION.md defines partial-progress accrual, fixed windows, and signed matched-baseline comparisons; queue waiting alone is not total traffic delay.
- **Decision:** Verify conservation, nonnegative populations, storage limits, deterministic evolution independent of playback speed, and reproducible incident/report timelines.
- **Decision:** Verify the speed curve endpoints, incident speed caps, closure versus impassability, overlap removal, and absence of random state overwrites.
- **Decision:** Verify next-step movement/service eligibility, turning-proportion conservation, proportional receiving allocation, and retention of unmet external demand.
- **Decision:** Verify that predicted providers cannot read hidden incident state and that junction estimators respect the same information boundary as road providers.

## Topic 5 integration

- **Decision:** SIGNALS.md defines approach-at-a-time service, transitions, timing limits, emergency arbitration/recovery, and bounded junction forecasts.
- **Decision:** ALGORITHM.md now uses movement-aware states and junction estimators; live horizons remain on the base road graph.
- **Decision:** Ambulance capacity and queue accounting refine the original purely fractional flow rules as documented above.
- **Decision:** ARCHITECTURE.md resolves boundary ordering and shared service/allocation details; scenario fixture values remain in OPEN_QUESTIONS.md.
