package in.geopulse.engine;

import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class RoutingTest {
    final Graph graph = new Graph(List.of(new Graph.Node("s",0,0),new Graph.Node("a",1,0),new Graph.Node("b",0,1),new Graph.Node("d",1,1)),
        List.of(new Graph.Edge("sa","s","a",100,10),new Graph.Edge("sb","s","b",100,10),new Graph.Edge("ad","a","d",100,10),new Graph.Edge("bd","b","d",100,10)));
    final RoadWeightProvider ten = (e,t) -> Estimate.available(10,"HISTORICAL");
    RoutingSnapshot snapshot(int h, RoadWeightProvider live, JunctionDelayEstimator junction, Set<String> blocked) {
        return new RoutingSnapshot(graph,"s",h,42,live,ten,junction,blocked);
    }
    @Test void horizonsIncludeEveryBranchBeforeBlocking() {
        assertEquals(Set.of(),snapshot(0,ten,new M1ZeroJunctionDelay(),Set.of()).liveEdges());
        assertEquals(Set.of("sa","sb"),snapshot(1,ten,new M1ZeroJunctionDelay(),Set.of("sa")).liveEdges());
        assertEquals(Set.of("sa","sb","ad","bd"),snapshot(2,ten,new M1ZeroJunctionDelay(),Set.of("sa")).liveEdges());
        assertEquals(4,snapshot(-1,ten,new M1ZeroJunctionDelay(),Set.of()).liveEdges().size());
    }
    @Test void unknownLiveFallsBackButKnownClosureDoesNot() {
        var snap=snapshot(2,(e,t)->e.id().equals("sa")?Estimate.blocked("closure"):Estimate.unknown("sensor missing"),new M1ZeroJunctionDelay(),Set.of());
        assertEquals("HISTORICAL_FALLBACK",snap.road("sb").source());
        assertEquals("BLOCKED",snap.road("sa").status());
        assertEquals(List.of("sb","bd"),new DijkstraRouter().route(graph,"s","entry","d",snap).edges());
    }
    @Test void replacingM1StubChangesRouteWithoutChangingDijkstra() {
        var router=new DijkstraRouter();
        assertEquals(List.of("sa","ad"),router.route(graph,"s","entry","d",snapshot(2,ten,new M1ZeroJunctionDelay(),Set.of())).edges());
        JunctionDelayEstimator future=(incoming,out,t)->Estimate.available(incoming.equals("sa")&&out.id().equals("ad")?100:0,"TEST_FORECAST");
        assertEquals(List.of("sb","bd"),router.route(graph,"s","entry","d",snapshot(2,ten,future,Set.of())).edges());
    }
    @Test void snapshotUsesCurrentClockAndMemoizesMovementEstimates() {
        List<Long> times=new ArrayList<>(); int[] calls={0};
        var snap=snapshot(2,(e,t)->{times.add(t);return ten.estimate(e,t);},(i,e,t)->{times.add(t);calls[0]++;return Estimate.available(0,"TEST");},Set.of());
        snap.junction("entry","sa");snap.junction("entry","sa");
        assertEquals(1,calls[0]); assertTrue(times.stream().allMatch(t->t==42));
    }
    @Test void disconnectedAndImmediateArrivalAreExplicit() {
        var snap=snapshot(2,ten,new M1ZeroJunctionDelay(),Set.of("ad","bd"));
        assertFalse(new DijkstraRouter().route(graph,"s","entry","d",snap).reachable());
        assertEquals(0,new DijkstraRouter().route(graph,"s","entry","s",snap).seconds());
    }
    @Test void hiddenDistantDataIsNeverRequested() {
        Set<String> accessed=new TreeSet<>();
        snapshot(1,(e,t)->{accessed.add(e.id());return ten.estimate(e,t);},new M1ZeroJunctionDelay(),Set.of());
        assertEquals(Set.of("sa","sb"),accessed);
    }
    @Test void invalidTimesAreUnknownNotZero() {
        for(double bad: new double[]{-1,Double.NaN,Double.POSITIVE_INFINITY}) assertEquals("UNKNOWN",Estimate.available(bad,"TEST").status());
    }
}
