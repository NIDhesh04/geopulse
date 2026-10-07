import osmnx as ox
import networkx as nx
import pandas as pd
import numpy as np

ox.settings.use_cache = True
ox.settings.requests_timeout = 300
ox.settings.user_agent = 'GeoPulseResearch/1.0 (academic research; contact: research@geopulse.bhu)'

print("Loading G...")
G = ox.graph_from_place('Bhubaneswar, India', network_type='drive', simplify=True)
print(f"Original G: {len(G)} nodes, {G.number_of_edges()} edges")

scc = max(nx.strongly_connected_components(G), key=len)
G_scc = G.subgraph(scc).copy()
print(f"SCC G: {len(G_scc)} nodes, {G_scc.number_of_edges()} edges")

print("Projecting to EPSG:32645...")
G_proj = ox.project_graph(G_scc, to_crs='EPSG:32645')

endpoints = pd.read_csv('data/interim/segment_endpoints.csv', index_col=0)
meta = pd.read_csv('data/interim/segment_metadata.csv', index_col=0)

# Check matches in G_proj
edges_df = ox.graph_to_gdfs(G_proj, nodes=False, fill_edge_geometry=True).reset_index()
print(f"Edges DataFrame: {len(edges_df)} rows")

# Check endpoint matching
direct_matches = 0
for sid, r in endpoints.iterrows():
    u, v = r.get('u'), r.get('v')
    if pd.notna(u) and pd.notna(v):
        u, v = int(u), int(v)
        if G_proj.has_edge(u, v) or G_proj.has_edge(v, u):
            direct_matches += 1

print(f"Direct (u, v) or (v, u) matches in G_scc: {direct_matches} / {len(endpoints)}")
