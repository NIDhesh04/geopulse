package in.geopulse.application;

import com.fasterxml.jackson.databind.JsonNode;
import in.geopulse.engine.RoutingSimulation;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import org.springframework.jdbc.core.JdbcTemplate;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/** Maps source-backed pickup fields onto the named synthetic integration fixture. */
final class Emergency108Handoffs {
    static final String SUBMIT = "EMERGENCY108_HANDOFF";
    static final String AUTHORIZE = "EMERGENCY108_AUTHORIZE";
    private static final String SCENARIO = "fleet-conflict-5x5";
    private static final long HOSPITAL_REF = 501;
    private static final String HOSPITAL = "n04_04";
    private static final String LEG = "TO_HOSPITAL";
    private static final String PENDING = "PENDING_AUTHORIZATION";
    private static final String AUTHORIZED = "AUTHORIZED";
    private static final String SUPERSEDED = "SUPERSEDED";
    private static final Map<Long,String> FLEET = Map.of(301L,"AMB-001",302L,"AMB-008");

    record HospitalLeg(@Positive long emergencyRef, @Positive long assignmentRef,
                       @Positive long ambulanceRef, @Positive long destinationRef,
                       @NotBlank String journeyLeg, @NotBlank String emergencyStatus,
                       @NotBlank String assignmentStatus) {}

    record Handoff(long assignmentRef, long emergencyRef, long ambulanceRef, long destinationRef, String journeyLeg,
                   String ambulanceId, String origin, String destination, String status,
                   UUID submissionCommand, UUID authorizationCommand, Long replacedBy) {}
    record Pending(String assignmentRef,String emergencyRef,String ambulanceId,String origin,String destination) {}

    static HospitalLeg demoLeg() {
        return new HospitalLeg(410,7001,301,HOSPITAL_REF,LEG,LEG,"ACCEPTED");
    }

    private final JdbcTemplate db;

    Emergency108Handoffs(JdbcTemplate db) { this.db = db; }

    Runnable prepare(UUID run, String scenario, boolean priorityEnabled, RoutingSimulation candidate, RunService.Command command) {
        return SUBMIT.equals(command.type())
                ? prepareSubmission(run,scenario,priorityEnabled,candidate,command)
                : prepareAuthorization(run,candidate,command);
    }

    private Runnable prepareSubmission(UUID run,String scenario,boolean priorityEnabled,RoutingSimulation candidate,
                                       RunService.Command command) {
        var payload = command.payload();
        if (!LEG.equals(payload.path("journeyLeg").asText()))
            throw new IllegalArgumentException("Only the hospital-bound leg is supported");
        if (!LEG.equals(payload.path("emergencyStatus").asText()) || !"ACCEPTED".equals(payload.path("assignmentStatus").asText()))
            throw new IllegalArgumentException("An accepted assignment must already be on the hospital-bound leg");
        long emergency = reference(payload,"emergencyRef");
        long assignment = reference(payload,"assignmentRef");
        long ambulance = reference(payload,"ambulanceRef");
        long destination = reference(payload,"destinationRef");
        var existing = find(run,assignment);
        if (existing != null) {
            if (existing.emergencyRef()!=emergency || existing.ambulanceRef()!=ambulance || existing.destinationRef()!=destination)
                throw new IllegalArgumentException("Assignment reference already has different handoff details");
            return null;
        }
        String ambulanceId = FLEET.get(ambulance);
        if (!SCENARIO.equals(scenario) || ambulanceId==null || destination!=HOSPITAL_REF)
            throw new IllegalArgumentException("No Emergency108 test mapping for this scenario, ambulance, and hospital");
        var recent = query("""
                select * from emergency108_handoff where run_id=? and emergency_ref=? and journey_leg=?
                order by assignment_ref desc limit 1
                """,run,emergency,LEG);
        Handoff previous = recent.isEmpty()?null:recent.getFirst();
        if (previous!=null && assignment<previous.assignmentRef())
            throw new IllegalArgumentException("An updated assignment was already received");

        boolean reservedForAnother = Boolean.TRUE.equals(db.queryForObject("""
                select exists(select 1 from emergency108_handoff
                  where run_id=? and ambulance_id=? and emergency_ref<>? and status <> 'SUPERSEDED')
                """,Boolean.class,run,ambulanceId,emergency));
        if (reservedForAnother || candidate.fleetView().get(ambulanceId).ambulance().activatedAt()!=null)
            throw new IllegalArgumentException("The mapped simulation ambulance is already reserved or active");
        if (priorityEnabled && previous!=null && AUTHORIZED.equals(previous.status())
                && candidate.fleetView().get(previous.ambulanceId()).ambulance().arrivedAt()==null) {
            candidate.suspendPriority(previous.ambulanceId(),true);
        }
        String origin = RoutingSimulation.fixtureOrigins().get(ambulanceId);
        return () -> {
            if (previous!=null) db.update("""
                    update emergency108_handoff set status='SUPERSEDED' where run_id=? and assignment_ref=?
                    """,run,previous.assignmentRef());
            db.update("""
                    insert into emergency108_handoff (run_id,assignment_ref,emergency_ref,ambulance_ref,destination_ref,
                        journey_leg,ambulance_id,origin,destination,submission_command,status)
                    values (?,?,?,?,?,?,?,?,?,?,'PENDING_AUTHORIZATION')
                    """,run,assignment,emergency,ambulance,destination,LEG,ambulanceId,origin,HOSPITAL,command.commandId());
            if (previous!=null) db.update("""
                    update emergency108_handoff set replaced_by=? where run_id=? and assignment_ref=?
                    """,assignment,run,previous.assignmentRef());
        };
    }

    private Runnable prepareAuthorization(UUID run,RoutingSimulation candidate,RunService.Command command) {
        long assignment = reference(command.payload(),"assignmentRef");
        Handoff handoff = find(run,assignment);
        if (handoff==null) throw new IllegalArgumentException("Assignment handoff does not exist in this run");
        if (SUPERSEDED.equals(handoff.status())) throw new IllegalArgumentException("Assignment was superseded");
        if (AUTHORIZED.equals(handoff.status())) return null;
        candidate.activate(handoff.ambulanceId(),handoff.origin(),handoff.destination());
        return () -> db.update("""
                update emergency108_handoff set status='AUTHORIZED',authorization_command=?
                where run_id=? and assignment_ref=?
                """,command.commandId(),run,assignment);
    }

    boolean reserved(UUID run,String ambulance) {
        return Boolean.TRUE.equals(db.queryForObject("""
                select exists(select 1 from emergency108_handoff where run_id=? and ambulance_id=?
                    and status='PENDING_AUTHORIZATION')
                """,Boolean.class,run,ambulance));
    }

    Handoff find(UUID run,long assignment) {
        var rows=query("select * from emergency108_handoff where run_id=? and assignment_ref=?",run,assignment);
        return rows.isEmpty()?null:rows.getFirst();
    }

    List<Pending> pending(UUID run) {
        return query("""
                select * from emergency108_handoff where run_id=? and status='PENDING_AUTHORIZATION'
                order by assignment_ref
                """,run).stream().map(handoff -> new Pending(Long.toString(handoff.assignmentRef()),
                Long.toString(handoff.emergencyRef()),handoff.ambulanceId(),handoff.origin(),handoff.destination())).toList();
    }

    private List<Handoff> query(String sql,Object... arguments) {
        return db.query(sql,(row,index)->asHandoff(row),arguments);
    }

    private static Handoff asHandoff(ResultSet row) throws SQLException {
        return new Handoff(row.getLong("assignment_ref"),row.getLong("emergency_ref"),row.getLong("ambulance_ref"),
                row.getLong("destination_ref"),row.getString("journey_leg"),row.getString("ambulance_id"),
                row.getString("origin"),row.getString("destination"),row.getString("status"),
                row.getObject("submission_command",UUID.class),row.getObject("authorization_command",UUID.class),
                row.getObject("replaced_by",Long.class));
    }

    private static long reference(JsonNode payload,String field) {
        JsonNode value=payload.path(field);
        if (!value.isIntegralNumber() || !value.canConvertToLong() || value.longValue()<=0)
            throw new IllegalArgumentException(field+" must be a positive source identifier");
        return value.longValue();
    }

    static boolean internalCommand(String type) {
        return SUBMIT.equals(type) || AUTHORIZE.equals(type);
    }

    static boolean activated(Handoff handoff) {
        return handoff.authorizationCommand()!=null;
    }

    static String status(Handoff handoff,JsonNode mission,String runStatus) {
        if (List.of("INTERRUPTED","PERSISTENCE_FAULT").contains(runStatus) && !SUPERSEDED.equals(handoff.status()))
            return runStatus;
        if (!AUTHORIZED.equals(handoff.status())) return handoff.status();
        return switch(mission.path("status").asText()) {
            case "ARRIVED" -> "ARRIVED";
            case "STOPPED" -> "STOPPED";
            default -> "ACTIVE";
        };
    }
}
