package in.geopulse.application;
import java.io.IOException;
import java.nio.file.Path;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
@SpringBootApplication
public class GeoPulseApplication {
    public static void main(String[] args) throws IOException {
        if (args.length == 1 && args[0].equals("--calibrate-jaipur")) {
            JaipurScenario.calibrate();
            return;
        }
        if (args.length == 4 && args[0].equals("--check-jaipur-import")) {
            JaipurScenario.verifyRoadImport(Path.of(args[1]),args[2],args[3]);
            return;
        }
        SpringApplication.run(GeoPulseApplication.class,args);
    }
}
