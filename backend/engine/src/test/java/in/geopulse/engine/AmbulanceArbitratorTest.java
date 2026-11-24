package in.geopulse.engine;

import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class AmbulanceArbitratorTest {
    private final JunctionService.Movement east = new JunctionService.Movement("west", "east");
    private final JunctionService.Movement north = new JunctionService.Movement("south", "north");

    @Test
    void ordersEqualPriorityByArrivalThenRequestTimeThenStableId() {
        var arbitrator = new AmbulanceArbitrator();
        var requests = List.of(
                request("AMB-003", east, 12, 3),
                request("AMB-002", north, 10, 4),
                request("AMB-001", east, 10, 4));

        var decision = arbitrator.decide(null, requests, Set.of(east, north), Set.of());

        assertEquals("AMB-001", decision.grant().ambulanceId());
        assertEquals(List.of("AMB-001", "AMB-002", "AMB-003"),
                decision.orderedRequests().stream().map(AmbulanceArbitrator.Request::ambulanceId).toList());
    }

    @Test
    void activeProductiveGrantRemainsCommittedDespiteEarlierNewRequest() {
        var arbitrator = new AmbulanceArbitrator();
        var active = request("AMB-009", east, 20, 2);
        var earlier = request("AMB-001", north, 5, 3);

        var decision = arbitrator.decide(active, List.of(active, earlier), Set.of(east, north), Set.of());

        assertEquals(active, decision.grant());
        assertEquals("ACTIVE_GRANT_COMMITTED", decision.reason());
    }

    @Test
    void suspendedAndDownstreamBlockedRequestsAreNotGranted() {
        var arbitrator = new AmbulanceArbitrator();
        var suspended = request("AMB-001", east, 1, 1);
        var blocked = request("AMB-002", north, 2, 1);

        var decision = arbitrator.decide(null, List.of(suspended, blocked), Set.of(east),
                Set.of("AMB-001"));

        assertNull(decision.grant());
        assertEquals(List.of("AMB-001", "AMB-002"), decision.pendingIds());
    }

    @Test
    void passageOrUnproductiveMovementReleasesCommittedGrant() {
        var arbitrator = new AmbulanceArbitrator();
        var active = request("AMB-001", east, 1, 1);
        var waiting = request("AMB-002", north, 2, 2);

        assertEquals(waiting, arbitrator.decide(active, List.of(waiting), Set.of(north), Set.of()).grant());
        assertEquals(waiting, arbitrator.decide(active, List.of(active, waiting), Set.of(north), Set.of()).grant());
    }

    private AmbulanceArbitrator.Request request(String id, JunctionService.Movement movement,
                                                 long arrival, long requested) {
        return new AmbulanceArbitrator.Request(id, movement, arrival, requested, 1);
    }
}
