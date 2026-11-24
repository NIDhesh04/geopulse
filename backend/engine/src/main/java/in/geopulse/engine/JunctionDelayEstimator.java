package in.geopulse.engine;
/** Implementations bind immutable policy/queue context when a routing snapshot is created. */
@FunctionalInterface
public interface JunctionDelayEstimator {
    Estimate estimate(String incomingEdge,Graph.Edge outgoingEdge,long simulationTimeSeconds);
}
