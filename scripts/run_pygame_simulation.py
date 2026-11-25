"""GeoPulse Three-Strategy Synchronized Pygame Simulation Launcher.

Runs Static Dijkstra, Dynamic Dijkstra, and GeoPulse Two-Edge Selection
side by side on the same road network and traffic timeline.

Usage:
    python scripts/run_pygame_simulation.py
    python scripts/run_pygame_simulation.py --network custom --speed 1.0
    python scripts/run_pygame_simulation.py --network osm --od-id 0
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pygame_simulation.comparison_renderer import ThreePanelComparisonRenderer
from src.pygame_simulation.gis_renderer import GISNavigationRenderer
from src.pygame_simulation.temporal_comparison import (
    ThreeStrategySimulation,
    build_custom_temporal_bundle,
    build_osm_temporal_bundle,
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="GeoPulse Three-Strategy Pygame Simulation (Static vs Dynamic vs GeoPulse)"
    )
    parser.add_argument(
        "--network",
        choices=["custom", "osm"],
        default="custom",
        help="Network scenario: 'custom' urban grid (instant launch) or 'osm' Bhubaneswar corridor",
    )
    parser.add_argument(
        "--congestion",
        choices=["congested", "normal"],
        default="congested",
        help="Traffic condition for the custom scenario",
    )
    parser.add_argument(
        "--od-id",
        type=int,
        default=0,
        help="Origin-Destination pair ID when using --network osm",
    )
    parser.add_argument(
        "--departure",
        type=str,
        default="2026-01-15T15:59:00Z",
        help="UTC departure timestamp when using --network osm",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Initial playback speed multiplier (0.5, 1.0, 2.0, 5.0)",
    )
    parser.add_argument(
        "--view",
        choices=["gis", "split"],
        default="gis",
        help="Visualization layout: 'gis' (default Phase 6.1 dark-mode GIS view) or 'split' (3-panel)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Use SDL dummy video driver for automated verification",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Optional max wall-clock runtime in seconds before closing automatically",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    print("=" * 72)
    print("  GEOPULSE — 3-STRATEGY SYNCHRONIZED PYGAME SIMULATION")
    print("  Comparing: Static Dijkstra | Dynamic Dijkstra | GeoPulse Two-Edge")
    print("=" * 72)

    if args.network == "custom":
        bundle = build_custom_temporal_bundle(congestion_level=args.congestion)
    else:
        print(f"Loading Bhubaneswar OSM graph and Phase 7 predictions (OD #{args.od_id})...")
        bundle = build_osm_temporal_bundle(
            od_id=args.od_id,
            departure_timestamp=args.departure,
        )

    sim = ThreeStrategySimulation(bundle)
    sim.speed_multiplier = float(args.speed)

    print(f"Scenario:   {bundle.title}")
    print(f"Origin:     {bundle.origin}  ->  Destination: {bundle.destination}")
    print(f"Departure:  {bundle.departure_timestamp}")
    print(f"Speed:      {sim.speed_multiplier}x (base {sim.base_sim_sec_per_real_sec:.0f} sim-s/s)")
    print(f"View:       {args.view.upper()}")
    print("Controls:   Wheel=Zoom | Drag=Pan | V=Fit | SPACE=Pause | N=Step | R=Reset | F11=Fullscreen | ESC=Quit")
    print("=" * 72)

    if args.view == "split":
        renderer = ThreePanelComparisonRenderer(sim, headless=args.headless)
    else:
        renderer = GISNavigationRenderer(sim, headless=args.headless)
    renderer.run_loop(max_seconds=args.duration)

    print("\nFinal Simulation Summary:")
    for row in sim.get_comparison_rows():
        saved = (
            f" ({row['saved_vs_static_s']:+.2f}s / {row['saved_vs_static_pct']:+.1f}%)"
            if row["saved_vs_static_s"] is not None
            else ""
        )
        print(
            f"  - {row['label']:<18} | status={row['status']:<18} | "
            f"time={row['elapsed_time_s']:7.2f}s{saved} | dist={row['distance_m']:7.1f}m | "
            f"edges={row['edges_traversed']} | updates={row['updates_applied']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
