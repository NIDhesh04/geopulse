# Design risk review

**Fact:** Reviewed on 2026-11-23 to close the remaining risks topic before milestone approval. Controls below restate approved boundaries or identify work that must be verified; no new product features are added.

| Risk | Existing control / validation |
|---|---|
| **Fact:** Synthetic speed, fractional queues, and one-approach signal service simplify real traffic | **Decision:** State the homogeneous-model limits; report simulation evidence only |
| **Fact:** Per-route 300-second forecasts may dominate runtime | **Decision:** Cache complete identical snapshot inputs, profile headlessly, and measure the 30-ambulance case before claiming playback/scale performance |
| **Fact:** A forecast horizon can exclude a route that would eventually become usable | **Decision:** Show unknown/horizon-exceeded separately from blockage and include completion/failure outcomes |
| **Fact:** Shared truth state can accidentally leak into routing or operational UI | **Decision:** Enforce explicit projections/provider inputs and test hidden incidents and historical forecasts |
| **Fact:** Fractional flow plus indivisible ambulances introduces allocation edge cases | **Decision:** Test conservation, whole-slot allocation, service credits, queue movement changes, and downstream saturation before broad UI integration |
| **Fact:** Finite windows and successful-only statistics can make bad policies appear good | **Decision:** Use common windows, boundary backlogs, partial-progress delay, and full completion/unfinished counts |
| **Fact:** A large feature list can delay the first useful demonstration | **Decision:** Build one milestone at a time; benchmarks, generated art, and integration do not block the first route demo |
| **Fact:** External tiles and integration services can make a live demo fragile | **Decision:** Synthetic map works locally; Emergency108 remains optional and test-only |
| **Fact:** Existing Emergency108 descriptions do not establish exact API/event compatibility | **Decision:** Inspect its code before wiring; keep ownership and simulated outputs separate |

## Readiness findings

- **Fact:** The project currently contains design documents only; no engine, frontend, database schema, or infrastructure has been implemented or tested.
- **Fact:** On inspection of this WSL environment, Java and Maven were unavailable; Node 20.20.0 and npm 10.8.2 were present; the Docker Desktop command reported that WSL integration was unavailable. This is an environment setup requirement, not a reason to replace PostgreSQL with H2.
- **Decision:** Resolve environment readiness in the approved scaffold step, then verify actual builds/tests. Do not claim test success from document checks.
- **Assumption:** The initial 5x5 fixture and one ambulance should be a manageable validation target, but no runtime measurement exists yet.
