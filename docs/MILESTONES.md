# Milestones — M6 test handoff verified

**Fact:** Prepared on 2026-11-23 after consolidation of Topics 1–10 and the design risk review. M1 through M5 are verified, and M6 is verified with the local Emergency108 test handoff.

## Delivery approach

- **Decision:** Preserve the complete multi-ambulance design, build one milestone at a time, write engine tests first, and commit working steps once implementation is authorized.
- **Assumption (proposal):** Use the milestones below to keep each demonstration understandable. Detailed later-milestone acceptance is refined before its implementation, without reopening approved product boundaries unnecessarily.

| Milestone | Demonstrable result | Acceptance and test focus | Deliberately deferred |
|---|---|---|---|
| **Decision: M1 approved** | One ambulance follows explainable hybrid routes on a synthetic map | Scaffold builds; real PostgreSQL/Flyway; deterministic routing; HTTP/STOMP controls and event history; no-signal fixture explicitly identified | Background flow, production junction forecasts, priority, multi-ambulance contention, polished driver screen |
| **Decision: M2 authorized** | Ordinary traffic queues and signals affect a single ambulance | Conservation/storage/credits; signal timings and clearance; reported versus physical incidents; bounded forecasts; actual delays | Multi-ambulance conflict workflow and full benchmark suite |
| **Decision: M3 authorized** | Multiple ambulances share junctions correctly | 10-ambulance contention, deterministic ordering, active-grant commitment, suspension and recovery; fleet/driver state isolation | 30-ambulance performance claim and external integration |
| **Fact: M4 verified** | Polished control-room/driver product and calibrated routing fixture | Responsive and keyboard checks, scenario picker, reproducible historical profiles, projected historical estimates in the route inspector | Real operational deployment, individual civilian physics, auth expansion |
| **Fact: M5 verified** | Reproducible comparison report and scale results | 980 core/reference runs, 35 scale/reference runs, paired completion-aware delay and recovery results | Claims about CoSiCoSt superiority or real-world accuracy |
| **Fact: M6 verified for local replay** | Test Emergency108 hospital-leg handoff | Source-backed mapping, replay and reassignment tests, pending police authorization, read-only simulated status | Live Emergency108 producer, GPS ingestion, completion writes, pickup leg |

## M1 — scaffold and first routing slice

**Decision (approved M1 scope):** Deliver one 5x5 scenario, one ambulance, a route-explanation map, play/pause/step, real persistence, and repeatable routing. Use an explicitly named ROUTING_ONLY scenario mode with a valid zero-junction-wait provider because this milestone has no signals or civilian queues. It is not a fallback for failed estimates and cannot be presented as the completed traffic-control model. The approved signal estimator replaces this fixture provider in M2.

### Working steps

1. **Assumption (planned step):** Establish the toolchain: Java 21, Maven Wrapper, Node/npm, Docker Engine/Compose working from WSL. Select and pin supported compatible Spring Boot, Flyway/PostgreSQL driver, React/Vite/TypeScript, MapLibre, and test versions in manifests/lockfiles before implementing features. Use the same PostgreSQL major version for Compose and database integration tests. Do not install tools or change the machine during the design-only phase.
2. **Assumption (planned step):** Create Maven modules backend/engine and backend/application, React/TypeScript frontend, scenarios, and docs; add root Compose for PostgreSQL with a named volume/health check, a local environment example without secrets, and ignored build/runtime files. Keep the engine dependency boundary enforceable.
3. **Assumption (planned step):** Add Flyway migrations and application repositories for scenario/run metadata, commands/outcomes, and ordered events, using JSONB for structured payloads and relational uniqueness/ordering. Use JDBC application adapters; no JPA entities in the engine. M1 does not need final benchmark metric tables yet.
4. **Assumption (planned step):** Test then implement stable graph IDs, base-graph horizon 0/2/all, current-clock weight selection, movement-aware Dijkstra, deterministic ties, source explanations, unknown/blocked distinctions, and arrival/no-route behavior. Snapshot providers never read unpermitted hidden incidents.
5. **Assumption (planned step):** Implement one-agent fixed-step motion with explicit road availability, starting-entry context, and the routing-only zero-wait provider. Keep the same interfaces that M2 will use. Add command-driven closure/reopening and retry so alternative routing and stopped states can be demonstrated.
6. **Assumption (planned step):** Implement run creation, idempotent play/pause/step/speed/mission/incident commands, persist-before-publish, state snapshot queries, STOMP state/events, and interrupted-run restart handling. Scope payloads to M1 features; reject unsupported commands explicitly.
7. **Assumption (planned step):** Build the control-room shell with approved tokens, local MapLibre synthetic graph, ambulance selection/Locate, route and solid/dashed source styling, play controls, routing explanation, and event panel. Show the routing-only scenario identity and do not display invented signals, civilian delays, or priority grants.
8. **Assumption (planned step):** Run engine, PostgreSQL/application, and frontend checks; manually verify the short scenario below; document exact startup/test commands and commit each verified working step. No deployment, Emergency108 connection, or force push is part of M1.

### Initial fixture

- **Assumption (planned fixture):** Use a bidirectional 5x5 orthogonal grid, 100 metres per road, baseline speed 10 m/s, stable row/column IDs, one dedicated departure entry at (0,0), and destination (4,4). Explicit lengths govern movement; geographic coordinates are display-only.
- **Assumption (planned fixture):** No civilian arrivals or signal phases in ROUTING_ONLY. Road costs are 10 seconds under the baseline profile; a configured local speed incident can reduce speed to 2 m/s without changing the historical profile. The fixture uses a fixed seed and deterministic timeline.
- **Assumption (planned fixture):** Mission activation uses the departure entry; zero wait reflects that this fixture has no controller. Playback is 1/5/10/30/60x with identical simulated outcomes, not a guarantee of real-time 60x throughput.
- **Assumption (planned fixture):** Test graph fixtures separately cover alternate equal-cost paths, source-dependent choices, disconnection, and unknown estimates. The UI demo need not expose every test graph.

### M1 acceptance

- **Assumption (acceptance):** A clean checkout can start PostgreSQL, apply Flyway, build backend/frontend, and display the synthetic graph using documented commands after prerequisite setup.
- **Assumption (acceptance):** Creating/activating a mission and stepping advances the ambulance deterministically; no state changes through client-side authority. Pause freezes simulation time. Repeated identical command IDs do not repeat actions.
- **Assumption (acceptance):** Route inspection shows the live/historical source and current decision timestamp. Horizon changes are selected when creating a run so the UI does not silently change an active experiment.
- **Assumption (acceptance):** A reported closure excludes that edge. A feasible alternative is selected at a valid routing boundary; no feasible route stops and alerts. Reopening and retry can recover. A closure while traversing never teleports/reverses the ambulance.
- **Assumption (acceptance):** Same seed and applied command sequence produce the same journey, routes, and events at different playback speeds. Reconnect restores current state/event history; backend restart marks unfinished runs interrupted.
- **Assumption (acceptance):** PostgreSQL contains inspectable scenario JSONB, command outcomes, and ordered events; engine tests still run with no database or Spring context.
- **Assumption (acceptance):** The UI uses the approved visual foundations and remains clear that background traffic/signals are not active in this first routing fixture. No benchmark effectiveness claims are made from M1.

### Test plan

- **Assumption (planned tests):** Pure engine tests: horizons and directed branches; closure-independent neighborhood; frozen clock; deterministic ties; movement context; live fallback/unknown; immediate destination; all blocked/unreachable; mid-edge impassability; re-plan versus reroute counts.
- **Assumption (planned tests):** Application tests against real PostgreSQL: Flyway from empty schema, JSONB round-trip, duplicate/conflicting commands, sequence ordering, paused commands, exact step, publish-after-commit, persistence failure, restart interruption, and event query ordering.
- **Assumption (planned tests):** Frontend tests: snapshot revision rejection, event deduplication, pending/outcome feedback, disconnected state, selection synchronization, and routing-source display. Type-check and production build must pass.
- **Assumption (planned checks):** Browser walkthrough: start run, activate mission, inspect route, step, play/pause, introduce a closure at a safe boundary, see reroute/stop, reopen/retry, reconnect, and inspect saved events. Automated browser checks depend on the available browser tooling; report any verification limitation.

## Approval gate

- **Decision:** Review the risk/design summary and approve M1 before scaffolding application files. The user may adjust milestone boundaries explicitly. Later milestones require their own acceptance review before build.
- **Fact:** The initial toolchain gaps have been resolved for backend verification: JDK 21, Maven Wrapper and Docker WSL integration work. Frontend dependencies require Node 22.12+ and npm 11. See README.md for repeatable commands.

## Verification checkpoint — 2026-11-24

- **Fact:** Maven Wrapper verification passed: 13 pure-engine tests and 3 application tests against PostgreSQL, including persist-before-publish, failure rollback and interrupted-run handling.
- **Fact:** Frontend TypeScript/production build and 2 stream-reconciliation tests passed. One Chromium walkthrough passed mission activation, rendered roads, routing explanations, closure/reroute, all-outgoing-blocked stop, reopening, step/play/pause, reload, disconnect/reconnect and 390 px layout checks. Desktop screenshot inspection confirmed that the map renders after reconnect.
- **Fact:** Verification fixed explicit MapLibre worker bundling and a replacement-map readiness race. The frontend requires Node 22.12+; this environment was verified with a temporary Node 22 runtime.
- **Fact:** Vite reports a large map-containing JavaScript chunk. This is a remaining frontend optimization, not a failed build.
- **Decision:** This checkpoint remains the routing-only M1 fixture. It does not establish signal, civilian-flow, multi-ambulance or benchmark readiness. M3 and later milestones remain unapproved.


## M2 — first engine checkpoint

- **Decision:** Implement and test ordinary signal timing before coupling it to queue transfers. The same normal-service rules will be available to bounded junction forecasts.
- **Fact:** This checkpoint adds minimum and maximum green, amber and all-red clearance, stable approach rotation, and a permission vector that includes station entries. Queue discharge, forecasts, priority and the M2 demo still need integration.
- **Decision:** Keep the synthetic grid for repeatable tests. Track the Jaipur road network as a separate demo scenario in [JAIPUR_MAP.md](JAIPUR_MAP.md).

## M2 verification checkpoint — 2026-11-24

- **Fact:** The traffic-and-signals scenario integrates civilian cohorts, finite storage, movement queues, boundary backlog and component delay. Ambulances use whole receiving slots and continuous-green service credit. The scenario supports one active mission.
- **Fact:** Next-junction requests, clearance, capped greens and cyclic recovery run in the same engine as normal traffic. The control room shows signal state, priority state and actual junction wait, with priority suspension and a priority-disabled run option.
- **Fact:** Dijkstra uses a 300-second junction forecast through the existing estimator interface. Forecasts reuse junction service, use permitted observations and frozen historical expectations, and return unknown on timeout.
- **Fact:** The full backend, frontend production build, frontend stream tests, and browser walkthroughs for both scenarios passed. PostgreSQL stores the latest committed traffic measurements.
- **Assumption:** The M2 demo uses constant calibrated historical inputs for its stationary synthetic demand. Full time-of-day profiles, the Jaipur import and multi-ambulance contention remain future work.

## M3 — coordinated multi-ambulance operations

**Decision:** M3 is authorized with these delivery slices.

1. Add a 10-ambulance conflict fixture with stable IDs, individual routes and ordered movement-queue positions in one shared traffic world.
2. Arbitrate equal-priority requests by predicted junction arrival, request time and ambulance ID. Preserve an active grant until passage, unproductivity or the 45-second emergency limit, then apply the approved recovery green while preserving the ordinary cursor.
3. Support mission-level priority suspension for one ambulance without cancelling other ambulances' requests or bypassing signal transitions.
4. Keep physical incident injection, operational report submission/review and alert acknowledgement as distinct commands and persisted records. Driver obstruction reports remain pending until police review.
5. Publish fleet-isolated snapshots and explanations from the single authoritative backend. Add synchronized fleet selection and a Driver Navigation view for the selected ambulance.
6. Add mutually exclusive Operational, Ambulance Routing and Simulation Truth map modes. Operational views expose confirmed knowledge, and Simulation Truth exposes physical effects.
7. Verify deterministic 10-ambulance contention, request tie-breaking, grant commitment, recovery, capacity and queue ordering, report workflow separation, reconnect, and control-room/driver state isolation.

**Decision:** Add scenario-calibrated, time-indexed historical profiles with predictable bottlenecks during M3/M4 and freeze them before M5 evaluation fixtures are prepared.

**Fact:** The first M3 engine checkpoint connects equal-priority request ordering to the existing signal phase controller. It keeps the current grant when an updated ETA or an earlier competing request arrives and preserves clearance and recovery when the grant ends. Shared fleet movement and the operator and driver workflows are subsequent M3 slices.

**Fact:** The M3 backend adds the `fleet-conflict-5x5` scenario with ten independently activated missions sharing one clock and traffic world. The scenario response provides each ambulance's station through `departureByAmbulance`. Activation, retry, and suspension accept an `ambulanceId`. The operational snapshot includes the fleet, signal state, and confirmed reports. Individual mission snapshots provide routing explanations with their own live neighborhoods. The simulation truth endpoint provides physical effects separately. Obstruction reports enter review before they affect confirmed network knowledge.

**Fact:** The M3 browser walkthroughs check the ten-ambulance fleet, map information modes, isolated physical effects, report confirmation, and a driver report submitted from the current road. They cover mobile Follow and Recenter, live grant and suspension status, and controlled snapshots for stale, exceeded, unavailable, and completed ETA states.

## M4 — product polish and scenario calibration

**Assumption (planned milestone):** Polish the control room and driver experience, including responsive and keyboard behavior, inspector and report review details, and the concise landing experience. Calibrate time-indexed historical profiles against scenario demand with predictable bottlenecks, then freeze them before M5 evaluation.

**Fact:** M4 Part 1 adds the landing page at `/welcome`, scenario selection, and responsive control room drawers. Keyboard selection exposes the same junction and road inspectors as map selection. Drawer dismissal restores focus. Incoming events append without moving keyboard focus or the current reading position.

**Fact:** M4 Part 2 adds the [predictable corridor congestion fixture](../scenarios/PREDICTABLE_CONGESTION.md). Historical-only and Hybrid both anticipate the distant congestion at activation. The application bundles the frozen profile and records its provenance with each run. The route inspector displays the projected interval on selected historical roads.

## M5 — strategy evaluation and scale

1. **Decision:** Prepare the seven core fixtures with paired demand, incident and mission schedules. Freeze historical profiles on the benchmark clock from independent incident-free calibration runs. Clone the 600-second warm state across configurations.
2. **Decision:** Run Historical-only, Hybrid and All-live with priority enabled and disabled over 20 seeds per core fixture, plus a matched ordinary-traffic-only reference per seed. Measure across 1,800 seconds of evaluation and 600 seconds of follow-up.
3. **Decision:** Report completion and unfinished missions, matched journey-time differences, civilian delay components, signed priority cost and queue recovery. Summarize seed-level medians and interquartile ranges.
4. **Decision:** Profile the separate 10×10, 30-ambulance fixture over five seeds. Limit presentation claims to the tested scenarios and simulation assumptions.

**Fact:** [The evaluation design](METRICS_AND_EVALUATION.md) defines the scenario matrix, recovery criterion and presentation rules.

**Fact:** The database-free Java benchmark runner implements all seven scenario schedules and the separate scale fixture. The reporting scripts retain individual missions and aggregate paired seed results. See [execution commands and output definitions](../scenarios/BENCHMARKS.md).

**Fact:** The [M5 results](M5_RESULTS.md) record all 1,015 runs at engine revision `32147e0`. The [compressed TSV](../scenarios/m5-32147e0.tsv.gz) contains the run and mission records used for the report.

## M6 — Emergency108 hospital-leg test handoff

**Fact:** The opt-in Control Room demo replays the source-shaped pickup fields, creates a pending handoff, and runs explicit police authorization through the normal command queue. Assignment identity, replacement, and interrupted-run state are tested against the PostgreSQL application. The simulator remains independent of the Emergency108 backend. [Contract and walkthrough](EMERGENCY108_INTEGRATION.md)
