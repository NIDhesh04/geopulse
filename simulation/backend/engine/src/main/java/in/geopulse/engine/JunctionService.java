package in.geopulse.engine;

import java.util.*;

/** One junction's deterministic service boundary, shared by the world and forecasts. */
public final class JunctionService {
    private static final double EPSILON = 1e-9;
    public static final int FORECAST_SECONDS = 300;

    public record Movement(String incoming, String outgoing) implements Comparable<Movement> {
        @Override public int compareTo(Movement other) {
            int first = incoming.compareTo(other.incoming);
            return first == 0 ? outgoing.compareTo(other.outgoing) : first;
        }
    }

    /** Only the first ambulance in a movement queue is eligible for service. */
    public record Queue(double ahead, String ambulanceId, double behind) {
        public Queue(double ahead, boolean ambulance, double behind) {
            this(ahead, ambulance ? "AMB-001" : null, behind);
        }
        public boolean ambulance() { return ambulanceId != null; }
    }
    public record Request(Movement movement, long routeRevision, String ambulanceId,
                          double predictedArrival, long requestedAt) {
        public Request(Movement movement, long routeRevision) {
            this(movement, routeRevision, "AMB-001", 0, 0);
        }

        AmbulanceArbitrator.Request arbitrationRequest() {
            return new AmbulanceArbitrator.Request(ambulanceId, movement, predictedArrival,
                    requestedAt, routeRevision);
        }
    }
    public record State(NormalSignal.Phase phase, int approach, int ordinaryCursor, long startedAt,
                        Request grant, boolean recoveryPending, boolean recoveryGreen,
                        Movement credited, double credit, Map<Movement, Credit> credits,
                        boolean grantPassed) {
        State(NormalSignal.Phase phase, int approach, int ordinaryCursor, long startedAt,
              Request grant, boolean recoveryPending, boolean recoveryGreen, Movement credited, double credit) {
            this(phase, approach, ordinaryCursor, startedAt, grant, recoveryPending, recoveryGreen,
                    credited, credit, Map.of(), false);
        }
    }
    public record Credit(String ambulanceId, double amount) {}
    public record Result(State state, Map<Movement, Double> civilianTransfers,
                         Movement ambulanceTransfer, String priority, Map<String, Movement> crossings) {}

    private final List<String> approaches;
    private final NormalSignal signal;
    private final AmbulanceArbitrator arbitrator = new AmbulanceArbitrator();

    public JunctionService(List<String> approaches) {
        this.approaches = List.copyOf(approaches);
        this.signal = new NormalSignal(approaches);
    }

    public State initial() {
        return new State(NormalSignal.Phase.ALL_RED, -1, -1, -2, null, false, false, null, 0);
    }

    public List<Integer> permissions(State state) {
        return signal.permissions(new NormalSignal.State(state.phase(), state.approach(), state.startedAt()));
    }

    public Result step(State previous, long tick, Map<Movement, Queue> queues, Map<String, Double> rates,
                       Map<String, Double> receiving, Request request) {
        return serve(previous, tick, queues, rates, receiving, request);
    }

    public record ContendedResult(Result service, Map<String, String> priorityByAmbulance) {}

    public ContendedResult stepContended(State previous, long tick, Map<Movement, Queue> queues,
                                         Map<String, Double> rates, Map<String, Double> receiving,
                                         List<Request> requests) {
        Set<Movement> productive = new HashSet<>();
        for (var request : requests) {
            if (approaches.contains(request.movement().incoming())
                    && room(receiving, request.movement()) + EPSILON >= 1
                    && rate(rates, request.movement()) > 0) {
                productive.add(request.movement());
            }
        }
        var active = previous.grant() == null || previous.grantPassed() ? null : previous.grant().arbitrationRequest();
        var decision = arbitrator.decide(active, requests.stream().map(Request::arbitrationRequest).toList(),
                productive, Set.of());
        Request selected = decision.grant() == null ? null : requests.stream()
                .filter(candidate -> candidate.arbitrationRequest().equals(decision.grant()))
                .findFirst().orElseThrow();
        var result = serve(previous, tick, queues, rates, receiving, selected);
        Map<String, String> statuses = new TreeMap<>();
        for (var request : requests) {
            String status = !productive.contains(request.movement()) ? "DOWNSTREAM_BLOCKED"
                    : result.state().grant() != null && AmbulanceArbitrator.sameGrant(
                            result.state().grant().arbitrationRequest(), request.arbitrationRequest())
                        ? "GRANTED" : "REQUESTED";
            statuses.put(request.ambulanceId(), status);
        }
        if (requests.size() == 1) {
            result = new Result(result.state(), result.civilianTransfers(), result.ambulanceTransfer(),
                    statuses.get(requests.getFirst().ambulanceId()), result.crossings());
        }
        return new ContendedResult(result, Collections.unmodifiableMap(statuses));
    }

    private Result serve(State previous, long tick, Map<Movement, Queue> queues, Map<String, Double> rates,
                         Map<String, Double> receiving, Request request) {
        boolean eligible = request != null && room(receiving, request.movement()) + EPSILON >= 1
                && rate(rates, request.movement()) > 0;
        Set<String> productive = new HashSet<>();
        queues.forEach((movement, queue) -> {
            if (demand(queue, room(receiving, movement), 0) > 0 && rate(rates, movement) > 0) {
                productive.add(movement.incoming());
            }
        });
        State phase = phase(previous, tick, productive, eligible ? request : null);
        String priority = request == null ? "NONE" : !eligible ? "DOWNSTREAM_BLOCKED"
                : request.equals(phase.grant()) ? "GRANTED" : "REQUESTED";
        if (phase.phase() != NormalSignal.Phase.GREEN) return new Result(phase, Map.of(), null, priority, Map.of());

        String incoming = approaches.get(phase.approach());
        Map<Movement, Credit> credits = new TreeMap<>();
        if (previous.phase() == NormalSignal.Phase.GREEN && previous.approach() == phase.approach()
                && previous.startedAt() == phase.startedAt()) {
            previous.credits().forEach((movement, credit) -> {
                var queue = queues.get(movement);
                if (queue != null && credit.ambulanceId().equals(queue.ambulanceId())) credits.put(movement, credit);
            });
        }
        Map<Movement, Double> demands = new TreeMap<>();
        queues.forEach((movement, queue) -> {
            if (movement.incoming().equals(incoming)) {
                double carried = credits.containsKey(movement) ? credits.get(movement).amount() : 0;
                double amount = demand(queue, room(receiving, movement), carried);
                if (amount > 0) demands.put(movement, amount);
            }
        });
        double total = demands.values().stream().mapToDouble(Double::doubleValue).sum();
        double share = total == 0 ? 0 : Math.min(1, rates.getOrDefault(incoming, 0.0) / total);
        Map<Movement, Double> civilians = new TreeMap<>();
        Map<String, Movement> crossings = new TreeMap<>();
        Map<String, Integer> reserved = new TreeMap<>();
        for (var item : demands.entrySet()) {
            Movement movement = item.getKey();
            Queue queue = queues.get(movement);
            double budget = item.getValue() * share;
            double civilian = Math.min(queue.ahead(), budget);
            if (civilian > 0) civilians.put(movement, civilian);
            if (queue.ambulance() && civilian + EPSILON >= queue.ahead()
                    && room(receiving, movement) + EPSILON >= 1 + civilian) {
                double carried = credits.containsKey(movement) ? credits.get(movement).amount() : 0;
                double credit = Math.min(1, carried + Math.max(0, budget - civilian));
                int taken = reserved.getOrDefault(movement.outgoing(), 0);
                if (credit + EPSILON >= 1 && room(receiving, movement) + EPSILON >= taken + 1 + civilian) {
                    crossings.put(queue.ambulanceId(), movement);
                    reserved.merge(movement.outgoing(), 1, Integer::sum);
                    credits.remove(movement);
                } else if (credit > 0) {
                    credits.put(movement, new Credit(queue.ambulanceId(), credit));
                }
            }
        }

        // Reserve the indivisible ambulance slot before distributing remaining receiving space.
        Map<String, Double> totalByRoad = new TreeMap<>();
        civilians.forEach((movement, count) -> totalByRoad.merge(movement.outgoing(), count, Double::sum));
        civilians.replaceAll((movement, count) -> {
            double free = room(receiving, movement) - reserved.getOrDefault(movement.outgoing(), 0);
            return count * Math.min(1, Math.max(0, free) / totalByRoad.get(movement.outgoing()));
        });
        var first = credits.entrySet().stream().findFirst().orElse(null);
        State next = new State(phase.phase(), phase.approach(), phase.ordinaryCursor(), phase.startedAt(),
                phase.grant(), phase.recoveryPending(), phase.recoveryGreen(),
                first == null ? null : first.getKey(), first == null ? 0 : first.getValue().amount(),
                Map.copyOf(credits), phase.grant() != null && crossings.containsKey(phase.grant().ambulanceId()));
        return new Result(next, Collections.unmodifiableMap(civilians),
                crossings.values().stream().findFirst().orElse(null), priority, Map.copyOf(crossings));
    }

    private State phase(State old, long tick, Set<String> productive, Request request) {
        long elapsed = tick - old.startedAt();
        if (old.phase() == NormalSignal.Phase.GREEN) {
            String active = approaches.get(old.approach());
            boolean sameApproach = request != null && request.movement().incoming().equals(active);
            Request grant = old.grant();
            if (old.recoveryGreen()) {
                return elapsed >= 10 ? amber(old, tick, false) : old;
            }
            boolean followingOnSameGreen = old.grantPassed() && sameApproach && elapsed < 45;
            if (grant != null && (!followingOnSameGreen && (old.grantPassed() || request == null
                    || !AmbulanceArbitrator.sameGrant(grant.arbitrationRequest(), request.arbitrationRequest()))
                    || elapsed >= 45)) {
                if (elapsed >= 10) return amber(old, tick, true);
                return new State(old.phase(), old.approach(), old.ordinaryCursor(), old.startedAt(),
                        null, true, false, old.credited(), old.credit());
            }
            if (old.recoveryPending() && elapsed >= 10) return amber(old, tick, true);
            if (sameApproach && !old.recoveryPending() && elapsed < 45) {
                return new State(old.phase(), old.approach(), old.ordinaryCursor(), old.startedAt(),
                        request, false, false, old.credited(), old.credit());
            }
            if (request != null && !sameApproach && elapsed >= 10) return amber(old, tick, false);
            var normal = signal.atBoundary(new NormalSignal.State(old.phase(), old.approach(), old.startedAt()),
                    tick, productive);
            return normal.phase() == NormalSignal.Phase.AMBER ? amber(old, tick, false) : old;
        }
        if (old.phase() == NormalSignal.Phase.AMBER) {
            if (elapsed < 3) return old;
            return new State(NormalSignal.Phase.ALL_RED, -1, old.ordinaryCursor(), tick,
                    null, old.recoveryPending(), false, null, 0);
        }
        if (elapsed < 2) return old;
        var normal = signal.atBoundary(new NormalSignal.State(old.phase(), old.ordinaryCursor(), old.startedAt()),
                tick, productive);
        boolean normalReady = normal.phase() == NormalSignal.Phase.GREEN;
        if (request != null && !(old.recoveryPending() && normalReady)) {
            int approach = approaches.indexOf(request.movement().incoming());
            if (approach >= 0) return new State(NormalSignal.Phase.GREEN, approach, old.ordinaryCursor(),
                    tick, request, false, false, null, 0);
        }
        if (!normalReady) return old;
        return new State(NormalSignal.Phase.GREEN, normal.cursor(), normal.cursor(), tick,
                null, false, old.recoveryPending(), null, 0);
    }

    private State amber(State old, long tick, boolean recover) {
        return new State(NormalSignal.Phase.AMBER, old.approach(), old.ordinaryCursor(), tick,
                null, recover, false, null, 0);
    }

    private static double rate(Map<String, Double> rates, Movement movement) {
        return rates.getOrDefault(movement.incoming(), 0.0);
    }

    private static double room(Map<String, Double> receiving, Movement movement) {
        return receiving.getOrDefault(movement.outgoing(), 0.0);
    }

    private static double demand(Queue queue, double room, double credit) {
        if (room <= 0) return 0;
        if (!queue.ambulance()) return queue.ahead();
        return queue.ahead() + (room + EPSILON >= 1 ? 1 - credit : 0);
    }

    public Estimate forecast(State state, long start, Movement candidate, Map<Movement, Queue> queues,
                             Map<String, Double> rates, Map<String, Double> receiving, String source) {
        return forecast(state, start, candidate, queues, rates, receiving,
                Map.of(), Map.of(), source);
    }

    Estimate forecast(State state, long start, Movement candidate, Map<Movement, Queue> queues,
                      Map<String, Double> rates, Map<String, Double> receiving,
                      Map<Movement, Double> expectedQueueArrivals, Map<String, Double> expectedReleases,
                      String source) {
        var projected = new TreeMap<Movement, Queue>();
        queues.forEach((movement, queue) -> projected.put(movement, movement.equals(candidate)
                ? queue : new Queue(queue.ahead() + queue.behind(), false, 0)));
        var existing = projected.getOrDefault(candidate, new Queue(0, false, 0));
        projected.put(candidate, new Queue(existing.ahead(),
                existing.ambulance() ? existing.ambulanceId() : "forecast", existing.behind()));
        if (!existing.ambulance() || !candidate.equals(state.credited())) {
            state = new State(state.phase(), state.approach(), state.ordinaryCursor(), state.startedAt(),
                    state.grant(), state.recoveryPending(), state.recoveryGreen(), null, 0);
        }
        Request established = state.grant();
        var predictedRoom = new TreeMap<>(receiving);
        for (int offset = 0; offset < FORECAST_SECONDS; offset++) {
            var step = step(state, start + offset, projected, rates, predictedRoom, established);
            if (candidate.equals(step.ambulanceTransfer())) return Estimate.available(offset + 1, source);
            state = step.state();
            if (state.grant() == null) established = null;
            step.civilianTransfers().forEach((movement, count) -> {
                Queue before = projected.get(movement);
                projected.put(movement, new Queue(Math.max(0, before.ahead() - count),
                        before.ambulanceId(), before.behind()));
                predictedRoom.computeIfPresent(movement.outgoing(), (road, free) -> Math.max(0, free - count));
            });
            expectedReleases.forEach((road, release) ->
                    predictedRoom.computeIfPresent(road, (id, free) -> Math.min(TrafficWorld.STORAGE, free + release)));
            var remainingByApproach = new HashMap<String, Double>();
            projected.forEach((movement, queue) -> remainingByApproach.merge(movement.incoming(),
                    queue.ahead() + queue.behind() + (queue.ambulance() ? 1 : 0), Double::sum));
            expectedQueueArrivals.forEach((movement, count) -> {
                double occupied = remainingByApproach.getOrDefault(movement.incoming(), 0.0);
                double admitted = Math.min(count, Math.max(0, TrafficWorld.STORAGE - occupied));
                projected.compute(movement, (key, prior) -> {
                    Queue before = prior == null ? new Queue(0, false, 0) : prior;
                    return before.ambulance()
                            ? new Queue(before.ahead(), before.ambulanceId(), before.behind() + admitted)
                            : new Queue(before.ahead() + admitted, false, 0);
                });
                remainingByApproach.put(movement.incoming(), occupied + admitted);
            });
        }
        return Estimate.unknown("Junction forecast exceeded 300 seconds");
    }
}
