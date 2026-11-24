# GeoPulse product brief

**Fact:** Consolidates approved Topics 1–10 as of 2026-11-23. Detailed behavior lives in the linked design documents; milestone scope is separately approved.

## Problem and claim

- **Decision:** Build a synthetic traffic-control platform combining ordinary signal management with emergency routing through the professor's hybrid algorithm and CoSiCoSt-inspired queue-service principles.
- **Decision:** The contribution is an explainable police/driver workflow plus reproducible evaluation. Do not claim CoSiCoSt replacement, new invention of Dijkstra, or proven real-world traffic improvement.
- **Decision:** Prioritize a polished usable product, with traffic effectiveness evaluated honestly. Keep explanations simple even when benchmark execution is extensive.

## Users and experience

- **Decision:** Police operators supervise authorized missions and exceptions. Drivers see navigation and report obstructions. Simulation operators control scenarios and physical incidents. One demonstrator can use these roles without auth accounts initially.
- **Decision:** Deliver a map-centered police interface, responsive driver view, concise landing page, and scenario selector. Operational information, ambulance routing snapshots, and Simulation Truth remain distinct.
- **Decision:** Use the approved graphite/cyan/purple design and MapLibre synthetic map by default. Generated imagery is restricted to presentation/scenario surfaces. No Pygame.

## Product target and staged delivery

- **Decision:** The complete project supports multiple ambulances with centralized conflict handling; a single-ambulance first milestone is a delivery step, not the final product boundary.
- **Decision:** Model ordinary traffic as fractional travelling cohorts and ordered movement queues, with finite storage, conservation, and boundary backlogs. Model ambulances individually and indivisibly.
- **Decision:** Implement the configurable live/predicted routing loop, incident reporting, bounded signal service/preemption/recovery, fleet supervision, and component-based outcome metrics.
- **Decision:** Java pure engine + Spring Boot application + React/TypeScript; PostgreSQL via Docker Compose and Flyway. One authoritative execution loop per run; HTTP commands and STOMP updates.
- **Decision:** Keep future Emergency108 integration separate and test-only initially, hospital leg first. No duplicate dispatch/patient lifecycle system.

## Non-goals and deferred work

- **Decision:** No real signal hardware, real traffic data requirement, paid/Google Maps services, civilian app, individual civilian driver physics, Pygame, or unqualified real-world accuracy claims.
- **Decision:** Defer backtracking, arrival-time/time-dependent routing variants, trained ML, greedy/blended variants, distributed zone control/handoffs, authenticated role accounts, and replay scrubber unless explicitly reintroduced.
- **Decision:** Do not add patient contacts, first aid, triage, hospital optimization, or other Emergency108 patient-side features.

## Success and review

- **Decision:** A reviewer can see why a route was chosen, how priority is requested and served, why an ambulance stops, and how ordinary traffic is affected.
- **Decision:** Measured claims report completion rates, paired ambulance time differences, and civilian delay/backlog/unfinished populations. UI demonstrations do not substitute for benchmark evidence.
- **Decision:** Engine tests verify deterministic behavior and conservation. Application tests verify commands, PostgreSQL/Flyway, commit-before-publication, and reconnect/restart semantics. UI checks cover visibility boundaries and responsive/accessibility behavior.
- **Fact:** The design index is ALGORITHM.md, SIMULATION.md, SIGNALS.md, ROLES_AND_COORDINATION.md, ARCHITECTURE.md, UI_UX.md, METRICS_AND_EVALUATION.md, and EMERGENCY108_INTEGRATION.md. RISKS.md records the final design review; M1 in MILESTONES.md is approved and implemented; later milestones remain proposals.
