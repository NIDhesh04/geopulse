# GeoPulse

**Fact:** M1 is a routing-only demonstration: one ambulance, a synthetic 5×5 network, current-clock hybrid routing, explainable decisions, and durable command/event history. Signals, background traffic, ambulance priority and multi-ambulance contention belong to later milestones.

## Open and edit the project

**Fact:** The active checkout is `/home/nidhesh/projects/geopulse2.0` in WSL. Open that folder in your editor (for VS Code, run `code .` there). The earlier OneDrive folder is not the active checkout.

| Folder | Purpose |
|---|---|
| `backend/engine` | Framework-independent Java graph, estimators, routing and fixed-step simulation |
| `backend/application` | Spring Boot HTTP/STOMP, execution queues, JDBC and Flyway |
| `frontend/src` | React control room, MapLibre map and server-state reconciliation |
| `frontend/src/tokens.css` | Shared visual colors |
| `scenarios` | Description of the initial routing fixture |
| `docs` | Approved design, milestone scope and deferred questions |

## Prerequisites

**Decision:** Use JDK 21, Docker Desktop with WSL integration, and Node **22.12 or later** with npm 11. Maven 3.9.12 is pinned by the included wrapper. `frontend/.nvmrc` selects Node 22 if you use nvm. First builds need internet access; the synthetic map uses no external tiles or map keys.

## Start locally

**Decision:** Run these commands from the project root in WSL. On the first setup only, copy the environment example and set a nonempty local PostgreSQL password in `.env`. Never commit that file. If `.env` already exists, keep it.

```bash
cp -n .env.example .env
# Edit .env and set POSTGRES_PASSWORD before starting Compose.
docker compose up -d --wait
./backend/mvnw -f backend/pom.xml verify
java -jar backend/application/target/application-0.1.0-SNAPSHOT.jar
```

**Decision:** In another terminal, from the same project root:

```bash
npm --prefix frontend ci
npm --prefix frontend run dev
```

**Fact:** Open http://localhost:5173. The backend listens on `127.0.0.1:8080`, and PostgreSQL on `127.0.0.1:5433`. Vite proxies HTTP and WebSocket requests. Stop frontend/backend with Ctrl+C; `docker compose stop` stops the database while preserving its named volume.

**Fact:** Backend startup runs Flyway and marks unfinished persisted runs `INTERRUPTED`. It does not resume an in-memory world. Create a new run after restarting. Event history and last saved ambulance results remain inspectable.

## First demonstration

1. Choose **Hybrid · 2 hops**, create a run, then activate the mission.
2. Inspect **Why this turn?** and expand a candidate. Road and junction costs are separate; `M1_ZERO_WAIT` is explicitly identified.
3. Use **Step 1s**, then Play/Pause and playback speed. All motion is backend-authoritative.
4. While paused at departure, close the selected first road with reporting enabled. The alternative becomes the route. Close both outgoing roads to produce an operator alert.
5. Restore a road with reporting enabled to recover. A fully impassable occupied road stops the ambulance in place; restoring it resumes motion. An entry closure does not eject an ambulance already on the road.
6. Reload the browser to restore the snapshot and ordered events. Select a different horizon only when creating a new run.

## Verify

```bash
# Pure Java tests, without Docker or Spring
./backend/mvnw -f backend/pom.xml -pl engine test
# Full backend including real PostgreSQL Testcontainers tests
./backend/mvnw -f backend/pom.xml verify
npm --prefix frontend test
npm --prefix frontend run build
# Optional browser walkthrough, with backend/frontend running
npm --prefix frontend run test:e2e
```

**Decision:** The browser suite needs its Chromium installation (`cd frontend && npx playwright install chromium`). Testcontainers requires Docker and uses the same PostgreSQL 18 image as Compose. Never replace it with an in-memory database to claim persistence verification.

## Inspect the database

```bash
docker compose exec postgres psql -U geopulse -d geopulse
```

```sql
SELECT id, status, simulation_time, revision FROM simulation_run;
SELECT type, status, applied_tick, boundary_ordinal, reason
FROM run_command ORDER BY created_at;
SELECT run_id, sequence, tick, type, payload FROM run_event
ORDER BY run_id, sequence;
```

## M1 boundaries

- **Decision:** `JunctionDelayEstimator` is the movement-aware interface. `M1ZeroJunctionDelay` is a deliberate fixture stub, never a fallback for failed forecasts. The simulator accepts an injected estimator; Dijkstra does not need modification for M2's bounded forecast.
- **Fact:** The historical M1 profile is constant free-flow travel time. Calibrated time-of-day profiles and traffic-driven congestion arrive with the world model; M1 demonstrates the information boundary only.
- **Fact:** The fixture includes discrete road-entry boundaries. An ambulance enters at a tick boundary and begins progress on the next tick. Consequently the unobstructed 800 m route estimates 80 seconds of traversal but completes in 88 simulation seconds. Actual time starts at activation; these are deliberately separate measurements.
- **Fact:** Scenario JSON currently describes the single built-in fixture. It is not a general importer. Optional node latitude/longitude fields are supported; default map coordinates are synthetic display coordinates, not real roads.
- **Decision:** HTTP command acceptance is durable before enqueueing. Each boundary computes an isolated candidate, commits results/events, then exposes it. Publication failure is repaired by HTTP catch-up; database failure stops that run at its last committed state.
- **Decision:** M1 is a local development demo with no authentication or real traffic control. No CoSiCoSt effectiveness comparison is claimed. Read `docs/MILESTONES.md` before extending scope.
