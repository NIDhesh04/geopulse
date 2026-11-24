# Jaipur demonstration scenario

**Fact:** The runnable SMS Hospital demo uses 27 junctions and 41 directed corridor polylines from the supplied GeoPulse prototype’s cached OpenStreetMap/OSRM geometry. The simulation starts at Chandpole Gate. Each retained link keeps the original sampled direction and ordered curve. The archive does not identify the OSM extract date or a complete set of legal turn restrictions, so this is a curated demonstration graph.

**Fact:** The Control Room, scenario preview, and Driver Navigation use those same local road shapes. The All Streets layer colors visible Jaipur driving streets from OpenFreeMap, including neighborhood and service roads, and samples animated dots for readability. This citywide traffic visualization is synthetic and separate from the backend corridor model. Simulation Truth shows the engine’s occupancy and queues alongside it. Local corridor roads and routing remain available if the OpenFreeMap context cannot load (© OpenMapTiles, © OpenStreetMap contributors).

**Decision:** Model Jaipur road storage at 12 vehicle-equivalents per 100 metres of link length, with a 12-unit minimum. This is a synthetic density assumption for longer links. The 5×5 fixtures retain their existing storage rule.

**Fact:** The bundled Jaipur historical profile covers 1,800 seconds in 60-second intervals. It was generated from incident-free simulations using seeds `-1101` through `-1103`, independently of demo and benchmark seeds. At the default demo seed, the Chandpole–SMS mission completed in all six routing and priority configurations in 478 simulated seconds. This run showed no arrival-time difference between configurations.

**Decision:** Regenerate the profile from the repository root.

```sh
./backend/mvnw -f backend/pom.xml -DskipTests package
java -jar backend/application/target/application-0.1.0-SNAPSHOT.jar --calibrate-jaipur > scenarios/jaipur-sms-corridor.profile.tsv
```

**Decision:** Use a bounded Jaipur road network from a dated OpenStreetMap extract for the first geographic demo. Keep the synthetic grid as the reference fixture for checking routing, queues and signal timing. Introduce Jaipur once those mechanics are integrated on the grid.

**Fact:** OpenStreetMap provides road data under the ODbL. A downloaded extract can be processed offline without an API key. Display © OpenStreetMap contributors on the map and preserve the source date, attribution and license with any distributed data. [OpenStreetMap copyright and attribution](https://www.openstreetmap.org/copyright)

**Assumption:** Start with a small hospital catchment and confirm one reachable station-to-hospital journey. Use a directed driving graph built from the extract. Validate one-way roads, access and turn restrictions, divided roads, and grade separation along the demo corridor. Save junction latitude/longitude and local metre coordinates, plus stable directed edge IDs, measured lengths, and full ordered road geometry. Check signal locations and hospital access points for the chosen route. [OSMnx graph reference](https://osmnx.readthedocs.io/en/stable/internals-reference.html)

**Decision:** Render the same edge geometry that the engine routes over. Convert the engine's distance along an edge to distance along the rendered polyline so the marker follows bends. Store the first fixture as a versioned scenario and local GeoJSON for MapLibre. PostGIS can be added for spatial indexing, nearest-road queries or larger imports. [PostGIS overview](https://postgis.net/docs/manual-dev/en/postgis_introduction.html)

**Fact:** Google's Roads API restricts storing or extracting road data for reuse outside its services. The imported OpenStreetMap graph supplies the topology and geometry GeoPulse needs. [Google Roads API policies](https://developers.google.com/maps/documentation/roads/policies)

**Decision:** Label the demo as real Jaipur road geometry with simulated traffic, incidents and signal timing. OpenStreetMap geometry alone does not establish measured demand, current road conditions, or actual controller behavior.

**Decision:** Collapse degree-two pass-through points into the ordered road polyline. Keep topology nodes wherever connectivity, a mapped control, an access point, or a restriction requires one. An unsignalized bend does not create a signal. Map one-way rules to directed edges and turn restrictions to allowed incoming/outgoing movements, including restrictions that span multiple edges. Build each controller's approach list from its actual incoming roads and any station entry.
