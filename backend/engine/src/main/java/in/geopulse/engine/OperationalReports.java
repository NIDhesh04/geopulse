package in.geopulse.engine;

import java.util.Collections;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

/** Operational knowledge and acknowledgements, independent of physical incidents. */
public final class OperationalReports {
    public record Report(String id, String ambulanceId, String road, boolean closure,
                         long submittedAt, String status, Long reviewedAt) {}

    private final Map<String, Report> reports = new TreeMap<>();
    private final Set<String> confirmedClosures = new TreeSet<>();
    private final Map<String, Long> acknowledgements = new TreeMap<>();

    public OperationalReports copy() {
        var copy = new OperationalReports();
        copy.reports.putAll(reports);
        copy.confirmedClosures.addAll(confirmedClosures);
        copy.acknowledgements.putAll(acknowledgements);
        return copy;
    }

    public void submit(String id, String ambulanceId, String road, boolean closure, long tick) {
        if (id == null || id.isBlank() || ambulanceId == null || ambulanceId.isBlank()
                || road == null || road.isBlank() || reports.containsKey(id)) {
            throw new IllegalArgumentException("Report must have a unique ID, ambulance and road");
        }
        reports.put(id, new Report(id, ambulanceId, road, closure, tick, "PENDING", null));
    }

    public void review(String id, boolean confirmed, long tick) {
        var report = reports.get(id);
        if (report == null || !report.status().equals("PENDING")) {
            throw new IllegalArgumentException("Report is not pending");
        }
        reports.put(id, new Report(id, report.ambulanceId(), report.road(), report.closure(),
                report.submittedAt(), confirmed ? "CONFIRMED" : "REJECTED", tick));
        if (confirmed) {
            if (report.closure()) confirmedClosures.add(report.road());
            else confirmedClosures.remove(report.road());
        }
    }

    public void acknowledge(String alertId, long tick) {
        if (alertId == null || alertId.isBlank()) throw new IllegalArgumentException("Alert ID required");
        acknowledgements.putIfAbsent(alertId, tick);
    }

    public Map<String, Report> reports() { return Collections.unmodifiableMap(reports); }
    public Set<String> confirmedClosures() { return Collections.unmodifiableSet(confirmedClosures); }
    public Map<String, Long> acknowledgements() { return Collections.unmodifiableMap(acknowledgements); }
}
