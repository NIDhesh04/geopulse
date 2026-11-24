# Architecture — Topic 7

**Fact:** Consolidates approved stack/transport choices and the user's PostgreSQL correction, plus execution details resolved under the request to close Topic 7, on 2026-11-22. Application implementation has not begun.

## Stack, modules, and ownership

- **Decision:** Use Java/Spring Boot with a framework-independent pure Java engine, and React/TypeScript with server-authoritative state and client-side animation interpolation.
- **Decision:** Use a Maven multi-module backend: `backend/engine` and `backend/application`. Other top-level areas are `frontend`, `scenarios`, and `docs`. The root Docker Compose configuration starts PostgreSQL for local development; deployment packaging is later work.
- **Decision:** The engine owns graph/world state, cohorts, ambulances, deterministic clock, routing, forecasts, and signal policy. It imports no Spring, persistence entities, HTTP/STOMP DTOs, or database libraries.
- **Decision:** The application owns run execution, command admission, report review, HTTP/STOMP adapters, database transactions, and publication. Dependency direction is application -> engine only.
- **Decision:** One authoritative execution loop and command queue own each run. HTTP/WebSocket handlers never mutate engine state. Start with one active run supported by the demo application; run IDs and per-run ownership isolate later concurrent runs. This does not limit the number of ambulances in a run.
- **Decision:** Keep focused interfaces for road weight providers, movement-aware routing, junction forecasting, signal service, and clock advancement. Avoid per-class interfaces without a replaceable responsibility.
- **Decision:** Keep GeoPulse standalone initially. Emergency108 integration remains a later contract/integration topic, not a source-code dependency.

## HTTP commands and query contracts

| Contract | Purpose |
|---|---|
| **Decision:** GET /api/scenarios | List scenario definitions/versions |
| **Decision:** POST /api/runs | Create a paused run from a scenario version and seed |
| **Decision:** GET /api/runs/{id}/snapshot | Latest committed dynamic view |
| **Decision:** POST /api/runs/{id}/commands | Submit an idempotent user action |
| **Decision:** GET /api/runs/{id}/commands/{commandId} | Query command outcome |
| **Decision:** GET /api/runs/{id}/events?after=... | Recover ordered events, paginated with a continuation cursor |
| **Decision:** GET /api/runs/{id}/results | Measurements and completion/interruption status |
| **Decision:** GET /api/runs/{id}/ambulances/{ambulanceId}/route-explanation | Latest committed route explanation, with decision revision/time |

- **Decision:** Command envelopes contain run ID, client-generated command ID, type, and payload. Demonstration-role metadata is audit context, not authentication.
- **Decision:** Supported action families are playback/step, mission activation/priority suspension, physical incident injection, report submission/review, alert acknowledgement, and routing retry. Do not add unrestricted signal writes.
- **Decision:** Validate syntax, persist acceptance, and enqueue. HTTP 202 means ACCEPTED, not APPLIED. Apply state-dependent validation in execution order; outcomes are APPLIED or REJECTED with a reason.
- **Decision:** Command ID is unique within a run. Duplicate identical content returns the existing outcome without reapplying. A different payload using the same ID returns conflict. Compare parsed canonical content, not JSON whitespace or property order.
- **Decision:** Serialize acceptance per run to assign a monotonically increasing durable sequence. Queue order follows that sequence, not thread scheduling or browser timestamps. The queue is an application delivery mechanism; persistence remains the accepted-command record.
- **Decision:** Record actual application tick and boundary ordinal. Commands received after a boundary's cutoff apply at a later boundary. Capture a finite cutoff so a continuous command stream cannot indefinitely postpone stepping.
- **Decision:** Paused runs still process queued commands without advancing simulation time. STEP requires paused mode and advances exactly one tick. PAUSE takes effect at the next boundary; do not interrupt an in-progress tick. A control command that changes advancement (PLAY, PAUSE, STEP) ends the current command batch, making later control commands apply at the next boundary in sequence.
- **Decision:** Starting a scenario again creates a new run ID. Failed state-dependent commands remain in history with their rejection reason.

## Deterministic boundary execution

1. **Decision:** At tick t, apply due physical/reporting scenario events, ordered by stable event ID; then apply the cutoff batch of commands by acceptance sequence. A scheduled event at t executes only once even if the run remains paused at t. Later commands at that same tick may explicitly change its state.
2. **Decision:** Refresh permitted observations and process cancelled/invalid requests. Freeze routing inputs from this state and the already-established signal state, timers, and committed grants. Expired timers are visible as expired; forecasting can transition them using established policy.
3. **Decision:** Evaluate all due routes in stable ambulance-ID order against that frozen information version. Install route results, update queue membership where necessary, and invalidate obsolete route-version requests. A candidate forecast never creates a priority request.
4. **Decision:** Evaluate next-junction request triggers from the selected routes. Update the request set and arbitrate signal transitions once. This tick's new grants do not feed back into this tick's route search. They become established inputs at the next routing snapshot.
5. **Decision:** If time advancement is authorized, calculate one second of movement, receiving allocation, and metrics from the beginning-of-movement state; commit transfers simultaneously. New entrants/newly queued cohorts follow next-step eligibility. Then advance time to t+1. Paused boundaries do not earn service credits or consume green/clearance time.
6. **Decision:** Persist boundary command outcomes, domain events, required metric samples, and run revision atomically before installing/publishing the new committed state.

- **Decision:** Prepare an isolated candidate state for a boundary. On database failure, do not expose that candidate or advance the committed world. Stop processing the run, expose a persistence-fault condition, and require recovery/restart handling; do not claim unsaved work succeeded.
- **Decision:** During pause, information refresh/routes/request selection may change at a boundary, but physical service and time do not advance. Record these same-tick boundaries explicitly for reproducibility.
- **Decision:** Cache forecasts within each frozen routing snapshot using all relevant context: incoming/outgoing movement, ambulance position, visible/estimated state, provider/profile version, clock, policy/timers/grants, and horizon. Forecasts use isolated estimated state and call signal-service primitives, not live command processing or the priority-trigger estimator recursively.
- **Decision:** Retry no-route ambulances once per advancing boundary when the information snapshot changes, and on explicit operator retry or a relevant report/closure/route-context change while paused. Do not busy-loop unchanged paused snapshots. Coalesce simultaneous retry reasons per ambulance.

## Execution clarifications from Topics 5 and 6

- **Decision:** Preserve the 10-second minimum green during recovery. 'Up to 10 seconds' means skip an ineligible recovery opportunity before it starts, or serve exactly 10 seconds once started. If it empties/becomes blocked after starting, it provides no transfers but does not shorten the minimum. End via normal amber/all-red.
- **Decision:** Priority suspension removes requests immediately at the boundary. It cancels entitlement to an emergency extension, not existing signal permissions abruptly. After required minimum green, transition into recovery/ordinary selection; clearance already in progress finishes without restart. No new timing credit is introduced.
- **Decision:** If a waiting ambulance changes outgoing movement, remove its old queue entry and append it to the new movement queue; clear service credit. Preserve its junction arrival time for request arbitration, but do not transfer its former queue position to bypass traffic. Unchanged movements retain position.
- **Decision:** For whole-slot allocation, use the same arrival/request/ID ordering for contenders. A contender without an active request uses its actual junction arrival time and movement-queue entry sequence in place of request creation order. This is capacity arbitration only and does not create a signal-priority grant.
- **Decision:** Head-of-queue civilian batches or ambulance credit deficits request service; all requests share the incoming approach's discharge budget. Allocate the budget proportionally to eligible requested amounts, capped at each amount, with redistribution of excess in stable movement-ID order. Do not multiply one road's discharge rate by its number of outgoing movements.
- **Decision:** Allocate feasible whole receiving slots to service-ready ambulances first using deterministic ordering; civilians share remaining receiving space proportionally. Receiving space is still based on the start of the movement phase. Ambulatory service credit is earned only while permission exists and entry is feasible; previously earned credit may remain while the same green continues but never reserves receiving space.
- **Decision:** Departure-entry capacity and discharge rate are explicit positive scenario attributes. Reject activation when entry storage is full with a clear reason; do not silently spawn outside capacity. A rejected activation does not start a journey clock. The default fixture values are selected with scenario fixtures.
- **Decision:** Estimate priority queue-clearance time as civilian equivalents/ambulances ahead divided by estimated effective movement discharge rate. This estimate excludes red/clearance waits; the separate 15-second trigger allowance covers preparation. It does not call the full waiting forecast. A nonpositive/unavailable effective rate yields unknown. While still approaching, an unknown clearance estimate does not create an advance grant; surface the estimation warning. An authorized ambulance physically waiting at the junction may submit a pending request regardless, still subject to receiving-space eligibility.
- **Decision:** Forecast downstream occupancy with permitted current/expected occupancy and frozen estimated arrivals/releases, clamped to physical storage. For the baseline use historical per-road arrival/release rates from incident-free calibration, modified by locally observed or explicitly reported restrictions. These are estimates, never reads of hidden future engine state. Scenario validation requires forecast profiles for all used road classes/movements.
- **Decision:** Report review outcomes are CONFIRMED and REJECTED, following PENDING. Confirmation changes operational knowledge only. A confirmed closure persists until explicit reopening; a report of reopening removes that reported restriction but cannot override a fresh local observation of physical blockage. Surface discrepancies. Acknowledgement never changes physical or routing availability.

## State and live-update contracts

- **Decision:** Use HTTP for commands and STOMP over WebSocket with Spring's built-in broker for publication. No external message broker is required initially. WebSocket endpoint is /ws; channels are /topic/runs/{id}/state and /topic/runs/{id}/events.
- **Decision:** A state envelope contains schemaVersion, runId, stateRevision, simulationTimeSeconds, playback/run status, latestEventSequence, and complete dynamic view data. Static geometry comes from versioned scenario data, not every update.
- **Decision:** Publish state at most five times per wall-clock second; coalesce obsolete states without skipping engine ticks. Publish command/event outcomes separately after commit. Persisted event sequence, not WebSocket delivery, establishes history.
- **Decision:** Treat stateRevision as monotonic even for same-tick paused changes. Event sequences are monotonic per run. Encode potentially large revision/sequence integers as decimal strings in JSON to avoid JavaScript integer precision loss.
- **Decision:** On connect/reconnect subscribe and buffer, fetch current state, then discard buffered states no newer than the fetched revision. Continue accepting newer full states; query missing event pages and deduplicate by event sequence. A lower revision can never overwrite a newer view.
- **Decision:** The in-memory broker is not a durable event queue. Periodic state envelopes expose the latest event sequence; clients reconcile missing events over HTTP. While paused, send a lightweight current-state heartbeat every two wall-clock seconds so silent gaps can be detected. Backpressure may replace queued state messages with newer states; event recovery uses persistence.
- **Decision:** Frontend interpolates between confirmed positions only. Never infer an unconfirmed junction crossing. On disconnect/stale updates, stop extrapolating and show the last confirmed state with a connection indicator.
- **Decision:** Route explanations carry the routing snapshot revision, time, cost sources, fallbacks, and unknown/blockage reasons; they may be older than current physical state and must be labeled accordingly.
- **Decision:** Engine estimate results distinguish available seconds, known blocked, and unknown (including horizon exceeded). Transport never emits JSON Infinity or NaN; use explicit status/reason with an absent/null numeric estimate.
- **Decision:** Use integer simulation ticks and stable ID ordering. Use Java double for fractional counts, speed, and estimated costs with deterministic iteration order and a documented 1e-9 vehicle-equivalent tolerance for numerical invariant checks. Only normalize tiny residuals within tolerance, never hide substantial conservation errors. Determinism is scoped to the pinned engine/runtime/configuration, not promised across arbitrary future versions.

## PostgreSQL and migrations

- **Decision:** Use PostgreSQL through Docker Compose from the start. H2 is superseded and must not be used as an application or integration-test substitute. Keep active world state in memory and backend/engine database-free.
- **Decision:** Use Flyway versioned SQL migrations as the single schema owner. No Hibernate schema creation/update or parallel ad-hoc initialization path. Choose exact compatible supported Java/Spring/PostgreSQL/Flyway versions at milestone planning and pin them; do not use floating latest tags.
- **Decision:** Persist run metadata; immutable scenario/configuration snapshots and seed; engine/profile/schema versions; commands/outcomes; ordered domain events; reports/acknowledgements; periodic metrics; and final/interrupted results.
- **Decision:** Keep identifiers, run status, command type/status, ordering, simulation ticks, and timestamps in typed relational columns with constraints. Store versioned structured scenario/command/event/metric payloads as JSONB. Do not bury uniqueness or ordering exclusively in JSON.
- **Decision:** Enforce unique (run_id, command_id), (run_id, acceptance_sequence), and (run_id, event_sequence), with foreign keys to runs and ordered-read indexes. Add JSONB indexes only for actual queried fields; JSONB availability does not require blanket indexing.
- **Decision:** Record dashboard metric samples every five simulation seconds and on run termination, plus exact event-triggered measurements. Engine counters update each tick. Benchmark recovery additionally retains one-second aggregate queue measurements to evaluate its 60-consecutive-second condition. Do not persist every cohort position/animation frame.
- **Decision:** Compose uses a named data volume and a database health check. Credentials are local environment configuration, never committed values. Provide a documented psql/GUI connection for inspection during implementation. Application startup requires database availability and successful migrations.
- **Decision:** Persist accepted commands before returning 202. Boundary outcomes/events/metrics/revision commit atomically before publication. Event payloads and the scenario definition are immutable historical records; corrections append new actions rather than rewriting history.
- **Decision:** On backend restart, unfinished runs become INTERRUPTED; accepted-but-unapplied commands become REJECTED with RUN_INTERRUPTED. Never silently replay them into a new world. Completed/interrupted records remain queryable. Creating another run from the same scenario is explicit.
- **Decision:** Exact checkpoint resume and replay scrubber remain deferred. Persisted events alone are not advertised as complete state recovery. After a crash, live snapshot endpoints for interrupted runs report snapshot unavailable rather than manufacture engine state.
- **Fact:** PostgreSQL provides JSONB storage and indexing; Spring Boot supports Flyway initialization with PostgreSQL-specific support. References: [PostgreSQL JSON types](https://www.postgresql.org/docs/current/datatype-json.html), [Spring Boot database initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html).

## Tests and remaining design work

- **Decision:** Engine tests run without Spring, Docker, or databases. Application integration tests run against real PostgreSQL with the same Flyway migrations, including JSONB and transaction/constraint behavior.
- **Decision:** Verify command retries/conflicts, concurrent acceptance ordering, boundary cutoffs, paused changes, exact single-step, route/grant snapshot isolation, cancellation/recovery, queue switching, and insufficient service/receiving capacity.
- **Decision:** Verify uncached/cached forecast equivalence and no future-state leakage; ensure every route candidate uses established policy rather than its own potential grant.
- **Decision:** Verify publish-after-commit, failed persistence retaining last committed state, restart interruption, missed/duplicate/out-of-order live messages, paused heartbeats, and event catch-up.
- **Decision:** Verify identical headless versus web-driven engine results given the same applied commands/ticks, independent of playback pacing. Test that roles/reporting cannot mutate physical incidents accidentally.
- **Assumption (remaining design):** Scenario numeric fixtures, exact dependency versions, concrete UI adapters/assets and performance targets are finalized during milestone planning. UI behavior and metric comparison protocols are now specified in UI_UX.md and METRICS_AND_EVALUATION.md. The architecture fixes ownership and sequencing without inventing those scenario values.
