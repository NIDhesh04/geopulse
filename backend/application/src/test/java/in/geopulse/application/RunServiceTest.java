package in.geopulse.application;
import com.fasterxml.jackson.databind.ObjectMapper;
import in.geopulse.engine.CalibrationRunner;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
@Testcontainers
@SpringBootTest
class RunServiceTest {
    @Test void jaipurMissionRoutesOverThePublishedGeometry() throws Exception {
        String scenarioId = "jaipur-sms-corridor";
        var definition = runs.scenarios().stream().filter(s -> scenarioId.equals(s.get("id"))).findFirst().orElseThrow();
        var graph = (in.geopulse.engine.Graph) definition.get("graph");
        var geometry = json.valueToTree(definition.get("edgeGeometry"));
        for (var road : graph.edges()) {
            var shape = geometry.path(road.id());
            assertTrue(shape.size() >= 2);
            assertEquals(graph.node(road.from()).lng(), shape.get(0).get(0).asDouble());
            assertEquals(graph.node(road.to()).lat(), shape.get(shape.size()-1).get(1).asDouble());
        }
        var created = runs.create("2", 108, scenarioId, true);
        var id = UUID.fromString(created.get("runId").toString());
        assertEquals("JAIPUR_CORRIDOR", created.get("mode"));
        String origin = (String) definition.get("origin");
        String destination = (String) definition.get("destination");
        var activation = command(id, UUID.randomUUID(), "ACTIVATE", Map.of("origin",origin,"destination",destination));
        assertEquals("APPLIED", activation.get("status"), activation.toString());
        var mission = runs.mission(id, "AMB-001").ambulance();
        assertFalse(mission.route().isEmpty());
        assertEquals(origin, graph.edge(mission.route().getFirst()).from());
        assertEquals(destination, graph.edge(mission.route().getLast()).to());
        for (int tick = 0; tick < 30 && mission.edge() == null; tick++) {
            assertEquals("APPLIED", command(id, UUID.randomUUID(), "STEP", Map.of()).get("status"));
            mission = runs.mission(id, "AMB-001").ambulance();
        }
        assertNotNull(mission.edge());
        assertTrue(geometry.has(mission.edge()));
    }
    @Test void predictableCongestionRunUsesTheReproduciblePackagedProfile() throws Exception {
        assertEquals(CalibrationRunner.calibrate(CalibrationRunner.CALIBRATION_SEEDS), RunService.readCongestionProfile());
        var created = runs.create("2", CalibrationRunner.DEMO_SEED, CalibrationRunner.SCENARIO, false);
        var run = UUID.fromString(created.get("runId").toString());
        assertEquals("PREDICTABLE_CONGESTION", created.get("mode"));
        assertEquals("APPLIED", command(run, UUID.randomUUID(), "ACTIVATE",
                Map.of("origin", "n00_00", "destination", "n00_04")).get("status"));
        var mission = runs.mission(run, "AMB-001");
        assertFalse(mission.ambulance().route().contains(CalibrationRunner.CORRIDOR));
        var selectedHistoricalRoad = mission.ambulance().route().stream()
                .filter(road -> !mission.explanation().liveEdges().contains(road)).findFirst().orElseThrow();
        var estimate = mission.explanation().roads().get(selectedHistoricalRoad);
        assertEquals("HISTORICAL", estimate.source());
        assertTrue(estimate.reason().startsWith("Historical interval 20–") ||
                estimate.reason().startsWith("Historical interval 40–"));
        assertEquals(CalibrationRunner.CALIBRATION_SEEDS.toString(), jdbc.queryForObject(
                "select scenario_snapshot #>> '{historicalProfile,calibrationSeeds}' from simulation_run where id=?",
                String.class, run));
    }
    @Test void fleetCommandsPublishSeparateOperationalRoutingAndTruthViews() throws Exception {
        var run = UUID.fromString(runs.create("2", 108, "fleet-conflict-5x5", true).get("runId").toString());
        assertEquals(10, ((List<?>) runs.snapshot(run).get("fleet")).size());
        for (var entry : Map.of("AMB-001","n00_00", "AMB-008","n04_00").entrySet()) {
            assertEquals("APPLIED", command(run, UUID.randomUUID(), "ACTIVATE",
                    Map.of("ambulanceId",entry.getKey(),"origin",entry.getValue(),"destination","n04_04")).get("status"));
        }
        String road = runs.mission(run, "AMB-001").ambulance().route().getFirst();
        assertEquals("APPLIED", command(run, UUID.randomUUID(), "INCIDENT",
                Map.of("edge",road,"effect","ENTRY_CLOSED")).get("status"));
        assertNull(runs.snapshot(run).get("explanation"));
        assertFalse(runs.snapshot(run).containsKey("physicalEffects"));
        assertEquals(Set.of(), runs.snapshot(run).get("reportedClosures"));
        assertTrue(((Map<?,?>) runs.simulationTruth(run).get("physicalEffects")).containsKey(road));
        assertEquals("BLOCKED", runs.mission(run,"AMB-001").explanation().roads().get(road).status());
        assertEquals("HISTORICAL", runs.mission(run,"AMB-008").explanation().roads().get(road).source());
        assertEquals("APPLIED", command(run, UUID.randomUUID(), "SUBMIT_OBSTRUCTION",
                Map.of("reportId","r1","ambulanceId","AMB-001","edge",road,"closure",true)).get("status"));
        assertEquals(Set.of(), runs.snapshot(run).get("reportedClosures"));
        assertEquals("APPLIED", command(run, UUID.randomUUID(), "REVIEW_OBSTRUCTION",
                Map.of("reportId","r1","confirmed",true)).get("status"));
        assertEquals(Set.of(road), runs.snapshot(run).get("reportedClosures"));
        assertEquals("BLOCKED", runs.mission(run,"AMB-008").explanation().roads().get(road).status());
        assertEquals("CONFIRMED", ((com.fasterxml.jackson.databind.JsonNode) runs.results(run).get("traffic"))
                .path("reports").path("r1").path("status").asText());
    }
    @Autowired org.springframework.transaction.support.TransactionTemplate tx;
    @Container static PostgreSQLContainer<?> db=new PostgreSQLContainer<>("postgres:18.7-alpine");
    @DynamicPropertySource static void properties(DynamicPropertyRegistry r){r.add("spring.datasource.url",db::getJdbcUrl);r.add("spring.datasource.username",db::getUsername);r.add("spring.datasource.password",db::getPassword);}
    @Autowired RunService runs; @Autowired ObjectMapper json; @Autowired JdbcTemplate jdbc;
    Map<String,Object> command(UUID run,UUID id,String type,Map<String,Object> payload)throws Exception{
        runs.accept(run,new RunService.Command(id,type,json.valueToTree(payload)));
        for (int i=0;i<100;i++) {
            var result=runs.command(run,id);
            if (!result.get("status").equals("ACCEPTED")
                    && Long.parseLong(runs.snapshot(run).get("stateRevision").toString())
                    >= Long.parseLong(result.get("boundary_ordinal").toString())) return result;
            Thread.sleep(20);
        }
        fail("command never completed");return Map.of();
    }
    @Test void migrationJsonbCommandsAndStepping()throws Exception{
        UUID run=UUID.fromString(runs.create("2",108).get("runId").toString());UUID id=UUID.randomUUID();
        assertEquals("APPLIED",command(run,id,"ACTIVATE",Map.of("origin","n00_00","destination","n04_04")).get("status"));
        runs.accept(run,new RunService.Command(id,"ACTIVATE",json.valueToTree(Map.of("destination","n04_04","origin","n00_00"))));
        assertEquals(1,jdbc.queryForObject("select count(*) from run_command where run_id=?",Integer.class,run));
        assertThrows(RunService.ApiException.class,()->runs.accept(run,new RunService.Command(id,"STEP",json.createObjectNode())));
        assertEquals("APPLIED",command(run,UUID.randomUUID(),"STEP",Map.of()).get("status"));
        assertEquals(1L,runs.snapshot(run).get("simulationTimeSeconds"));
        assertEquals("REJECTED",command(run,UUID.randomUUID(),"SET_SPEED",Map.of("speed",999)).get("status"));
        assertEquals(1L,runs.snapshot(run).get("simulationTimeSeconds"));
        assertFalse(runs.events(run,0).isEmpty());
        assertEquals("object",jdbc.queryForObject("select jsonb_typeof(scenario_snapshot) from simulation_run where id=?",String.class,run));
    }
    @Test void publicationSeesCommittedEventsAndRestartInterrupts()throws Exception {
        var broker=org.mockito.Mockito.mock(org.springframework.messaging.simp.SimpMessagingTemplate.class);
        var service=new RunService(jdbc,json,tx,broker);
        try {
            UUID run=UUID.fromString(service.create("0",108).get("runId").toString());
            var observed=new java.util.concurrent.atomic.AtomicInteger();
            org.mockito.Mockito.doAnswer(call->{
                String destination=call.getArgument(0);
                if(destination.endsWith("/events")){
                    Map<?,?> event=call.getArgument(1);
                    assertEquals(1,jdbc.queryForObject("select count(*) from run_event where run_id=? and sequence=?",Integer.class,run,Long.parseLong(event.get("sequence").toString())));
                    observed.incrementAndGet();
                }return null;
            }).when(broker).convertAndSend(org.mockito.ArgumentMatchers.anyString(),org.mockito.ArgumentMatchers.any(Object.class));
            UUID id=UUID.randomUUID();service.accept(run,new RunService.Command(id,"STEP",json.createObjectNode()));
            for(int i=0;i<100&&observed.get()==0;i++)Thread.sleep(20);
            assertTrue(observed.get()>0,"Events must be published after committing");
            service.shutdown();
            var restarted=new RunService(jdbc,json,tx,broker);
            try {restarted.startup();assertEquals("INTERRUPTED",restarted.results(run).get("status"));
                assertEquals(410,assertThrows(RunService.ApiException.class,()->restarted.snapshot(run)).status);
                assertFalse(restarted.events(run,0).isEmpty());
            }finally{restarted.shutdown();}
        }finally{service.shutdown();}
    }
    @Test void persistenceFailureKeepsLastCommittedWorldAndPublishesNoCandidate()throws Exception {
        var broker=org.mockito.Mockito.mock(org.springframework.messaging.simp.SimpMessagingTemplate.class);
        var service=new RunService(jdbc,json,tx,broker);
        UUID run=UUID.fromString(service.create("2",108).get("runId").toString());
        jdbc.execute("create function fail_test_event() returns trigger language plpgsql as $$ begin if NEW.run_id='"+run+"'::uuid then raise exception 'injected disk failure'; end if; return NEW; end $$");
        jdbc.execute("create trigger test_event_failure before insert on run_event for each row execute function fail_test_event()");
        try {
            service.accept(run,new RunService.Command(UUID.randomUUID(),"STEP",json.createObjectNode()));
            for(int i=0;i<100&&!service.snapshot(run).get("runStatus").equals("PERSISTENCE_FAULT");i++)Thread.sleep(20);
            assertEquals("PERSISTENCE_FAULT",service.snapshot(run).get("runStatus"));
            assertEquals(0L,service.snapshot(run).get("simulationTimeSeconds"));
            assertEquals("0",service.snapshot(run).get("stateRevision"));assertTrue(service.events(run,0).isEmpty());
            org.mockito.Mockito.verifyNoInteractions(broker);
            assertEquals(503,assertThrows(RunService.ApiException.class,()->service.accept(run,new RunService.Command(UUID.randomUUID(),"STEP",json.createObjectNode()))).status);
        }finally {service.shutdown();jdbc.execute("drop trigger test_event_failure on run_event");jdbc.execute("drop function fail_test_event()");}
    }
    @Test void trafficRunPersistsScenarioAndMeasurement() throws Exception {
        var created = runs.create("2", 108, "traffic-signals-5x5", false);
        var run = UUID.fromString(created.get("runId").toString());
        assertEquals("TRAFFIC_SIGNALS", created.get("mode"));
        assertEquals("APPLIED", command(run, UUID.randomUUID(), "ACTIVATE",
                Map.of("origin", "n00_00", "destination", "n04_04")).get("status"));
        assertEquals("APPLIED", command(run, UUID.randomUUID(), "STEP", Map.of()).get("status"));
        assertEquals("object", jdbc.queryForObject(
                "select jsonb_typeof(traffic_result) from simulation_run where id=?", String.class, run));
        assertNotNull(runs.results(run).get("traffic"));
    }
}
