package in.geopulse.application;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import in.geopulse.engine.CalibrationRunner;
import in.geopulse.engine.DijkstraRouter;
import in.geopulse.engine.Estimate;
import in.geopulse.engine.Graph;
import in.geopulse.engine.HistoricalProfile;
import in.geopulse.engine.M1ZeroJunctionDelay;
import in.geopulse.engine.RoadWeightProvider;
import in.geopulse.engine.RoutingSnapshot;
import java.io.IOException;
import java.io.PrintWriter;
import java.nio.file.Path;
import java.util.Map;
import java.util.Set;

final class JaipurScenario {
    static final String ID = "jaipur-sms-corridor";
    static final String PROFILE = "/scenarios/" + ID + ".profile.tsv";

    private JaipurScenario() {}

    static Map<String,Object> read(ObjectMapper json) {
        try (var resource = JaipurScenario.class.getResourceAsStream("/scenarios/" + ID + ".json")) {
            if (resource == null) throw new IllegalStateException("Missing Jaipur corridor scenario");
            var definition = json.readValue(resource, new TypeReference<Map<String,Object>>() {});
            definition.put("graph", json.convertValue(definition.get("graph"), Graph.class));
            return definition;
        } catch (IOException e) {
            throw new IllegalStateException("Invalid Jaipur corridor scenario", e);
        }
    }

    static HistoricalProfile profile() {
        return RunService.readProfile(PROFILE);
    }

    static void calibrate() {
        var definition = read(new ObjectMapper());
        CalibrationRunner.calibrateGeographic((Graph) definition.get("graph"), (String) definition.get("origin"))
                .write(new PrintWriter(System.out));
    }

    static void verifyRoadImport(Path file,String origin,String destination) throws IOException {
        var json=new ObjectMapper();
        var graph=json.readValue(file.toFile(),Graph.class);
        RoadWeightProvider costs=(road,time)->Estimate.available(road.length()/road.freeSpeed(),"HISTORICAL");
        var snapshot=new RoutingSnapshot(graph,origin,0,0,costs,costs,new M1ZeroJunctionDelay(),Set.of());
        var route=new DijkstraRouter().route(graph,origin,"station-entry:"+origin,destination,snapshot);
        if(!route.reachable())throw new IllegalStateException("Imported graph has no feasible route between the selected anchors");
        var result=Map.of("nodes",graph.nodes().size(),"roads",graph.edges().size(),"secondsAtFreeFlow",route.seconds(),
                "length",route.edges().stream().mapToDouble(id->graph.edge(id).length()).sum(),"edgeIds",route.edges());
        System.out.println(json.writeValueAsString(result));
    }
}
