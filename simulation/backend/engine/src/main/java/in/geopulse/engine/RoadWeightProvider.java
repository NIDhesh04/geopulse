package in.geopulse.engine;
@FunctionalInterface
public interface RoadWeightProvider { Estimate estimate(Graph.Edge edge,long simulationTimeSeconds); }
