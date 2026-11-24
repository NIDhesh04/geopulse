# Milestones — M1 approved

**Fact:** Prepared on 2026-11-23 after consolidation of Topics 1–10 and the design risk review. M1 was explicitly approved by the user on 2026-11-23; later milestones remain proposals. Original phase names are Phase 1 Design, Phase 2 Plan, Phase 3 Build.

## Delivery approach

- **Decision:** Preserve the complete multi-ambulance design, build one milestone at a time, write engine tests first, and commit working steps once implementation is authorized.
- **Assumption (proposal):** Use the milestones below to keep each demonstration understandable. Detailed later-milestone acceptance is refined before its implementation, without reopening approved product boundaries unnecessarily.

| Milestone | Demonstrable result | Acceptance and test focus | Deliberately deferred |
|---|---|---|---|
| **Decision: M1 approved** | One ambulance follows explainable hybrid routes on a synthetic map | Scaffold builds; real PostgreSQL/Flyway; deterministic routing; HTTP/STOMP controls and event history; no-signal fixture explicitly identified | Background flow, production junction forecasts, priority, multi-ambulance contention, polished driver screen |
| **Assumption: M2** | Ordinary traffic queues and signals affect a single ambulance | Conservation/storage/credits; signal timings and clearance; reported versus physical incidents; bounded forecasts; actual delays | Multi-ambulance conflict workflow and full benchmark suite |
| **Assumption: M3** | Multiple ambulances share junctions correctly | 10-ambulance contention, deterministic ordering, active-grant commitment, suspension and recovery; fleet/driver state isolation | 30-ambulance performance claim and external integration |
| **Assumption: M4** | Complete polished control-room/driver product | Approved information modes, inspectors, report review, ETA states, responsive/keyboard behavior, local synthetic map, concise landing | Real operational deployment, individual civilian physics, auth expansion |
| **Assumption: M5** | Reproducible comparison report and scale results | Paired schedules/warm starts, seven scenarios, completion-aware delays, exact recovery, seed summaries, 30-ambulance profiling | Claims about CoSiCoSt superiority or real-world accuracy |
| **Assumption: M6** | Test Emergency108 hospital-leg handoff | Inspect real code; mapping/dedup/reassignment tests; pending police authorization; read-only simulated status | Real GPS ingestion/map matching, production completion writes, pickup-leg integration |

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
- **Decision:** This checkpoint remains the routing-only M1 fixture. It does not establish signal, civilian-flow, multi-ambulance or benchmark readiness. Later milestones remain unapproved.
