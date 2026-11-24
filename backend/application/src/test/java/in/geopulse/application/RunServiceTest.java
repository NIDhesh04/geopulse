package in.geopulse.application;
import com.fasterxml.jackson.databind.ObjectMapper;
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
    @Autowired org.springframework.transaction.support.TransactionTemplate tx;
    @Container static PostgreSQLContainer<?> db=new PostgreSQLContainer<>("postgres:18.7-alpine");
    @DynamicPropertySource static void properties(DynamicPropertyRegistry r){r.add("spring.datasource.url",db::getJdbcUrl);r.add("spring.datasource.username",db::getUsername);r.add("spring.datasource.password",db::getPassword);}
    @Autowired RunService runs; @Autowired ObjectMapper json; @Autowired JdbcTemplate jdbc;
    Map<String,Object> command(UUID run,UUID id,String type,Map<String,Object> payload)throws Exception{
        runs.accept(run,new RunService.Command(id,type,json.valueToTree(payload)));
        for(int i=0;i<100;i++){var result=runs.command(run,id);if(!result.get("status").equals("ACCEPTED"))return result;Thread.sleep(20);}
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
