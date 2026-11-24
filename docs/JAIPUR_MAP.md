# Jaipur demonstration scenario

**Decision:** Use a bounded Jaipur road network from a dated OpenStreetMap extract for the first geographic demo. Keep the synthetic grid as the reference fixture for checking routing, queues and signal timing. Introduce Jaipur once those mechanics are integrated on the grid.

**Fact:** OpenStreetMap provides road data under the ODbL. A downloaded extract can be processed offline without an API key. Display © OpenStreetMap contributors on the map and preserve the source date, attribution and license with any distributed data. [OpenStreetMap copyright and attribution](https://www.openstreetmap.org/copyright)

**Assumption:** Start with a small hospital catchment and confirm one reachable station-to-hospital journey. Use a directed driving graph built from the extract. Validate one-way roads, access and turn restrictions, divided roads, and grade separation along the demo corridor. Save junction latitude/longitude and local metre coordinates, plus stable directed edge IDs, measured lengths, and full ordered road geometry. Check signal locations and hospital access points for the chosen route. [OSMnx graph reference](https://osmnx.readthedocs.io/en/stable/internals-reference.html)

**Decision:** Render the same edge geometry that the engine routes over. Convert the engine's distance along an edge to distance along the rendered polyline so the marker follows bends. Store the first fixture as a versioned scenario and local GeoJSON for MapLibre. PostGIS can be added for spatial indexing, nearest-road queries or larger imports. [PostGIS overview](https://postgis.net/docs/manual-dev/en/postgis_introduction.html)

**Fact:** Google's Roads API restricts storing or extracting road data for reuse outside its services. The imported OpenStreetMap graph supplies the topology and geometry GeoPulse needs. [Google Roads API policies](https://developers.google.com/maps/documentation/roads/policies)

**Decision:** Label the demo as real Jaipur road geometry with simulated traffic, incidents and signal timing. OpenStreetMap geometry alone does not establish measured demand, current road conditions, or actual controller behavior.
