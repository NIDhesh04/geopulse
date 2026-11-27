package in.geopulse.engine;

import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class NormalSignalTest {
    private final NormalSignal signal = new NormalSignal(List.of("north", "east", "station"));
    private final Set<String> all = Set.of("north", "east", "station");

    @Test
    void emptyOrBlockedApproachKeepsMinimumGreenThenGoesThroughClearance() {
        var green = signal.atBoundary(signal.initial(), 0, all);
        assertEquals(List.of(1, 0, 0), signal.permissions(green));
        assertEquals(green, signal.atBoundary(green, 9, Set.of("station")));

        var amber = signal.atBoundary(green, 10, Set.of("east"));
        assertEquals(NormalSignal.Phase.AMBER, amber.phase());
        assertEquals(List.of(0, 0, 0), signal.permissions(amber));
        assertEquals(amber, signal.atBoundary(amber, 12, all));

        var clearance = signal.atBoundary(amber, 13, all);
        assertEquals(NormalSignal.Phase.ALL_RED, clearance.phase());
        assertEquals(List.of(0, 0, 0), signal.permissions(clearance));
        assertEquals(clearance, signal.atBoundary(clearance, 14, all));
        var next = signal.atBoundary(clearance, 15, Set.of("north", "station"));
        assertEquals(List.of(0, 0, 1), signal.permissions(next));
    }

    @Test
    void productiveApproachExtendsToMaximumAndCursorSurvivesIdleClearance() {
        var green = signal.atBoundary(signal.initial(), 0, all);
        assertEquals(green, signal.atBoundary(green, 29, all));
        var amber = signal.atBoundary(green, 30, all);
        assertEquals(NormalSignal.Phase.AMBER, amber.phase());
        var clearance = signal.atBoundary(amber, 33, all);
        assertEquals(clearance, signal.atBoundary(clearance, 35, Set.of()));
        var next = signal.atBoundary(clearance, 40, all);
        assertEquals(List.of(0, 1, 0), signal.permissions(next));
        assertEquals(40, next.startedAt());
    }
}
