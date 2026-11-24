package in.geopulse.engine;

import java.io.*;
import java.util.*;
import static in.geopulse.engine.JunctionService.Movement;

/** Frozen incident-free observations. Each series is indexed by simulation-time bucket. */
public record HistoricalProfile(int bucketSeconds, int buckets, List<Long> seeds,
                                Map<String, List<Double>> roads, Map<Movement, List<Double>> junctions) {
    public HistoricalProfile {
        if (bucketSeconds <= 0 || buckets <= 0 || seeds.isEmpty() || Set.copyOf(seeds).size() != seeds.size())
            throw new IllegalArgumentException("Invalid profile metadata");
        seeds = List.copyOf(seeds);
        roads = freeze(roads, buckets);
        junctions = freeze(junctions, buckets);
    }

    private static <K extends Comparable<K>> Map<K, List<Double>> freeze(Map<K, List<Double>> source, int buckets) {
        var copy = new TreeMap<K, List<Double>>();
        source.forEach((key, values) -> {
            if (values.size() != buckets || values.stream().anyMatch(value -> !Double.isFinite(value) || value < 0))
                throw new IllegalArgumentException("Invalid bucket series: " + key);
            copy.put(key, List.copyOf(values));
        });
        return Collections.unmodifiableMap(copy);
    }

    public Estimate road(String edge, double projectedTime) { return lookup(roads.get(edge), projectedTime); }
    public Estimate junction(String incoming, String outgoing, double projectedTime) {
        return lookup(junctions.get(new Movement(incoming, outgoing)), projectedTime);
    }

    private Estimate lookup(List<Double> series, double time) {
        if (series == null || !Double.isFinite(time)) return Estimate.unknown("Historical profile estimate unavailable");
        double t = Math.max(0, time);
        int bucket = Math.min(buckets - 1, (int) (t / bucketSeconds));
        double delay = series.get(bucket);
        // Both costs are queried at the same arrival time. Limiting each one's
        // falling slope to 1/2 gives their sum a FIFO arrival function.
        for (int before = bucket - 1; before >= 0; before--) {
            double previousEnd = (before + 1.0) * bucketSeconds;
            delay = Math.max(delay, series.get(before) - (t - previousEnd) / 2);
        }
        return new Estimate("AVAILABLE", delay, "HISTORICAL", t >= (double) bucketSeconds * buckets
                ? "Beyond calibrated window; using the final historical bucket"
                : "Historical interval " + bucket * bucketSeconds + "–" + (bucket + 1) * bucketSeconds + "s");
    }

    public void write(PrintWriter out) {
        out.println("geopulse-profile-v1\t" + bucketSeconds + "\t" + buckets + "\t" +
                String.join(",", seeds.stream().map(String::valueOf).toList()));
        roads.forEach((key, values) -> row(out, "R\t" + key, values));
        junctions.forEach((key, values) -> row(out, "J\t" + key.incoming() + "\t" + key.outgoing(), values));
        out.flush();
    }

    private static void row(PrintWriter out, String key, List<Double> values) {
        out.print(key);
        values.forEach(value -> out.print("\t" + value));
        out.println();
    }

    public static HistoricalProfile read(BufferedReader in) throws IOException {
        String header = in.readLine();
        if (header == null) throw new IOException("Missing historical profile");
        String[] fields = header.split("\t");
        if (fields.length != 4 || !fields[0].equals("geopulse-profile-v1")) throw new IOException("Unknown profile format");
        var roads = new TreeMap<String, List<Double>>();
        var junctions = new TreeMap<Movement, List<Double>>();
        for (String line; (line = in.readLine()) != null;) {
            var items = line.split("\t");
            int valueStart = switch (items[0]) {
                case "R" -> 2;
                case "J" -> 3;
                default -> throw new IOException("Unknown historical profile row");
            };
            if (items.length <= valueStart) throw new IOException("Incomplete historical profile row");
            var values = Arrays.stream(items, valueStart, items.length).map(Double::parseDouble).toList();
            var previous = valueStart == 2 ? roads.put(items[1], values)
                    : junctions.put(new Movement(items[1], items[2]), values);
            if (previous != null) throw new IOException("Duplicate historical profile row");
        }
        return new HistoricalProfile(Integer.parseInt(fields[1]), Integer.parseInt(fields[2]),
                Arrays.stream(fields[3].split(",")).map(Long::parseLong).toList(), roads, junctions);
    }
}
