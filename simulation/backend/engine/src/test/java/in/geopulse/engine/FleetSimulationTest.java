package in.geopulse.engine;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class FleetSimulationTest {
    @Test
    void tenMissionsUseOneClockAndSharedSignalRecovery() {
        var run = RoutingSimulation.fleet(Graph.grid(5), 2, true);
        RoutingSimulation.fixtureOrigins().forEach((id, origin) -> run.activate(id, origin, "n04_04"));
        var replica = run.copy();
        boolean recovery = false;
        boolean contested = false;
        for (int tick = 0; tick < 360 && !run.completed(); tick++) {
            run.step();
            replica.step();
            recovery |= run.trafficState().signals().values().stream().anyMatch(TrafficWorld.SignalView::recoveryGreen);
            var selected = run.fleetView();
            contested |= selected.values().stream().anyMatch(m -> m.priority().equals("REQUESTED"))
                    && selected.values().stream().anyMatch(m -> m.priority().equals("GRANTED"));
        }
        assertEquals(10, run.fleetView().size());
        assertTrue(run.fleetView().values().stream().allMatch(m -> m.ambulance().arrivedAt() != null),
                () -> run.fleetView().values().stream().map(m -> m.ambulance().id() + ":" + m.ambulance().status()).toList().toString());
        assertTrue(recovery);
        assertTrue(contested);
        assertEquals(replica.fleetView(), run.fleetView());
        assertEquals(replica.trafficState(), run.trafficState());
    }

    @Test
    void passingGrantToFollowerDoesNotExtendTheEmergencyMaximum() {
        var controller = new JunctionService(List.of("station"));
        var turn = new JunctionService.Movement("station", "road");
        var first = new JunctionService.Request(turn, 1, "AMB-001", 0, 0);
        var second = new JunctionService.Request(turn, 1, "AMB-002", 0, 0);
        var rates = java.util.Map.of("station", 1.0);
        var room = java.util.Map.of("road", 4.0);
        var initial = controller.stepContended(controller.initial(), 0, java.util.Map.of(),
                rates, room, List.of(first, second)).service().state();
        var crossed = controller.stepContended(initial, 40,
                java.util.Map.of(turn, new JunctionService.Queue(0, "AMB-001", 0)),
                rates, room, List.of(first, second)).service();
        assertEquals(turn, crossed.crossings().get("AMB-001"));
        var following = controller.stepContended(crossed.state(), 41, java.util.Map.of(),
                rates, room, List.of(second)).service().state();
        assertEquals("AMB-002", following.grant().ambulanceId());
        assertEquals(0, following.startedAt());
        var capped = controller.stepContended(following, 45, java.util.Map.of(),
                rates, room, List.of(second)).service().state();
        assertEquals(NormalSignal.Phase.AMBER, capped.phase());
        assertTrue(capped.recoveryPending());
    }

    @Test
    void twoAmbulancesCrossSameApproachInQueueOrderOnOneGreen() {
        var run = RoutingSimulation.fleet(Graph.grid(5), 2, true);
        run.activate("AMB-001", "n00_00", "n04_04");
        run.activate("AMB-002", "n00_00", "n04_04");
        var order = new ArrayList<String>();
        var starts = new ArrayList<Long>();
        for (int tick = 0; tick < 10 && order.size() < 2; tick++) {
            run.step();
            for (var id : List.of("AMB-001", "AMB-002")) {
                if (!order.contains(id) && run.fleetView().get(id).ambulance().edge() != null) {
                    order.add(id);
                    starts.add(run.trafficState().signals().get("n00_00").startedAt());
                }
            }
        }
        assertEquals(List.of("AMB-001", "AMB-002"), order);
        assertEquals(List.of(0L, 0L), starts);
    }

    @Test
    void unconfirmedDiscoveryIsLocalUntilOperatorConfirmsReport() {
        var run = RoutingSimulation.fleet(Graph.grid(5), 2, true);
        run.activate("AMB-001", "n00_00", "n04_04");
        run.activate("AMB-008", "n04_00", "n00_04");
        var before = run.fleetView();
        var obstruction = before.get("AMB-001").ambulance().route().getFirst();
        assertFalse(before.get("AMB-008").explanation().liveEdges().contains(obstruction));
        run.incident(obstruction, "ENTRY_CLOSED", false);
        var observed = run.fleetView();
        assertEquals("BLOCKED", observed.get("AMB-001").explanation().roads().get(obstruction).status());
        assertNotEquals(obstruction, observed.get("AMB-001").ambulance().route().getFirst());
        assertEquals(before.get("AMB-008").explanation().roads().get(obstruction),
                observed.get("AMB-008").explanation().roads().get(obstruction));
        assertEquals(before.get("AMB-008").ambulance().route(), observed.get("AMB-008").ambulance().route());
        assertEquals(before.get("AMB-008").explanation(), observed.get("AMB-008").explanation());
        run.submitObstruction("pending", "AMB-001", obstruction, true);
        assertTrue(run.reported().isEmpty());
        run.reviewObstruction("pending", true);
        assertEquals("BLOCKED", run.fleetView().get("AMB-008").explanation().roads().get(obstruction).status());
        run.submitObstruction("reopened", "AMB-001", obstruction, false);
        run.reviewObstruction("reopened", true);
        assertTrue(run.reported().isEmpty());
        assertEquals("BLOCKED", run.fleetView().get("AMB-001").explanation().roads().get(obstruction).status());
    }

    @Test
    void anotherAmbulanceObservesTheObstructionWhenItsOwnWindowReachesIt() {
        var run = RoutingSimulation.fleet(Graph.grid(5), 2, false);
        var obstruction = run.graph().outgoing("n00_00").getFirst().id();
        run.activate("AMB-008", "n04_00", "n00_00");
        run.incident(obstruction, "ENTRY_CLOSED", false);
        assertEquals("HISTORICAL", run.fleetView().get("AMB-008").explanation().roads().get(obstruction).source());
        for (int i = 0; i < 160; i++) {
            run.step();
            var explanation = run.fleetView().get("AMB-008").explanation();
            if (explanation.liveEdges().contains(obstruction)) {
                assertEquals("BLOCKED", explanation.roads().get(obstruction).status());
                assertTrue(run.reported().isEmpty());
                return;
            }
        }
        fail("Ambulance never reached its own observation window");
    }
}
