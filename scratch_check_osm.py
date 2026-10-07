import json
import math
import pandas as pd

ways = json.load(open('data/external/osm_ways.json', encoding='utf-8'))
nodes = json.load(open('data/external/osm_nodes.json', encoding='utf-8'))
meta = pd.read_csv('data/interim/segment_metadata.csv', index_col=0)

def haversine(n1, n2):
    p1, p2 = nodes[str(n1)], nodes[str(n2)]
    R = 6371000.0
    phi1, phi2 = math.radians(p1['lat']), math.radians(p2['lat'])
    dphi = math.radians(p2['lat'] - p1['lat'])
    dlam = math.radians(p2['lon'] - p1['lon'])
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2)**2
    return 2 * R * math.asin(math.sqrt(a))

way_lengths = {}
for wid, w in ways.items():
    nds = w.get('nodes', [])
    l = sum(haversine(nds[i], nds[i+1]) for i in range(len(nds)-1))
    way_lengths[int(wid)] = l

print("Sample calculated OSM way lengths vs dataset length_m:")
diffs = []
for sid in meta.index:
    r = meta.loc[sid]
    wids = [int(x) for x in str(r['osmid_key']).split('|')]
    tot_l = sum(way_lengths.get(w, 0) for w in wids)
    diff = abs(tot_l - r['length_m'])
    diffs.append((sid, r['length_m'], tot_l, diff))
    if sid in [0, 1, 2, 350, 351, 352]:
        print(f"sid={sid}, road_type={r['road_type']}, dataset_len={r['length_m']:.2f}, osm_calc_len={tot_l:.2f}, diff={diff:.2f}, ways={wids}")

df_diff = pd.DataFrame(diffs, columns=['sid', 'ds_len', 'osm_len', 'diff'])
print("Diff summary (meters):")
print(df_diff['diff'].describe())
print(f"Number with diff < 2m or < 2%: {((df_diff['diff'] <= 2.0) | (df_diff['diff'] / df_diff['ds_len'] <= 0.02)).sum()} / {len(df_diff)}")
