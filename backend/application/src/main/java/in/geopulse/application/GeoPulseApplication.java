package in.geopulse.application;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
@SpringBootApplication
public class GeoPulseApplication {
    public static void main(String[] args) {
        if (args.length == 1 && args[0].equals("--calibrate-jaipur")) {
            JaipurScenario.calibrate();
            return;
        }
        SpringApplication.run(GeoPulseApplication.class,args);
    }
}
