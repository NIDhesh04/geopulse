package in.geopulse.engine;

import java.util.List;

/** Calculates and explains routes from one frozen cost snapshot. */
public interface RoutingPolicy {
    public record Route(boolean reachable,List<String> edges,Double seconds){
        public Route{edges=List.copyOf(edges);}
    }
    public record Candidate(String edge,Estimate road,Estimate junction,Double pathSeconds,String outcome,String reason){}

    Route route(Graph graph, String start, String incoming, String destination,
                RoutingSnapshot snapshot);

    List<Candidate> explain(Graph graph, String start, String incoming, String destination,
                            RoutingSnapshot snapshot, Route selected);
}
