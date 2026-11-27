package in.geopulse.application;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import java.util.*;
@RestController
@RequestMapping("/api")
public class RunController {
    public record CreateRun(@NotBlank String horizon,long seed,String scenarioId,Boolean priorityEnabled){}
    private final RunService runs;public RunController(RunService runs){this.runs=runs;}
    @GetMapping("/scenarios") public Object scenarios(){return runs.scenarios();}
    @PostMapping("/runs") public ResponseEntity<?> create(@Valid @RequestBody CreateRun request){return ResponseEntity.status(201).body(runs.create(request.horizon(),request.seed(),request.scenarioId(),request.priorityEnabled()));}
    @GetMapping("/runs/{id}/snapshot") public Object snapshot(@PathVariable UUID id){return runs.snapshot(id);}
    @PostMapping("/runs/{id}/commands") public ResponseEntity<?> command(@PathVariable UUID id,@RequestBody RunService.Command command){return ResponseEntity.accepted().body(runs.accept(id,command));}
    @GetMapping("/runs/{id}/commands/{command}") public Object command(@PathVariable UUID id,@PathVariable UUID command){return runs.command(id,command);}
    @GetMapping("/runs/{id}/events") public Object events(@PathVariable UUID id,@RequestParam(defaultValue="0") long after){return runs.events(id,after);}
    @GetMapping("/runs/{id}/results") public Object results(@PathVariable UUID id){return runs.results(id);}
    @GetMapping("/runs/{id}/ambulances/{ambulanceId}/route-explanation") public Object explanation(@PathVariable UUID id,@PathVariable String ambulanceId){return runs.mission(id,ambulanceId).explanation();}
    @GetMapping("/runs/{id}/ambulances/{ambulanceId}/snapshot") public Object ambulance(@PathVariable UUID id,@PathVariable String ambulanceId){return runs.mission(id,ambulanceId);}
    @GetMapping("/runs/{id}/simulation-truth") public Object truth(@PathVariable UUID id){return runs.simulationTruth(id);}
    @ExceptionHandler(RunService.ApiException.class) public ResponseEntity<?> error(RunService.ApiException e){return ResponseEntity.status(e.status).body(Map.of("message",e.getMessage()));}
    @ExceptionHandler(IllegalArgumentException.class) public ResponseEntity<?> invalid(IllegalArgumentException e){return ResponseEntity.badRequest().body(Map.of("message",e.getMessage()));}
}
