package in.geopulse.engine;

import java.util.*;
import static in.geopulse.engine.JunctionService.*;
import in.geopulse.engine.JunctionService.Queue;

/** Aggregate traffic state for the deterministic M2 fixture. */
public final class TrafficWorld {
    static final double STORAGE = 12;
    private static final double DISCHARGE = 0.6;
    private static final double ARRIVAL_RATE = 0.18;
    private static final double EXIT_SHARE = 0.3;
    private static final String EXIT = "@exit";
    private static final String STATION = "station-entry:";
    private static final double EPSILON = 1e-9;

    private record Cohort(double count, double position) {}
    private record Junction(List<String> approaches, List<Movement> movements, JunctionService service) {}
    private record Network(Graph graph, Map<String, Graph.Edge> roads, Map<String, Junction> junctions,
                           Map<String, List<Movement>> turns, Set<String> entries) {}
    private record Profile(Map<String, Double> speed, Map<String, Double> occupancy,
                           Map<Movement, Double> queues, Map<Movement, Double> arrivals, Map<String, Double> releases) {}
    public record Totals(double arrivals, double travelling, double queued, double exited,
                         double boundaryBacklog, double junctionWaiting, double boundaryWaiting,
                         double runningExcess) {}
    public record SignalView(List<String> approaches, String phase, List<Integer> permissions,
                             long startedAt, String grantedAmbulance, boolean recoveryGreen,
                             Map<String, String> requests) {}
    public record RoadTruth(double occupancy, double queued, double capacity) {}
    public record View(Totals totals, Map<String, SignalView> signals, String priority) {}
    record Crossing(Movement movement, String priority) {}
    record FleetCrossing(Map<String, Movement> crossings, Map<String, String> priorities) {}
    record Vehicle(String id, String road, boolean moving, Movement waiting) {}
    private record QueuePosition(Movement movement, double civiliansAhead) {}

    private final Network network;
    private final Map<String, List<Cohort>> travelling = new TreeMap<>();
    private final Map<Movement, Double> queues = new TreeMap<>();
    private final Map<String, Double> backlog = new TreeMap<>();
    private final Map<String, State> signals = new TreeMap<>();
    private final Map<String, Map<String, String>> signalRequests = new TreeMap<>();
    private Profile history;
    private final Map<String, QueuePosition> waitingAmbulances = new LinkedHashMap<>();
    private Map<String, Integer> occupiedByFleet = Map.of();
    private Map<String, Integer> movingByFleet = Map.of();
    private double arrivals, exited, junctionWait, boundaryWait, runningExcess;
    private String priority = "NONE";
    private final Map<Movement, Double> queueArrivals = new TreeMap<>();
    private final Map<String, Double> releases = new TreeMap<>();

    public TrafficWorld(Graph graph) {
        this(network(graph, false));
    }

    private TrafficWorld(Network network) {
        this.network = network;
        network.roads().keySet().forEach(id -> travelling.put(id, List.of()));
        network.entries().forEach(id -> backlog.put(id, 0.0));
        network.junctions().forEach((id, junction) -> signals.put(id, junction.service().initial()));
    }

    private static Network network(Graph graph, boolean fleetStations) {
        Map<String, Graph.Edge> roads = new TreeMap<>();
        Map<String, Junction> junctions = new TreeMap<>();
        Map<String, List<Movement>> turns = new TreeMap<>();
        Set<String> entries = new TreeSet<>();
        graph.edges().forEach(edge -> roads.put(edge.id(), edge));
        double minX = graph.nodes().stream().mapToDouble(Graph.Node::x).min().orElse(0);
        double minY = graph.nodes().stream().mapToDouble(Graph.Node::y).min().orElse(0);
        double maxX = graph.nodes().stream().mapToDouble(Graph.Node::x).max().orElse(0);
        double maxY = graph.nodes().stream().mapToDouble(Graph.Node::y).max().orElse(0);
        for (var node : graph.nodes()) {
            var outgoing = graph.outgoing(node.id());
            if ((node.x() == minX || node.x() == maxX) && (node.y() == minY || node.y() == maxY)) {
                outgoing.forEach(edge -> entries.add(edge.id()));
            }
            var approaches = new ArrayList<String>();
            var local = new ArrayList<Movement>();
            for (var road : graph.edges()) {
                if (!road.to().equals(node.id())) continue;
                approaches.add(road.id());
                var choices = outgoing.stream().filter(edge -> !edge.to().equals(road.from()))
                        .map(edge -> new Movement(road.id(), edge.id())).toList();
                var distribution = new ArrayList<>(choices);
                boolean boundary = node.x() == minX || node.x() == maxX || node.y() == minY || node.y() == maxY;
                if (boundary || choices.isEmpty()) distribution.add(new Movement(road.id(), EXIT));
                turns.put(road.id(), List.copyOf(distribution));
                local.addAll(distribution);
                outgoing.stream().filter(edge -> edge.to().equals(road.from()))
                        .forEach(edge -> local.add(new Movement(road.id(), edge.id())));
            }
            String station = STATION + node.id();
            if (node.id().equals("n00_00") || (fleetStations && Set.of("n00_04", "n04_00").contains(node.id()))
                    || approaches.isEmpty()) {
                approaches.add(station);
                outgoing.forEach(edge -> local.add(new Movement(station, edge.id())));
            }
            junctions.put(node.id(), new Junction(List.copyOf(approaches), List.copyOf(local),
                    new JunctionService(approaches)));
        }
        return new Network(graph, roads, junctions, turns, entries);
    }

    /** Calibration uses a separate incident-free run. The live run starts empty. */
    static TrafficWorld fixture(Graph graph) {
        return fixture(graph, false);
    }

    static TrafficWorld fixture(Graph graph, boolean fleetStations) {
        var world = new TrafficWorld(network(graph, fleetStations));
        var baseline = new TrafficWorld(world.network);
        Map<String, Double> speeds = new TreeMap<>();
        Map<String, Double> populations = new TreeMap<>();
        Map<Movement, Double> waiting = new TreeMap<>();
        Map<Movement, Double> expectedArrivals = new TreeMap<>();
        Map<String, Double> expectedReleases = new TreeMap<>();
        for (int tick = 0; tick < 240; tick++) {
            baseline.step(tick, Map.of(), null, false, null, null);
            if (tick < 120) continue;
            for (var edge : graph.edges()) {
                speeds.merge(edge.id(), baseline.speed(edge, Map.of(), null, false) / 120, Double::sum);
                populations.merge(edge.id(), baseline.civilianOccupancy(edge.id()) / 120, Double::sum);
            }
            baseline.queues.forEach((movement, count) -> waiting.merge(movement, count / 120, Double::sum));
            baseline.queueArrivals.forEach((movement, count) -> expectedArrivals.merge(movement, count / 120, Double::sum));
            baseline.releases.forEach((road, count) -> expectedReleases.merge(road, count / 120, Double::sum));
        }
        world.history = new Profile(Map.copyOf(speeds), Map.copyOf(populations), Map.copyOf(waiting),
                Collections.unmodifiableMap(expectedArrivals), Map.copyOf(expectedReleases));
        return world;
    }

    TrafficWorld copy() {
        var copy = new TrafficWorld(network);
        copy.travelling.putAll(travelling);
        copy.queues.putAll(queues);
        copy.backlog.putAll(backlog);
        copy.signals.putAll(signals);
        copy.signalRequests.putAll(signalRequests);
        copy.history = history;
        copy.waitingAmbulances.putAll(waitingAmbulances);
        copy.occupiedByFleet = occupiedByFleet;
        copy.movingByFleet = movingByFleet;
        copy.arrivals = arrivals;
        copy.exited = exited;
        copy.junctionWait = junctionWait;
        copy.boundaryWait = boundaryWait;
        copy.runningExcess = runningExcess;
        copy.priority = priority;
        return copy;
    }

    Totals totals() {
        return new Totals(arrivals, travelling.values().stream().flatMap(List::stream).mapToDouble(Cohort::count).sum(),
                sum(queues), exited, sum(backlog), junctionWait, boundaryWait, runningExcess);
    }

    View view() {
        Map<String, SignalView> views = new TreeMap<>();
        network.junctions().forEach((id, junction) -> {
            State state = signals.get(id);
            views.put(id, new SignalView(junction.approaches(), state.phase().name(),
                    junction.service().permissions(state), state.startedAt(),
                    state.grant() == null ? null : state.grant().ambulanceId(), state.recoveryGreen(),
                    signalRequests.getOrDefault(id, Map.of())));
        });
        return new View(totals(), Collections.unmodifiableMap(views), priority);
    }

    Map<String, RoadTruth> roadTruth() {
        var truth = new TreeMap<String, RoadTruth>();
        network.roads().keySet().forEach(id -> {
            double queued = network.turns().get(id).stream().mapToDouble(m -> queues.getOrDefault(m, 0.0)).sum();
            int fleet = occupiedByFleet.getOrDefault(id, 0);
            truth.put(id, new RoadTruth(runningPopulation(id) + queued + fleet,
                    queued + fleet - movingByFleet.getOrDefault(id, 0), STORAGE));
        });
        return Collections.unmodifiableMap(truth);
    }

    private static double sum(Map<?, Double> values) {
        return values.values().stream().mapToDouble(Double::doubleValue).sum();
    }

    private double runningPopulation(String road) {
        return travelling.get(road).stream().mapToDouble(Cohort::count).sum();
    }

    double civilianOccupancy(String road) {
        return runningPopulation(road) + network.turns().get(road).stream()
                .mapToDouble(movement -> queues.getOrDefault(movement, 0.0)).sum();
    }

    double speed(Graph.Edge road, Map<String, Set<String>> physical, String ambulanceRoad, boolean moving) {
        return speed(road, physical, moving && road.id().equals(ambulanceRoad) ? 1 : 0);
    }

    double fleetSpeed(Graph.Edge road, Map<String, Set<String>> physical) {
        return speed(road, physical, movingByFleet.getOrDefault(road.id(), 0));
    }

    private double speed(Graph.Edge road, Map<String, Set<String>> physical, int movingAmbulances) {
        Set<String> effects = physical.getOrDefault(road.id(), Set.of());
        if (effects.contains("IMPASSABLE")) return 0;
        double running = runningPopulation(road.id()) + movingAmbulances;
        double free = road.freeSpeed() * Math.max(0.2, 1 - 0.8 * Math.min(1, running / STORAGE));
        return effects.contains("SLOW") ? Math.min(2, free) : free;
    }

    double historicalSpeed(Graph.Edge road) {
        return history.speed().getOrDefault(road.id(), road.freeSpeed());
    }

    private static boolean closed(Set<String> effects) {
        return effects != null && (effects.contains("ENTRY_CLOSED") || effects.contains("IMPASSABLE"));
    }

    private static double rate(Set<String> effects) {
        if (effects == null) return DISCHARGE;
        if (effects.contains("IMPASSABLE")) return 0;
        return effects.contains("DISCHARGE_REDUCED") ? 0.2 : DISCHARGE;
    }

    String priority() { return priority; }

    boolean hasBoundaryEntry(String edge) { return backlog.containsKey(edge); }

    void joinMovement(String id, Movement movement) { queueAmbulance(id, movement); }

    private void queueAmbulance(String id, Movement movement) {
        QueuePosition old = waitingAmbulances.get(id);
        if (old != null && old.movement().equals(movement)) return;
        waitingAmbulances.remove(id);
        if (movement != null) waitingAmbulances.put(id, new QueuePosition(movement, queues.getOrDefault(movement, 0.0)));
    }

    void observeFleet(List<Vehicle> vehicles) {
        Map<String, Integer> occupied = new TreeMap<>();
        Map<String, Integer> moving = new TreeMap<>();
        for (var vehicle : vehicles) {
            if (vehicle.road() == null) continue;
            occupied.merge(vehicle.road(), 1, Integer::sum);
            if (vehicle.moving()) moving.merge(vehicle.road(), 1, Integer::sum);
        }
        occupiedByFleet = Map.copyOf(occupied);
        movingByFleet = Map.copyOf(moving);
    }

    private Map<Movement, Queue> localQueues(Junction junction, boolean live) {
        Map<Movement, Queue> result = new TreeMap<>();
        var population = live ? queues : history.queues();
        for (var movement : junction.movements()) {
            double count = population.getOrDefault(movement, 0.0);
            if (count > 0) result.put(movement, new Queue(count, false, 0));
        }
        if (live) waitingAmbulances.forEach((id, position) -> {
            if (!junction.movements().contains(position.movement())) return;
            var current = result.get(position.movement());
            if (current != null && current.ambulance()) return;
            double count = queues.getOrDefault(position.movement(), 0.0);
            result.put(position.movement(), new Queue(position.civiliansAhead(), id,
                    Math.max(0, count - position.civiliansAhead())));
        });
        return result;
    }

    JunctionDelayEstimator estimator(long tick, Set<String> liveEdges, Map<String, Set<String>> physical,
                                     Set<String> reported, String ambulanceRoad) {
        return estimator(tick, liveEdges, physical, reported, ambulanceRoad, "AMB-001");
    }

    JunctionDelayEstimator estimator(long tick, Set<String> liveEdges, Map<String, Set<String>> physical,
                                     Set<String> reported, String ambulanceRoad, String ambulanceId) {
        return (incoming, outgoing, time) -> {
            Junction junction = network.junctions().get(outgoing.from());
            if (!junction.approaches().contains(incoming)) return Estimate.unknown("Unknown approach");
            boolean live = liveEdges.contains(outgoing.id());
            var movements = localQueues(junction, live);
            var candidate = new Movement(incoming, outgoing.id());
            if (live) {
                // Forecast other ambulances ahead as whole queued units. Only the
                // subject ambulance can use its own accumulated service credit.
                var position = waitingAmbulances.get(ambulanceId);
                boolean queuedHere = position != null && candidate.equals(position.movement());
                double ahead = queuedHere ? position.civiliansAhead() : queues.getOrDefault(candidate, 0.0);
                for (var waiting : waitingAmbulances.entrySet()) {
                    if (queuedHere && waiting.getKey().equals(ambulanceId)) break;
                    if (candidate.equals(waiting.getValue().movement())) ahead++;
                }
                movements.put(candidate, new Queue(ahead, queuedHere ? ambulanceId : null, 0));
            }
            var room = new TreeMap<String, Double>();
            room.put(EXIT, Double.POSITIVE_INFINITY);
            var release = new TreeMap<String, Double>();
            for (var road : network.graph().outgoing(outgoing.from())) {
                boolean visible = liveEdges.contains(road.id());
                double used = visible ? civilianOccupancy(road.id())
                        : history.occupancy().getOrDefault(road.id(), 0.0);
                if (visible) used += occupiedByFleet.getOrDefault(road.id(), 0);
                else if (road.id().equals(ambulanceRoad)) used++;
                boolean blocked = reported.contains(road.id()) || (visible && closed(physical.get(road.id())));
                room.put(road.id(), blocked ? 0 : Math.max(0, STORAGE - used));
                if (!blocked) release.put(road.id(), Math.min(history.releases().getOrDefault(road.id(), 0.0),
                        rate(visible ? physical.get(road.id()) : null)));
            }
            var rates = new TreeMap<String, Double>();
            junction.approaches().forEach(approach -> rates.put(approach,
                    rate(live && (liveEdges.contains(approach) || approach.equals(incoming))
                            ? physical.get(approach) : null)));
            State state = live ? signals.get(outgoing.from()) : junction.service().initial();
            var newQueues = new TreeMap<Movement, Double>();
            junction.movements().forEach(movement -> {
                double expected = history.arrivals().getOrDefault(movement, 0.0);
                if (expected > 0 && rate(live && liveEdges.contains(movement.incoming())
                        ? physical.get(movement.incoming()) : null) > 0) newQueues.put(movement, expected);
            });
            return junction.service().forecast(state, tick, candidate, movements, rates, room, newQueues, release,
                    live ? "LIVE_JUNCTION_FORECAST" : "HISTORICAL_JUNCTION_FORECAST");
        };
    }

    Request request(String ambulanceId, Movement movement, double secondsToEnd, long routeRevision,
                    long tick, long junctionArrival, Request previous, Map<String, Set<String>> physical) {
        if (movement == null) return null;
        boolean alreadyRequested = previous != null && previous.ambulanceId().equals(ambulanceId)
                && previous.movement().equals(movement) && previous.routeRevision() == routeRevision;
        double service = rate(physical.get(movement.incoming()));
        var position = waitingAmbulances.get(ambulanceId);
        boolean queuedHere = position != null && movement.equals(position.movement());
        double count = queuedHere ? position.civiliansAhead() : queues.getOrDefault(movement, 0.0);
        for (var waiting : waitingAmbulances.entrySet()) {
            if (queuedHere && waiting.getKey().equals(ambulanceId)) break;
            if (movement.equals(waiting.getValue().movement())) count++;
        }
        if (!alreadyRequested && secondsToEnd > 0 && (service <= 0 || secondsToEnd > count / service + 15)) {
            return null;
        }
        double arrival = secondsToEnd > 0 ? tick + secondsToEnd : junctionArrival;
        return new Request(movement, routeRevision, ambulanceId, arrival,
                alreadyRequested ? previous.requestedAt() : tick);
    }

    Crossing step(long tick, Map<String, Set<String>> physical, String ambulanceRoad, boolean moving,
                  Movement waiting, Request request) {
        var fleet = stepFleet(tick, physical, List.of(new Vehicle("AMB-001", ambulanceRoad, moving, waiting)),
                request == null ? List.of() : List.of(request));
        return new Crossing(fleet.crossings().get("AMB-001"), fleet.priorities().getOrDefault("AMB-001", "NONE"));
    }

    FleetCrossing stepFleet(long tick, Map<String, Set<String>> physical, List<Vehicle> vehicles,
                            List<Request> requests) {
        observeFleet(vehicles);
        vehicles.forEach(vehicle -> queueAmbulance(vehicle.id(), vehicle.waiting()));
        releases.clear();
        queueArrivals.clear();
        junctionWait += sum(queues);
        boundaryWait += sum(backlog);
        Map<String, Double> room = new TreeMap<>();
        room.put(EXIT, Double.POSITIVE_INFINITY);
        Map<String, Double> speed = new TreeMap<>();
        network.roads().forEach((id, road) -> {
            double occupied = civilianOccupancy(id) + occupiedByFleet.getOrDefault(id, 0);
            room.put(id, closed(physical.get(id)) ? 0 : Math.max(0, STORAGE - occupied));
            speed.put(id, fleetSpeed(road, physical));
        });
        Map<String, Double> receivingUsed = new TreeMap<>();
        Map<String, Double> arrivalsOnRoads = new TreeMap<>();
        Map<String, Movement> crossings = new TreeMap<>();
        Map<String, String> statuses = new TreeMap<>();
        signalRequests.clear();
        // Each outgoing road has exactly one upstream junction, so each junction
        // allocates its receiving capacity once. Boundary demand uses the residual.
        for (var entry : network.junctions().entrySet()) {
            String node = entry.getKey();
            Junction junction = entry.getValue();
            var rates = new TreeMap<String, Double>();
            junction.approaches().forEach(id -> rates.put(id, rate(physical.get(id))));
            var local = requests.stream().filter(request ->
                    network.roads().get(request.movement().outgoing()).from().equals(node)).toList();
            var previous = signals.get(node);
            var waitingQueues = localQueues(junction, true);
            JunctionService.Result result;
            if (local.isEmpty()) {
                result = junction.service().step(previous, tick, waitingQueues, rates, room, null);
            } else {
                var contention = junction.service().stepContended(previous, tick, waitingQueues,
                        rates, room, local);
                result = contention.service();
                statuses.putAll(contention.priorityByAmbulance());
                signalRequests.put(node, contention.priorityByAmbulance());
            }
            signals.put(node, result.state());
            crossings.putAll(result.crossings());
            result.crossings().values().forEach(crossing ->
                    receivingUsed.merge(crossing.outgoing(), 1.0, Double::sum));
            result.civilianTransfers().forEach((movement, count) -> {
                releases.merge(movement.incoming(), count, Double::sum);
                queues.compute(movement, (key, amount) -> {
                    double remaining = (amount == null ? 0 : amount) - count;
                    return remaining > EPSILON ? remaining : null;
                });
                waitingAmbulances.replaceAll((id, position) -> position.movement().equals(movement)
                        ? new QueuePosition(movement, Math.max(0, position.civiliansAhead() - count)) : position);
                if (movement.outgoing().equals(EXIT)) exited += count;
                else {
                    receivingUsed.merge(movement.outgoing(), count, Double::sum);
                    arrivalsOnRoads.merge(movement.outgoing(), count, Double::sum);
                }
            });
        }
        crossings.keySet().forEach(waitingAmbulances::remove);
        for (var entry : backlog.entrySet()) {
            double demandRate = physical.getOrDefault(entry.getKey(), Set.of()).contains("DEMAND_SURGE") ? 2 * ARRIVAL_RATE : ARRIVAL_RATE;
            arrivals += demandRate;
            double demand = entry.getValue() + demandRate;
            double entered = Math.min(demand, Math.max(0,
                    room.get(entry.getKey()) - receivingUsed.getOrDefault(entry.getKey(), 0.0)));
            entry.setValue(demand - entered);
            arrivalsOnRoads.merge(entry.getKey(), entered, Double::sum);
        }
        network.roads().forEach((id, road) -> {
            var next = new ArrayList<Cohort>();
            for (var cohort : travelling.get(id)) {
                double metres = Math.min(road.length() - cohort.position(), speed.get(id));
                double seconds = speed.get(id) <= 0 ? 1 : metres / speed.get(id);
                runningExcess += cohort.count() * Math.max(0, seconds - metres / road.freeSpeed());
                double position = cohort.position() + metres;
                if (position + EPSILON >= road.length()) enqueue(id, cohort.count());
                else next.add(new Cohort(cohort.count(), position));
            }
            double newlyEntered = arrivalsOnRoads.getOrDefault(id, 0.0);
            if (newlyEntered > 0) next.add(new Cohort(newlyEntered, 0));
            travelling.put(id, List.copyOf(next));
        });
        priority = statuses.getOrDefault("AMB-001", "NONE");
        return new FleetCrossing(Map.copyOf(crossings), Map.copyOf(statuses));
    }

    private void enqueue(String road, double count) {
        var movements = network.turns().get(road);
        if (movements.size() == 1) {
            addToQueue(movements.getFirst(), count);
            return;
        }
        boolean hasExit = movements.getLast().outgoing().equals(EXIT);
        double turnShare = hasExit ? (1 - EXIT_SHARE) / (movements.size() - 1) : 1.0 / movements.size();
        movements.forEach(movement -> addToQueue(movement,
                count * (movement.outgoing().equals(EXIT) ? EXIT_SHARE : turnShare)));
    }
    private void addToQueue(Movement movement, double count) {
        queues.merge(movement, count, Double::sum);
        queueArrivals.merge(movement, count, Double::sum);
    }
}
