package in.geopulse.engine;

import org.junit.jupiter.api.Test;
import java.util.*;
import static in.geopulse.engine.JunctionService.Movement;
import static org.junit.jupiter.api.Assertions.*;

class HistoricalProfileTest {
    private static final HistoricalProfile CALIBRATED = CalibrationRunner.calibrate(CalibrationRunner.CALIBRATION_SEEDS);
    private static final String STATION = "station";

    @Test void roadAndMovementEstimatesUseProjectedArrivalIncludingCandidateTails() {
        var graph = new Graph(List.of(new Graph.Node("s", 0, 0), new Graph.Node("a", 1, 0),
                new Graph.Node("b", 1, 1), new Graph.Node("d", 2, 0)),
                List.of(new Graph.Edge("sa", "s", "a", 9, 1), new Graph.Edge("ad", "a", "d", 5, 1),
                        new Graph.Edge("sb", "s", "b", 11, 1), new Graph.Edge("bd", "b", "d", 11, 1)));
        var profile = new HistoricalProfile(20, 2, List.of(-1001L),
                Map.of("sa", List.of(9., 9.), "ad", List.of(5., 20.),
                        "sb", List.of(11., 11.), "bd", List.of(11., 11.)),
                Map.of(new Movement(STATION, "sa"), List.of(0., 0.), new Movement("sa", "ad"), List.of(1., 9.),
                        new Movement(STATION, "sb"), List.of(0., 0.), new Movement("sb", "bd"), List.of(0., 0.)));
        RoadWeightProvider freeFlow = (road, time) -> Estimate.available(road.length(), "HISTORICAL");
        var snapshot = new RoutingSnapshot(graph, 12, freeFlow, freeFlow, new M1ZeroJunctionDelay(),
                Set.of(), Set.of(), profile);
        var router = new DijkstraRouter();
        var route = router.route(graph, "s", STATION, "d", snapshot);
        assertEquals(List.of("sb", "bd"), route.edges());
        var candidates = router.explain(graph, "s", STATION, "d", snapshot, route);
        assertEquals(38., candidates.getFirst().pathSeconds());
        assertEquals(route.seconds(), candidates.getLast().pathSeconds());
        assertEquals(5., snapshot.road("ad", 19.99).seconds());
        assertEquals(20., snapshot.road("ad", 20).seconds());
        assertEquals(9., snapshot.junction("sa", "ad", 20).seconds());
        assertEquals(20., snapshot.road("ad", 400).seconds());
        assertTrue(snapshot.road("ad", 40).reason().contains("Beyond calibrated window"));
    }

    @Test void fallingBucketsPreserveFifoEvenWhenBothComponentsFall() {
        var profile = new HistoricalProfile(20, 2, List.of(-1001L),
                Map.of("road", List.of(30., 10.)), Map.of(new Movement(STATION, "road"), List.of(25., 0.)));
        double previous = 0;
        for (double time = 0; time <= 80; time += .25) {
            double arrival = time + profile.road("road", time).seconds() + profile.junction(STATION, "road", time).seconds();
            assertTrue(arrival >= previous, "FIFO at " + time);
            previous = arrival;
        }
        assertEquals(10., profile.road("road", 80).seconds());
        assertEquals(0., profile.junction(STATION, "road", 80).seconds());
    }

    @Test void calibrationSeedsAreReservedAndProduceTheSameProfile() {
        var demo = Set.of(CalibrationRunner.DEMO_SEED);
        assertTrue(Collections.disjoint(CalibrationRunner.CALIBRATION_SEEDS, demo));
        assertTrue(Collections.disjoint(CalibrationRunner.CALIBRATION_SEEDS, CalibrationRunner.CORE_BENCHMARK_SEEDS));
        assertTrue(Collections.disjoint(CalibrationRunner.CALIBRATION_SEEDS, CalibrationRunner.SCALE_BENCHMARK_SEEDS));
        assertThrows(IllegalArgumentException.class, () -> CalibrationRunner.calibrate(List.copyOf(demo)));
        assertThrows(IllegalArgumentException.class, () -> CalibrationRunner.calibrate(CalibrationRunner.CORE_BENCHMARK_SEEDS));
        assertThrows(IllegalArgumentException.class, () -> CalibrationRunner.calibrate(CalibrationRunner.SCALE_BENCHMARK_SEEDS));
        assertEquals(CALIBRATED, CalibrationRunner.calibrate(CalibrationRunner.CALIBRATION_SEEDS.reversed()));
    }

    @Test void bothHorizonsAnticipateCongestionOutsideTheLiveNeighborhood() {
        var corridor = CalibrationRunner.CORRIDOR;
        assertTrue(CALIBRATED.road(corridor, 40).seconds() > 2 * CALIBRATED.road(corridor, 0).seconds());
        var freeFlow = new HistoricalProfile(20, 1, CalibrationRunner.CALIBRATION_SEEDS,
                CALIBRATED.roads().keySet().stream().collect(java.util.stream.Collectors.toMap(
                        id -> id, id -> List.of(10.))),
                CALIBRATED.junctions().keySet().stream().collect(java.util.stream.Collectors.toMap(
                        movement -> movement, movement -> List.of(0.))));
        for (int horizon : List.of(0, 2)) {
            var calibrated = RoutingSimulation.predictableCongestion(horizon, false, CalibrationRunner.DEMO_SEED, CALIBRATED);
            var constant = RoutingSimulation.predictableCongestion(horizon, false, CalibrationRunner.DEMO_SEED, freeFlow);
            calibrated.activate("n00_00", "n00_04");
            constant.activate("n00_00", "n00_04");
            var explanation = calibrated.fleetView().get("AMB-001").explanation();
            assertFalse(explanation.liveEdges().contains(corridor));
            assertEquals("HISTORICAL", explanation.roads().get(corridor).source());
            assertFalse(calibrated.ambulance().route().contains(corridor), "calibrated horizon " + horizon);
            assertTrue(constant.ambulance().route().contains(corridor), "constant horizon " + horizon);
        }
    }
}
