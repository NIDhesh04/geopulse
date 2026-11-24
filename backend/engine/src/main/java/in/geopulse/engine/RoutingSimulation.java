package in.geopulse.engine;
import java.util.*;
/** Headless routing with an optional deterministic traffic world. */
public final class RoutingSimulation {
    public record Ambulance(String id,String status,String node,String edge,double progress,String destination,List<String> route,
        Long activatedAt,Long arrivedAt,long replans,long reroutes,String reason,Double initialEta,Double estimatedArrival){}
    public record Event(long time,String type,String message){}
    public record Explanation(String routingRevision,long time,String incoming,List<RoutingPolicy.Candidate> candidates,Set<String> liveEdges,Map<String,Estimate> roads){}
    private final Graph graph;private final int horizon;private final JunctionDelayEstimator junctionDelay;
    private final RoutingPolicy router;
    private TrafficWorld traffic;
    private boolean priorityEnabled;
    private boolean prioritySuspended;
    private long routeVersion;
    private long junctionWait;
    private String observedDepartureJunction;
    private long time,replans,reroutes;private Long activatedAt,arrivedAt;private Double initialEta,estimatedArrival;
    private String node="n00_00",destination="n04_04",incoming="station-entry",edge,status="IDLE",reason;
    private double progress;private boolean needsPlan,planned;
    private List<String> route=new ArrayList<>();private Explanation explanation;
    private final Map<String,Set<String>> physical=new TreeMap<>();
    private final Map<String,Map<String,String>> incidents = new TreeMap<>();
    private final Map<String,Set<String>> reportedIncidents = new TreeMap<>();private final Set<String> reported=new TreeSet<>();
    private final List<Event> pending=new ArrayList<>();
    public RoutingSimulation(Graph graph,int horizon){this(graph,horizon,new M1ZeroJunctionDelay());}
    public RoutingSimulation(Graph graph,int horizon,JunctionDelayEstimator junctionDelay){
        this(graph, horizon, junctionDelay, new DijkstraRouter());
    }
    public RoutingSimulation(Graph graph,int horizon,JunctionDelayEstimator junctionDelay,RoutingPolicy router){
        this.router=Objects.requireNonNull(router);
        this.junctionDelay=Objects.requireNonNull(junctionDelay);this.graph=graph;this.horizon=horizon;if(!Set.of(0,2,-1).contains(horizon))throw new IllegalArgumentException("Horizon must be 0, 2 or all");}
    public static RoutingSimulation traffic(Graph graph, int horizon, boolean priorityEnabled) {
        var simulation = new RoutingSimulation(graph, horizon);
        simulation.traffic = TrafficWorld.fixture(graph);
        simulation.priorityEnabled = priorityEnabled;
        return simulation;
    }

    public TrafficWorld.View trafficState() {
        return traffic == null ? null : traffic.view();
    }

    public boolean prioritySuspended() { return prioritySuspended; }

    public long junctionWait() { return junctionWait; }

    public void suspendPriority(boolean suspended) {
        if (traffic == null || !priorityEnabled) throw new IllegalArgumentException("Priority is disabled for this run");
        prioritySuspended = suspended;
        emit("PRIORITY_POLICY", suspended ? "Priority suspended" : "Priority resumed");
    }

    public RoutingSimulation copy(){
        var c=new RoutingSimulation(graph,horizon,junctionDelay,router);c.time=time;c.replans=replans;c.reroutes=reroutes;c.activatedAt=activatedAt;c.arrivedAt=arrivedAt;c.initialEta=initialEta;c.estimatedArrival=estimatedArrival;
        c.node=node;c.destination=destination;c.incoming=incoming;c.edge=edge;c.status=status;c.reason=reason;c.progress=progress;c.needsPlan=needsPlan;c.planned=planned;c.route=new ArrayList<>(route);c.explanation=explanation;
        c.traffic = traffic == null ? null : traffic.copy();
        c.priorityEnabled = priorityEnabled;
        c.prioritySuspended = prioritySuspended;
        c.routeVersion = routeVersion;
        c.junctionWait = junctionWait;
        c.observedDepartureJunction = observedDepartureJunction;
        c.physical.putAll(physical);
        c.incidents.putAll(incidents);
        c.reportedIncidents.putAll(reportedIncidents);c.reported.addAll(reported);c.pending.addAll(pending);return c;
    }
    public Graph graph(){return graph;}public long time(){return time;}public int horizon(){return horizon;}
    public Ambulance ambulance(){return new Ambulance("AMB-001",status,node,edge,progress,destination,List.copyOf(route),activatedAt,arrivedAt,replans,reroutes,reason,initialEta,estimatedArrival);}
    public Explanation explanation(){return explanation;}
    public Set<String> reported(){
        var known = new TreeSet<>(reported);
        known.addAll(reportedIncidents.keySet());
        return Collections.unmodifiableSet(known);
    }
    public List<Event> drainEvents(){var events=List.copyOf(pending);pending.clear();return events;}
    private void emit(String type,String message){pending.add(new Event(time,type,message));}
    public void activate(String from,String to){
        if(!status.equals("IDLE"))throw new IllegalArgumentException("This scenario supports one mission per run; create a new run to restart");
        graph.node(from);graph.node(to);
        if (traffic != null && !from.equals("n00_00")) throw new IllegalArgumentException("Use the configured station entry");
        node=from;destination=to;incoming="station-entry:"+from;activatedAt=time;status="AT_JUNCTION";emit("MISSION_ACTIVATED","AMB-001 activated");
        if(from.equals(to)){initialEta=0.0;arrive();return;}plan();
    }
    public void incident(String road,String effect,boolean report){
        incident(road, effect, report, "operator");
    }

    public void incident(String road,String effect,boolean report,String incidentId){
        graph.edge(road);if (!Set.of("OPEN", "SLOW", "ENTRY_CLOSED", "IMPASSABLE").contains(effect)
                && (traffic == null || !Set.of("DISCHARGE_REDUCED", "DEMAND_SURGE").contains(effect))) {
            throw new IllegalArgumentException("Unsupported incident for this scenario");
        }
        if (effect.equals("DEMAND_SURGE") && !traffic.hasBoundaryEntry(road)) {
            throw new IllegalArgumentException("Demand changes require a boundary entry road");
        }
        var effects = new TreeMap<>(incidents.getOrDefault(road, Map.of()));
        if(effect.equals("OPEN")) effects.remove(incidentId);
        else effects.put(incidentId, effect);
        incidents.put(road, Map.copyOf(effects));
        if (effects.isEmpty()) physical.remove(road);
        else physical.put(road, Set.copyOf(effects.values()));
        if (report) {
            var known = new TreeSet<>(reportedIncidents.getOrDefault(road, Set.of()));
            if (effect.equals("ENTRY_CLOSED") || effect.equals("IMPASSABLE")) known.add(incidentId);
            else known.remove(incidentId);
            if (known.isEmpty()) reportedIncidents.remove(road);
            else reportedIncidents.put(road, Set.copyOf(known));
            if (effect.equals("OPEN")) reported.remove(road);
        }
        emit("PHYSICAL_INCIDENT",road+": "+effect+(report?" (reported)":" (unreported)"));
        if(edge==null&&activatedAt!=null&&arrivedAt==null)plan();
    }
    public void report(String road,boolean closed){
        graph.edge(road);
        if(closed)reported.add(road);
        else {
            reported.remove(road);
            reportedIncidents.remove(road);
        }
        emit("ROAD_REPORT",road+": "+(closed?"closed":"reopened"));
        if(edge==null&&activatedAt!=null&&arrivedAt==null)plan();
    }
    public void retry(){if(activatedAt==null||arrivedAt!=null||edge!=null)throw new IllegalArgumentException("Retry requires a waiting active mission");plan();}
    private double speed(Graph.Edge road){
        if (traffic != null) return traffic.speed(road, physical, ambulanceRoad(), edge != null);
        var effects = physical.getOrDefault(road.id(), Set.of());
        return effects.contains("IMPASSABLE") ? 0 : effects.contains("SLOW") ? 2 : road.freeSpeed();}
    private boolean closed(String id){var effects = physical.getOrDefault(id, Set.of());
        return effects.contains("ENTRY_CLOSED") || effects.contains("IMPASSABLE");}
    private void plan(){
        String oldStatus=status;String oldReason=reason;
        RoadWeightProvider live=(road,t)->closed(road.id())?Estimate.blocked("Observed closure"):Estimate.available(road.length()/speed(road),"LIVE");
        RoadWeightProvider historical=(road,t)->Estimate.available(road.length()/road.freeSpeed(),"HISTORICAL");
        Set<String> knownClosures = new TreeSet<>(reported());
        if (node.equals(observedDepartureJunction)) {
            graph.outgoing(node).stream().map(Graph.Edge::id).filter(this::closed).forEach(knownClosures::add);
        }
        var visible = RoutingSnapshot.liveEdges(graph, node, horizon);
        JunctionDelayEstimator estimator = junctionDelay;
        if (traffic != null) {
            historical = (road,t) -> Estimate.available(road.length() / traffic.historicalSpeed(road), "HISTORICAL");
            estimator = traffic.estimator(time, visible, Map.copyOf(physical), knownClosures, ambulanceRoad());
        }
        var snap = new RoutingSnapshot(graph, time, live, historical, estimator, knownClosures, visible);
        var result=router.route(graph,node,incoming,destination,snap);
        if(planned)replans++;explanation=new Explanation(Long.toString(replans+1),time,incoming,router.explain(graph,node,incoming,destination,snap,result),snap.liveEdges(),Map.copyOf(snap.roads()));
        if(result.reachable()){
            if(planned&&!route.isEmpty()&&!route.equals(result.edges())){reroutes++;emit("REROUTED","Route changed at "+node);}
            if (!route.equals(result.edges()) || !planned || oldStatus.equals("STOPPED")) routeVersion++;
            route=new ArrayList<>(result.edges());estimatedArrival=time+result.seconds();if(!planned)initialEta=result.seconds();
            status="AT_JUNCTION";reason=null;if(oldStatus.equals("STOPPED"))emit("ROUTE_RECOVERED","Feasible route available");
        }else{
            status="STOPPED";estimatedArrival=null;reason=graph.outgoing(node).stream().allMatch(e->snap.road(e.id()).status().equals("BLOCKED"))?"ALL_OUTGOING_BLOCKED":"DESTINATION_UNREACHABLE";
            if(!oldStatus.equals(status)||!Objects.equals(oldReason,reason))emit("OPERATOR_ALERT",reason);
        }
        planned=true;needsPlan=false;
    }
    public void step(){
        if (traffic != null) {
            stepTraffic();
            return;
        }
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
    private String ambulanceRoad() {
        if (activatedAt == null || arrivedAt != null) return null;
        return edge == null ? incoming : edge;
    }

    private void stepTraffic() {
        boolean active = activatedAt != null && arrivedAt == null;
        if (active && edge == null && (needsPlan || status.equals("STOPPED"))) plan();
        if (active && edge == null && status.equals("AT_JUNCTION") && !route.isEmpty()
                && closed(route.getFirst())) {
            observedDepartureJunction = node;
            plan();
        }
        JunctionService.Movement waiting = null;
        JunctionService.Movement next = null;
        double toRoadEnd = 0;
        if (active && edge == null && status.equals("AT_JUNCTION") && !route.isEmpty()) {
            String departure = route.getFirst();
            waiting = new JunctionService.Movement(incoming, departure);
            next = waiting;
        } else if (active && edge != null && route.size() >= 2) {
            var road = graph.edge(edge);
            double speed = speed(road);
            if (speed > 0) {
                next = new JunctionService.Movement(edge, route.get(1));
                toRoadEnd = (road.length() - progress) / speed;
            }
        }
        var request = priorityEnabled && !prioritySuspended ? traffic.request(next, toRoadEnd, routeVersion, physical) : null;
        String oldPriority = traffic.priority();
        double actualSpeed = edge == null ? 0 : speed(graph.edge(edge));
        var passed = traffic.step(time, physical, ambulanceRoad(), edge != null, waiting, request);
        if (!oldPriority.equals(passed.priority())) {
            emit("PRIORITY_" + passed.priority(), passed.priority().replace('_', ' '));
        }
        time++;
        if (!active) return;
        if (edge == null) {
            junctionWait++;
            if (passed.movement() != null) {
                observedDepartureJunction = null;
                edge = passed.movement().outgoing();
                progress = 0;
                status = "MOVING";
                reason = null;
                emit("ROAD_ENTERED", edge);
            }
            return;
        }
        if (actualSpeed <= 0) {
            if (!"ROAD_IMPASSABLE".equals(reason)) emit("OPERATOR_ALERT", "ROAD_IMPASSABLE");
            status = "STOPPED";
            reason = "ROAD_IMPASSABLE";
            estimatedArrival = null;
            return;
        }
        var road = graph.edge(edge);
        if ("ROAD_IMPASSABLE".equals(reason)) emit("ROAD_RECOVERED", edge);
        status = "MOVING";
        reason = null;
        progress = Math.min(road.length(), progress + actualSpeed);
        if (progress >= road.length()) {
            node = road.to();
            incoming = edge;
            edge = null;
            progress = 0;
            route.removeFirst();
            if (node.equals(destination)) arrive();
            else {
                status = "AT_JUNCTION";
                needsPlan = true;
                traffic.joinMovement(route.isEmpty() ? null : new JunctionService.Movement(incoming, route.getFirst()));
                emit("JUNCTION_REACHED", node);
            }
        }
    }

    private void arrive(){status="ARRIVED";reason=null;arrivedAt=time;estimatedArrival=(double)time;route.clear();emit("ARRIVED","Journey took "+(time-activatedAt)+" seconds");}
}
