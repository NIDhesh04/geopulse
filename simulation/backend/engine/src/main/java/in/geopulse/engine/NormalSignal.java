package in.geopulse.engine;

import java.util.List;
import java.util.Set;
import java.util.stream.IntStream;

/** Ordinary approach service. The caller supplies approaches with dischargeable traffic. */
public final class NormalSignal {
    public enum Phase { GREEN, AMBER, ALL_RED }

    public record State(Phase phase, int cursor, long startedAt) {}

    public record Timing(int minGreen, int maxGreen, int amber, int allRed) {
        public Timing {
            if (minGreen <= 0 || maxGreen < minGreen || amber <= 0 || allRed <= 0) {
                throw new IllegalArgumentException("Invalid signal timing");
            }
        }
    }

    private final List<String> approaches;
    private final Timing timing;

    public NormalSignal(List<String> approaches) {
        this(approaches, new Timing(10, 30, 3, 2));
    }

    public NormalSignal(List<String> approaches, Timing timing) {
        this.approaches = List.copyOf(approaches);
        if (approaches.isEmpty() || Set.copyOf(approaches).size() != approaches.size()) {
            throw new IllegalArgumentException("Approaches must be nonempty and unique");
        }
        this.timing = java.util.Objects.requireNonNull(timing);
    }

    public State initial() {
        // At tick zero there is no previous green to clear.
        return new State(Phase.ALL_RED, -1, -timing.allRed());
    }

    /** Called before service at each one-second boundary, including tick zero. */
    public State atBoundary(State state, long tick, Set<String> dischargeable) {
        long elapsed = tick - state.startedAt();
        return switch (state.phase()) {
            case GREEN -> {
                boolean productive = dischargeable.contains(approaches.get(state.cursor()));
                boolean yield = elapsed >= timing.maxGreen()
                        || (elapsed >= timing.minGreen() && !productive);
                yield yield ? new State(Phase.AMBER, state.cursor(), tick) : state;
            }
            case AMBER -> elapsed >= timing.amber()
                    ? new State(Phase.ALL_RED, state.cursor(), tick) : state;
            case ALL_RED -> elapsed >= timing.allRed()
                    ? startNextGreen(state, tick, dischargeable) : state;
        };
    }

    private State startNextGreen(State state, long tick, Set<String> dischargeable) {
        for (int offset = 1; offset <= approaches.size(); offset++) {
            int index = (state.cursor() + offset) % approaches.size();
            if (dischargeable.contains(approaches.get(index))) {
                return new State(Phase.GREEN, index, tick);
            }
        }
        return state;
    }

    public List<Integer> permissions(State state) {
        return IntStream.range(0, approaches.size())
                .mapToObj(i -> state.phase() == Phase.GREEN && i == state.cursor() ? 1 : 0)
                .toList();
    }
}
