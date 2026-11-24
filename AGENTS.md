# GeoPulse agent rules

- **Decision:** This is a design-led project. Read docs/PRD.md, docs/DECISIONS.md, docs/OPEN_QUESTIONS.md, and the approved milestone before changing application code. M1 through M3 are verified. User instructions can explicitly change phase gates.
- **Decision:** Work one approved milestone at a time. Write meaningful engine tests first, verify working steps, and commit them during the authorized build phase. Do not deploy or force-push without user authorization.
- **Decision:** Keep backend/engine pure Java: no Spring, persistence, transport DTOs, or wall-clock/network dependencies. Application owns command serialization, transactions, adapters, and publication; frontend displays server-authoritative state.
- **Decision:** Use PostgreSQL through Compose and Flyway, never substitute H2. Keep credentials out of source. Active world state stays in memory; unfinished runs become INTERRUPTED after restart.
- **Decision:** Preserve deterministic tick/ID order, information boundaries, conservation, one-unit ambulance transfers, and signal transition rules. Read the detailed algorithm/simulation/signal specs before editing these areas.
- **Decision:** Use projected-arrival routing for scenarios with a calibrated time-indexed profile. Backtracking, trained ML, distributed handoffs, and unrelated Emergency108 features are deferred.
- **Decision:** Label document statements Fact, Assumption, or Decision. Distinguish proposed milestone staging from approved final behavior. Surface contradictions rather than silently changing requirements.
- **Decision:** Follow docs/UI_UX.md for map modes, tokens, accessibility, and uncertainty states. No Google Maps services, Pygame, or required external tiles for the synthetic demo.
- **Decision:** Emergency108 integration is test-only and later. Never write simulated GPS positions or emergency completion back into its operational APIs.
- **Decision:** Keep the design explainable and avoid unrelated features, services, abstractions, or research claims. Use docs/METRICS_AND_EVALUATION.md for claims and fair comparisons.
