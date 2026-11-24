# Open questions and deferred extensions

**Fact:** Updated on 2026-11-23 after approval of Topics 1 through 10, with a risk review and proposed milestone plan. Approved routing behavior is in [ALGORITHM.md](ALGORITHM.md); the approved world model is in [SIMULATION.md](SIMULATION.md), signal control is in [SIGNALS.md](SIGNALS.md), roles are in [ROLES_AND_COORDINATION.md](ROLES_AND_COORDINATION.md), execution/transport/persistence are in [ARCHITECTURE.md](ARCHITECTURE.md), UI/map behavior is in [UI_UX.md](UI_UX.md), evaluation is in [METRICS_AND_EVALUATION.md](METRICS_AND_EVALUATION.md), and integration is in [EMERGENCY108_INTEGRATION.md](EMERGENCY108_INTEGRATION.md). PRD.md/DECISIONS.md summarize the approved product; RISKS.md reviews limitations; M1 in MILESTONES.md is approved; later milestones remain proposed.

## Deferred routing extensions

### Arrival-time forecasts beyond historical profiles

- **Fact:** M4 implements time-dependent Dijkstra for frozen historical road and movement profiles with FIFO costs. Existing current-clock fixtures keep their baseline provider.
- **Assumption (unresolved):** Future signal interventions and multi-ambulance reservations may influence projected live forecasts. Resolve with their respective designs.

### Backtracking

- **Decision:** Future extension only. Do not design a two-node cap, U-turn rules, or a BACKTRACKING state.
- **Assumption (unresolved):** Whether to introduce a backtracking policy remains undecided and will be revisited only when explicitly brought into scope.

## Upcoming design topics

- **Decision:** Topic 4 separates road running time, movement-queue waiting, and boundary waiting. Topic 5 adds one-unit ambulance queue/storage accounting while preserving this separation.
- **Decision:** ARCHITECTURE.md resolves estimator statuses, retry triggers, numeric/time representation, and run sequencing.
- **Decision:** UI_UX.md defines simulation-time ETA countdown, Estimate exceeded, ETA unavailable, and stale/disconnected behavior.

## Resolved in Topic 3

- **Decision:** The algorithm document records approved horizon semantics, frozen current-clock costs, travel-time composition, fallback and unknown-data handling, known closures, deterministic ties, no-route stopping and retry, movement commitment, and metrics.
- **Decision:** Actual journey time starts at activation and includes initial waiting. A red light causes waiting, not a blocked-edge classification. Backtracking remains deferred.

## Resolved in Topic 4 and remaining implementation details

- **Decision:** Adopt the graph, units, fixed-step update order, incident effects, estimation principles, synthetic speed curve, cohort transitions, finite receiving capacity, and conservation rules in SIMULATION.md.
- **Assumption (unresolved, scenario specification):** Set concrete road attributes, demand profiles, turning proportions, and historical profile fixtures with incident-free calibration criteria before implementation.
- **Assumption (unresolved, incident fixtures):** Define composition of overlapping arrival-demand changes; most-restrictive precedence is directly defined only for restrictions. Initial fixtures should avoid ambiguous overlapping demand overrides.
- **Decision:** METRICS_AND_EVALUATION.md defines partial-progress running excess, fixed observation windows, and explicit unfinished/backlogged populations.

## Resolved in Topic 5

- **Decision:** SIGNALS.md records bounded queue service, phase transitions, timing defaults, next-junction requests, equal-priority arbitration, recovery, indivisible ambulance accounting, and bounded deterministic junction forecasting.
- **Decision:** Routing states are (junction, incoming_edge), waiting estimates use (incoming_edge, outgoing_edge, time), and activation uses a dedicated departure entry. Base-graph live horizons are unchanged.

## Execution clarifications resolved in Topic 7

- **Decision:** ARCHITECTURE.md resolves routing before new grant arbitration, recovery/minimum-green interaction, suspension transitions, queue changes, shared discharge and discrete receiving allocation, unknown clearance triggers, and forecast downstream estimates.
- **Decision:** Departure entry capacities/discharge rates are validated scenario attributes; concrete fixture values remain for scenario specification.

## Resolved in Topic 6

- **Decision:** Adopt the five responsibility boundaries, mission-level authorization, automatic junction requests, operator exception handling, and driver-report review queue in ROLES_AND_COORDINATION.md.
- **Decision:** Separate physical injection, operational reporting, and acknowledgement. Use one authoritative backend; zones are labels/filters initially. Authentication, distributed zone authorities, and handoff protocols are deferred.

## Resolved in Topic 7

- **Decision:** Adopt pure Java engine plus Spring Boot application, React/TypeScript, one state owner and command queue per run, HTTP commands, STOMP state/events, and the Maven layout documented in ARCHITECTURE.md.
- **Decision:** Use PostgreSQL via Docker Compose and Flyway migrations, with relational metadata/constraints and JSONB payloads. H2 is superseded. Persist-before-publish and interrupted-run restart semantics are explicit.
- **Decision:** Command ordering, paused boundaries, snapshot isolation, publication/reconnection, report review outcomes, and active-grant cancellation are specified in ARCHITECTURE.md.

## Resolved in Topic 8

- **Decision:** Adopt the approved control-room/driver layouts and interactions, MapLibre renderer, mutually exclusive information modes, optional geographic background, responsive behavior, tokens, and concise landing/scenario selection in UI_UX.md.
- **Decision:** Selection does not automatically recenter; Locate/Follow are explicit. Commands remain Pending until applied, historical routing explanations are timestamped, and physical truth remains distinct from operational information.

## Resolved in Topic 9

- **Decision:** Adopt the six paired configurations, seven core scenarios, ordinary-only references, separate scale experiment, seed counts, measurement/recovery windows, completion-aware metrics, and claim rules in METRICS_AND_EVALUATION.md.
- **Decision:** Keep the presentation explainable: a few clear comparisons with the full headless benchmark behind them. Do not make the full suite a prerequisite for the first working demo.

## Resolved in Topic 10

- **Decision:** Adopt hospital-bound test handoff, assignmentRef dedup/reassignment distinction, explicit scenario mapping, pending police authorization, and read-only simulated status in EMERGENCY108_INTEGRATION.md. Keep backend/engine untouched and do not write simulated locations/completion into Emergency108.
- **Assumption (integration milestone):** Inspect actual code/API payloads, lifecycle hooks, assignment identifiers, and test authentication before wiring; decide active reassignment handling without deleting physical simulation state.

## Phase readiness

- **Fact:** Topics 1–10 are consolidated, risks reviewed in RISKS.md, and a proposed milestone plan is available in MILESTONES.md. M1 implementation is now present in the repository.
- **Decision:** M1 is approved as the routing-only first slice; its no-signal fixture is staged delivery, not a replacement for the approved full traffic model.
- **Fact:** JDK 21, Maven and Docker WSL integration are now functioning. Frontend verification uses Node 22; see README.md for prerequisites.



## Milestone follow-up

- **Assumption (unresolved):** Pin supported compatible dependency versions, finalize concrete scenario/profile fixtures, and set performance targets before implementation.
- **Assumption (unresolved, UI milestone):** Specify operational observation retention/projection, stale-connection threshold, map coordinate adapter, optional geographic basemap/attribution, and final visual assets. Preserve the synthetic map's independence from external tile access.

- **Assumption (unresolved, benchmark preparation):** Specify concrete fixture/seed lists and the optional static-routing baseline behavior; do not tune these after examining benchmark outcomes.
