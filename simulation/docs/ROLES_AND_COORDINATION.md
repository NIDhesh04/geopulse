# Roles and coordination — approved Topic 6

**Fact:** Consolidated from user approvals on 2026-11-22. The application is a synthetic traffic-control simulation and decision-support prototype. These responsibilities do not establish real police authorization or operational signal connectivity.

## Role boundaries

| Role | Approved responsibility | Approved boundary |
|---|---|---|
| **Decision:** Police operator | Activate missions, inspect fleet/route explanations, report closures/reopenings, handle exceptions, suspend priority, and request retries | Cannot bypass transitions, storage limits, or ambulance queue positions |
| **Decision:** Routing system | Compute routes, explain selections, re-plan, and identify no-route outcomes | Cannot directly command green signals |
| **Decision:** Signal controller | Serve ordinary traffic, arbitrate requests, enforce transitions, and recover after interventions | Automatic and operator-originated requests remain subject to the same controller constraints |
| **Decision:** Driver view | Show route, ETA, next movement, signal status, and stop reasons; submit obstruction reports | Cannot authorize its own signal priority |
| **Decision:** Simulation operator | Select scenarios, inject physical effects, control playback, and inspect ground truth | Simulation controls and truth must be distinguished from operational reports and router-visible observations |

- **Decision:** One demonstrator may use all surfaces without separate authentication accounts initially. These are responsibility boundaries, not claims of authenticated access control.
- **Decision:** Do not include an unrestricted force-green bypass. Any later manual service-request feature must use controller rules; it is not automatically included by this document.

## Mission authorization and exceptions

- **Decision:** Police activate a mission and enable or disable its emergency priority. Routing and next-junction requests then run automatically; individual junction approvals are not required.
- **Decision:** Operator attention focuses on exceptions such as no route, downstream blockage, unsuccessful grants, and questionable information.
- **Decision:** Suspending an ambulance's priority cancels its emergency requests. The ambulance can continue under ordinary service if a feasible route exists. Suspension does not remove the ambulance or bypass signal transitions.
- **Decision:** Preserve Topic 5's equal-priority arbitration; operator supervision does not introduce an unapproved severity ranking.
- **Decision:** Priority suspension cancels entitlement to extension, not signal permissions abruptly. Honor minimum green and any clearance already in progress, then recover normally without timer resets; see ARCHITECTURE.md.

## Physical events, reports, and acknowledgements

- **Decision:** Incident injection changes physical simulation state. Operational reporting changes what the system knows. Alert acknowledgement records that the operator has seen the alert; it does not repair or clear the underlying condition.
- **Decision:** A reported reopening cannot physically remove a hidden obstruction. Reported information and simulated reality may disagree and must be distinguishable in the interface.
- **Decision:** Driver obstruction reports enter an operator review queue. They do not immediately become confirmed network-wide closures.
- **Decision:** Explicitly confirmed closure/reopening reports feed the routing information layer; physical effects continue to follow scenario events and simulation controls.
- **Decision:** Review outcomes are PENDING, CONFIRMED, and REJECTED. ARCHITECTURE.md defines idempotent command IDs, ordered event IDs, and restrictive reconciliation between confirmed reports and local observations. Topic 8 decides discrepancy presentation.

## Centralized multi-ambulance coordination

- **Decision:** Use one authoritative backend for the simulated region. Each junction has one authoritative signal controller; competing ambulance requests are arbitrated there using SIGNALS.md.
- **Decision:** Police views observe the same committed state. Clients cannot independently grant conflicting signal permissions.
- **Decision:** Zones initially provide optional administrative labels and UI filters. Crossing a zone boundary does not restart a mission, transfer signal ownership, or invoke a handoff protocol.
- **Decision:** Independent zone authorities, disconnected zone operation, and jurisdictional handoffs are later extensions. Multi-ambulance operation does not require multiple backend services.

## Required checks

- **Decision:** Verify that mission authorization enables automatic requests, priority suspension removes requests while preserving ordinary travel, and no client action bypasses controller transitions/capacity.
- **Decision:** Verify that report submission/review, physical incident injection, and alert acknowledgement have distinct effects.
- **Decision:** Verify that acknowledging an alert does not remove its cause and reporting reopening does not remove an actual obstruction.
- **Decision:** Verify that driver reports await review, concurrent views receive the same committed signal state, and zone crossings do not change route/ownership behavior.

## Topic 7 handoff

- **Decision:** ARCHITECTURE.md specifies the approved stack, module boundaries, deterministic processing, transport, PostgreSQL/Flyway persistence, and repository layout.
- **Decision:** Keep the headless deterministic engine and swappable routing/estimate providers required by the approved algorithm and world model. Architecture must preserve the five responsibilities above even if several live in one process.
