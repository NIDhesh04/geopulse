# Decision log

**Fact:** This is a consolidated log of explicit conversation approvals, not an implementation history. Dates below are consolidation dates unless the original approval date is known. Detailed specifications take precedence over these short summaries.

| Date | Status | Decision | Reason / alternative |
|---|---|---|---|
| 2026-11-23 | **Decision: approved** | Traffic-control product with hybrid ambulance routing and CoSiCoSt-inspired support | Replaces a superiority/replacement pitch with an integrated application and measurable outcomes |
| 2026-11-23 | **Decision: approved** | Multi-ambulance final product; one ambulance first slice | Avoids limiting the product while keeping initial delivery testable |
| 2026-11-22 | **Decision: approved** | Base-graph horizons 0, 2, all; current-clock snapshots; travel-time costs | Faithful measurable baseline; arrival-time forecasts and backtracking deferred |
| 2026-11-22 | **Decision: approved** | Movement-aware Dijkstra and separate junction forecast | Incoming approach affects wait; simple outgoing-edge-only costs were insufficient |
| 2026-11-22 | **Decision: approved** | Aggregate traffic, 1-second deterministic simulation, finite queues/storage | Gives signals causal traffic effects without individual civilian physics |
| 2026-11-22 | **Decision: approved** | Bounded queue service, one approach at a time, constrained emergency priority | Explainable controller with explicit simplified intersection assumptions |
| 2026-11-22 | **Decision: approved** | Central authority with zone labels; role boundaries without auth initially | Multi-ambulance correctness without distributed handoff infrastructure |
| 2026-11-23 | **Decision: approved** | Pure Java engine, Spring Boot, React/TypeScript | User experience and single backend ownership; Python service unnecessary now |
| 2026-11-23 | **Decision: approved** | PostgreSQL/JSONB via Compose + Flyway | Explicit user correction replacing the H2 proposal |
| 2026-11-23 | **Decision: approved** | HTTP idempotent commands, STOMP snapshots/events, interrupted runs on restart | Clear ownership/recovery boundaries without pretending logs are full checkpoints |
| 2026-11-23 | **Decision: approved** | MapLibre, synthetic default, three information modes, approved UI tokens | Professional visual workflow while preserving routing information boundaries |
| 2026-11-23 | **Decision: approved** | Six paired configurations, seven scenarios, fixed windows and seed-level reporting | Separate information and priority effects; do not hide failed/unfinished traffic |
| 2026-11-23 | **Decision: approved** | Emergency108 test hospital-leg adapter only | Reuse dispatch ownership without writing simulated positions/completion into operations |
| 2026-11-23 | **Decision: approved M1 staging** | M1 uses explicit routing-only no-signal fixtures; M2 adds approved queues/signals | Keeps the first slice manageable; M1 approved 2026-11-23, not a revision of final product behavior |

- **Decision:** Phase gates from the original brief remain: design, milestone planning, then one approved build milestone at a time. New requests can explicitly change these gates. M1 implementation was authorized on 2026-11-23.
