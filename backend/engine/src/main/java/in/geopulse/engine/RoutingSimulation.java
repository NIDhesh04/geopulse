package in.geopulse.engine;
import java.util.*;
/** Headless M1 routing fixture. No civilian queues or signal service are simulated here. */
public final class RoutingSimulation {
    public record Ambulance(String id,String status,String node,String edge,double progress,String destination,List<String> route,
        Long activatedAt,Long arrivedAt,long replans,long reroutes,String reason,Double initialEta,Double estimatedArrival){}
    public record Event(long time,String type,String message){}
    public record Explanation(String routingRevision,long time,String incoming,List<RoutingPolicy.Candidate> candidates,Set<String> liveEdges,Map<String,Estimate> roads){}
    private final Graph graph;private final int horizon;private final JunctionDelayEstimator junctionDelay;
    private final RoutingPolicy router;
    private long time,replans,reroutes;private Long activatedAt,arrivedAt;private Double initialEta,estimatedArrival;
    private String node="n00_00",destination="n04_04",incoming="station-entry",edge,status="IDLE",reason;
    private double progress;private boolean needsPlan,planned;
    private List<String> route=new ArrayList<>();private Explanation explanation;
    private final Map<String,String> physical=new TreeMap<>();private final Set<String> reported=new TreeSet<>();
    private final List<Event> pending=new ArrayList<>();
    public RoutingSimulation(Graph graph,int horizon){this(graph,horizon,new M1ZeroJunctionDelay());}
    public RoutingSimulation(Graph graph,int horizon,JunctionDelayEstimator junctionDelay){
        this(graph, horizon, junctionDelay, new DijkstraRouter());
    }
    public RoutingSimulation(Graph graph,int horizon,JunctionDelayEstimator junctionDelay,RoutingPolicy router){
        this.router=Objects.requireNonNull(router);
        this.junctionDelay=Objects.requireNonNull(junctionDelay);this.graph=graph;this.horizon=horizon;if(!Set.of(0,2,-1).contains(horizon))throw new IllegalArgumentException("Horizon must be 0, 2 or all");}
    public RoutingSimulation copy(){
        var c=new RoutingSimulation(graph,horizon,junctionDelay,router);c.time=time;c.replans=replans;c.reroutes=reroutes;c.activatedAt=activatedAt;c.arrivedAt=arrivedAt;c.initialEta=initialEta;c.estimatedArrival=estimatedArrival;
        c.node=node;c.destination=destination;c.incoming=incoming;c.edge=edge;c.status=status;c.reason=reason;c.progress=progress;c.needsPlan=needsPlan;c.planned=planned;c.route=new ArrayList<>(route);c.explanation=explanation;
        c.physical.putAll(physical);c.reported.addAll(reported);c.pending.addAll(pending);return c;
    }
    public Graph graph(){return graph;}public long time(){return time;}public int horizon(){return horizon;}
    public Ambulance ambulance(){return new Ambulance("AMB-001",status,node,edge,progress,destination,List.copyOf(route),activatedAt,arrivedAt,replans,reroutes,reason,initialEta,estimatedArrival);}
    public Explanation explanation(){return explanation;}
    public Map<String,String> physical(){return Map.copyOf(physical);}public Set<String> reported(){return Set.copyOf(reported);}
    public List<Event> drainEvents(){var events=List.copyOf(pending);pending.clear();return events;}
    private void emit(String type,String message){pending.add(new Event(time,type,message));}
    public void activate(String from,String to){
        if(!status.equals("IDLE"))throw new IllegalArgumentException("M1 supports one mission per run; create a new run to restart");
        graph.node(from);graph.node(to);node=from;destination=to;incoming="station-entry:"+from;activatedAt=time;status="AT_JUNCTION";emit("MISSION_ACTIVATED","AMB-001 activated");
        if(from.equals(to)){initialEta=0.0;arrive();return;}plan();
    }
    public void incident(String road,String effect,boolean report){
        graph.edge(road);if(!Set.of("OPEN","SLOW","ENTRY_CLOSED","IMPASSABLE").contains(effect))throw new IllegalArgumentException("Unsupported M1 incident");
        if(effect.equals("OPEN"))physical.remove(road);else physical.put(road,effect);
        if(report){if(effect.equals("ENTRY_CLOSED")||effect.equals("IMPASSABLE"))reported.add(road);else if(effect.equals("OPEN"))reported.remove(road);}
        emit("PHYSICAL_INCIDENT",road+": "+effect+(report?" (reported)":" (unreported)"));
        if(edge==null&&activatedAt!=null&&arrivedAt==null)plan();
    }
    public void report(String road,boolean closed){graph.edge(road);if(closed)reported.add(road);else reported.remove(road);emit("ROAD_REPORT",road+": "+(closed?"closed":"reopened"));if(edge==null&&activatedAt!=null&&arrivedAt==null)plan();}
    public void retry(){if(activatedAt==null||arrivedAt!=null||edge!=null)throw new IllegalArgumentException("Retry requires a waiting active mission");plan();}
    private double speed(Graph.Edge road){return physical.getOrDefault(road.id(),"").equals("IMPASSABLE")?0:physical.getOrDefault(road.id(),"").equals("SLOW")?2:road.freeSpeed();}
    private boolean closed(String id){return Set.of("ENTRY_CLOSED","IMPASSABLE").contains(physical.getOrDefault(id,""));}
    private void plan(){
        String oldStatus=status;String oldReason=reason;
        RoadWeightProvider live=(road,t)->closed(road.id())?Estimate.blocked("Observed closure"):Estimate.available(road.length()/speed(road),"LIVE");
        RoadWeightProvider historical=(road,t)->Estimate.available(road.length()/road.freeSpeed(),"HISTORICAL");
        var snap=new RoutingSnapshot(graph,node,horizon,time,live,historical,junctionDelay,reported);
        var result=router.route(graph,node,incoming,destination,snap);
        if(planned)replans++;explanation=new Explanation(Long.toString(replans+1),time,incoming,router.explain(graph,node,incoming,destination,snap,result),snap.liveEdges(),Map.copyOf(snap.roads()));
        if(result.reachable()){
            if(planned&&!route.isEmpty()&&!route.equals(result.edges())){reroutes++;emit("REROUTED","Route changed at "+node);}
            route=new ArrayList<>(result.edges());estimatedArrival=time+result.seconds();if(!planned)initialEta=result.seconds();
            status="AT_JUNCTION";reason=null;if(oldStatus.equals("STOPPED"))emit("ROUTE_RECOVERED","Feasible route available");
        }else{
            status="STOPPED";estimatedArrival=null;reason=graph.outgoing(node).stream().allMatch(e->snap.road(e.id()).status().equals("BLOCKED"))?"ALL_OUTGOING_BLOCKED":"DESTINATION_UNREACHABLE";
            if(!oldStatus.equals(status)||!Objects.equals(oldReason,reason))emit("OPERATOR_ALERT",reason);
        }
        planned=true;needsPlan=false;
    }
    public void step(){
        if(activatedAt==null||arrivedAt!=null){time++;return;}
        if(edge!=null){
            var road=graph.edge(edge);double v=speed(road);
            if(v==0){if(!"ROAD_IMPASSABLE".equals(reason))emit("OPERATOR_ALERT","ROAD_IMPASSABLE");status="STOPPED";reason="ROAD_IMPASSABLE";estimatedArrival=null;time++;return;}
            if("ROAD_IMPASSABLE".equals(reason))emit("ROAD_RECOVERED",edge);
            status="MOVING";reason=null;progress=Math.min(road.length(),progress+v);time++;
            if(progress>=road.length()){
                node=road.to();incoming=edge;edge=null;progress=0;if(!route.isEmpty())route.removeFirst();
                if(node.equals(destination))arrive();else{status="AT_JUNCTION";needsPlan=true;emit("JUNCTION_REACHED",node);}
            }return;
        }
        if(needsPlan||status.equals("STOPPED"))plan();
        if(!route.isEmpty()&&status.equals("AT_JUNCTION")){
            String next=route.getFirst();if(closed(next)){status="STOPPED";reason="ENTRY_CLOSED";estimatedArrival=null;emit("OPERATOR_ALERT","Entry blocked: "+next);}
            else{edge=next;progress=0;status="MOVING";reason=null;emit("ROAD_ENTERED",edge);}
        }time++;
    }
    private void arrive(){status="ARRIVED";reason=null;arrivedAt=time;estimatedArrival=(double)time;route.clear();emit("ARRIVED","Journey took "+(time-activatedAt)+" seconds");}
}
