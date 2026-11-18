"""
GeoPulse Pygame Interactive Simulation Entrypoint

Usage:
    python -m src.pygame_simulation.main --network custom --strategy destination_aware
    python -m src.pygame_simulation.main --network osm --strategy lookahead_2
    python -m src.pygame_simulation.main --headless --duration 3.0
"""

import os
import sys
import argparse

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath('.'))

from src.pygame_simulation.scenario_manager import ScenarioManager
from src.pygame_simulation.simulation_controller import SimulationController
from src.pygame_simulation.renderer import SimulationRenderer


def parse_args():
    parser = argparse.ArgumentParser(description="GeoPulse Sequential Routing Pygame Simulation")
    parser.add_argument(
        "--network",
        type=str,
        default="custom",
        choices=["custom", "osm"],
        help="Road network to simulate ('custom' demo grid or 'osm' Bhubaneswar)"
    )
    parser.add_argument(
        "--strategy",
        type=str,
        default="destination_aware",
        choices=["greedy", "destination_aware", "lookahead_2", "lookahead_3", "adaptive"],
        help="Two-edge decision strategy to execute"
    )
    parser.add_argument(
        "--congestion",
        type=str,
        default="congested",
        choices=["normal", "congested"],
        help="Traffic scenario condition"
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Simulation playback speed multiplier (e.g. 1.0, 2.0, 5.0)"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run without displaying a graphical window (for automated verification)"
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Maximum duration in seconds to run before closing (useful for testing)"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    print("=" * 65)
    print("     GEOPULSE — SEQUENTIAL TWO-EDGE ROUTING PYGAME SIMULATION")
    print("=" * 65)
    print(f"Network:    {args.network.upper()}")
    print(f"Strategy:   {args.strategy.upper()}")
    print(f"Traffic:    {args.congestion.upper()}")
    print(f"Speed:      {args.speed}x")
    print(f"Headless:   {args.headless}")
    print("=" * 65)

    if args.network == "custom":
        scenario = ScenarioManager.create_custom_network_scenario(congestion_level=args.congestion)
    else:
        print("Loading OSM Bhubaneswar road graph...")
        scenario = ScenarioManager.create_osm_network_scenario()

    controller = SimulationController(
        scenario=scenario,
        strategy_type=args.strategy,
        move_speed_multiplier=args.speed
    )

    renderer = SimulationRenderer(
        controller=controller,
        headless=args.headless
    )

    print("Simulation started. Press SPACE to Pause/Resume, N for Step, R for Reset, ESC to Quit.")
    renderer.run_loop(max_seconds=args.duration)
    print("Simulation finished cleanly.")


if __name__ == "__main__":
    main()
