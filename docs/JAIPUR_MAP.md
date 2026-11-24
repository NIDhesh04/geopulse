# Jaipur demonstration scenario

**Fact:** The runnable SMS Hospital demo uses 27 junctions and 41 directed corridor polylines from the supplied GeoPulse prototype’s cached OpenStreetMap/OSRM geometry. The simulation starts at Chandpole Gate. Each retained link keeps the original sampled direction and ordered curve. The archive does not identify the OSM extract date or a complete set of legal turn restrictions, so this is a curated demonstration graph.

**Fact:** The Control Room, scenario preview, and Driver Navigation use those same local road shapes. Optional online geographic context comes from OpenFreeMap vector tiles (© OpenMapTiles, © OpenStreetMap contributors). The local road shapes and the server simulation still run when context tiles are unavailable. The moving dots in Simulation Truth represent simulated travelling traffic, with their count capped for readability.

**Decision:** Use a bounded Jaipur road network from a dated OpenStreetMap extract for the first geographic demo. Keep the synthetic grid as the reference fixture for checking routing, queues and signal timing. Introduce Jaipur once those mechanics are integrated on the grid.

**Fact:** OpenStreetMap provides road data under the ODbL. A downloaded extract can be processed offline without an API key. Display © OpenStreetMap contributors on the map and preserve the source date, attribution and license with any distributed data. [OpenStreetMap copyright and attribution](https://www.openstreetmap.org/copyright)

**Assumption:** Start with a small hospital catchment and confirm one reachable station-to-hospital journey. Use a directed driving graph built from the extract. Validate one-way roads, access and turn restrictions, divided roads, and grade separation along the demo corridor. Save junction latitude/longitude and local metre coordinates, plus stable directed edge IDs, measured lengths, and full ordered road geometry. Check signal locations and hospital access points for the chosen route. [OSMnx graph reference](https://osmnx.readthedocs.io/en/stable/internals-reference.html)

**Decision:** Render the same edge geometry that the engine routes over. Convert the engine's distance along an edge to distance along the rendered polyline so the marker follows bends. Store the first fixture as a versioned scenario and local GeoJSON for MapLibre. PostGIS can be added for spatial indexing, nearest-road queries or larger imports. [PostGIS overview](https://postgis.net/docs/manual-dev/en/postgis_introduction.html)

**Fact:** Google's Roads API restricts storing or extracting road data for reuse outside its services. The imported OpenStreetMap graph supplies the topology and geometry GeoPulse needs. [Google Roads API policies](https://developers.google.com/maps/documentation/roads/policies)

**Decision:** Label the demo as real Jaipur road geometry with simulated traffic, incidents and signal timing. OpenStreetMap geometry alone does not establish measured demand, current road conditions, or actual controller behavior.

**Decision:** Collapse degree-two pass-through points into the ordered road polyline. Keep topology nodes wherever connectivity, a mapped control, an access point, or a restriction requires one. An unsignalized bend does not create a signal. Map one-way rules to directed edges and turn restrictions to allowed incoming/outgoing movements, including restrictions that span multiple edges. Build each controller's approach list from its actual incoming roads and any station entry.
