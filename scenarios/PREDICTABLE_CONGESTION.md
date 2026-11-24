# Predictable corridor congestion

**Fact:** This 5×5 fixture starts the ambulance at `n00_00` with destination `n00_04`. Extra civilian demand enters the eastbound road `n00_02_n00_03` from 20s through 154s. That road is outside the station's two-hop live window. The demo seed is `108`.

**Fact:** The frozen [historical profile](predictable-congestion-5x5.profile.tsv) uses twelve 20-second buckets. For each bucket, the runner averages road traversal estimates from observed simulated speeds and movement-delay estimates from observed queues, signal phases and receiving storage. The movement model approximates service delay. The separate bounded live forecast continues to use the signal controller.

**Decision:** Calibration uses incident-free civilian-only runs with reserved seeds `-1001`, `-1002` and `-1003`. The M5 core seeds are reserved as `1000–1019` and scale seeds as `2000–2004`. This short fixture starts on the demo clock. M5 will freeze profiles for its own warm-up and measurement schedule before comparisons.

**Decision:** Regenerate the profile from the repository root.

```sh
./backend/mvnw -f backend/pom.xml -pl engine -DskipTests package
java -cp backend/engine/target/classes in.geopulse.engine.CalibrationRunner > scenarios/predictable-congestion-5x5.profile.tsv
```
