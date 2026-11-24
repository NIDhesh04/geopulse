package in.geopulse.application;

import com.fasterxml.jackson.databind.*;
import in.geopulse.engine.*;
import jakarta.annotation.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
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
    private final JdbcTemplate db;private final ObjectMapper json;private final TransactionTemplate tx;private final SimpMessagingTemplate messages;
    private final ConcurrentMap<UUID,Run> active=new ConcurrentHashMap<>();
    private static final class Run {
        final UUID id;final long seed;final String scenarioId;final boolean priorityEnabled;final ScheduledExecutorService loop;
        RoutingSimulation simulation;long revision,eventSequence;boolean paused=true;int speed=1;
        volatile boolean fault;volatile Map<String,Object> view;
        long lastTick=System.nanoTime(),lastPublish;double credit;
        Run(UUID id,long seed,int horizon,String scenarioId,boolean priorityEnabled){
            this.id=id;this.seed=seed;this.scenarioId=scenarioId;this.priorityEnabled=priorityEnabled;
            simulation=TRAFFIC_SCENARIO.equals(scenarioId)
                    ? RoutingSimulation.traffic(Graph.grid(5),horizon,priorityEnabled)
                    : new RoutingSimulation(Graph.grid(5),horizon);loop=Executors.newSingleThreadScheduledExecutor(r->{Thread t=new Thread(r,"run-"+id);t.setDaemon(true);return t;});}
    }
    public RunService(JdbcTemplate db,ObjectMapper json,TransactionTemplate tx,SimpMessagingTemplate messages){this.db=db;this.json=json;this.tx=tx;this.messages=messages;}
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
        return List.of(scenario(), trafficScenario);
    }

    public Map<String,Object> create(String horizon,long seed){
        return create(horizon, seed, null, false);
    }

    public synchronized Map<String,Object> create(String horizon,long seed,String scenarioId,Boolean priority){
        String selected = scenarioId == null ? SCENARIO : scenarioId;
        var definition = new LinkedHashMap<>(scenarios().stream()
                .filter(item -> selected.equals(item.get("id"))).findFirst()
                .orElseThrow(() -> new ApiException(400,"Unknown scenario")));
        boolean priorityEnabled = TRAFFIC_SCENARIO.equals(selected) && !Boolean.FALSE.equals(priority);
        definition.put("priorityEnabled", priorityEnabled);
        int h=switch(horizon){case "0"->0;case "2"->2;case "all"->-1;default->throw new ApiException(400,"Horizon must be 0, 2 or all");};
        UUID id=UUID.randomUUID();Run r=new Run(id,seed,h,selected,priorityEnabled);
        db.update("insert into simulation_run(id,scenario_id,scenario_snapshot,seed,horizon,status) values (?,?,?::jsonb,?,?,'PAUSED')",id,selected,encode(definition),seed,horizon);
        r.view=view(r,r.simulation,0,0,true,1);active.put(id,r);r.loop.scheduleWithFixedDelay(()->tick(r),100,100,TimeUnit.MILLISECONDS);return r.view;
    }
    private Run require(UUID id){Run r=active.get(id);if(r!=null)return r;var rows=db.queryForList("select status from simulation_run where id=?",id);if(rows.isEmpty())throw new ApiException(404,"Run not found");throw new ApiException(410,"Live snapshot unavailable: "+rows.getFirst().get("status")+". Create a new run.");}
    public Map<String,Object> snapshot(UUID id){Run r=require(id);if(r.fault){var out=new LinkedHashMap<>(r.view);out.put("runStatus","PERSISTENCE_FAULT");return out;}return r.view;}
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
        var result=new LinkedHashMap<>(rows.getFirst());Run r=active.get(id);if(r!=null)result.put("ambulance",r.view.get("ambulance"));
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
                case "ACTIVATE"->candidate.activate(text(p,"origin"),text(p,"destination"));
                case "PLAY"->{if(candidate.ambulance().arrivedAt()!=null)throw new IllegalArgumentException("Journey completed; create a new run");paused=false;}
                case "PAUSE"->paused=true;
                case "STEP"->{if(!paused)throw new IllegalArgumentException("Pause before stepping");if(candidate.ambulance().arrivedAt()!=null)throw new IllegalArgumentException("Journey completed");candidate.step();}
                case "SET_SPEED"->{if(!p.path("speed").isIntegralNumber()||!Set.of(1,5,10,30,60).contains(p.path("speed").asInt()))throw new IllegalArgumentException("Speed must be 1, 5, 10, 30 or 60");speed=p.path("speed").asInt();}
                case "INCIDENT"->{if(!p.path("reported").isBoolean())throw new IllegalArgumentException("reported must be boolean");candidate.incident(text(p,"edge"),text(p,"effect"),p.path("reported").asBoolean(),
                            p.has("incidentId") ? text(p,"incidentId") : "operator");}
                case "REPORT_CLOSURE"->candidate.report(text(p,"edge"),true);
                case "REPORT_REOPENING"->candidate.report(text(p,"edge"),false);
                case "RETRY_ROUTE"->candidate.retry();
                case "SUSPEND_PRIORITY"->{
                    if (!p.path("suspended").isBoolean()) throw new IllegalArgumentException("suspended must be boolean");
                    candidate.suspendPriority(p.path("suspended").booleanValue());
                }
                default->throw new IllegalArgumentException("Unsupported command: "+command.type());
            }}else if(advance)candidate.step();
        }catch(IllegalArgumentException e){outcome="REJECTED";rejection=e.getMessage();candidate=r.simulation.copy();paused=r.paused;speed=r.speed;}
        if(candidate.ambulance().arrivedAt()!=null)paused=true;
        List<RoutingSimulation.Event> emitted=new ArrayList<>(candidate.drainEvents());
        if(command!=null)emitted.add(new RoutingSimulation.Event(candidate.time(),"COMMAND_"+outcome,command.type()+": "+(rejection==null?"applied":rejection)));
        final RoutingSimulation next=candidate;final String appliedOutcome=outcome,reason=rejection;
        final long revision=r.revision+1,lastEvent=r.eventSequence+emitted.size();
        String runStatus=candidate.ambulance().arrivedAt()!=null?"COMPLETED":paused?"PAUSED":"RUNNING";
        List<Map<String,Object>> notifications=new ArrayList<>();long seq=r.eventSequence;
        for(var event:emitted){Map<String,Object> data=new LinkedHashMap<>();data.put("message",event.type().equals("PHYSICAL_INCIDENT")?"Physical scenario changed":event.message());if(command!=null)data.put("commandId",command.commandId().toString());notifications.add(Map.of("sequence",Long.toString(++seq),"time",event.time(),"type",event.type(),"data",data));}
        try{
            tx.executeWithoutResult(s->{
                if(command!=null)db.update("update run_command set status=?,applied_tick=?,boundary_ordinal=?,reason=? where run_id=? and id=?",appliedOutcome,r.simulation.time(),revision,reason,r.id,command.commandId());
                for(var event:notifications)db.update("insert into run_event(run_id,sequence,tick,type,payload) values (?,?,?,?,?::jsonb)",r.id,Long.parseLong(event.get("sequence").toString()),event.get("time"),event.get("type"),encode(event.get("data")));
                var traffic = next.trafficState();
                String measured = traffic == null ? null : encode(Map.of(
                        "civilian", traffic.totals(), "ambulanceJunctionWait", next.junctionWait()));
                db.update("update simulation_run set status=?,revision=?,event_sequence=?,simulation_time=?,ambulance_result=?::jsonb,traffic_result=?::jsonb where id=?",runStatus,revision,lastEvent,next.time(),encode(next.ambulance()),measured,r.id);
            });
        }catch(RuntimeException failure){r.fault=true;return;}
        r.simulation=next;r.paused=paused;r.speed=speed;r.revision=revision;r.eventSequence=lastEvent;
        r.view=view(r,next,revision,lastEvent,paused,speed);
        for(var event:notifications)try{messages.convertAndSend("/topic/runs/"+r.id+"/events",event);}catch(RuntimeException ignored){/* HTTP event catch-up is durable. */}
        if(System.nanoTime()-r.lastPublish>=200_000_000L)publishState(r);
    }
    private Map<String,Object> view(Run r,RoutingSimulation sim,long revision,long events,boolean paused,int speed){
        Map<String,Object> view=new LinkedHashMap<>();view.put("schemaVersion",1);view.put("runId",r.id.toString());view.put("scenarioId",r.scenarioId);view.put("mode",TRAFFIC_SCENARIO.equals(r.scenarioId)?"TRAFFIC_SIGNALS":"ROUTING_ONLY");view.put("seed",r.seed);
        view.put("stateRevision",Long.toString(revision));view.put("latestEventSequence",Long.toString(events));view.put("simulationTimeSeconds",sim.time());view.put("paused",paused);view.put("speed",speed);view.put("horizon",sim.horizon()==-1?"all":Integer.toString(sim.horizon()));
        view.put("runStatus",sim.ambulance().arrivedAt()!=null?"COMPLETED":paused?"PAUSED":"RUNNING");view.put("ambulance",sim.ambulance());view.put("explanation",sim.explanation());view.put("reportedClosures",sim.reported());
        var traffic = sim.trafficState();
        if (traffic != null) {
            view.put("traffic", traffic);
            view.put("ambulanceJunctionWait", sim.junctionWait());
            view.put("priorityEnabled", r.priorityEnabled);
            view.put("prioritySuspended", sim.prioritySuspended());
        }
        return Collections.unmodifiableMap(view);
    }
    private void publishState(Run r){try{messages.convertAndSend("/topic/runs/"+r.id+"/state",snapshot(r.id));r.lastPublish=System.nanoTime();}catch(RuntimeException ignored){/* Next heartbeat or HTTP snapshot repairs delivery. */}}
}
