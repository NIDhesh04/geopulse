package in.geopulse.engine;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Set;

/** Equal-priority request ordering and active-grant commitment for one junction. */
public final class AmbulanceArbitrator {
    public record Request(String ambulanceId, JunctionService.Movement movement,
                          double predictedArrival, long requestedAt, long routeVersion) {}

    public record Decision(Request grant, List<Request> orderedRequests,
                           List<String> pendingIds, String reason) {}

    private static final Comparator<Request> ORDER = Comparator
            .comparingDouble(Request::predictedArrival)
            .thenComparingLong(Request::requestedAt)
            .thenComparing(Request::ambulanceId);

    public Decision decide(Request active, List<Request> requests,
                           Set<JunctionService.Movement> productive,
                           Set<String> suspendedAmbulances) {
        var ordered = requests.stream().sorted(ORDER).toList();
        var eligible = ordered.stream()
                .filter(request -> !suspendedAmbulances.contains(request.ambulanceId()))
                .filter(request -> productive.contains(request.movement()))
                .toList();

        if (active != null) {
            for (var request : eligible) {
                if (sameGrant(active, request)) {
                    return result(request, ordered, "ACTIVE_GRANT_COMMITTED");
                }
            }
        }

        Request next = eligible.isEmpty() ? null : eligible.getFirst();
        return result(next, ordered, next == null ? "NO_PRODUCTIVE_REQUEST" : "NEXT_REQUEST_SELECTED");
    }

    static boolean sameGrant(Request previous, Request current) {
        return current != null && previous.ambulanceId().equals(current.ambulanceId())
                && previous.movement().equals(current.movement())
                && previous.routeVersion() == current.routeVersion();
    }

    private Decision result(Request grant, List<Request> ordered, String reason) {
        var pending = new ArrayList<String>();
        for (var request : ordered) {
            if (!request.equals(grant)) pending.add(request.ambulanceId());
        }
        return new Decision(grant, ordered, List.copyOf(pending), reason);
    }
}
