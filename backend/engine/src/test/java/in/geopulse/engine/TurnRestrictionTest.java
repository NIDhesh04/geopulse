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
        while (!restricted.ambulance().node().equals("c")) restricted.step();
        restricted.step();
        assertEquals("ce",restricted.ambulance().edge());
        assertEquals("TURN_RESTRICTED",restricted.explanation().candidates().getFirst().outcome());
        var other=new RoutingSimulation(graph,0);
        other.activate("f","d");
        assertEquals(List.of("fb","bc","cd"),other.ambulance().route());
    }

    @Test void onlyTurnConstrainsTheEntireViaWayPrefix() {
        var graph=network(new TurnRestrictions(List.of(),List.of(
                new TurnRestrictions.Only(List.of("ab","bc"),List.of("ce")))));
        var simulation=new RoutingSimulation(graph,2);
        simulation.activate("a","d");
        assertEquals(List.of("ab","bc","ce","ed"),simulation.ambulance().route());
    }

    @Test void rejectsNoncontiguousRestrictions() {
        assertThrows(IllegalArgumentException.class,()->network(
                new TurnRestrictions(List.of(List.of("ab","ed")),List.of())));
    }
}
