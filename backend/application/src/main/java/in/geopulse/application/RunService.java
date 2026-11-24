package in.geopulse.application;

import com.fasterxml.jackson.databind.*;
import in.geopulse.engine.*;
import jakarta.annotation.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;

@Service
public class RunService {
    public record Command(UUID commandId,String type,JsonNode payload){}
    public static class ApiException extends RuntimeException {
        public final int status;public ApiException(int status,String message){super(message);this.status=status;}
    }
    private static final String SCENARIO="routing-only-5x5";
    private static final String TRAFFIC_SCENARIO = "traffic-signals-5x5";
    private static final String FLEET_SCENARIO = "fleet-conflict-5x5";
    private static final String JAIPUR_SCENARIO = "jaipur-sms-corridor";
    private static final String PROFILE_RESOURCE = "/scenarios/" + CalibrationRunner.SCENARIO + ".profile.tsv";
    private final HistoricalProfile congestionProfile = readCongestionProfile();
    private final Map<String,Object> jaipurScenario;
    private final JdbcTemplate db;private final ObjectMapper json;private final TransactionTemplate tx;private final SimpMessagingTemplate messages;
    private final ConcurrentMap<UUID,Run> active=new ConcurrentHashMap<>();
    private static final class Run {
        final UUID id;final long seed;final String scenarioId;final boolean priorityEnabled;final ScheduledExecutorService loop;
        RoutingSimulation simulation;long revision,eventSequence;boolean paused=true;int speed=1;
        volatile boolean fault;
        volatile Published published;
        long lastTick=System.nanoTime(),lastPublish;double credit;
        Run(UUID id,long seed,int horizon,String scenarioId,boolean priorityEnabled,HistoricalProfile profile,Map<String,Object> definition){
            this.id=id;this.seed=seed;this.scenarioId=scenarioId;this.priorityEnabled=priorityEnabled;
            simulation = switch (scenarioId) {
                case FLEET_SCENARIO -> RoutingSimulation.fleet(Graph.grid(5), horizon, priorityEnabled);
                case TRAFFIC_SCENARIO -> RoutingSimulation.traffic(Graph.grid(5), horizon, priorityEnabled);
                case CalibrationRunner.SCENARIO -> RoutingSimulation.predictableCongestion(horizon, priorityEnabled, seed, profile);
                case JAIPUR_SCENARIO -> RoutingSimulation.geographicTraffic((Graph) definition.get("graph"),
                        horizon, priorityEnabled, (String) definition.get("origin"));
                default -> new RoutingSimulation(Graph.grid(5), horizon);
            };
            loop=Executors.newSingleThreadScheduledExecutor(r->{Thread t=new Thread(r,"run-"+id);t.setDaemon(true);return t;});}
    }
    private record Published(Map<String, Object> operational, Map<String, RoutingSimulation.MissionView> fleet,
                             Map<String, Set<String>> physicalEffects, Map<String, TrafficWorld.RoadTruth> roadTruth) {}
    public RunService(JdbcTemplate db,ObjectMapper json,TransactionTemplate tx,SimpMessagingTemplate messages){
        this.db=db;this.json=json;this.tx=tx;this.messages=messages;
        try (var resource = RunService.class.getResourceAsStream("/scenarios/" + JAIPUR_SCENARIO + ".json")) {
            if (resource == null) throw new IllegalStateException("Missing Jaipur corridor scenario");
            var definition = json.readValue(resource, new com.fasterxml.jackson.core.type.TypeReference<Map<String,Object>>() {});
            definition.put("graph", json.convertValue(definition.get("graph"), Graph.class));
            jaipurScenario = Map.copyOf(definition);
        } catch (IOException e) {
            throw new IllegalStateException("Invalid Jaipur corridor scenario", e);
        }
    }
    static HistoricalProfile readCongestionProfile() {
        var resource = RunService.class.getResourceAsStream(PROFILE_RESOURCE);
        if (resource == null) throw new IllegalStateException("Missing profile: " + PROFILE_RESOURCE);
        try (var reader = new BufferedReader(new InputStreamReader(resource, StandardCharsets.UTF_8))) {
            return HistoricalProfile.read(reader);
        } catch (IOException | IllegalArgumentException e) {
            throw new IllegalStateException("Invalid profile: " + PROFILE_RESOURCE, e);
        }
    }
    private String encode(Object data){try{return json.writeValueAsString(data);}catch(Exception e){throw new IllegalStateException("Cannot encode state",e);}}
    @PostConstruct void startup(){
        tx.executeWithoutResult(s->{
            db.update("update run_command set status='REJECTED', reason='RUN_INTERRUPTED' where status='ACCEPTED'");
            db.update("update simulation_run set status='INTERRUPTED' where status in ('RUNNING','PAUSED')");
            for (var definition : scenarios()) {
                db.update("insert into scenario_definition(id,version,definition) values (?,1,?::jsonb) on conflict(id) do nothing",
                        definition.get("id"),encode(definition));
            }
        });
    }
    @PreDestroy void shutdown(){active.values().forEach(r->r.loop.shutdownNow());}
    public Map<String,Object> scenario(){return Map.of("id",SCENARIO,"version",1,"mode","ROUTING_ONLY","name","Central district · routing laboratory","graph",Graph.grid(5),"origin","n00_00","destination","n04_04","junctionEstimator","M1_ZERO_WAIT");}
    public List<Map<String,Object>> scenarios(){
        var trafficScenario = new LinkedHashMap<>(scenario());
        trafficScenario.put("id", TRAFFIC_SCENARIO);
        trafficScenario.put("mode", "TRAFFIC_SIGNALS");
        trafficScenario.put("name", "Central district · traffic and signals");
        trafficScenario.put("junctionEstimator", "BOUNDED_JUNCTION_FORECAST");
        var fleetScenario = new LinkedHashMap<>(trafficScenario);
        fleetScenario.put("id", FLEET_SCENARIO);
        fleetScenario.put("mode", "FLEET_TRAFFIC");
        fleetScenario.put("name", "Central district · ten ambulance conflict");
        fleetScenario.put("departureByAmbulance", RoutingSimulation.fixtureOrigins());
        var congestionScenario = new LinkedHashMap<>(trafficScenario);
        congestionScenario.put("id", CalibrationRunner.SCENARIO);
        congestionScenario.put("mode", "PREDICTABLE_CONGESTION");
        congestionScenario.put("name", "Central district · predictable corridor congestion");
        congestionScenario.put("destination", "n00_04");
        congestionScenario.put("demoSeed", CalibrationRunner.DEMO_SEED);
        congestionScenario.put("historicalProfile", Map.of("resource", PROFILE_RESOURCE, "formatVersion", 1,
                "bucketSeconds", congestionProfile.bucketSeconds(), "buckets", congestionProfile.buckets(),
                "calibrationSeeds", congestionProfile.seeds()));
        return List.of(scenario(), trafficScenario, fleetScenario, congestionScenario, jaipurScenario);
    }

    public Map<String,Object> create(String horizon,long seed){
        return create(horizon, seed, null, false);
    }

    public synchronized Map<String,Object> create(String horizon,long seed,String scenarioId,Boolean priority){
        String selected = scenarioId == null ? SCENARIO : scenarioId;
        var definition = new LinkedHashMap<>(scenarios().stream()
                .filter(item -> selected.equals(item.get("id"))).findFirst()
                .orElseThrow(() -> new ApiException(400,"Unknown scenario")));
        boolean priorityEnabled = !SCENARIO.equals(selected) && !Boolean.FALSE.equals(priority);
        definition.put("priorityEnabled", priorityEnabled);
        int h=switch(horizon){case "0"->0;case "2"->2;case "all"->-1;default->throw new ApiException(400,"Horizon must be 0, 2 or all");};
        UUID id=UUID.randomUUID();Run r=new Run(id,seed,h,selected,priorityEnabled,congestionProfile,definition);
        db.update("insert into simulation_run(id,scenario_id,scenario_snapshot,seed,horizon,status) values (?,?,?::jsonb,?,?,'PAUSED')",id,selected,encode(definition),seed,horizon);
        r.published=publishable(r,r.simulation,0,0,true,1);active.put(id,r);r.loop.scheduleWithFixedDelay(()->tick(r),100,100,TimeUnit.MILLISECONDS);return r.published.operational();
    }
    private Run require(UUID id){Run r=active.get(id);if(r!=null)return r;var rows=db.queryForList("select status from simulation_run where id=?",id);if(rows.isEmpty())throw new ApiException(404,"Run not found");throw new ApiException(410,"Live snapshot unavailable: "+rows.getFirst().get("status")+". Create a new run.");}
    public Map<String,Object> snapshot(UUID id){Run r=require(id);var view=r.published.operational();if(r.fault){var out=new LinkedHashMap<>(view);out.put("runStatus","PERSISTENCE_FAULT");return out;}return view;}
    public RoutingSimulation.MissionView mission(UUID id, String ambulanceId) {
        var selected = require(id).published.fleet().get(ambulanceId);
        if (selected == null) throw new ApiException(404,"Ambulance not found");
        return selected;
    }
    public Map<String,Object> simulationTruth(UUID id) {
        var published = require(id).published;
        return Map.of("stateRevision", published.operational().get("stateRevision"),
                "simulationTimeSeconds", published.operational().get("simulationTimeSeconds"),
                "physicalEffects", published.physicalEffects(), "roads", published.roadTruth());
    }
    public synchronized Map<String,Object> accept(UUID runId,Command command){
        if(command==null||command.commandId()==null||command.type()==null||command.payload()==null||!command.payload().isObject())throw new ApiException(400,"commandId, type and object payload are required");
        var existing=db.queryForList("select type,payload from run_command where run_id=? and id=?",runId,command.commandId());
        if(!existing.isEmpty()){
            try{var old=existing.getFirst();if(!old.get("type").equals(command.type())||!json.readTree(old.get("payload").toString()).equals(command.payload()))throw new ApiException(409,"Command ID already has different content");}
            catch(com.fasterxml.jackson.core.JsonProcessingException e){throw new IllegalStateException(e);}return command(runId,command.commandId());
        }
        Run r=require(runId);if(r.fault)throw new ApiException(503,"Run stopped after persistence failure");
        tx.executeWithoutResult(s->{long sequence=db.queryForObject("update simulation_run set acceptance_sequence=acceptance_sequence+1 where id=? returning acceptance_sequence",Long.class,runId);
            db.update("insert into run_command(run_id,id,acceptance_sequence,type,payload,status) values (?,?,?,?,?::jsonb,'ACCEPTED')",runId,command.commandId(),sequence,command.type(),encode(command.payload()));});
        r.loop.execute(()->apply(r,command,false));return command(runId,command.commandId());
    }
    public Map<String,Object> command(UUID run,UUID command){var rows=db.queryForList("select id::text as command_id,type,status,applied_tick,boundary_ordinal::text,reason,acceptance_sequence::text from run_command where run_id=? and id=?",run,command);if(rows.isEmpty())throw new ApiException(404,"Command not found");return rows.getFirst();}
    public List<Map<String,Object>> events(UUID run,long after){
        if(after<0)throw new ApiException(400,"Event cursor cannot be negative");
        return db.query("select sequence,tick,type,payload from run_event where run_id=? and sequence>? order by sequence limit 200",(rs,n)->{
            Map<String,Object> event=new LinkedHashMap<>();event.put("sequence",Long.toString(rs.getLong(1)));event.put("time",rs.getLong(2));event.put("type",rs.getString(3));
            try{event.put("data",json.readTree(rs.getString(4)));}catch(Exception e){throw new IllegalStateException(e);}return event;},run,after);
    }
    public Map<String,Object> results(UUID id){
        var rows=db.queryForList("select id::text,status,simulation_time,revision::text,ambulance_result,traffic_result from simulation_run where id=?",id);if(rows.isEmpty())throw new ApiException(404,"Run not found");
        var result=new LinkedHashMap<>(rows.getFirst());Run r=active.get(id);if(r!=null)result.put("ambulance",r.published.operational().get("ambulance"));
        else if(result.get("ambulance_result")!=null)try{result.put("ambulance",json.readTree(result.get("ambulance_result").toString()));}catch(Exception e){throw new IllegalStateException(e);}
        result.remove("ambulance_result");
        var trafficResult = result.remove("traffic_result");
        if (trafficResult != null) try {
            result.put("traffic", json.readTree(trafficResult.toString()));
        } catch (com.fasterxml.jackson.core.JsonProcessingException e) {
            throw new IllegalStateException("Cannot decode traffic results", e);
        }
        return result;
    }
    private String text(JsonNode p,String name){if(!p.path(name).isTextual()||p.path(name).asText().isBlank())throw new IllegalArgumentException(name+" must be a nonempty string");return p.path(name).asText();}
    private String ambulanceId(JsonNode payload) {
        return payload.has("ambulanceId") ? text(payload, "ambulanceId") : "AMB-001";
    }
    private void tick(Run r){
        try{
            long now=System.nanoTime();double seconds=(now-r.lastTick)/1_000_000_000.0;r.lastTick=now;
            if(r.fault)return;
            if(r.paused){r.credit=0;if(now-r.lastPublish>=2_000_000_000L)publishState(r);return;}
            r.credit=Math.min(60,r.credit+seconds*r.speed);
            // One boundary per task lets accepted commands enter between ticks.
            if(r.credit>=1){int steps=Math.min(6,(int)r.credit);r.credit-=steps;for(int i=0;i<steps;i++)r.loop.execute(()->{if(!r.paused&&!r.fault)apply(r,null,true);});}
        }catch(RuntimeException e){r.fault=true;}
    }
    private void apply(Run r,Command command,boolean advance){
        if(r.fault)return;
        RoutingSimulation candidate=r.simulation.copy();boolean paused=r.paused;int speed=r.speed;String outcome="APPLIED",rejection=null;
        try{
            if(command!=null){JsonNode p=command.payload();switch(command.type()){
                case "ACTIVATE"->candidate.activate(ambulanceId(p),text(p,"origin"),text(p,"destination"));
                case "PLAY"->{if(candidate.completed())throw new IllegalArgumentException("Journey completed; create a new run");paused=false;}
                case "PAUSE"->paused=true;
                case "STEP"->{if(!paused)throw new IllegalArgumentException("Pause before stepping");if(candidate.completed())throw new IllegalArgumentException("Journey completed");candidate.step();}
                case "SET_SPEED"->{if(!p.path("speed").isIntegralNumber()||!Set.of(1,5,10,30,60).contains(p.path("speed").asInt()))throw new IllegalArgumentException("Speed must be 1, 5, 10, 30 or 60");speed=p.path("speed").asInt();}
                case "INCIDENT"->{if(p.has("reported")&&!p.path("reported").isBoolean())throw new IllegalArgumentException("reported must be boolean");
                    if (FLEET_SCENARIO.equals(r.scenarioId) && p.path("reported").asBoolean())
                        throw new IllegalArgumentException("Use a separate operational report");
                    candidate.incident(text(p,"edge"),text(p,"effect"),p.path("reported").asBoolean(),
                            p.has("incidentId") ? text(p,"incidentId") : "operator");}
                case "REPORT_CLOSURE"->candidate.report(text(p,"edge"),true);
                case "REPORT_REOPENING"->candidate.report(text(p,"edge"),false);
                case "RETRY_ROUTE"->candidate.retry(ambulanceId(p));
                case "SUBMIT_OBSTRUCTION"->{
                    if (!p.path("closure").isBoolean()) throw new IllegalArgumentException("closure must be boolean");
                    candidate.submitObstruction(text(p,"reportId"),text(p,"ambulanceId"),text(p,"edge"),p.path("closure").booleanValue());
                }
                case "REVIEW_OBSTRUCTION"->{
                    if (!p.path("confirmed").isBoolean()) throw new IllegalArgumentException("confirmed must be boolean");
                    candidate.reviewObstruction(text(p,"reportId"),p.path("confirmed").booleanValue());
                }
                case "ACKNOWLEDGE_ALERT"->candidate.acknowledgeAlert(text(p,"alertId"));
                case "SUSPEND_PRIORITY"->{
                    if (!p.path("suspended").isBoolean()) throw new IllegalArgumentException("suspended must be boolean");
                    candidate.suspendPriority(ambulanceId(p),p.path("suspended").booleanValue());
                }
                default->throw new IllegalArgumentException("Unsupported command: "+command.type());
            }}else if(advance)candidate.step();
        }catch(IllegalArgumentException e){outcome="REJECTED";rejection=e.getMessage();candidate=r.simulation.copy();paused=r.paused;speed=r.speed;}
        if(candidate.completed())paused=true;
        List<RoutingSimulation.Event> emitted=new ArrayList<>(candidate.drainEvents());
        boolean privateIncident = command != null && FLEET_SCENARIO.equals(r.scenarioId) && command.type().equals("INCIDENT");
        if (privateIncident) emitted.removeIf(event -> event.type().equals("PHYSICAL_INCIDENT"));
        if(command!=null && !privateIncident)emitted.add(new RoutingSimulation.Event(candidate.time(),"COMMAND_"+outcome,command.type()+": "+(rejection==null?"applied":rejection)));
        final RoutingSimulation next=candidate;final String appliedOutcome=outcome,reason=rejection;
        final long revision=r.revision+1,lastEvent=r.eventSequence+emitted.size();
        String runStatus=candidate.completed()?"COMPLETED":paused?"PAUSED":"RUNNING";
        List<Map<String,Object>> notifications=new ArrayList<>();long seq=r.eventSequence;
        for(var event:emitted){Map<String,Object> data=new LinkedHashMap<>();data.put("message",event.type().equals("PHYSICAL_INCIDENT")?"Physical scenario changed":event.message());if(command!=null)data.put("commandId",command.commandId().toString());notifications.add(Map.of("sequence",Long.toString(++seq),"time",event.time(),"type",event.type(),"data",data));}
        try{
            tx.executeWithoutResult(s->{
                if(command!=null)db.update("update run_command set status=?,applied_tick=?,boundary_ordinal=?,reason=? where run_id=? and id=?",appliedOutcome,r.simulation.time(),revision,reason,r.id,command.commandId());
                for(var event:notifications)db.update("insert into run_event(run_id,sequence,tick,type,payload) values (?,?,?,?,?::jsonb)",r.id,Long.parseLong(event.get("sequence").toString()),event.get("time"),event.get("type"),encode(event.get("data")));
                var traffic = next.trafficState();
                var measurements = new LinkedHashMap<String, Object>();
                if (traffic != null) {
                    measurements.put("civilian", traffic.totals());
                    measurements.put("ambulanceJunctionWait", next.junctionWait());
                }
                if (FLEET_SCENARIO.equals(r.scenarioId)) {
                    measurements.put("fleet", next.fleetView().values().stream()
                            .map(RoutingSimulation.MissionView::ambulance).toList());
                    measurements.put("reports", next.operationalReports().reports());
                    measurements.put("acknowledgements", next.operationalReports().acknowledgements());
                }
                String measured = measurements.isEmpty() ? null : encode(measurements);
                db.update("update simulation_run set status=?,revision=?,event_sequence=?,simulation_time=?,ambulance_result=?::jsonb,traffic_result=?::jsonb where id=?",runStatus,revision,lastEvent,next.time(),encode(next.ambulance()),measured,r.id);
            });
        }catch(RuntimeException failure){r.fault=true;return;}
        r.simulation=next;r.paused=paused;r.speed=speed;r.revision=revision;r.eventSequence=lastEvent;
        r.published=publishable(r,next,revision,lastEvent,paused,speed);
        for(var event:notifications)try{messages.convertAndSend("/topic/runs/"+r.id+"/events",event);}catch(RuntimeException ignored){/* HTTP event catch-up is durable. */}
        if(System.nanoTime()-r.lastPublish>=200_000_000L)publishState(r);
    }
    private Published publishable(Run r,RoutingSimulation sim,long revision,long events,boolean paused,int speed){
        boolean fleetScenario = FLEET_SCENARIO.equals(r.scenarioId);
        String mode = switch (r.scenarioId) {
            case FLEET_SCENARIO -> "FLEET_TRAFFIC";
            case TRAFFIC_SCENARIO -> "TRAFFIC_SIGNALS";
            case CalibrationRunner.SCENARIO -> "PREDICTABLE_CONGESTION";
            case JAIPUR_SCENARIO -> "JAIPUR_CORRIDOR";
            default -> "ROUTING_ONLY";
        };
        Map<String,Object> view=new LinkedHashMap<>();view.put("schemaVersion",1);view.put("runId",r.id.toString());view.put("scenarioId",r.scenarioId);view.put("mode",mode);view.put("seed",r.seed);
        view.put("stateRevision",Long.toString(revision));view.put("latestEventSequence",Long.toString(events));view.put("simulationTimeSeconds",sim.time());view.put("paused",paused);view.put("speed",speed);view.put("horizon",sim.horizon()==-1?"all":Integer.toString(sim.horizon()));
        view.put("runStatus",sim.completed()?"COMPLETED":paused?"PAUSED":"RUNNING");view.put("ambulance",sim.ambulance());view.put("explanation",fleetScenario?null:sim.explanation());view.put("reportedClosures",sim.reported());
        var fleet = sim.fleetView();
        view.put("fleet", fleet.values().stream().map(RoutingSimulation.MissionView::ambulance).toList());
        view.put("reports",sim.operationalReports().reports());
        view.put("acknowledgements",sim.operationalReports().acknowledgements());
        var traffic = sim.trafficState();
        if (traffic != null) {
            view.put("traffic", traffic);
            view.put("ambulanceJunctionWait", sim.junctionWait());
            view.put("priorityEnabled", r.priorityEnabled);
            view.put("prioritySuspended", sim.prioritySuspended());
        }
        return new Published(Collections.unmodifiableMap(view), fleet, sim.physicalEffects(), sim.roadTruth());
    }
    private void publishState(Run r){try{messages.convertAndSend("/topic/runs/"+r.id+"/state",snapshot(r.id));r.lastPublish=System.nanoTime();}catch(RuntimeException ignored){/* Next heartbeat or HTTP snapshot repairs delivery. */}}
}
