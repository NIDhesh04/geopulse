package in.geopulse.engine;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class JunctionServiceTest {
    private static final JunctionService.Movement EAST = new JunctionService.Movement("west", "east");
    private static final JunctionService.Movement NORTH = new JunctionService.Movement("west", "north");
    private static final JunctionService.Movement OTHER = new JunctionService.Movement("south", "east");
    private final JunctionService service = new JunctionService(List.of("west", "south"));
    private final Map<String, Double> room = Map.of("east", 2.0, "north", 2.0);
    private final Map<String, Double> rates = Map.of("west", 0.5, "south", 0.5);

    @Test
    void ambulanceWaitsBehindFractionalBatchAndEarnsWholeTransferAcrossTicks() {
        var queue = new JunctionService.Queue(0.5, true, 0.2);
        var first = service.step(service.initial(), 0, Map.of(EAST, queue), rates, room, null);
        assertEquals(0.5, first.civilianTransfers().get(EAST));
        assertNull(first.ambulanceTransfer());
        var front = Map.of(EAST, new JunctionService.Queue(0, true, 0.2));
        var next = service.step(first.state(), 1, front, rates, room, null);
        assertEquals(0.5, next.state().credit());
        assertNull(next.ambulanceTransfer());
        var last = service.step(next.state(), 2, front, rates, room, null);
        assertEquals(EAST, last.ambulanceTransfer());
        assertEquals(0, last.state().credit());
    }

    @Test
    void sharedApproachBudgetAndReceivingSpaceBoundCivilianService() {
        var queues = Map.of(EAST, new JunctionService.Queue(2, false, 0),
                NORTH, new JunctionService.Queue(2, false, 0));
        var result = service.step(service.initial(), 0, queues, rates,
                Map.of("east", 0.1, "north", 3.0), null);
        assertEquals(0.1, result.civilianTransfers().get(EAST), 1e-9);
        assertEquals(0.25, result.civilianTransfers().get(NORTH), 1e-9);
    }

    @Test
    void preemptionRespectsMinimumAndClearanceAndSkipsBlockedRequest() {
        var queues = Map.of(EAST, new JunctionService.Queue(4, false, 0),
                OTHER, new JunctionService.Queue(0, true, 0));
        var state = service.step(service.initial(), 0, queues, rates, room, null).state();
        var request = new JunctionService.Request(OTHER, 1);
        var blocked = service.step(state, 10, queues, rates, Map.of("east", 0.5), request);
        assertEquals("DOWNSTREAM_BLOCKED", blocked.priority());
        assertEquals(NormalSignal.Phase.GREEN, blocked.state().phase());
        assertEquals(NormalSignal.Phase.GREEN, service.step(state, 9, queues, rates, room, request).state().phase());
        state = service.step(state, 10, queues, rates, room, request).state();
        assertEquals(NormalSignal.Phase.AMBER, state.phase());
        state = service.step(state, 13, queues, rates, room, request).state();
        assertEquals(NormalSignal.Phase.ALL_RED, state.phase());
        var grant = service.step(state, 15, queues, rates, room, request);
        assertEquals("GRANTED", grant.priority());
        assertEquals(List.of(0, 1), service.permissions(grant.state()));
    }

    @Test
    void forecastUsesServiceRulesAndReportsFullReceivingRoadAsUnknown() {
        var queues = Map.of(EAST, new JunctionService.Queue(0.5, true, 0));
        assertEquals(3.0, service.forecast(service.initial(), 0, EAST, queues, rates, room, "LIVE").seconds());
        var blocked = service.forecast(service.initial(), 0, EAST, queues, rates, Map.of("east", 0.5), "LIVE");
        assertEquals("UNKNOWN", blocked.status());
    }
    @Test
    void emergencyLimitUsesOriginalGreenAndRecoveryPreservesOrdinaryCursor() {
        var queues = Map.of(EAST, new JunctionService.Queue(8, false, 0),
                OTHER, new JunctionService.Queue(8, false, 0));
        var state = service.step(service.initial(), 0, queues, rates, room, null).state();
        var request = new JunctionService.Request(EAST, 2);
        state = service.step(state, 29, queues, rates, room, request).state();
        assertEquals(request, state.grant());
        assertEquals(0, state.startedAt());
        state = service.step(state, 45, queues, rates, room, request).state();
        assertEquals(NormalSignal.Phase.AMBER, state.phase());
        assertTrue(state.recoveryPending());
        state = service.step(state, 48, queues, rates, room, request).state();
        state = service.step(state, 50, queues, rates, room, request).state();
        assertTrue(state.recoveryGreen());
        assertEquals(List.of(0, 1), service.permissions(state));
        state = service.step(state, 60, queues, rates, room, request).state();
        assertEquals(NormalSignal.Phase.AMBER, state.phase());
    }
    @Test
    void earlierRequestWaitsForCommittedGrantAndRecoveryClearance() {
        var controller = new JunctionService(List.of("a", "b", "c"));
        var a = new JunctionService.Movement("a", "out-a");
        var b = new JunctionService.Movement("b", "out-b");
        var c = new JunctionService.Movement("c", "out-c");
        var queues = Map.of(c, new JunctionService.Queue(3, false, 0));
        var rates = Map.of("a", 0.6, "b", 0.6, "c", 0.6);
        var room = Map.of("out-a", 2.0, "out-b", 2.0, "out-c", 2.0);
        var active = new JunctionService.Request(a, 1, "AMB-002", 20, 0);
        var contender = new JunctionService.Request(b, 1, "AMB-001", 4, 1);
        var state = controller.stepContended(controller.initial(), 0, queues, rates, room,
                List.of(active)).service().state();
        var updated = new JunctionService.Request(a, 1, "AMB-002", 23, 0);
        var contested = controller.stepContended(state, 5, queues, rates, room,
                List.of(contender, updated));
        assertEquals(Map.of("AMB-001", "REQUESTED", "AMB-002", "GRANTED"),
                contested.priorityByAmbulance());

        state = controller.stepContended(contested.service().state(), 6, queues, rates, room,
                List.of(contender)).service().state();
        assertEquals(NormalSignal.Phase.GREEN, state.phase());
        assertNull(state.grant());
        state = controller.stepContended(state, 10, queues, rates, room, List.of(contender)).service().state();
        assertEquals(NormalSignal.Phase.AMBER, state.phase());
        state = controller.stepContended(state, 13, queues, rates, room, List.of(contender)).service().state();
        assertEquals(NormalSignal.Phase.ALL_RED, state.phase());
        state = controller.stepContended(state, 15, queues, rates, room, List.of(contender)).service().state();
        assertTrue(state.recoveryGreen());
        assertEquals(List.of(0, 0, 1), controller.permissions(state));
        state = controller.stepContended(state, 25, queues, rates, room, List.of(contender)).service().state();
        state = controller.stepContended(state, 28, queues, rates, room, List.of(contender)).service().state();
        state = controller.stepContended(state, 30, queues, rates, room, List.of(contender)).service().state();
        assertEquals(contender, state.grant());
    }
}
