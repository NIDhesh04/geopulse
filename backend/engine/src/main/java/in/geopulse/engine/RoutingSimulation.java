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
    private long junctionArrival;
    private JunctionService.Request priorityRequest;
    private String observedDepartureJunction;
    private long time,replans,reroutes;private Long activatedAt,arrivedAt;private Double initialEta,estimatedArrival;
    private String node="n00_00",destination="n04_04",incoming="station-entry",edge,status="IDLE",reason;
    private double progress;private boolean needsPlan,planned;
    private List<String> route=new ArrayList<>();private Explanation explanation;
    private final Map<String,Set<String>> physical=new TreeMap<>();
    private final Map<String,Map<String,String>> incidents = new TreeMap<>();
    private final Map<String,Set<String>> reportedIncidents = new TreeMap<>();private final Set<String> reported=new TreeSet<>();
    private final List<Event> pending=new ArrayList<>();
    private OperationalReports operationalReports = new OperationalReports();
    private HistoricalProfile historicalProfile;
    private long benchmarkJunctionForecasts;
    private String ambulanceId = "AMB-001";
    private final Map<String, RoutingSimulation> additionalMissions = new TreeMap<>();
    private boolean fleetEnabled;
    private String priorityStatus = "NONE";
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

    public static RoutingSimulation geographicTraffic(Graph graph, int horizon, boolean priorityEnabled, String origin,
                                                      long seed, HistoricalProfile profile) {
        graph.node(origin);
        var simulation = new RoutingSimulation(graph, horizon);
        simulation.traffic = TrafficWorld.geographicFixture(graph, origin, seed);
        simulation.historicalProfile = Objects.requireNonNull(profile);
        simulation.priorityEnabled = priorityEnabled;
        simulation.node = origin;
        return simulation;
    }

    public static RoutingSimulation predictableCongestion(int horizon, boolean priorityEnabled, long seed,
                                                          HistoricalProfile profile) {
        var simulation = traffic(Graph.grid(5), horizon, priorityEnabled);
        simulation.historicalProfile = Objects.requireNonNull(profile);
        simulation.traffic.enableCorridorDemand(seed);
        return simulation;
    }

    public static RoutingSimulation fleet(Graph graph, int horizon, boolean priorityEnabled) {
        return fleet(graph, horizon, priorityEnabled, fixtureOrigins(), TrafficWorld.fixture(graph, true), null);
    }

    static RoutingSimulation benchmark(Graph graph, Map<String,String> stations, long seed, boolean pulse, HistoricalProfile profile) {
        var world = TrafficWorld.benchmarkWorld(graph, Set.copyOf(stations.values()), seed, pulse, true);
        return fleet(graph, 0, false, stations, world, profile);
    }

    private static RoutingSimulation fleet(Graph graph, int horizon, boolean priorityEnabled, Map<String,String> stations,
                                           TrafficWorld world, HistoricalProfile profile) {
        var run = new RoutingSimulation(graph, horizon);
        run.traffic = world;
        run.historicalProfile = profile;
        run.node = Objects.requireNonNull(stations.get(run.ambulanceId));
        run.priorityEnabled = priorityEnabled;
        run.fleetEnabled = true;
        stations.forEach((id, origin) -> {
            if (run.ambulanceId.equals(id)) return;
            var mission = new RoutingSimulation(graph, horizon);
            mission.ambulanceId = id;
            mission.node = origin;
            mission.traffic = run.traffic;
            mission.historicalProfile = profile;
            mission.priorityEnabled = priorityEnabled;
            mission.fleetEnabled = true;
            run.additionalMissions.put(mission.ambulanceId, mission);
        });
        return run;
    }

    RoutingSimulation forkPolicy(int horizon, boolean priorityEnabled) {
        if (missions().stream().anyMatch(mission -> mission.activatedAt != null))
            throw new IllegalStateException("Fork a warmed state before mission activation");
        return copy(horizon, priorityEnabled);
    }

    TrafficWorld.Totals benchmarkTotals() { return traffic.totals(); }
    Map<String,JunctionService.State> benchmarkGrants() { return traffic.grants(); }
    long benchmarkForecastCount() { return missions().stream().mapToLong(mission -> mission.benchmarkJunctionForecasts).sum(); }
    int benchmarkFullRoads() { return traffic.fullRoads(); }
    List<Ambulance> benchmarkFleet() { return missions().stream().map(RoutingSimulation::ambulance).toList(); }
    List<JunctionService.Request> benchmarkRequests() {
        return missions().stream().map(mission -> mission.priorityRequest).filter(Objects::nonNull).toList();
    }

    String benchmarkWaiting(String id) {
        var mission = mission(id);
        if (mission.status.equals("STOPPED"))
            return "ROAD_IMPASSABLE".equals(mission.reason) ? "impassable" : "route_unavailable";
        if (!mission.status.equals("AT_JUNCTION") || mission.route.isEmpty()) return null;
        if (!traffic.receivingAvailable(mission.route.getFirst())) return "queue_or_receiving";
        return traffic.movementGreen(mission.node,mission.incoming) ? "queue_or_receiving" : "signal";
    }

    public static Map<String, String> fixtureOrigins() {
        var origins = new TreeMap<String, String>();
        for (int i = 1; i <= 10; i++) {
            origins.put("AMB-%03d".formatted(i), i <= 4 ? "n00_00" : i <= 7 ? "n00_04" : "n04_00");
        }
        return Collections.unmodifiableMap(origins);
    }

    private List<RoutingSimulation> missions() {
        var missions = new ArrayList<RoutingSimulation>();
        missions.add(this);
        missions.addAll(additionalMissions.values());
        return missions;
    }

    private RoutingSimulation mission(String id) {
        if (ambulanceId.equals(id)) return this;
        var selected = additionalMissions.get(id);
        if (selected == null) throw new IllegalArgumentException("Unknown ambulance");
        return selected;
    }

    public record MissionView(Ambulance ambulance, Explanation explanation, String priority,
                              boolean prioritySuspended, long junctionWait) {}

    public Map<String, MissionView> fleetView() {
        var result = new TreeMap<String, MissionView>();
        for (var mission : missions()) {
            result.put(mission.ambulanceId, new MissionView(mission.ambulance(), mission.explanation,
                    mission.priorityStatus, mission.prioritySuspended, mission.junctionWait));
        }
        return Collections.unmodifiableMap(result);
    }

    public boolean completed() {
        return missions().stream().allMatch(mission -> mission.arrivedAt != null);
    }

    public Map<String, Set<String>> physicalEffects() { return Map.copyOf(physical); }
    public Map<String, TrafficWorld.RoadTruth> roadTruth() { return traffic == null ? Map.of() : traffic.roadTruth(); }

    public void activate(String id, String from, String to) {
        mission(id).activate(from, to);
    }

    public void suspendPriority(String id, boolean suspended) { mission(id).suspendPriority(suspended); }
    public void retry(String id) { mission(id).retry(); }

    public TrafficWorld.View trafficState() {
        return traffic == null ? null : traffic.view();
    }

    public boolean prioritySuspended() { return prioritySuspended; }

    public long junctionWait() { return junctionWait; }

    public void suspendPriority(boolean suspended) {
        if (traffic == null || !priorityEnabled) throw new IllegalArgumentException("Priority is disabled for this run");
        prioritySuspended = suspended;
        if (suspended) priorityRequest = null;
        emit("PRIORITY_POLICY", suspended ? "Priority suspended" : "Priority resumed");
    }

    public RoutingSimulation copy(){
        return copy(horizon, priorityEnabled);
    }

    private RoutingSimulation copy(int horizon, boolean priorityEnabled) {
        var copy = copyMission(traffic == null ? null : traffic.copy(), horizon, priorityEnabled);
        additionalMissions.forEach((id, mission) -> copy.additionalMissions.put(id, mission.copyMission(copy.traffic, horizon, priorityEnabled)));
        return copy;
    }

    private RoutingSimulation copyMission(TrafficWorld world,int horizon,boolean priorityEnabled){
        var c=new RoutingSimulation(graph,horizon,junctionDelay,router);c.time=time;c.replans=replans;c.reroutes=reroutes;c.activatedAt=activatedAt;c.arrivedAt=arrivedAt;c.initialEta=initialEta;c.estimatedArrival=estimatedArrival;
        c.node=node;c.destination=destination;c.incoming=incoming;c.edge=edge;c.status=status;c.reason=reason;c.progress=progress;c.needsPlan=needsPlan;c.planned=planned;c.route=new ArrayList<>(route);c.explanation=explanation;
        c.traffic = world;
        c.ambulanceId = ambulanceId;
        c.fleetEnabled = fleetEnabled;
        c.priorityStatus = priorityStatus;
        c.priorityEnabled = priorityEnabled;
        c.prioritySuspended = prioritySuspended;
        c.routeVersion = routeVersion;
        c.junctionWait = junctionWait;
        c.junctionArrival = junctionArrival;
        c.priorityRequest = priorityRequest;
        c.historicalProfile = historicalProfile;
        c.benchmarkJunctionForecasts = benchmarkJunctionForecasts;
        c.operationalReports = operationalReports.copy();
        c.observedDepartureJunction = observedDepartureJunction;
        c.physical.putAll(physical);
        c.incidents.putAll(incidents);
        c.reportedIncidents.putAll(reportedIncidents);c.reported.addAll(reported);c.pending.addAll(pending);return c;
    }
    public Graph graph(){return graph;}public long time(){return time;}public int horizon(){return horizon;}
    public Ambulance ambulance(){return new Ambulance(ambulanceId,status,node,edge,progress,destination,List.copyOf(route),activatedAt,arrivedAt,replans,reroutes,reason,initialEta,estimatedArrival);}
    public Explanation explanation(){return explanation;}
    public Set<String> reported(){
        var known = new TreeSet<>(reported);
        known.addAll(reportedIncidents.keySet());
        known.addAll(operationalReports.confirmedClosures());
        return Collections.unmodifiableSet(known);
    }
    public OperationalReports operationalReports() { return operationalReports; }

    public void submitObstruction(String id, String ambulanceId, String road, boolean closure) {
        graph.edge(road);
        mission(ambulanceId);
        operationalReports.submit(id, ambulanceId, road, closure, time);
        emit("REPORT_SUBMITTED", id + " awaiting operator review");
    }

    public void reviewObstruction(String id, boolean confirmed) {
        operationalReports.review(id, confirmed, time);
        emit("REPORT_REVIEWED", id + (confirmed ? " confirmed" : " rejected"));
        if (confirmed) {
            var report = operationalReports.reports().get(id);
            if (!report.closure()) {
                reported.remove(report.road());
                reportedIncidents.remove(report.road());
            }
            refreshWaitingMissions(null);
        }
    }

    public void acknowledgeAlert(String id) {
        operationalReports.acknowledge(id, time);
        emit("ALERT_ACKNOWLEDGED", id);
    }
    public List<Event> drainEvents(){
        var events = new ArrayList<Event>();
        for (var mission : missions()) {
            events.addAll(mission.pending);
            mission.pending.clear();
        }
        events.sort(Comparator.comparingLong(Event::time));
        return List.copyOf(events);
    }
    private void emit(String type,String message){pending.add(new Event(time,type,message));}
    public void activate(String from,String to){
        if(!status.equals("IDLE"))throw new IllegalArgumentException("This scenario supports one mission per run; create a new run to restart");
        graph.node(from);graph.node(to);
        if (traffic != null && !from.equals(node))
            throw new IllegalArgumentException("Use the configured station entry");
        node=from;destination=to;incoming="station-entry:"+from;activatedAt=time;junctionArrival=time;status="AT_JUNCTION";emit("MISSION_ACTIVATED",ambulanceId+" activated");
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
        refreshWaitingMissions(report ? null : road);
    }
    public void report(String road,boolean closed){
        graph.edge(road);
        if(closed)reported.add(road);
        else {
            reported.remove(road);
            reportedIncidents.remove(road);
            operationalReports.reopen(road);
        }
        emit("ROAD_REPORT",road+": "+(closed?"closed":"reopened"));
        refreshWaitingMissions(null);
    }

    private void refreshWaitingMissions(String locallyChangedRoad) {
        var known = reported();
        for (var mission : missions()) {
            if (mission != this) {
                mission.physical.clear();
                mission.physical.putAll(physical);
                mission.reported.clear();
                mission.reported.addAll(known);
            }
            if (mission.edge != null || mission.activatedAt == null || mission.arrivedAt != null) continue;
            boolean observed = locallyChangedRoad == null
                    || RoutingSnapshot.liveEdges(graph, mission.node, mission.horizon).contains(locallyChangedRoad)
                    || (mission.node.equals(mission.observedDepartureJunction)
                        && graph.edge(locallyChangedRoad).from().equals(mission.node));
            if (!fleetEnabled || observed) mission.plan();
        }
    }
    public void retry(){if(activatedAt==null||arrivedAt!=null||edge!=null)throw new IllegalArgumentException("Retry requires a waiting active mission");plan();}
    private double speed(Graph.Edge road){
        if (traffic != null) return traffic.fleetSpeed(road, physical);
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
            estimator = traffic.estimator(time, visible, Map.copyOf(physical), knownClosures, ambulanceRoad(), ambulanceId);
        }
        var snap = new RoutingSnapshot(graph, time, live, historical, estimator, knownClosures, visible, historicalProfile);
        var result=router.route(graph,node,incoming,destination,snap);
        if(planned)replans++;explanation=new Explanation(Long.toString(replans+1),time,incoming,router.explain(graph,node,incoming,destination,snap,result),snap.liveEdges(),Map.copyOf(snap.roadsForRoute(result.edges(), incoming)));
        benchmarkJunctionForecasts += snap.cachedJunctionEstimates();
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
        var missions = missions();
        traffic.observeFleet(missions.stream().map(mission -> mission.vehicle(null)).toList());
        var prepared = missions.stream().map(RoutingSimulation::prepareTraffic).toList();
        var result = traffic.stepFleet(time, physical, prepared.stream().map(Prepared::vehicle).toList(),
                missions.stream().map(mission -> mission.priorityRequest).filter(Objects::nonNull).toList());
        for (int index = 0; index < missions.size(); index++) {
            var mission = missions.get(index);
            mission.advanceTraffic(prepared.get(index), result.crossings().get(mission.ambulanceId),
                    result.priorities().getOrDefault(mission.ambulanceId, "NONE"));
        }
        traffic.observeFleet(missions.stream().map(mission -> mission.vehicle(null)).toList());
    }

    private record Prepared(TrafficWorld.Vehicle vehicle, boolean active, double speed) {}

    private TrafficWorld.Vehicle vehicle(JunctionService.Movement waiting) {
        return new TrafficWorld.Vehicle(ambulanceId, ambulanceRoad(), edge != null, waiting);
    }

    private Prepared prepareTraffic() {
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
        priorityRequest = priorityEnabled && !prioritySuspended
                ? traffic.request(ambulanceId, next, toRoadEnd, routeVersion, time, junctionArrival, priorityRequest, physical)
                : null;
        double actualSpeed = edge == null ? 0 : speed(graph.edge(edge));
        return new Prepared(vehicle(waiting), active, actualSpeed);
    }

    private void advanceTraffic(Prepared prepared, JunctionService.Movement passed, String priority) {
        if (!priorityStatus.equals(priority)) {
            emit("PRIORITY_" + priority, priority.replace('_', ' '));
        }
        priorityStatus = priority;
        time++;
        if (!prepared.active()) return;
        if (edge == null) {
            junctionWait++;
            if (passed != null) {
                observedDepartureJunction = null;
                edge = passed.outgoing();
                progress = 0;
                status = "MOVING";
                reason = null;
                emit("ROAD_ENTERED", edge);
            }
            return;
        }
        if (prepared.speed() <= 0) {
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
        progress = Math.min(road.length(), progress + prepared.speed());
        if (progress >= road.length()) {
            junctionArrival = time;
            node = road.to();
            incoming = edge;
            edge = null;
            progress = 0;
            route.removeFirst();
            if (node.equals(destination)) arrive();
            else {
                status = "AT_JUNCTION";
                needsPlan = true;
                traffic.joinMovement(ambulanceId,
                        route.isEmpty() ? null : new JunctionService.Movement(incoming, route.getFirst()));
                emit("JUNCTION_REACHED", node);
            }
        }
    }

    private void arrive(){status="ARRIVED";reason=null;arrivedAt=time;estimatedArrival=(double)time;route.clear();emit("ARRIVED","Journey took "+(time-activatedAt)+" seconds");}
}
