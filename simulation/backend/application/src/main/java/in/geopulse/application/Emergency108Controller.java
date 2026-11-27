package in.geopulse.application;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/api/test-integrations/emergency108/runs/{runId}/handoffs")
@ConditionalOnProperty(name="geopulse.emergency108.test-enabled",havingValue="true")
public class Emergency108Controller {
    public record Submission(@NotNull UUID commandId,@NotNull @Valid Emergency108Handoffs.HospitalLeg handoff) {}
    public record Authorization(@NotNull UUID commandId) {}

    private final RunService runs;
    private final ObjectMapper json;

    public Emergency108Controller(RunService runs,ObjectMapper json) {
        this.runs=runs;
        this.json=json;
    }

    @PostMapping
    public ResponseEntity<?> submit(@PathVariable UUID runId,@RequestBody @Valid Submission submission) {
        return ResponseEntity.accepted().body(runs.acceptEmergency108(runId,new RunService.Command(
                submission.commandId(),Emergency108Handoffs.SUBMIT,json.valueToTree(submission.handoff()))));
    }

    @PostMapping("/{assignmentRef}/authorize")
    public ResponseEntity<?> authorize(@PathVariable UUID runId,@PathVariable long assignmentRef,
                                       @RequestBody @Valid Authorization authorization) {
        return ResponseEntity.accepted().body(runs.acceptEmergency108(runId,new RunService.Command(
                authorization.commandId(),Emergency108Handoffs.AUTHORIZE,json.valueToTree(Map.of("assignmentRef",assignmentRef)))));
    }

    @PostMapping("/replay-example")
    public ResponseEntity<?> replayExample(@PathVariable UUID runId,@RequestBody @Valid Authorization request) {
        return submit(runId,new Submission(request.commandId(),Emergency108Handoffs.demoLeg()));
    }

    @GetMapping("/{assignmentRef}")
    public Map<String,Object> status(@PathVariable UUID runId,@PathVariable long assignmentRef) {
        return runs.emergency108Status(runId,assignmentRef);
    }

    @ExceptionHandler(RunService.ApiException.class)
    public ResponseEntity<?> error(RunService.ApiException error) {
        return ResponseEntity.status(error.status).body(Map.of("message",error.getMessage()));
    }
}
