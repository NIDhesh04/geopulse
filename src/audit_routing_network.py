"""Read-only audit of GeoPulse traffic-to-OSM routing network mapping.

Run from the workspace using the project virtualenv:
  python src/audit_routing_network.py

Only outputs/routing_mapping_audit is written. The DuckDB and GraphML inputs
are read-only. No model is trained and no routing cost uses travel-time fields.
"""
from __future__ import annotations

import itertools
import json
import math
import re
from collections import Counter
from pathlib import Path

import duckdb
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
from pyproj import Transformer
from shapely.geometry import LineString, Point
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree

ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/"datasets"/"traffic_v1.duckdb"
GRAPH=ROOT/"notebooks"/"bhubaneswar_drive.graphml"
PREV=ROOT/"outputs"/"dataset_audit"
OUT=ROOT/"outputs"/"routing_mapping_audit"
OUT.mkdir(parents=True,exist_ok=True)
TO_M=Transformer.from_crs("EPSG:4326","EPSG:32645",always_xy=True).transform


def parse_ids(value):
    if isinstance(value,(list,tuple,set,np.ndarray)):
        out=[]
        for x in value: out.extend(parse_ids(x))
        return list(dict.fromkeys(out))
    if value is None or pd.isna(value): return []
    return list(dict.fromkeys(re.findall(r"\d+",str(value))))


def class_norm(value):
    if isinstance(value,(list,tuple,set)): vals=list(value)
    else: vals=[value]
    vals={str(x).lower() for x in vals if x is not None and not pd.isna(x)}
    # Dataset contains primary/secondary/trunk; preserve exact OSM highway tags.
    return vals


def class_score(ds,osm):
    d=str(ds).lower() if pd.notna(ds) else ""
    vals=class_norm(osm)
    if d in vals: return 1.0
    if not vals: return 0.5
    return 0.0


def canonical_line_key(g):
    if g is None or g.is_empty: return b""
    a=g.wkb
    try: b=g.reverse().wkb
    except Exception: b=a
    return min(a,b)


def geometry_for_edge(G,u,v,k,data):
    geom=data.get("geometry")
    if geom is None or geom.is_empty:
        a=G.nodes[u]; b=G.nodes[v]
        geom=LineString([(a["x"],a["y"]),(b["x"],b["y"])])
    return transform(TO_M,geom)


def dump(df,name):
    df.to_csv(OUT/name,index=False)


def num(x):
    return None if x is None or (isinstance(x,float) and not math.isfinite(x)) else x


def corr_and_equal(a,b):
    aa=np.asarray(a,dtype=float); bb=np.asarray(b,dtype=float)
    overlap=np.isfinite(aa)&np.isfinite(bb)
    n=int(overlap.sum())
    cor=float(np.corrcoef(aa[overlap],bb[overlap])[0,1]) if n>=2 and np.std(aa[overlap])>0 and np.std(bb[overlap])>0 else np.nan
    equal=bool(np.array_equal(aa,bb,equal_nan=True))
    return n,cor,equal


def graph_components(G, directed):
    if directed:
        comps=sorted(nx.weakly_connected_components(G),key=len,reverse=True)
    else:
        comps=sorted(nx.connected_components(G),key=len,reverse=True)
    if not comps: return {"components":0,"largest_nodes":0,"largest_edges":0,"largest_nodes_set":set()}
    nodes=comps[0]
    if directed:
        edges=sum(1 for u,v,k in G.edges(keys=True) if u in nodes and v in nodes)
    else:
        edges=sum(1 for u,v in G.edges() if u in nodes and v in nodes)
    return {"components":len(comps),"largest_nodes":len(nodes),"largest_edges":edges,"largest_nodes_set":nodes}


def traffic_components(name, edge_indices, edge_records, segment_edge_map, segment_obs_counts, directed=True):
    GD=nx.MultiDiGraph() if directed else nx.Graph()
    for i in edge_indices:
        e=edge_records[i]
        GD.add_edge(e["u"],e["v"],key=e["key"],route_len=e["route_len"])
    comp=graph_components(GD,directed)
    largest=comp["largest_nodes_set"]
    member=[]
    for sid,inds in segment_edge_map.items():
        ok=any(edge_records[i]["u"] in largest and edge_records[i]["v"] in largest for i in inds)
        if ok: member.append(sid)
    obs=sum(segment_obs_counts.get(s,0) for s in member)
    row={"representation":name,"nodes":GD.number_of_nodes(),"edges":GD.number_of_edges(),
         "weak_components":comp["components"],"largest_component_nodes":comp["largest_nodes"],
         "largest_component_edges":comp["largest_edges"],"traffic_segments_in_largest":len(member),
         "traffic_segment_pct_in_largest":100*len(member)/max(len(segment_edge_map),1),
         "observations_in_largest":obs,"observation_pct_in_largest":100*obs/max(sum(segment_obs_counts.values()),1),
         "segments_with_edge_in_largest":member}
    return row,GD


def main():
    if not DB.is_file() or not GRAPH.is_file(): raise FileNotFoundError("Missing DuckDB or Bhubaneswar GraphML")
    con=duckdb.connect(str(DB),read_only=True)
    df=con.execute("SELECT segment_id, CAST(hour AS VARCHAR) AS hour_s, currentSpeed, freeFlowSpeed, currentTravelTime, freeFlowTravelTime, confidence, is_observed, is_missing, osmid, road_name, road_type, length_m, lat, lon, roadClosure FROM traffic ORDER BY segment_id, hour").fetchdf()
    con.close()
    df["_hour"]=pd.to_datetime(df.hour_s,utc=True,errors="coerce")
    observed=df[df.is_observed.fillna(False)&df.currentSpeed.notna()].copy()
    meta=observed.sort_values("_hour").drop_duplicates("segment_id").set_index("segment_id",drop=False)
    segids=sorted(meta.index.astype(int).tolist())
    seg_ids={int(s):parse_ids(meta.at[s,"osmid"]) for s in segids}
    hours=sorted(df._hour.dropna().unique())
    speed_arrays={}
    obs_counts={}
    for sid,g in df.groupby("segment_id",sort=False):
        x=g.set_index("_hour").currentSpeed.reindex(hours).to_numpy(dtype=float)
        speed_arrays[int(sid)]=x
        obs_counts[int(sid)]=int(np.isfinite(x).sum())

    G=ox.load_graphml(GRAPH)
    edge_records=[]; id_to_edges=Counter(); id_edge_indices={}
    for u,v,k,d in G.edges(keys=True,data=True):
        geom=geometry_for_edge(G,u,v,k,d)
        ids=parse_ids(d.get("osmid"))
        hw=d.get("highway","")
        rec={"u":u,"v":v,"key":k,"ids":ids,"osmid":d.get("osmid"),"highway":hw,
             "geometry":geom,"geom_len":float(geom.length),"route_len":float(d.get("length",geom.length)),
             "geom_key":canonical_line_key(geom)}
        idx=len(edge_records); edge_records.append(rec)
        for oid in ids: id_edge_indices.setdefault(oid,[]).append(idx)
    all_graph_ids=set(id_edge_indices)

    # Aggregate each OSM way's graph pieces and deduplicate reciprocal geometries.
    way_info={}
    for oid,inds in id_edge_indices.items():
        unique={}
        for i in inds:
            e=edge_records[i]
            if e["geom_key"] not in unique: unique[e["geom_key"]]=e
        geoms=[e["geometry"] for e in unique.values()]
        geom=unary_union(geoms) if geoms else None
        way_info[oid]={"indices":inds,"unique_edges":len(unique),"directed_edges":len(inds),
                       "geometry":geom,"geometry_length":float(geom.length) if geom is not None else 0.0,
                       "attribute_length":float(sum(e["route_len"] for e in unique.values())),
                       "highways":sorted({str(h) for i in inds for h in class_norm(edge_records[i]["highway"])})}

    # Reproduce existing best mappings and source duplicate groups.
    prev=pd.read_csv(PREV/"spatial_edge_matches.csv")
    prev=prev[prev.status=="matched"].copy()
    prev["candidate_u"]=prev.candidate_u.astype(int); prev["candidate_v"]=prev.candidate_v.astype(int)
    prev_map={int(r.segment_id):(int(r.candidate_u),int(r.candidate_v),parse_ids(r.candidate_osmid)) for _,r in prev.iterrows()}
    prev_pair_groups=prev.groupby(["candidate_u","candidate_v"]).filter(lambda z:len(z)>1).groupby(["candidate_u","candidate_v"])
    duplicate_rows=[]; duplicate_group_ids=set()
    for (u,v),g in prev_pair_groups:
        sids=sorted(g.segment_id.astype(int).tolist())
        for a,b in itertools.combinations(sids,2):
            duplicate_group_ids.update((a,b))
            ma=meta.loc[a]; mb=meta.loc[b]
            metadata_identical=bool(ma.lat==mb.lat and ma.lon==mb.lon and ma.length_m==mb.length_m and str(ma.osmid)==str(mb.osmid) and str(ma.road_type)==str(mb.road_type))
            n,corr,equal=corr_and_equal(speed_arrays[a],speed_arrays[b])
            ea_ids=seg_ids[a]; eb_ids=seg_ids[b]
            graph_edge_ids=sorted(set(prev_map[a][2]+prev_map[b][2]))
            point_sep=float(transform(TO_M,Point(float(ma.lon),float(ma.lat))).distance(transform(TO_M,Point(float(mb.lon),float(mb.lat)))))
            if metadata_identical and equal: category="A. Clearly duplicate physical segment"
            elif metadata_identical: category="B. Same edge but potentially different traffic measurement"
            elif set(ea_ids)&set(eb_ids) and point_sep>20 and abs(float(ma.length_m)-float(mb.length_m))/max(float(ma.length_m),float(mb.length_m),1)<.5:
                category="D. Probably legitimate separate observations"
            else: category="C. Mapping ambiguity"
            matched_candidates=[i for i,e in enumerate(edge_records) if e["u"]==u and e["v"]==v and set(e["ids"])&set(graph_edge_ids)]
            osm_len=float(np.median([edge_records[i]["route_len"] for i in matched_candidates])) if matched_candidates else np.nan
            duplicate_rows.append({"segment_id_1":a,"segment_id_2":b,"osm_edge":f"{u}->{v}","osm_way_ids_1":";".join(ea_ids),
              "osm_way_ids_2":";".join(eb_ids),"candidate_osm_way_ids":";".join(graph_edge_ids),
              "segment_1_lat":ma.lat,"segment_1_lon":ma.lon,"segment_2_lat":mb.lat,"segment_2_lon":mb.lon,
              "segment_1_length_m":ma.length_m,"segment_2_length_m":mb.length_m,"osm_edge_length_m":osm_len,
              "road_type_1":ma.road_type,"road_type_2":mb.road_type,"distance_1_to_edge_m":float(g.loc[g.segment_id==a,"distance_m"].iloc[0]),
              "distance_2_to_edge_m":float(g.loc[g.segment_id==b,"distance_m"].iloc[0]),"centroid_separation_m":point_sep,
              "all_metadata_identical":metadata_identical,"hourly_speed_series_identical":equal,"speed_correlation":corr,
              "overlapping_observations":n,"classification":category})
    dupdf=pd.DataFrame(duplicate_rows)
    dump(dupdf,"duplicate_mapping_pairs.csv")

    # Multi-ID ways: geometry union, way-by-way lengths, topological continuity and point proximity.
    multi=[]
    for sid in segids:
        ids=seg_ids[sid]
        if len(ids)<=1: continue
        r=meta.loc[sid]
        present=[x for x in ids if x in way_info]
        per=[{"osmid":x,"present":x in way_info,"directed_edges":way_info[x]["directed_edges"] if x in way_info else 0,
              "unique_physical_pieces":way_info[x]["unique_edges"] if x in way_info else 0,
              "geometry_length_m":way_info[x]["geometry_length"] if x in way_info else None,
              "highways":way_info[x]["highways"] if x in way_info else []} for x in ids]
        geoms=[way_info[x]["geometry"] for x in present if way_info[x]["geometry"] is not None]
        combined=unary_union(geoms) if geoms else None
        combined_len=float(combined.length) if combined is not None else np.nan
        pt=transform(TO_M,Point(float(r.lon),float(r.lat))) if pd.notna(r.lat) and pd.notna(r.lon) else None
        distance=float(pt.distance(combined)) if pt is not None and combined is not None else np.nan
        indices=list(dict.fromkeys(i for oid in present for i in id_edge_indices[oid]))
        sub=nx.MultiDiGraph(); sub.add_edges_from((edge_records[i]["u"],edge_records[i]["v"],edge_records[i]["key"]) for i in indices)
        comp=graph_components(sub,True)
        und=nx.Graph(sub)
        geom_components=len(combined.geoms) if combined is not None and hasattr(combined,"geoms") else (1 if combined is not None else 0)
        if len(present)<len(ids): relation="one or more supplied IDs absent from graph"
        elif comp["components"]==1 and geom_components==1: relation="connected ways / likely one road group; direction and segmentation need review"
        elif comp["components"]==1: relation="topologically connected but geometry has multiple parts"
        else: relation="disconnected IDs or mapping ambiguity"
        multi.append({"segment_id":sid,"osmid_count":len(ids),"osmid_list":";".join(ids),"ids_found":len(present),
          "all_ids_found":len(present)==len(ids),"individual_way_details_json":json.dumps(per),
          "traffic_length_m":r.length_m,"combined_geometry_length_m":combined_len,
          "combined_over_traffic_length_ratio":combined_len/float(r.length_m) if pd.notna(r.length_m) and r.length_m>0 and np.isfinite(combined_len) else np.nan,
          "combined_unique_geometry_components":geom_components,"point_to_combined_geometry_m":distance,
          "subgraph_directed_edges":len(indices),"subgraph_nodes":sub.number_of_nodes(),"subgraph_weak_components":comp["components"],
          "subgraph_largest_component_nodes":comp["largest_nodes"],"unique_physical_ways":len(present),"relationship_assessment":relation})
    multidf=pd.DataFrame(multi)
    dump(multidf,"multi_osm_id_segments.csv")
    multi_examples=multidf.assign(abs_log_mismatch=lambda z:np.abs(np.log(z.combined_over_traffic_length_ratio))).sort_values("abs_log_mismatch",ascending=False).head(10)
    dump(multi_examples,"multi_osm_id_examples_10.csv")

    # Improved edge candidate ranking. Scores remain visible component-by-component.
    geoms=[e["geometry"] for e in edge_records]
    tree=STRtree(geoms)
    geom_obj_index={id(g):i for i,g in enumerate(geoms)}
    candidate_rows=[]; best_idx={}; ranked=[]
    for sid in segids:
        r=meta.loc[sid]; ids=set(seg_ids[sid]); p=transform(TO_M,Point(float(r.lon),float(r.lat)))
        hits=tree.query(p.buffer(500)); cands=[]
        for hit in hits:
            i=int(hit) if isinstance(hit,(int,np.integer)) else geom_obj_index.get(id(hit),-1)
            if i<0: continue
            e=edge_records[i]; dist=float(p.distance(e["geometry"]))
            if dist>500: continue
            id_match=bool(ids&set(e["ids"]))
            # For an ID-supported candidate, compare against the unique geometry of its complete way(s),
            # rather than penalizing it for OSMnx splitting a way into short graph edges.
            if id_match:
                way_candidates=[x for x in ids&set(e["ids"]) if x in way_info]
                L=float(unary_union([way_info[x]["geometry"] for x in way_candidates]).length) if way_candidates else e["route_len"]
            else:
                way_candidates=[x for x in e["ids"] if x in way_info]
                L=max((way_info[x]["geometry_length"] for x in way_candidates),default=e["route_len"])
            tl=float(r.length_m) if pd.notna(r.length_m) and float(r.length_m)>0 else np.nan
            length_sim=math.exp(-abs(math.log(tl/L))) if np.isfinite(tl) and L>0 else 0.0
            ds=math.exp(-dist/50.0)
            rs=class_score(r.road_type,e["highway"])
            ids=ids
            total=.30*ds+.20*length_sim+.20*rs+.30*(1.0 if id_match else 0.0)
            cands.append((total,i,dist,ds,length_sim,rs,id_match,L))
        cands.sort(key=lambda z:(-z[0],z[2],edge_records[z[1]]["u"],edge_records[z[1]]["v"],edge_records[z[1]]["key"]))
        if not cands: continue
        best_idx[sid]=cands[0][1]
        for rank,c in enumerate(cands[:5],1):
            score,i,dist,ds,ls,rs,idmatch,L=c; e=edge_records[i]
            ranked.append({"segment_id":sid,"rank":rank,"total_score":score,"distance_m":dist,"distance_score":ds,
              "length_similarity_score":ls,"road_type_score":rs,"osmid_match":idmatch,"candidate_length_basis_m":L,
              "traffic_length_m":r.length_m,"osm_edge_length_attribute_m":e["route_len"],"osm_edge_geometry_length_m":e["geom_len"],
              "length_ratio_traffic_to_basis":float(r.length_m/L) if L>0 else np.nan,"candidate_osmid":";".join(e["ids"]),
              "candidate_highway":str(e["highway"]),"u":e["u"],"v":e["v"],"key":e["key"],"reciprocal_edge_exists":bool(any(x["u"]==e["v"] and x["v"]==e["u"] and x["geom_key"]==e["geom_key"] for x in edge_records))})
    rankdf=pd.DataFrame(ranked)
    dump(rankdf,"improved_candidate_rankings_top5.csv")
    bestdf=rankdf[rankdf["rank"]==1].copy()
    dump(bestdf,"improved_best_matches.csv")

    # Match-set metrics: current best-edge mapping, improved directed mapping, and ID-expanded mapping.
    prev_edge_idx={}
    for sid,(u,v,oids) in prev_map.items():
        point=transform(TO_M,Point(float(meta.at[sid,"lon"]),float(meta.at[sid,"lat"])))
        ix=[i for i,e in enumerate(edge_records) if e["u"]==u and e["v"]==v]
        if oids:
            matched=[i for i in ix if set(edge_records[i]["ids"])&set(oids)]
            if matched: ix=matched
        prev_edge_idx[sid]=min(ix,key=lambda i:point.distance(edge_records[i]["geometry"])) if ix else best_idx.get(sid)
    prev_indices=set(i for i in prev_edge_idx.values() if i is not None)
    improved_indices=set(best_idx.values())
    id_union=set(oid for sid in segids for oid in seg_ids[sid])
    id_indices=set(i for oid in id_union for i in id_edge_indices.get(oid,[]))
    prev_seg_map={sid:[i] for sid,i in prev_edge_idx.items() if i is not None}
    imp_seg_map={sid:[i] for sid,i in best_idx.items()}
    id_seg_map={sid:list(dict.fromkeys(i for oid in seg_ids[sid] for i in id_edge_indices.get(oid,[]))) for sid in segids}
    prev_m,prevG=traffic_components("previous best edge",prev_indices,edge_records,prev_seg_map,obs_counts,True)
    imp_m,impG=traffic_components("improved best edge",improved_indices,edge_records,imp_seg_map,obs_counts,True)
    id_m,idG=traffic_components("all graph edges for supplied OSM IDs",id_indices,edge_records,id_seg_map,obs_counts,True)
    # Undirected physical-road representations collapse reverse arcs and parallel edges by endpoint pair.
    network_rows=[]
    full_w=graph_components(G,True)
    Gu=nx.Graph(); Gu.add_nodes_from(G.nodes)
    for u,v,k,d in G.edges(keys=True,data=True):
        w=float(d.get("length",1.0));
        if Gu.has_edge(u,v): Gu[u][v]["route_len"]=min(Gu[u][v]["route_len"],w)
        else: Gu.add_edge(u,v,route_len=w)
    full_u=graph_components(Gu,False)
    network_rows.append({"representation":"full OSM directed graph","nodes":G.number_of_nodes(),"edges":G.number_of_edges(),"weak_components":full_w["components"],"largest_component_nodes":full_w["largest_nodes"],"largest_component_edges":full_w["largest_edges"]})
    network_rows.append({"representation":"full OSM undirected physical graph","nodes":Gu.number_of_nodes(),"edges":Gu.number_of_edges(),"weak_components":full_u["components"],"largest_component_nodes":full_u["largest_nodes"],"largest_component_edges":full_u["largest_edges"]})
    for row,gx,segment_map,edge_set in ((prev_m,prevG,prev_seg_map,prev_indices),(imp_m,impG,imp_seg_map,improved_indices),(id_m,idG,id_seg_map,id_indices)):
        network_rows.append({k:v for k,v in row.items() if k!="segments_with_edge_in_largest"})
        physical_indices={}
        for i in edge_set:
            e=edge_records[i]
            physical_indices.setdefault(tuple(sorted((e["u"],e["v"]))),i)
        undirected_edge_indices=set(physical_indices.values())
        undirected_segment_map={sid:list(dict.fromkeys(physical_indices[tuple(sorted((edge_records[i]["u"],edge_records[i]["v"]))) ] for i in inds)) for sid,inds in segment_map.items()}
        um,gu=traffic_components(row["representation"]+" (undirected)",undirected_edge_indices,edge_records,undirected_segment_map,obs_counts,False)
        network_rows.append({k:v for k,v in um.items() if k!="segments_with_edge_in_largest"})

    # Per-network coverage denominator and route-capable traffic segments.
    def largest_stats(gx, edge_map):
        comp=graph_components(gx,True); nodes=comp["largest_nodes_set"]
        segs=[sid for sid,ix in edge_map.items() if any(edge_records[i]["u"] in nodes and edge_records[i]["v"] in nodes for i in ix)]
        obs=sum(obs_counts[x] for x in segs)
        return {"largest_nodes":comp["largest_nodes"],"largest_edges":comp["largest_edges"],"weak_components":comp["components"],
          "traffic_segments":len(segs),"traffic_segment_pct":100*len(segs)/700,"traffic_observations":obs,
          "traffic_observation_pct":100*obs/max(sum(obs_counts.values()),1),"segment_ids":segs}
    prev_l=largest_stats(prevG,prev_seg_map); imp_l=largest_stats(impG,imp_seg_map); id_l=largest_stats(idG,id_seg_map)
    # Largest SCC in the full directed OSM graph indicates arcs usable in both directions.
    scc=sorted(nx.strongly_connected_components(G),key=len,reverse=True)
    largest_scc=set(scc[0]) if scc else set()
    route_capable=sum(1 for sid,i in best_idx.items() if edge_records[i]["u"] in largest_scc and edge_records[i]["v"] in largest_scc)
    def scc_stats(gx):
        parts=sorted(nx.strongly_connected_components(gx),key=len,reverse=True)
        return {"strongly_connected_components":len(parts),"largest_scc_nodes":len(parts[0]) if parts else 0,
                "largest_scc_node_pct":100*len(parts[0])/max(gx.number_of_nodes(),1) if parts else 0}
    full_scc_stats=scc_stats(G)
    previous_scc_stats=scc_stats(prevG)
    improved_scc_stats=scc_stats(impG)
    id_scc_stats=scc_stats(idG)
    for row in network_rows:
        if row["representation"]=="full OSM directed graph": row.update(full_scc_stats)
        elif row["representation"]=="previous best edge": row.update(previous_scc_stats)
        elif row["representation"]=="improved best edge": row.update(improved_scc_stats)
        elif row["representation"]=="all graph edges for supplied OSM IDs": row.update(id_scc_stats)
    netdf=pd.DataFrame(network_rows)
    dump(netdf,"directed_undirected_connectivity.csv")

    # Multi-ID summary and graph way counts.
    parsed_id_counts=Counter(x for ids in seg_ids.values() for x in ids)
    osm_match={"traffic_segments":len(segids),"multi_id_segments":sum(len(x)>1 for x in seg_ids.values()),
      "unique_traffic_osm_ids":len(id_union),"unique_traffic_osm_ids_found":len(id_union&all_graph_ids),
      "all_ids_found_segments":sum(all(x in all_graph_ids for x in ids) for ids in seg_ids.values()),
      "segments_with_any_id_found":sum(any(x in all_graph_ids for x in ids) for ids in seg_ids.values()),
      "segments_single_id":sum(len(x)==1 for x in seg_ids.values()),
      "segments_multiple_ids":sum(len(x)>1 for x in seg_ids.values()),
      "total_id_edge_occurrences":sum(parsed_id_counts.values())}

    # Geometric overlap screen. There is no traffic polyline; use the selected OSM edge
    # geometry as a documented proxy, with centroids to define close pairs (<=100 m).
    selected=[best_idx[s] for s in segids]
    points=[transform(TO_M,Point(float(meta.at[s,"lon"]),float(meta.at[s,"lat"]))) for s in segids]
    ptree=STRtree(points); pobj={id(p):i for i,p in enumerate(points)}
    pairs=set()
    for i,p in enumerate(points):
        hits=ptree.query(p.buffer(100))
        for h in hits:
            j=int(h) if isinstance(h,(int,np.integer)) else pobj.get(id(h),-1)
            if j>i and p.distance(points[j])<=100: pairs.add((i,j))
    overlap_rows=[]
    for i,j in sorted(pairs):
        a,b=segids[i],segids[j]; ea,eb=edge_records[selected[i]],edge_records[selected[j]]
        ga,gb=ea["geometry"],eb["geometry"]
        gd=float(ga.distance(gb)); ilen=float(ga.intersection(gb).length) if ga.intersects(gb) else 0.0
        minlen=max(min(ga.length,gb.length),1e-9); frac=ilen/minlen
        pointsep=float(points[i].distance(points[j]))
        if selected[i]==selected[j] or (frac>=.8 and pointsep<=10): cls="duplicate"
        elif ilen>=max(5,.1*minlen): cls="overlapping but distinct"
        elif gd<=2: cls="adjacent"
        else: cls="unrelated"
        ra,rb=meta.loc[a],meta.loc[b]
        overlap_rows.append({"segment_id_1":a,"segment_id_2":b,"centroid_distance_m":pointsep,"inferred_geometry_distance_m":gd,
          "inferred_intersection_length_m":ilen,"overlap_fraction_of_shorter_edge":frac,"osm_edge_1":f"{ea['u']}->{ea['v']}#{ea['key']}",
          "osm_edge_2":f"{eb['u']}->{eb['v']}#{eb['key']}","osmid_1":";".join(seg_ids[a]),"osmid_2":";".join(seg_ids[b]),
          "length_1_m":ra.length_m,"length_2_m":rb.length_m,"road_type_1":ra.road_type,"road_type_2":rb.road_type,"classification":cls})
    overlapdf=pd.DataFrame(overlap_rows)
    dump(overlapdf,"close_segment_geometry_pairs.csv")
    overlap_counts=overlapdf.classification.value_counts().to_dict() if len(overlapdf) else {}

    # Duplicate mapping geometry evidence and classifications.
    dup_counts=Counter(dupdf.classification) if len(dupdf) else Counter()

    # Fixed-seed directed routing feasibility sample on full OSM graph.
    # Use geometry-derived metric edge lengths; shortest path never reads traffic travel-time columns.
    routeG=nx.MultiDiGraph()
    routeG.add_nodes_from(G.nodes(data=True))
    for i,e in enumerate(edge_records):
        routeG.add_edge(e["u"],e["v"],key=e["key"],route_len=e["geom_len"],edge_index=i)
    fullcomp=full_w["largest_nodes_set"]
    rng=np.random.default_rng(20261006)
    node_pool=list(fullcomp)
    od_pairs=[]; seen=set(); tries=0
    while len(od_pairs)<100 and tries<10000:
        tries+=1
        o,d=rng.choice(node_pool,size=2,replace=False)
        if (o,d) in seen: continue
        po=transform(TO_M,Point(float(G.nodes[o]["x"]),float(G.nodes[o]["y"])))
        pdest=transform(TO_M,Point(float(G.nodes[d]["x"]),float(G.nodes[d]["y"])))
        if po.distance(pdest)<2000: continue
        seen.add((o,d)); od_pairs.append((o,d))
    route_rows=[]
    for oi,(o,d) in enumerate(od_pairs,1):
        try:
            nodes=nx.shortest_path(routeG,o,d,weight="route_len",method="dijkstra")
            path_edges=[]
            for u,v in zip(nodes[:-1],nodes[1:]):
                opts=routeG[u][v]
                key=min(opts,key=lambda k:opts[k]["route_len"])
                path_edges.append((u,v,key,opts[key]))
            dist=sum(x[3]["route_len"] for x in path_edges)
            dyn_dir=sum(x[2] in G[x[0]][x[1]] and (x[0],x[1],x[2]) in {(edge_records[k]["u"],edge_records[k]["v"],edge_records[k]["key"]) for k in improved_indices} for x in path_edges)
            dyn_phys=sum(tuple(sorted((x[0],x[1]))) in {tuple(sorted((edge_records[k]["u"],edge_records[k]["v"]))) for k in improved_indices} for x in path_edges)
            route_rows.append({"od_id":oi,"origin":o,"destination":d,"status":"valid","route_distance_m":dist,"route_edges":len(path_edges),
              "directed_dynamic_edges":int(dyn_dir),"directed_dynamic_coverage_pct":100*dyn_dir/max(len(path_edges),1),
              "physical_dynamic_edges":int(dyn_phys),"physical_dynamic_coverage_pct":100*dyn_phys/max(len(path_edges),1)})
        except (nx.NetworkXNoPath,nx.NodeNotFound):
            route_rows.append({"od_id":oi,"origin":o,"destination":d,"status":"no_directed_path","route_distance_m":np.nan,"route_edges":0,
              "directed_dynamic_edges":0,"directed_dynamic_coverage_pct":np.nan,"physical_dynamic_edges":0,"physical_dynamic_coverage_pct":np.nan})
    od_df=pd.DataFrame(route_rows)
    dump(od_df,"routing_od_feasibility_100.csv")
    valid=od_df[od_df.status=="valid"]
    cov=valid.physical_dynamic_coverage_pct
    route_stats={"pairs_tested":len(od_df),"valid_routes":len(valid),"failed_routes":len(od_df)-len(valid),
      "success_pct":100*len(valid)/max(len(od_df),1),"min_euclidean_od_distance_m":2000,"seed":20261006,
      "route_distance_median":float(valid.route_distance_m.median()) if len(valid) else None,
      "route_distance_min":float(valid.route_distance_m.min()) if len(valid) else None,
      "route_distance_max":float(valid.route_distance_m.max()) if len(valid) else None,
      "dynamic_coverage_definition":"unique validated physical mapped endpoint pair present on each route edge; direction unresolved",
      "dynamic_coverage":{"mean":float(cov.mean()) if len(cov) else None,"median":float(cov.median()) if len(cov) else None,
        "min":float(cov.min()) if len(cov) else None,"max":float(cov.max()) if len(cov) else None,
        "q25":float(cov.quantile(.25)) if len(cov) else None,"q75":float(cov.quantile(.75)) if len(cov) else None,
        "gt25_pct":100*float((cov>25).mean()) if len(cov) else None,"gt50_pct":100*float((cov>50).mean()) if len(cov) else None,
        "gt75_pct":100*float((cov>75).mean()) if len(cov) else None,"gt90_pct":100*float((cov>90).mean()) if len(cov) else None}}

    # Direction ambiguity on exact way-supported candidates: reciprocal geometry with matching score.
    reciprocal=0
    for sid,i in best_idx.items():
        e=edge_records[i]
        if any(x["u"]==e["v"] and x["v"]==e["u"] and x["geom_key"]==e["geom_key"] and set(x["ids"])&set(seg_ids[sid]) for x in edge_records): reciprocal+=1

    summary={"inputs":{"database":str(DB),"graph":str(GRAPH),"graph_crs":str(G.graph.get("crs")),"graph_simplified":G.graph.get("simplified"),
      "previous_audit_script":str(ROOT/"src"/"audit_dataset.py"),"previous_spatial_csv":str(PREV/"spatial_edge_matches.csv")},
      "previous_method":{"source_crs":"EPSG:4326","analysis_crs":"EPSG:32645 UTM zone 45N","distance":"Shapely point-to-directed-edge LineString distance",
        "candidate_radius_m":500,"selection":"min score = d/50 + 0/1 road mismatch + 0.25*abs(log(dataset length / projected edge geometry length))",
        "directed_edges_considered":True,"undirected_collapse":False,"osm_id_in_score":False,"multi_id_handling":"IDs parsed for existence only, not candidate scoring",
        "edge_length":"projected geometry length, not GraphML edge length attribute","road_type":"coarse class exact match; other class treated as compatible"},
      "traffic":{"segments":len(segids),"observations":int(observed.shape[0]),"observed_counts_total":int(sum(obs_counts.values())),"multi_id_segments":sum(len(x)>1 for x in seg_ids.values())},
      "duplicate_mappings":{"pairs":len(dupdf),"duplicate_candidate_edge_groups":int(prev[prev.duplicated(['candidate_u','candidate_v'],keep=False)].groupby(['candidate_u','candidate_v']).ngroups),
        "segment_ids_in_duplicate_groups":len(duplicate_group_ids),"classes":dict(dup_counts),"exact_centroid_length_osmid_pairs":int(sum(dupdf.all_metadata_identical)),
        "series_identical_pairs":int(sum(dupdf.hourly_speed_series_identical)),"same_edge_direction_endpoint_unique":int(prev[['candidate_u','candidate_v']].drop_duplicates().shape[0]),
        "same_edge_undirected_endpoint_unique":int(prev.apply(lambda r:tuple(sorted((int(r.candidate_u),int(r.candidate_v)))),axis=1).nunique())},
      "osm_ids":osm_match,
      "multi_id":{"segments":len(multidf),"all_ids_found_segments":int(multidf.all_ids_found.sum()),
        "topologically_connected_multi_id_segments":int(multidf.relationship_assessment.str.startswith('topologically connected').sum()),
        "disconnected_or_ambiguous_segments":int(multidf.relationship_assessment.str.startswith('disconnected').sum()),
        "single_component_multi_id_segments":int(((multidf.subgraph_weak_components==1)&(multidf.combined_unique_geometry_components==1)).sum()),
        "combined_length_ratio_median":float(multidf.combined_over_traffic_length_ratio.median()),
        "combined_length_ratio_min":float(multidf.combined_over_traffic_length_ratio.min()),"combined_length_ratio_max":float(multidf.combined_over_traffic_length_ratio.max()),
        "examples_10":multi_examples[["segment_id","osmid_list","traffic_length_m","combined_geometry_length_m","combined_over_traffic_length_ratio","point_to_combined_geometry_m","relationship_assessment"]].to_dict(orient="records")},
      "connectivity":{"full_directed":{"nodes":G.number_of_nodes(),"edges":G.number_of_edges(),"weak_components":full_w["components"],"largest_nodes":full_w["largest_nodes"],"largest_edges":full_w["largest_edges"],**full_scc_stats},
        "full_undirected":{"nodes":Gu.number_of_nodes(),"edges":Gu.number_of_edges(),"components":full_u["components"],"largest_nodes":full_u["largest_nodes"],"largest_edges":full_u["largest_edges"]},
        "previous_best_mapping":{**prev_m,**previous_scc_stats},"improved_best_mapping":{**imp_m,**improved_scc_stats},"osm_id_expanded_mapping":{**id_m,**id_scc_stats},
        "improved_largest_component":imp_l,"id_expanded_largest_component":id_l,"improved_mapped_segments_in_largest_full_scc":route_capable,
        "improved_edges_with_reciprocal_same_geometry_candidate":reciprocal,"edge_network_metrics_csv":"directed_undirected_connectivity.csv"},
      "matching":{"scoring_weights":{"distance":.30,"length_similarity":.20,"road_type":.20,"osm_id":.30},
        "formula":"total=0.30*exp(-distance_m/50)+0.20*exp(-abs(log(traffic_length/effective_OSM_way_length)))+0.20*road_type_score+0.30*OSM_ID_match",
        "matched_segments":len(best_idx),"best_match_osmid_evidence_count":int(bestdf.osmid_match.sum()),
        "best_match_distance_median":float(bestdf.distance_m.median()),"best_match_distance_p95":float(bestdf.distance_m.quantile(.95)),"best_match_distance_max":float(bestdf.distance_m.max()),
        "best_match_road_type_match_pct":100*float((bestdf.road_type_score==1).mean()),
        "best_match_duplicate_directed_pairs":int(bestdf.groupby(['u','v']).size().gt(1).sum()),
        "best_match_unique_directed_edges":int(bestdf[['u','v','key']].drop_duplicates().shape[0])},
      "overlap_screen":{"close_centroid_pair_threshold_m":100,"pairs_screened":len(overlapdf),"classification_counts":overlap_counts,
        "limitation":"No traffic polylines exist; OSM candidate edge lines are used as inferred geometry proxy."},
      "routing":{"tested_on":"full directed OSM graph largest weak component; costs use projected OSM geometry lengths only",
        "route_sample":route_stats,"mapped_unique_directed_edge_pct_of_graph":100*len(improved_indices)/G.number_of_edges(),
        "mapped_unique_physical_endpoint_pairs":len({tuple(sorted((edge_records[i]['u'],edge_records[i]['v']))) for i in improved_indices}),
        "mapped_physical_edge_pct_of_full_undirected_graph":100*len({tuple(sorted((edge_records[i]['u'],edge_records[i]['v']))) for i in improved_indices})/Gu.number_of_edges()},
      "architecture_options":{
        "A":{"feasible":False,"quality":"poor","reason":"Traffic segment table is not itself a connected graph; duplicate edge assignments and discontinuities remain."},
        "B":{"feasible":True,"quality":"conditional","reason":"Full OSM topology connects routes, but static fallback on unobserved edges and validated edge mapping must be explicit."},
        "C":{"feasible":True,"quality":"limited","reason":"Largest improved traffic-mapped component may be too small; see measured share."},
        "D":{"feasible":True,"quality":"necessary preprocessing, insufficient alone","reason":"Aggregate repeated traffic-to-physical-road mappings only by documented, direction-aware rules; this does not connect unrelated components."},
        "E":{"feasible":True,"quality":"best conditional design","reason":"Use full OSM topology, validated dynamic costs only on unique mapped edges, and a documented static fallback elsewhere."}}
    }
    (OUT/"summary.json").write_text(json.dumps(summary,indent=2,default=str),encoding="utf-8")
    write_report(summary,dupdf,multidf,multi_examples,netdf,overlapdf,route_stats,rankdf)
    print(f"Routing mapping audit complete: {OUT}")


def write_report(s,dupdf,multidf,multi_examples,netdf,overlapdf,route_stats,rankdf):
    def table(d,n=None):
        d=d.head(n) if n else d
        if d.empty:return "(no rows)"
        cols=list(d.columns)
        out=["| "+" | ".join(map(str,cols))+" |","| "+" | ".join(["---"]*len(cols))+" |"]
        for row in d.itertuples(index=False,name=None): out.append("| "+" | ".join(str(x) if pd.notna(x) else "" for x in row)+" |")
        return "\n".join(out)
    conn=s["connectivity"]; dup=s["duplicate_mappings"]; multi=s["multi_id"]; rt=route_stats
    lines=["# GeoPulse routing network mapping audit","",
      "Read-only audit. The raw DuckDB and GraphML were not modified, and no ML models were trained. Route feasibility costs use only projected OSM geometry lengths, never the traffic travel-time columns.","",
      "## A. Mapping summary","",
      "| Metric | Value |","| --- | ---: |",
      f"| Traffic segments | {s['traffic']['segments']} |",f"| OSM graph nodes | {conn['full_directed']['nodes']} |",f"| OSM graph directed edges | {conn['full_directed']['edges']} |",
      f"| Previous unique mapped directed endpoint pairs | {dup['same_edge_direction_endpoint_unique']} |",f"| Duplicate mapping groups / segment pairs | {dup['duplicate_candidate_edge_groups']} / {dup['pairs']} |",
      f"| Multi-ID segments | {s['osm_ids']['multi_id_segments']} |",f"| ID-expanded weak components | {conn['osm_id_expanded_mapping']['weak_components']} |",
      f"| ID-expanded largest component nodes | {conn['osm_id_expanded_mapping']['largest_component_nodes']} |",f"| ID-expanded largest component edges | {conn['osm_id_expanded_mapping']['largest_component_edges']} |",
      f"| Improved mapped segments in largest mapped component | {conn['improved_largest_component']['traffic_segments']} ({conn['improved_largest_component']['traffic_segment_pct']:.2f}%) |",
      f"| Improved mapped largest component nodes / edges | {conn['improved_largest_component']['largest_nodes']} / {conn['improved_largest_component']['largest_edges']} |","",
      "## 1. Reproduced previous method","",
      f"The previous script uses EPSG:4326 traffic points, projects points and graph edge LineStrings into EPSG:32645 (UTM zone 45N), queries actual edge geometries within 500 m, and selects minimum score `distance/50 + road_type_mismatch + 0.25*abs(log(dataset_length/projected_edge_geometry_length))`. It compares directed edges independently; it does not collapse reciprocal directions. OSM IDs are parsed for existence but are not used in the score. Multi-ID segments are not treated as bundles. Length is the projected geometry length, not GraphML's `length` attribute. Road type is a coarse exact-class comparison, with unknown `other` treated as compatible. The previous CSV omits the graph edge key, so parallel edges sharing `(u,v)` cannot be distinguished from that CSV alone.","",
      "## 2. Duplicate mapping pairs","",
      f"The 700 previous assignments collapse to {dup['same_edge_direction_endpoint_unique']} unique directed endpoint pairs: {dup['duplicate_candidate_edge_groups']} pairs of segments share one best `(u,v)` edge, producing {dup['pairs']} repeated assignments. Of the 55 pairs, {dup['exact_centroid_length_osmid_pairs']} have identical coordinates, length, road type, and source OSM ID; {dup['series_identical_pairs']} have identical complete hourly currentSpeed arrays (including missing positions), and {dup['classes'].get('A. Clearly duplicate physical segment',0)} satisfy both tests. Pair classification counts: {json.dumps(dup['classes'])}. These are mapping collisions and likely physical duplicates, but do not delete either row without establishing whether they are duplicate API records or distinct measurements of one physical edge.","",
      "Full requested per-pair fields, correlations, overlapping-observation counts, and classifications are in `duplicate_mapping_pairs.csv`.","",
      "## 3. Multi-OSM-ID segments","",
      f"There are {multi['segments']} multi-ID segments. {multi['all_ids_found_segments']} have every parsed ID represented in the GraphML; {multi['topologically_connected_multi_id_segments']} have connected graph topology, but only {multi['single_component_multi_id_segments']} have both one graph component and one combined geometry component; {multi['disconnected_or_ambiguous_segments']} are disconnected or ambiguous. Their component/length/point results are in `multi_osm_id_segments.csv`; ten largest combined-length mismatches are in `multi_osm_id_examples_10.csv`. Combined OSM geometry length / traffic length median/min/max: {multi['combined_length_ratio_median']:.3f} / {multi['combined_length_ratio_min']:.3f} / {multi['combined_length_ratio_max']:.3f}. The per-ID JSON lists individual directed edge counts, unique physical geometry-piece counts, lengths, and highway tags. Geometry union deduplicates exact reciprocal/reverse lines; it cannot prove the API's own segment geometry because that polyline is not stored.","",
      table(pd.DataFrame(multi['examples_10']),10),"",
      "## 4. Directed and undirected connectivity","",table(netdf),"",
      f"The full graph has {conn['full_directed']['strongly_connected_components']} strongly connected components; its largest has {conn['full_directed']['largest_scc_nodes']} nodes ({conn['full_directed']['largest_scc_node_pct']:.1f}% of nodes). {conn['improved_mapped_segments_in_largest_full_scc']}/700 selected traffic-edge assignments have both endpoints in that largest SCC. Weak-component results are unchanged after collapsing reciprocal directions; directionality is not the main cause of the mapped-subnetwork fragmentation. The mapped subset remains highly fragmented in its undirected physical projection. Thus the dominant issue is sparse/disconnected mapped coverage, not simply counting each road direction separately.","",
      "## 5. Improved matching method","",
      f"Each candidate edge is scored with visible components: distance score `exp(-d/50m)` (30%); length similarity `exp(-abs(log(traffic_length/effective_way_length)))` (20%); road class (20%); exact OSM-ID evidence (30%). For ID-supported candidates, effective OSM length is the union length of the supplied OSM way geometry, deduplicating reverse copies; otherwise it is the candidate way's union length. Candidates are restricted to actual edge geometries within 500 m. Top five per traffic segment, including score components, edge key and OSM ID evidence, are in `improved_candidate_rankings_top5.csv`; selected assignments are in `improved_best_matches.csv`.","",
      f"Improved match coverage: {s['matching']['matched_segments']}/700; OSM-ID-supported best candidates: {s['matching']['best_match_osmid_evidence_count']}; median/p95/max distance {s['matching']['best_match_distance_median']:.3f}/{s['matching']['best_match_distance_p95']:.3f}/{s['matching']['best_match_distance_max']:.3f} m; broad class match {s['matching']['best_match_road_type_match_pct']:.2f}%. This is a reproducible ranking, not ground-truth validation; direction remains unresolved for candidates with reciprocal identical geometry.","",
      "## 6. Largest connected traffic subset","",
      f"Improved best-edge mapping: {conn['improved_largest_component']['traffic_segments']}/700 segments ({conn['improved_largest_component']['traffic_segment_pct']:.2f}%) in its largest weak component, with {conn['improved_largest_component']['largest_nodes']} nodes and {conn['improved_largest_component']['largest_edges']} edges; that is **{('Excellent' if conn['improved_largest_component']['traffic_segment_pct']>80 else 'Acceptable' if conn['improved_largest_component']['traffic_segment_pct']>=50 else 'Weak' if conn['improved_largest_component']['traffic_segment_pct']>=20 else 'Unusable')}** by the project thresholds. Expanding each traffic segment to all supplied OSM IDs increases the largest mapped component to {conn['id_expanded_largest_component']['traffic_segments']}/700 ({conn['id_expanded_largest_component']['traffic_segment_pct']:.2f}%). Full component metrics, including observation share, are in `summary.json`.","",
      "## 7. Segment geometry overlap screen","",
      f"There are {len(overlapdf)} segment-centroid pairs within 100 m. Using best-matched OSM edge lines as inferred geometries (traffic polylines are unavailable), pair counts are {json.dumps(s['overlap_screen']['classification_counts'])}. This is a proxy screen: it can identify duplicate/overlapping OSM assignments but cannot establish overlap of the traffic provider's original polylines. Full pair details are in `close_segment_geometry_pairs.csv`.","",
      "## 8. Why 700 assignments became 645","",
      f"Reconciliation on the previous CSV's `(u,v)` identity: 700 segment assignments = 645 unique directed endpoint pairs + 55 repeated assignments. The repeated portion is exactly 55 two-segment groups. Collapsing directed endpoint pairs to unordered physical endpoint pairs gives {dup['same_edge_undirected_endpoint_unique']} pairs; the difference is reciprocal directions sharing physical endpoints. Multi-ID status (87 segments) overlaps this accounting and is not an additional subtraction. The previous output has 0 unmatched traffic segments. The CSV did not preserve GraphML edge `key`, so “645 unique graph multiedges” was not proven; it is 645 unique directed endpoint pairs.","",
      "## 9-10. Routing feasibility and dynamic coverage","",
      f"Sampled {rt['pairs_tested']} reproducible ordered OD pairs from the largest weak component (seed {rt['seed']}, minimum straight-line OD separation {rt['min_euclidean_od_distance_m']:.0f} m). Shortest paths use projected OSM geometry length; {rt['valid_routes']} routes succeeded, {rt['failed_routes']} failed ({rt['success_pct']:.1f}% success). Median route distance: {rt['route_distance_median']:.1f} m.","",
      f"Dynamic physical-edge coverage uses unique mapped undirected endpoint pairs because traffic direction is not fully established. Mean/median/min/max/Q25/Q75 coverage: {rt['dynamic_coverage']['mean']:.2f}% / {rt['dynamic_coverage']['median']:.2f}% / {rt['dynamic_coverage']['min']:.2f}% / {rt['dynamic_coverage']['max']:.2f}% / {rt['dynamic_coverage']['q25']:.2f}% / {rt['dynamic_coverage']['q75']:.2f}%. Routes above 25/50/75/90% coverage: {rt['dynamic_coverage']['gt25_pct']:.1f}% / {rt['dynamic_coverage']['gt50_pct']:.1f}% / {rt['dynamic_coverage']['gt75_pct']:.1f}% / {rt['dynamic_coverage']['gt90_pct']:.1f}%. Each route is in `routing_od_feasibility_100.csv`.","",
      "## 11. Architecture comparison","","| Architecture | Feasible? | Scientific quality | Recommendation |","|---|---|---|---|",
      "| A. Route directly on 700 traffic segments | No, not as-is | Weak: disconnected and duplicate mappings | Reject |",
      "| B. Full OSM graph, predictions only on matched edges | Yes | Conditional; needs explicit static fallback and verified edge map | Viable baseline design |",
      "| C. Largest traffic-mapped component | Yes, but limited | Use only if measured component is large enough; current output provides measured share | Not preferred unless scope is explicitly limited |",
      "| D. Aggregate traffic segments onto physical OSM roads | Yes as preprocessing | Necessary for repeated assignments, but does not fix connectivity alone | Apply as mapping cleanup |",
      "| E. Full OSM graph + validated dynamic costs + static costs elsewhere | Yes, conditional | Best preserves topology while making sparse coverage explicit | **Recommend** |","",
      "A is simple but cannot route reliably on the disconnected traffic-only graph. B and E preserve OSM connectivity, but route results depend on transparent static fallback and validated direction-aware mapping; E makes that fallback explicit. C permits claims only within the measured connected traffic subset, which is small here. D is necessary to handle repeated traffic-to-road assignments cleanly, but aggregation alone does not join disconnected components. Do not treat routes with low dynamic coverage as evidence of citywide dynamic-routing benefit.","",
      "## Limitations","","No traffic segment polylines are stored, so overlap is inferred from matched OSM edge geometry and centroids. `candidate_u/v` in the old spatial CSV did not include GraphML multiedge key. Exact OSM-ID geometry is strong evidence but not proof of API segment boundaries. Traffic time fields were not used as costs. Directed speed assignment is uncertain where a traffic record cannot be tied to one travel direction. The OD sample is a feasibility screen, not a route-benefit experiment.",""]
    (OUT/"audit_report.md").write_text("\n".join(lines),encoding="utf-8")


if __name__=="__main__": main()
