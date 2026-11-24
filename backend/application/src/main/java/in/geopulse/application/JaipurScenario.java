package in.geopulse.application;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import in.geopulse.engine.CalibrationRunner;
import in.geopulse.engine.Graph;
import in.geopulse.engine.HistoricalProfile;
import java.io.IOException;
import java.io.PrintWriter;
import java.util.Map;

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
}
