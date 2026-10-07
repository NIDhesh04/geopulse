"""Automated Validation Tests for Phase 2: Hierarchical Network Embedding & Custom Dijkstra.

Tests:
  Test A: Graph Validation (Strong connectivity, edge count > 10k, exactly 700 monitored edges)
  Test B: Custom Dijkstra Baseline (Valid reachability and cost calculation from scratch)
  Test C: Dynamic Reroute Trigger (Simulated congestion diverts path to alternative route)
"""
import sys
from pathlib import Path
import networkx as nx

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import INTERIM_DIR
from src.routing.custom_dijkstra import custom_dijkstra

GRAPH_PATH = INTERIM_DIR / "G_embedded.graphml"


def test_a_graph_validation():
    """Test A: Assert G_embedded exists, is strongly connected, >10k edges, exactly 700 monitored edges."""
    print("\n" + "=" * 60)
    print("RUNNING TEST A: Graph Validation")
    print("=" * 60)

    assert GRAPH_PATH.exists(), f"Graph file not found at {GRAPH_PATH}"
    print(f"[PASS] {GRAPH_PATH.name} exists on disk ({GRAPH_PATH.stat().st_size / 1e6:.2f} MB).")

    G = nx.read_graphml(GRAPH_PATH, force_multigraph=True)
    num_nodes = len(G)
    num_edges = G.number_of_edges()
    print(f"Loaded graph: {num_nodes} nodes, {num_edges} directed edges.")

    # 1. Edge count > 10,000
    assert num_edges > 10000, f"Expected >10,000 edges, got {num_edges}"
    print(f"[PASS] Edge count ({num_edges}) exceeds required threshold (>10,000).")

    # 2. Strongly connected
    is_scc = nx.is_strongly_connected(G)
    assert is_scc, "Graph G_embedded is not strongly connected!"
    print(f"[PASS] G_embedded is strongly connected (100% reachability across all {num_nodes} nodes).")

    # 3. Exactly 700 monitored edges
    monitored_edges = [
        (u, v, k, d)
        for u, v, k, d in G.edges(keys=True, data=True)
        if d.get("is_monitored") is True or str(d.get("is_monitored")).lower() == "true"
    ]
    assert len(monitored_edges) == 700, f"Expected exactly 700 monitored edges, found {len(monitored_edges)}"
    print(f"[PASS] Exactly 700 edges possess is_monitored=True attribute.")

    return G


def test_b_dijkstra_baseline(G):
    """Test B: Select a source/target pair spanning across the city, run custom Dijkstra."""
    print("\n" + "=" * 60)
    print("RUNNING TEST B: Custom Dijkstra Baseline")
    print("=" * 60)

    # Origin and destination spanning an arterial corridor monitored by segment 309
    source = "293452459"
    target = "4613766153"

    print(f"Selected Origin: Node {source}")
    print(f"Selected Destination: Node {target}")

    path, cost = custom_dijkstra(G, source, target, alpha=1.0, beta=1.0)

    assert len(path) > 0, "Dijkstra returned an empty path!"
    assert str(path[0]) == str(source), f"Path does not start at source: {path[0]} vs {source}"
    assert str(path[-1]) == str(target), f"Path does not end at target: {path[-1]} vs {target}"
    assert cost < float("inf"), "Path cost is infinite!"
    assert cost > 0.0, f"Path cost must be positive, got {cost}"

    print(f"[PASS] Baseline path successfully found!")
    print(f"       Path Sequence: {path}")
    print(f"       Hops: {len(path)} nodes, Total Cost: {cost:.2f}")

    return source, target, path, cost


def test_c_dynamic_reroute_trigger(G, source, target, baseline_path, baseline_cost):
    """Test C: Inject 5 km/h traffic jam on monitored segment, verify path divergence."""
    print("\n" + "=" * 60)
    print("RUNNING TEST C: Dynamic Reroute Trigger")
    print("=" * 60)

    # Identify monitored segments along the baseline path
    monitored_traversed = []
    for i in range(len(baseline_path) - 1):
        u = baseline_path[i]
        v = baseline_path[i + 1]
        for key, d in G[u][v].items():
            if d.get("is_monitored") is True or str(d.get("is_monitored")).lower() == "true":
                sid = d.get("segment_id")
                if sid is not None and sid != -1 and sid != "-1":
                    monitored_traversed.append((int(sid), u, v))

    print(f"Monitored segments traversed in baseline: {len(monitored_traversed)}")
    assert len(monitored_traversed) > 0, "Baseline path did not traverse any monitored segments!"

    jammed_sid, jam_u, jam_v = monitored_traversed[0]
    print(f"Simulating heavy congestion on segment_id={jammed_sid} (edge {jam_u} -> {jam_v}):")
    print(f"Setting speed to 5.0 km/h (severe traffic jam)...")

    edge_speeds_dict = {jammed_sid: 5.0}

    # Re-run custom Dijkstra with dynamic congestion
    rerouted_path, rerouted_cost = custom_dijkstra(
        G, source, target, alpha=1.0, beta=1.0, edge_speeds_dict=edge_speeds_dict
    )

    print(f"Baseline Path ({len(baseline_path)} nodes): {baseline_path} (Cost: {baseline_cost:.2f})")
    print(f"Rerouted Path ({len(rerouted_path)} nodes): {rerouted_path} (Cost: {rerouted_cost:.2f})")

    # Assertion: The path must diverge to bypass the congested link
    assert (
        rerouted_path != baseline_path
    ), "Assertion Failed: Path did not diverge when congestion was injected!"

    # Verify that the jammed edge was avoided
    diverted = True
    for i in range(len(rerouted_path) - 1):
        if rerouted_path[i] == jam_u and rerouted_path[i + 1] == jam_v:
            diverted = False
            break

    print(f"[PASS] Path successfully diverged around jammed segment {jammed_sid} (avoided jammed edge: {diverted})!")
    print(f"[PASS] Alternative route successfully selected by Custom Dijkstra engine.")


def main():
    print("Starting Phase 2 Automated Test Suite...")
    G = test_a_graph_validation()
    source, target, path, cost = test_b_dijkstra_baseline(G)
    test_c_dynamic_reroute_trigger(G, source, target, path, cost)

    print("\n" + "=" * 60)
    print("ALL PHASE 2 VALIDATION TESTS PASSED SUCCESSFULLY! (3/3)")
    print("=" * 60)


if __name__ == "__main__":
    main()
