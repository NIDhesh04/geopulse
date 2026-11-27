package in.geopulse.engine;

import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class BenchmarkSuiteTest {
    @Test void schedulesAreStableAndUseTheDocumentedFixtureSizes() {
        for (var fixture : BenchmarkSuite.Fixture.values()) {
            var schedule = BenchmarkSuite.schedule(fixture, 1000);
            assertEquals(schedule, BenchmarkSuite.schedule(fixture, 1000));
            assertNotEquals(schedule, BenchmarkSuite.schedule(fixture, 1001));
            assertEquals(fixture.ambulanceCount, schedule.missions().size());
            assertTrue(schedule.missions().stream().allMatch(m -> m.tick() >= 600 && m.tick() < 1200));
            assertTrue(schedule.changes().stream().allMatch(c -> c.tick() >= 600 && c.tick() < 3000));
        }
        assertEquals(10, BenchmarkSuite.Fixture.CONFLICT.stations().size());
        assertEquals(30, BenchmarkSuite.Fixture.SCALE.stations().size());
    }

    @Test void queueRecoveryRequiresSixtyConsecutiveMatchedSamples() {
        double[] disabled = new double[101];
        double[] enabled = new double[101];
        Arrays.fill(disabled, 10);
        Arrays.fill(enabled, 11);
        enabled[15] = 11.1;
        assertEquals(6, BenchmarkSuite.recovery(enabled,disabled,610));
        assertEquals(-1, BenchmarkSuite.recovery(enabled,disabled,645));
        assertEquals(-1, BenchmarkSuite.recovery(enabled,disabled,-1));
    }

    @Test void pairedPoliciesShareTheWarmStateAndExternalDemand() {
        var fixture = BenchmarkSuite.Fixture.DISCONNECTED;
        var graph = Graph.grid(5);
        var profile = CalibrationRunner.calibrateEvaluation(graph, Set.of("n00_00"), false);
        assertEquals(3000, profile.bucketSeconds()*profile.buckets());
        assertTrue(Collections.disjoint(profile.seeds(),CalibrationRunner.CORE_BENCHMARK_SEEDS));
        assertTrue(Collections.disjoint(profile.seeds(),CalibrationRunner.SCALE_BENCHMARK_SEEDS));
        var warm = BenchmarkSuite.warmed(fixture,1000,profile);
        var schedule = BenchmarkSuite.schedule(fixture,1000);
        var reference = BenchmarkSuite.evaluate(warm,schedule,new BenchmarkSuite.Policy(0,false,true));
        var hybrid = BenchmarkSuite.evaluate(warm,schedule,new BenchmarkSuite.Policy(2,true,false));
        assertEquals(reference.start(),hybrid.start());
        assertEquals(reference.end().arrivals(),hybrid.end().arrivals(),1e-8);
        assertEquals(BenchmarkSuite.WARMUP,warm.time());
        assertTrue(reference.missions().isEmpty());
        assertEquals(1,hybrid.missions().size());
        assertTrue(hybrid.missions().getFirst().routeWait()>0);
        var outcome = hybrid.missions().getFirst();
        assertNotNull(outcome.actual());
        long arrival = schedule.missions().getFirst().tick()+outcome.actual();
        assertEquals(arrival <= BenchmarkSuite.EVALUATION_END ? "ON_TIME" : "LATE", outcome.status());
    }
}
