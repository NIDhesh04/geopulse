"""Regression tests for synchronized three-strategy Pygame comparison simulation."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest

import networkx as nx
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.experiments.temporal_journey import STRATEGIES, TemporalJourneyEngine
from src.pygame_simulation.comparison_renderer import ThreePanelComparisonRenderer
from src.pygame_simulation.gis_map import interpolate_polyline
from src.pygame_simulation.gis_renderer import GISNavigationRenderer
from src.pygame_simulation.temporal_comparison import (
    TemporalScenarioBundle,
    ThreeStrategySimulation,
    build_custom_temporal_bundle,
    build_osm_temporal_bundle,
)
from src.routing.traffic_weights import GraphWeightManager
from src.traffic.replay import HistoricalTrafficReplay


class TestThreeStrategyPygameSimulation(unittest.TestCase):
    """Verify synchronized 3-strategy temporal logic and headless Pygame rendering."""

    def test_custom_bundle_synchronization_and_parity_with_temporal_engine(self) -> None:
        bundle = build_custom_temporal_bundle(congestion_level="congested")
        sim = ThreeStrategySimulation(bundle)

        # Shared origin/destination/initial route
        origins = {agent.origin for agent in sim.agents.values()}
        dests = {agent.destination for agent in sim.agents.values()}
        self.assertEqual(origins, {"0"})
        self.assertEqual(dests, {"10"})
        self.assertEqual(
            sim.agents["static_dijkstra"].active_edge,
            ("0", "1", 0),
        )
        self.assertEqual(
            sim.agents["dynamic_dijkstra"].active_edge,
            ("0", "1", 0),
        )
        self.assertEqual(
            sim.agents["geopulse_two_edge"].active_edge,
            ("0", "1", 0),
        )

        # Step until all three reach destination
        ticks = 0
        while not sim.all_finished and ticks < 500:
            sim.step_sim(1.0)
            ticks += 1
        self.assertTrue(sim.all_finished)

        # Verify exact match with unmodified Phase 4 TemporalJourneyEngine
        engine = TemporalJourneyEngine(bundle.weight_manager, bundle.replay_frames)
        for strategy in STRATEGIES:
            ref = engine.run(
                bundle.origin, bundle.destination, bundle.departure_timestamp, strategy
            )
            agent = sim.agents[strategy]
            self.assertTrue(ref.success)
            self.assertTrue(agent.arrived)
            self.assertFalse(agent.failed)
            self.assertAlmostEqual(agent.elapsed_time_s, ref.travel_time_s, places=5)
            self.assertAlmostEqual(agent.distance_m, ref.distance_m, places=5)
            self.assertEqual(agent.traversed_edges, ref.traversed_edge_path)
            self.assertEqual(agent.prediction_updates_applied, ref.prediction_updates_applied)
            self.assertEqual(agent.dijkstra_reroutes, ref.dijkstra_reroutes)
            self.assertEqual(
                agent.two_edge_alternative_selections, ref.two_edge_alternative_selections
            )
            self.assertEqual(agent.dijkstra_fallback_steps, ref.dijkstra_fallback_steps)

        # Confirm meaningful divergence between Static and Dynamic/GeoPulse
        static_t = sim.agents["static_dijkstra"].elapsed_time_s
        dyn_t = sim.agents["dynamic_dijkstra"].elapsed_time_s
        geo_t = sim.agents["geopulse_two_edge"].elapsed_time_s
        self.assertGreater(static_t, dyn_t + 30.0)
        self.assertAlmostEqual(dyn_t, geo_t, places=5)
        self.assertEqual(sim.agents["static_dijkstra"].prediction_updates_applied, 0)
        self.assertEqual(sim.agents["dynamic_dijkstra"].dijkstra_reroutes, 1)
        self.assertEqual(sim.agents["geopulse_two_edge"].two_edge_alternative_selections, 1)

    def test_predicted_speeds_drive_decisions_while_realized_speeds_drive_motion(self) -> None:
        graph = nx.MultiDiGraph()
        graph.add_node("S", x=0.0, y=0.0)
        graph.add_node("A", x=100.0, y=0.0)
        graph.add_node("T", x=200.0, y=0.0)
        graph.add_edge("S", "A", key=0, length=1_000.0, highway="primary")
        graph.add_edge("A", "T", key=0, length=1_000.0, highway="primary")
        mapping = pd.DataFrame(
            [
                {"traffic_segment_id": 1, "u": "S", "v": "A", "key": 0, "routing_eligibility": "DYNAMIC"},
                {"traffic_segment_id": 2, "u": "A", "v": "T", "key": 0, "routing_eligibility": "DYNAMIC"},
            ]
        )
        rows = pd.DataFrame(
            [
                {"timestamp": "2026-01-15T08:00:00Z", "traffic_segment_id": sid, "predicted_speed": 120.0, "actual_speed": 36.0}
                for sid in (1, 2)
            ]
            + [
                {"timestamp": "2026-01-15T09:00:00Z", "traffic_segment_id": sid, "predicted_speed": 120.0, "actual_speed": 36.0}
                for sid in (1, 2)
            ]
        )
        replay = HistoricalTrafficReplay(rows)
        frames = [replay.get_frame(ts) for ts in replay.available_timestamps]
        bundle = TemporalScenarioBundle(
            scenario_id="sep_test",
            title="Separation Test",
            network_type="custom",
            weight_manager=GraphWeightManager(graph, mapping),
            replay_frames=frames,
            node_coords={"S": (0.0, 0.0), "A": (100.0, 0.0), "T": (200.0, 0.0)},
            origin="S",
            destination="T",
            departure_timestamp="2026-01-15T09:50:00Z",
            default_sim_seconds_per_real_second=1.0,
        )
        sim = ThreeStrategySimulation(bundle)
        while not sim.all_finished:
            sim.step_sim(5.0)
        # Realized 36 km/h = 10 m/s -> 2000m takes 200s (NOT 60s under 120 km/h prediction)
        for strategy in STRATEGIES:
            self.assertAlmostEqual(sim.agents[strategy].elapsed_time_s, 200.0, places=5)

    def test_pause_resume_reset_and_comparison_rows(self) -> None:
        sim = ThreeStrategySimulation(build_custom_temporal_bundle())
        sim.is_paused = True
        sim.update(1.0)
        self.assertEqual(sim.sim_elapsed_s, 0.0)
        self.assertEqual(sim.live_elapsed_s("static_dijkstra"), 0.0)

        sim.is_paused = False
        sim.update(1.0)
        self.assertGreater(sim.sim_elapsed_s, 0.0)
        self.assertGreater(sim.live_elapsed_s("geopulse_two_edge"), 0.0)

        sim.reset()
        self.assertEqual(sim.sim_elapsed_s, 0.0)
        self.assertFalse(sim.all_finished)
        rows = sim.get_comparison_rows()
        self.assertEqual([r["strategy"] for r in rows], list(STRATEGIES))

    def test_headless_three_panel_renderer_executes_and_finishes(self) -> None:
        old_driver = os.environ.get("SDL_VIDEODRIVER")
        try:
            sim = ThreeStrategySimulation(build_custom_temporal_bundle())
            sim.speed_multiplier = 5.0
            renderer = ThreePanelComparisonRenderer(sim, headless=True)
            renderer.run_loop(max_seconds=0.6)
            self.assertGreater(sim.sim_elapsed_s, 0.0)
        finally:
            if old_driver is None:
                os.environ.pop("SDL_VIDEODRIVER", None)
            else:
                os.environ["SDL_VIDEODRIVER"] = old_driver

    @unittest.skipUnless(
        (ROOT / "data/raw/osm/bhubaneswar_drive.graphml").exists()
        and (ROOT / "results/phase7_predictions.parquet").exists(),
        "OSM graph / Phase 7 replay data not available",
    )
    def test_osm_od0_launches_and_matches_phase4_temporal_results(self) -> None:
        bundle = build_osm_temporal_bundle(od_id=0, departure_timestamp="2026-01-15T15:59:00Z")
        self.assertEqual(bundle.origin, "3722327026")
        self.assertEqual(bundle.destination, "2443921849")
        sim = ThreeStrategySimulation(bundle)
        while not sim.all_finished:
            sim.step_sim(10.0)
        for strategy in STRATEGIES:
            self.assertTrue(sim.agents[strategy].arrived)
            self.assertFalse(sim.agents[strategy].failed)
        self.assertAlmostEqual(sim.agents["static_dijkstra"].elapsed_time_s, 1268.40564, places=3)
        self.assertAlmostEqual(sim.agents["dynamic_dijkstra"].elapsed_time_s, 1183.50147, places=3)
        self.assertAlmostEqual(sim.agents["geopulse_two_edge"].elapsed_time_s, 1183.50147, places=3)
        # Verify real WKT polyline road geometry was extracted (>2 vertices on curved OSM links)
        curved_edges = [pts for pts in bundle.edge_geometries.values() if len(pts) > 2]
        self.assertGreater(len(curved_edges), 1000)

    def test_polyline_interpolation_and_gis_zoom_pan_reset(self) -> None:
        pts = [(0, 0), (100, 0), (100, 100)]
        pos, heading = interpolate_polyline(pts, 0.75)
        self.assertAlmostEqual(pos[0], 100.0, places=3)
        self.assertAlmostEqual(pos[1], 50.0, places=3)
        self.assertGreater(heading, 1.4)  # headed South (+pi/2) along second bend

        old_driver = os.environ.get("SDL_VIDEODRIVER")
        try:
            sim = ThreeStrategySimulation(build_custom_temporal_bundle())
            renderer = GISNavigationRenderer(sim, headless=True)
            cam = renderer.map_renderer.camera
            z0, cx0, cy0 = cam.zoom, cam.center_wx, cam.center_wy

            cam.zoom_at(renderer.map_rect.center, 1.5)
            self.assertGreater(cam.zoom, z0)
            cam.pan_by_pixels(60, -40)
            self.assertNotAlmostEqual(cam.center_wx, cx0)
            renderer.map_renderer.fit_corridor_view()
            self.assertAlmostEqual(cam.zoom, z0, places=4)
            self.assertAlmostEqual(cam.center_wx, cx0, places=4)
            self.assertAlmostEqual(cam.center_wy, cy0, places=4)

            renderer.run_loop(max_seconds=0.4)
            self.assertGreater(sim.sim_elapsed_s, 0.0)
        finally:
            if old_driver is None:
                os.environ.pop("SDL_VIDEODRIVER", None)
            else:
                os.environ["SDL_VIDEODRIVER"] = old_driver


if __name__ == "__main__":
    unittest.main()
