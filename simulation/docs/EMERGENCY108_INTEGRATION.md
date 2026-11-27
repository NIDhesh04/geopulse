# Emergency108 integration — approved Topic 10

**Fact:** The test adapter was checked against Emergency108 revision `3dd116a5a59ab32716682be20077c03777522c69`. The driver pickup transaction records the destination hospital on the existing assignment and sets the emergency to `TO_HOSPITAL`. The generated assignment row ID is the stable `assignmentRef`. Reassignment creates a different row. The pickup response contains the hospital details, and the existing assignment events carry emergency and ambulance IDs. A live producer would need to send the full handoff after the pickup transaction commits. [Pickup transaction](https://github.com/anupamkushwaha85/emergency-dispatch-system/blob/3dd116a5a59ab32716682be20077c03777522c69/src/main/java/com/emergency/emergency108/controller/DriverController.java#L246-L324) · [Assignment identity](https://github.com/anupamkushwaha85/emergency-dispatch-system/blob/3dd116a5a59ab32716682be20077c03777522c69/src/main/java/com/emergency/emergency108/entity/EmergencyAssignment.java#L12-L63)

## Ownership

- **Decision:** Emergency108 owns emergency creation, dispatch selection, driver acceptance/reassignment, patient pickup, and authoritative emergency completion.
- **Decision:** GeoPulse owns simulated route planning/explanations, traffic priority, signal simulation, and measured traffic impact. It does not replace Emergency108's emergency state machine.
- **Decision:** Begin with the hospital-bound leg. Include journeyLeg in the handoff so pickup routing can be added later; unsupported legs are rejected explicitly rather than interpreted as hospital transport.
- **Decision:** Keep integration test-only initially, using explicit mappings from external references to a synthetic scenario's ambulance, departure entry, and hospital node. No automatic GPS map matching is required.

## Minimal adapter and handoff

- **Decision:** Put a small adapter in backend/application. It translates external identifiers and submits existing GeoPulse application commands. Keep backend/engine unchanged and independent of Emergency108 DTOs, MySQL entities, authentication, and transport.
- **Decision:** Handoff carries external emergency reference, assignmentRef, ambulance reference, journeyLeg, and destination reference. Associate the request with an explicitly selected run and scenario mapping; do not silently select a live run or infer coordinates.
- **Decision:** Preserve command IDs for transport retries and assignmentRef for assignment identity. The same mapped assignment/leg delivered twice must not create another mission. A different assignmentRef is a reassignment, not a duplicate.
- **Decision:** Create a pending mission awaiting police authorization. Handoff acceptance does not activate the ambulance or authorize signal priority. The activation-time journey clock begins only when the mission is authorized and activated successfully.
- **Decision:** Return read-only GeoPulse status: accepted/rejected and reason, mission/run identity, pending/active/arrival or stop status, estimated arrival with simulation timestamp, and relevant stop reason. Clearly identify all results as simulated.
- **Decision:** Reuse the existing accepted/applied command pattern. Do not let an adapter mutate engine state directly or bypass signal/queue constraints.

## Boundaries and failures

- **Decision:** Do not send simulated locations to Emergency108's driver-location channel. Do not invoke its arrive/complete-mission APIs because a simulated ambulance reached a destination.
- **Decision:** Keep GeoPulse status in a separate test-integration view/response. Emergency108 retains its own checks for physical hospital arrival and completion.
- **Decision:** Keep GeoPulse's persist-before-publish and INTERRUPTED-on-restart policies. Do not copy Emergency108's described non-blocking audit or automatic emergency-recovery behavior into simulation runs.
- **Decision:** Missing/ambiguous scenario mappings are explicit validation failures; they must not spawn at arbitrary nodes.
- **Assumption (integration milestone):** Inspect actual Emergency108 assignment identity, payloads, post-acceptance/post-pickup hook, auth, and retry semantics before wiring. Verify how reassignment invalidates a pending or active GeoPulse handoff without deleting an ambulance mid-road. This lifecycle detail is not authorized as a production write-back.
- **Assumption (integration milestone):** Select the test adapter endpoint and response/event mechanism after inspecting the source. Do not claim the currently described Emergency108 endpoints already implement this contract.

## Acceptance for the later integration milestone

- **Decision:** Test one mapped hospital-leg handoff; pending authorization; duplicate delivery; changed assignment; missing mapping; unsupported leg; stale/interrupted run; and read-only status after simulated arrival.
- **Decision:** Verify no simulated location/completion writes reach Emergency108, no engine dependency is added, and both projects' independent lifecycle rules remain intact.

## Local M6 walkthrough

**Fact:** The endpoint is opt-in and the normal backend still binds to loopback. For the test preview start the application with `--geopulse.emergency108.test-enabled=true`. Select **Ten ambulance conflict**, create a run, and choose **Replay sample pickup**. **Authorize hospital leg** applies the queued command and starts the mission clock. Use Play to advance the simulator.

**Decision:** The local fixture maps external ambulance IDs 301 and 302 to AMB-001 and AMB-008, and external hospital ID 501 to `n04_04`. These are test identifiers. The upstream backend and deployed services are outside the local replay.

**Fact:** Test clients may submit a normalized pickup using `POST /api/test-integrations/emergency108/runs/{runId}/handoffs`.

```json
{
  "commandId": "baa74299-612a-465c-88e0-e56935f39f02",
  "handoff": {
    "assignmentRef": 7001,
    "emergencyRef": 410,
    "ambulanceRef": 301,
    "destinationRef": 501,
    "journeyLeg": "TO_HOSPITAL",
    "emergencyStatus": "TO_HOSPITAL",
    "assignmentStatus": "ACCEPTED"
  }
}
```

**Fact:** Poll the existing command endpoint until its outcome is final. Fetch the read-only simulated handoff state at `GET …/handoffs/7001`. The police action uses `POST …/handoffs/7001/authorize` with a fresh `commandId`. Keep the same command ID for a transport retry. Replaying a previously accepted assignment with a different command ID still preserves the original mission.

**Decision:** A newer source assignment can supersede a pending assignment or an authorized one with a different available simulated ambulance. If the previous ambulance is already active, it retains its physical state and its priority is suspended. A replacement must still be separately authorized. After restart an unfinished run is reported as interrupted and requires a new simulation run.
