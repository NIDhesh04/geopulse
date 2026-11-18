"""
GeoPulse Pygame Simulation: Scenario Manager

Provides graph topologies and traffic conditions for visual simulation:
1. Custom Test Network: Clean, structured urban grid with parallel arterials,
   known bottlenecks, and bypass corridors designed for clear live demonstrations.
2. OSM Bhubaneswar Network: Real OpenStreetMap subgraph surrounding canonical
   commuter corridors (e.g. Khandagiri to Rasulgarh).
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple, Set, Optional, Any
import networkx as nx
import pandas as pd
import numpy as np


@dataclass
class SimulationScenario:
    """Encapsulates a playable simulation scenario."""
    scenario_id: str
    scenario_name: str
    network_type: str  # 'custom' or 'osm'
    adjacency: Dict[str, List[Tuple[str, int]]]
    edge_lengths: Dict[Tuple[str, str, int], float]
    node_coords: Dict[str, Tuple[float, float]]  # node -> (x, y) or (lat, lon)
    initial_weights: Dict[Tuple[str, str, int], float]
    initial_speeds: Dict[Tuple[str, str, int], float]
    traffic_update_step: Optional[int] = None
    updated_weights: Optional[Dict[Tuple[str, str, int], float]] = None
    updated_speeds: Optional[Dict[Tuple[str, str, int], float]] = None
    source_node: str = ""
    destination_node: str = ""
    description: str = ""


class ScenarioManager:
    """Generates and loads simulation scenarios for Pygame visualization."""

    @staticmethod
    def create_custom_network_scenario(congestion_level: str = "congested") -> SimulationScenario:
        """
        Creates a clean custom urban network designed for classroom/presentation demonstration.
        Network layout:
            [0: Origin]
               |
             [1] (Fork)
            /   \\
          [2]   [3] (Candidate corridors: Main Arterial vs Scenic Bypass)
           |     |
          [4]   [5]
            \\   /
             [6] (Merge)
              |
             [7] (Secondary fork)
            /   \\
          [8]   [9]
            \\   /
            [10: Destination]
        """
        node_coords = {
            '0': (100.0, 300.0),
            '1': (200.0, 300.0),
            '2': (350.0, 180.0),  # Upper corridor (Arterial)
            '3': (350.0, 420.0),  # Lower corridor (Bypass)
            '4': (500.0, 180.0),
            '5': (500.0, 420.0),
            '6': (650.0, 300.0),
            '7': (750.0, 300.0),
            '8': (880.0, 200.0),
            '9': (880.0, 400.0),
            '10': (1000.0, 300.0)
        }

        # Directed edges: (u, v, key)
        edges = [
            ('0', '1', 0, 100.0, 40.0),
            ('1', '2', 0, 180.0, 50.0),  # Candidate A
            ('1', '3', 0, 180.0, 40.0),  # Candidate B
            ('2', '4', 0, 150.0, 50.0),
            ('3', '5', 0, 150.0, 40.0),
            ('4', '6', 0, 180.0, 50.0),
            ('5', '6', 0, 180.0, 40.0),
            ('6', '7', 0, 100.0, 40.0),
            ('7', '8', 0, 160.0, 45.0),  # Candidate A2
            ('7', '9', 0, 160.0, 45.0),  # Candidate B2
            ('8', '10', 0, 160.0, 45.0),
            ('9', '10', 0, 160.0, 45.0),
        ]

        adjacency: Dict[str, List[Tuple[str, int]]] = {str(i): [] for i in range(11)}
        edge_lengths = {}
        initial_weights = {}
        initial_speeds = {}

        for u, v, k, dist, spd in edges:
            adjacency[u].append((v, k))
            e = (u, v, k)
            edge_lengths[e] = dist
            initial_speeds[e] = spd
            initial_weights[e] = dist / (spd / 3.6)

        # Dynamic congestion update at step 2: Arterial 2->4 collapses from 50 km/h to 10 km/h
        updated_weights = dict(initial_weights)
        updated_speeds = dict(initial_speeds)

        if congestion_level == "congested":
            congested_edge = ('2', '4', 0)
            updated_speeds[congested_edge] = 8.0  # Heavy congestion
            updated_weights[congested_edge] = edge_lengths[congested_edge] / (8.0 / 3.6)

        return SimulationScenario(
            scenario_id="custom_grid_demo",
            scenario_name="Urban Arterial & Bypass Grid (Custom Network)",
            network_type="custom",
            adjacency=adjacency,
            edge_lengths=edge_lengths,
            node_coords=node_coords,
            initial_weights=initial_weights,
            initial_speeds=initial_speeds,
            traffic_update_step=2 if congestion_level == "congested" else None,
            updated_weights=updated_weights,
            updated_speeds=updated_speeds,
            source_node="0",
            destination_node="10",
            description="Clear dual-corridor demonstration network with forks, merges, and dynamic congestion."
        )

    @staticmethod
    def create_osm_network_scenario(
        graph_path: str = 'data/raw/osm/bhubaneswar_drive.graphml',
        mapping_path: str = 'data/processed/traffic_to_osm_mapping_final.parquet',
        source_node: str = "3722327026",
        destination_node: str = "2443921849"
    ) -> SimulationScenario:
        """
        Loads the Bhubaneswar OSM road network corridor for canonical OD pair #0.
        """
        G = nx.read_graphml(graph_path)
        mapping_df = pd.read_parquet(mapping_path)

        from src.routing.traffic_weights import GraphWeightManager
        weight_manager = GraphWeightManager(G, mapping_df)

        adjacency = weight_manager.adjacency
        edge_lengths = weight_manager.edge_lengths
        static_weights = weight_manager.get_static_weights()
        static_speeds = weight_manager.edge_static_speeds

        # Extract coordinates for nodes
        node_coords = {}
        for n, d in G.nodes(data=True):
            n_str = str(n)
            lat = float(d.get('y', 0.0))
            lon = float(d.get('x', 0.0))
            node_coords[n_str] = (lat, lon)

        # Build initial weights using static + dynamic if available
        initial_weights = dict(static_weights)
        initial_speeds = dict(static_speeds)

        # Dynamic congestion injection on critical corridor downstream
        updated_weights = dict(initial_weights)
        updated_speeds = dict(initial_speeds)

        # Inject real congestion event
        congested_count = 0
        for e, spd in initial_speeds.items():
            if spd > 35.0 and congested_count < 15:
                updated_speeds[e] = 12.0
                updated_weights[e] = edge_lengths[e] / (12.0 / 3.6)
                congested_count += 1

        return SimulationScenario(
            scenario_id="osm_bhubaneswar_od0",
            scenario_name="Bhubaneswar OSM Real Network (Khandagiri to Rasulgarh)",
            network_type="osm",
            adjacency=adjacency,
            edge_lengths=edge_lengths,
            node_coords=node_coords,
            initial_weights=initial_weights,
            initial_speeds=initial_speeds,
            traffic_update_step=5,
            updated_weights=updated_weights,
            updated_speeds=updated_speeds,
            source_node=source_node,
            destination_node=destination_node,
            description="Real OSM multi-lane urban network with 46,679 directed edges."
        )
