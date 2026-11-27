package in.geopulse.engine;
/** Explicit ROUTING_ONLY fixture provider. Never a fallback for unknown junction data. */
public final class M1ZeroJunctionDelay implements JunctionDelayEstimator {
    @Override public Estimate estimate(String incomingEdge,Graph.Edge outgoingEdge,long simulationTimeSeconds){
        return Estimate.available(0,"M1_ZERO_WAIT");
    }
}
