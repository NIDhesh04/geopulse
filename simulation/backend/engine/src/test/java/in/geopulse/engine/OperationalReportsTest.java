package in.geopulse.engine;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class OperationalReportsTest {
    @Test void driverReportRemainsPendingUntilConfirmedAndReopeningDoesNotChangeOtherReports() {
        var reports = new OperationalReports();
        reports.submit("r1", "AMB-001", "road-a", true, 5);
        reports.submit("r2", "AMB-002", "road-b", true, 5);
        assertTrue(reports.confirmedClosures().isEmpty());
        reports.review("r1", true, 7);
        assertEquals(java.util.Set.of("road-a"), reports.confirmedClosures());
        reports.submit("r3", "AMB-001", "road-a", false, 8);
        reports.review("r3", true, 9);
        assertTrue(reports.confirmedClosures().isEmpty());
        assertEquals("PENDING", reports.reports().get("r2").status());
    }

    @Test void rejectionAndAcknowledgementDoNotChangeConfirmedKnowledge() {
        var reports = new OperationalReports();
        reports.submit("r1", "AMB-001", "road-a", true, 1);
        reports.review("r1", false, 2);
        reports.acknowledge("alert-1", 3);
        assertTrue(reports.confirmedClosures().isEmpty());
        assertEquals("REJECTED", reports.reports().get("r1").status());
        assertEquals(3L, reports.acknowledgements().get("alert-1"));
        assertThrows(IllegalArgumentException.class, () -> reports.review("r1", true, 4));
    }
}
