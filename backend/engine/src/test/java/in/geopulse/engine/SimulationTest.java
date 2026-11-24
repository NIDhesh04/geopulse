package in.geopulse.engine;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class SimulationTest {
    @Test void midRoadBlockStopsWithoutTeleportAndReopeningResumes() {
        var run=new RoutingSimulation(Graph.grid(5),2);
        run.activate("n00_00","n04_04");run.step();run.step();
        String road=run.ambulance().edge();double position=run.ambulance().progress();
        run.incident(road,"IMPASSABLE",true);run.step();
        assertEquals(road,run.ambulance().edge());assertEquals(position,run.ambulance().progress());
        assertEquals("ROAD_IMPASSABLE",run.ambulance().reason());
        run.incident(road,"OPEN",true);run.step();assertTrue(run.ambulance().progress()>position);
    }
    @Test void copyIsIsolatedAndSameStepsAreDeterministic() {
        var a=new RoutingSimulation(Graph.grid(5),2);a.activate("n00_00","n04_04");var b=a.copy();
        a.step();assertEquals(0,b.time());
        for(int i=0;i<200;i++){if(i>0)a.step();b.step();}
        assertEquals(a.ambulance(),b.ambulance());assertEquals("ARRIVED",a.ambulance().status());
        assertEquals(0,a.ambulance().reroutes());
    }
    @Test void estimatorIsInjectedAndUnknownDelayIsNeverZero() {
        JunctionDelayEstimator unknown=(incoming,edge,time)->Estimate.unknown("Forecast horizon exceeded");
        var run=new RoutingSimulation(Graph.grid(5),2,unknown);
        run.activate("n00_00","n04_04");
        assertEquals("STOPPED",run.ambulance().status());
        assertNull(run.ambulance().initialEta());
    }
    @Test void initiallyUnavailableEtaStaysUnavailableAfterRecovery() {
        var run=new RoutingSimulation(Graph.grid(5),2);
        for(var road:run.graph().outgoing("n00_00"))run.incident(road.id(),"ENTRY_CLOSED",true);
        run.activate("n00_00","n04_04");
        assertEquals("ALL_OUTGOING_BLOCKED",run.ambulance().reason());
        assertNull(run.ambulance().initialEta());
        run.incident(run.graph().outgoing("n00_00").getFirst().id(),"OPEN",true);
        assertEquals("AT_JUNCTION",run.ambulance().status());
        assertNull(run.ambulance().initialEta());
        assertNotNull(run.ambulance().estimatedArrival());
    }
    @Test void reportedClosureReroutesAndEntryClosureDoesNotStopAnOccupiedRoad() {
        var run=new RoutingSimulation(Graph.grid(5),2);run.activate("n00_00","n04_04");
        String planned=run.ambulance().route().getFirst();
        run.report(planned,true);assertEquals(1,run.ambulance().reroutes());
        run.step();String entered=run.ambulance().edge();
        run.incident(entered,"ENTRY_CLOSED",true);run.step();
        assertEquals("MOVING",run.ambulance().status());assertTrue(run.ambulance().progress()>0);
    }
    @Test void activationAtDestinationHasZeroJourneyAndEta() {
        var run=new RoutingSimulation(Graph.grid(5),2);run.activate("n00_00","n00_00");
        assertEquals(0.0,run.ambulance().initialEta());assertEquals(0L,run.ambulance().arrivedAt());
    }
}
