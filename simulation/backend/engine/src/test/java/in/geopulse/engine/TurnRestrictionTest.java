package in.geopulse.engine;

import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class TurnRestrictionTest {
    private static Graph network(TurnRestrictions turns) {
        var nodes=List.of(new Graph.Node("a",0,0),new Graph.Node("b",1,0),new Graph.Node("c",2,0),
                new Graph.Node("d",3,0),new Graph.Node("e",2,1),new Graph.Node("f",0,1));
        var roads=List.of(new Graph.Edge("ab","a","b",2,1),new Graph.Edge("bc","b","c",2,1),
                new Graph.Edge("cd","c","d",2,1),new Graph.Edge("ce","c","e",2,1),
                new Graph.Edge("ed","e","d",2,1),new Graph.Edge("fb","f","b",2,1));
        return new Graph(nodes,roads,turns);
    }

    @Test void viaWayKeepsDistinctSearchStatesAndSurvivesReplanning() {
        var graph=network(new TurnRestrictions(List.of(List.of("ab","bc","cd")),List.of()));
        var restricted=new RoutingSimulation(graph,0);
        restricted.activate("a","d");
        assertEquals(List.of("ab","bc","ce","ed"),restricted.ambulance().route());
        for(int tick=0;tick<20&&!restricted.ambulance().node().equals("c");tick++) restricted.step();
        assertEquals("c",restricted.ambulance().node());
        restricted.step();
        assertEquals("ce",restricted.ambulance().edge());
        assertEquals("TURN_RESTRICTED",restricted.explanation().candidates().getFirst().outcome());
        var other=new RoutingSimulation(graph,0);
        other.activate("f","d");
        assertEquals(List.of("fb","bc","cd"),other.ambulance().route());
    }

    @Test void civilianThroughputCannotTakeForbiddenTurnAndStillConservesTraffic() {
        var restricted=TrafficWorld.geographicWorld(
                network(new TurnRestrictions(List.of(List.of("ab","bc","cd")),List.of())),"a",108);
        var ordinary=TrafficWorld.geographicWorld(network(TurnRestrictions.NONE),"a",108);
        var physical=Map.of("fb",Set.of("ENTRY_CLOSED"));
        boolean unrestrictedUsedLink=false,restrictedUsedAlternative=false;
        for(int tick=0;tick<220;tick++) {
            restricted.step(tick,physical,null,false,null,null);
            ordinary.step(tick,physical,null,false,null,null);
            var truth=restricted.roadTruth();
            assertEquals(0,truth.get("cd").occupancy(),1e-9);
            restrictedUsedAlternative|=truth.get("ce").occupancy()>0;
            unrestrictedUsedLink|=ordinary.roadTruth().get("cd").occupancy()>0;
            var totals=restricted.totals();
            assertEquals(totals.arrivals(),totals.travelling()+totals.queued()+totals.boundaryBacklog()+totals.exited(),1e-7);
            truth.values().forEach(road->assertTrue(road.occupancy()<=road.capacity()+1e-7));
            if(tick==110)restricted=restricted.copy();
        }
        assertTrue(restrictedUsedAlternative);
        assertTrue(unrestrictedUsedLink);
    }

    @Test void onlyTurnConstrainsTheEntireViaWayPrefix() {
        var graph=network(new TurnRestrictions(List.of(),List.of(
                new TurnRestrictions.Only(List.of("ab","bc"),List.of("ce")))));
        var simulation=new RoutingSimulation(graph,2);
        simulation.activate("a","d");
        assertEquals(List.of("ab","bc","ce","ed"),simulation.ambulance().route());
    }

    @Test void aShorterRestrictedPrefixDoesNotPruneALegalWayToTheSameIncomingRoad() {
        var base=network(new TurnRestrictions(List.of(List.of("ab","bc","cd")),List.of()));
        var roads=new ArrayList<>(base.edges());
        roads.add(new Graph.Edge("af","a","f",1,1));
        var graph=new Graph(base.nodes(),roads,base.turnRestrictions());
        var simulation=new RoutingSimulation(graph,0);
        simulation.incident("ce","ENTRY_CLOSED",true);
        simulation.activate("a","d");
        assertEquals(List.of("af","fb","bc","cd"),simulation.ambulance().route());
    }

    @Test void rejectsNoncontiguousRestrictions() {
        assertThrows(IllegalArgumentException.class,()->network(
                new TurnRestrictions(List.of(List.of("ab","ed")),List.of())));
    }
}
