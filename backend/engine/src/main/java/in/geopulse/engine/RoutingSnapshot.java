package in.geopulse.engine;
import java.util.*;
public final class RoutingSnapshot {
    private record Movement(String incoming,String outgoing){}
    private final Graph graph;private final long time;private final JunctionDelayEstimator delays;
    private final Set<String> liveEdges;private final Map<String,Estimate> roads=new TreeMap<>();
    private final Map<Movement,Estimate> waits=new HashMap<>();
    public RoutingSnapshot(Graph graph,String origin,int horizon,long time,RoadWeightProvider live,RoadWeightProvider historical,JunctionDelayEstimator delays,Set<String> reportedClosures){
        this(graph, time, live, historical, delays, reportedClosures, liveEdges(graph, origin, horizon));
    }

    RoutingSnapshot(Graph graph,long time,RoadWeightProvider live,RoadWeightProvider historical,
                    JunctionDelayEstimator delays,Set<String> reportedClosures,Set<String> liveEdges){
        this.graph=graph;this.time=time;this.delays=delays;this.liveEdges=liveEdges;
        for(var e:graph.edges()){
            Estimate value;
            if(reportedClosures.contains(e.id()))value=Estimate.blocked("Reported closure");
            else if(liveEdges.contains(e.id())){
                value=safe(live.estimate(e,time));
                if(value.status().equals("UNKNOWN")){
                    Estimate fallback=safe(historical.estimate(e,time));
                    value=fallback.usable()?new Estimate("AVAILABLE",fallback.seconds(),"HISTORICAL_FALLBACK",value.reason()):fallback;
                }
            }else value=safe(historical.estimate(e,time));
            roads.put(e.id(),value);
        }
    }

    static Set<String> liveEdges(Graph graph, String origin, int horizon) {
        if(horizon < -1)throw new IllegalArgumentException("Invalid horizon");
        graph.node(origin);
        TreeSet<String> local=new TreeSet<>();Map<String,Integer> depth=new HashMap<>();ArrayDeque<String> queue=new ArrayDeque<>();depth.put(origin,0);queue.add(origin);
        while(!queue.isEmpty()){
            String node=queue.remove();int d=depth.get(node);if(horizon>=0&&d>=horizon)continue;
            for(var e:graph.outgoing(node)){local.add(e.id());if(!depth.containsKey(e.to())){depth.put(e.to(),d+1);queue.add(e.to());}}
        }
        return Collections.unmodifiableSet(local);
    }
    private Estimate safe(Estimate e){return e==null?Estimate.unknown("Estimate unavailable"):e;}
    public Set<String> liveEdges(){return liveEdges;}
    public Map<String,Estimate> roads(){return Collections.unmodifiableMap(roads);}
    public Estimate road(String edge){return roads.get(edge);}
    public Estimate junction(String incoming,String outgoing){return waits.computeIfAbsent(new Movement(incoming,outgoing),m->safe(delays.estimate(incoming,graph.edge(outgoing),time)));}
    public long time(){return time;}
}
