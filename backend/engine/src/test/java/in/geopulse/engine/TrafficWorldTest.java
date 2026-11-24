package in.geopulse.engine;

import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class TrafficWorldTest {
    @Test
    void boundaryDemandAndCivilianTransfersConservePopulationDuringClosure() {
        var graph = Graph.grid(3);
        var world = new TrafficWorld(graph);
        var closed = graph.outgoing("n00_00").getFirst().id();
        for (int tick = 0; tick < 140; tick++) {
            world.step(tick, tick < 80 ? Map.of(closed, Set.of("ENTRY_CLOSED")) : Map.of(), null, false, null, null);
            var totals = world.totals();
            assertEquals(totals.arrivals(), totals.travelling() + totals.queued()
                    + totals.exited() + totals.boundaryBacklog(), 1e-8);
            for (var edge : graph.edges()) assertTrue(world.civilianOccupancy(edge.id()) <= TrafficWorld.STORAGE + 1e-8);
            if (tick == 70) assertTrue(totals.boundaryBacklog() > 0);
        }
        assertTrue(world.totals().exited() > 0);
        assertTrue(world.totals().junctionWaiting() > 0);
    }

    @Test
    void m2MissionUsesStationCreditAndCompletesDeterministically() {
        var run = RoutingSimulation.traffic(Graph.grid(5), 2, true);
        run.activate("n00_00", "n04_04");
        assertTrue(run.explanation().candidates().stream().anyMatch(c ->
                c.junction().usable() && c.junction().seconds() > 0));
        run.step();
        assertNull(run.ambulance().edge());
        var copy = run.copy();
        for (int tick = 0; tick < 500 && run.ambulance().arrivedAt() == null; tick++) {
            run.step();
            copy.step();
        }
        assertNotNull(run.ambulance().arrivedAt());
        assertEquals(run.ambulance(), copy.ambulance());
        assertEquals(run.trafficState(), copy.trafficState());
        assertTrue(run.trafficState().totals().exited() > 0);
    }
    @Test
    void clearingOneIncidentKeepsOtherPhysicalAndReportedRestrictions() {
        var run = RoutingSimulation.traffic(Graph.grid(5), 2, false);
        var road = run.graph().outgoing("n00_00").getFirst().id();
        run.incident(road, "ENTRY_CLOSED", true, "roadwork");
        run.incident(road, "IMPASSABLE", true, "collision");
        run.incident(road, "OPEN", true, "collision");
        run.activate("n00_00", "n04_04");
        assertTrue(run.reported().contains(road));
        assertEquals("BLOCKED", run.explanation().roads().get(road).status());
        run.report(road, false);
        assertEquals("BLOCKED", run.explanation().roads().get(road).status());
        run.incident(road, "OPEN", false, "roadwork");
        assertTrue(run.explanation().roads().get(road).usable());
    }
    @Test
    void historicalForecastCannotReadUnreportedPhysicalClosure() {
        var graph = Graph.grid(5);
        var world = TrafficWorld.fixture(graph);
        var road = graph.outgoing("n00_00").getFirst();
        var hidden = Map.of(road.id(), Set.of("ENTRY_CLOSED"));
        var historical = world.estimator(0, Set.of(), hidden, Set.of(), null);
        var baseline = world.estimator(0, Set.of(), Map.of(), Set.of(), null);
        assertEquals(baseline.estimate("station-entry:n00_00", road, 0),
                historical.estimate("station-entry:n00_00", road, 0));
        var live = world.estimator(0, Set.of(road.id()), hidden, Set.of(), null);
        assertEquals("UNKNOWN", live.estimate("station-entry:n00_00", road, 0).status());
    }
    @Test
    void historicalMissionReplansOnEncounteringAnInfeasibleDeparture() {
        var run = RoutingSimulation.traffic(Graph.grid(5), 0, false);
        run.activate("n00_00", "n04_04");
        String blocked = run.ambulance().route().getFirst();
        run.incident(blocked, "ENTRY_CLOSED", false);
        assertEquals(blocked, run.ambulance().route().getFirst());
        run.step();
        assertNotEquals(blocked, run.ambulance().route().getFirst());
        assertTrue(run.reported().isEmpty());
        assertEquals(1, run.ambulance().reroutes());
    }
}
