package in.geopulse.engine;

import java.io.PrintWriter;
import java.util.*;
import java.util.stream.LongStream;
import static in.geopulse.engine.JunctionService.Movement;

/** Headless incident-free baseline for the predictable congestion fixture. */
public final class CalibrationRunner {
    public static final String SCENARIO = "predictable-congestion-5x5";
    public static final String CORRIDOR = "n00_02_n00_03";
    public static final long DEMO_SEED = 108;
    public static final List<Long> CALIBRATION_SEEDS = List.of(-1001L, -1002L, -1003L);
    public static final List<Long> CORE_BENCHMARK_SEEDS = LongStream.range(1000, 1020).boxed().toList();
    public static final List<Long> SCALE_BENCHMARK_SEEDS = LongStream.range(2000, 2005).boxed().toList();
    public static final int BUCKET_SECONDS = 20;
    public static final int BUCKETS = 12;

    private CalibrationRunner() {}

    static double demand(long tick, long seed) {
        // Seed variation affects the height of the pulse. Every seed retains the same schedule.
        double pulse = 1.4 + new SplittableRandom(seed).nextDouble(-0.12, 0.12);
        return tick >= 20 && tick < 155 ? pulse : .035;
    }

    public static HistoricalProfile calibrate(List<Long> seeds) {
        if (seeds.isEmpty() || !CALIBRATION_SEEDS.containsAll(seeds)
                || Set.copyOf(seeds).size() != seeds.size()) {
            throw new IllegalArgumentException("Use distinct reserved calibration seeds");
        }
        var orderedSeeds = seeds.stream().sorted(Comparator.reverseOrder()).toList();
        var roads = new TreeMap<String, double[]>();
        var junctions = new TreeMap<Movement, double[]>();
        int samplesPerBucket = seeds.size() * BUCKET_SECONDS;
        for (long seed : orderedSeeds) {
            var world = TrafficWorld.calibrationWorld(Graph.grid(5), seed);
            for (int tick = 0; tick < BUCKET_SECONDS * BUCKETS; tick++) {
                // No ambulances, operational reports, physical incidents or future live inputs.
                world.step(tick, Map.of(), null, false, null, null);
                int bucket = tick / BUCKET_SECONDS;
                world.sampleHistorical(
                        (edge, seconds) -> roads.computeIfAbsent(edge, ignored -> new double[BUCKETS])[bucket] += seconds,
                        (movement, seconds) -> junctions.computeIfAbsent(movement, ignored -> new double[BUCKETS])[bucket] += seconds);
            }
        }
        return new HistoricalProfile(BUCKET_SECONDS, BUCKETS, orderedSeeds,
                average(roads, samplesPerBucket), average(junctions, samplesPerBucket));
    }

    private static <K extends Comparable<K>> Map<K, List<Double>> average(Map<K, double[]> sums, int samples) {
        var result = new TreeMap<K, List<Double>>();
        sums.forEach((key, series) -> result.put(key, Arrays.stream(series)
                .map(total -> Math.round(total * 1000 / samples) / 1000.0).boxed().toList()));
        return result;
    }

    public static void main(String[] args) {
        if (args.length != 0) throw new IllegalArgumentException("Redirect stdout to the scenario profile file");
        calibrate(CALIBRATION_SEEDS).write(new PrintWriter(System.out));
    }
}
