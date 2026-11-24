import {useEffect,useRef,useState} from 'react';
import * as maplibregl from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
maplibregl.setWorkerUrl(workerUrl);
import type {GeoJSONSource} from 'maplibre-gl';
import type {FeatureCollection} from 'geojson';
import type {Ambulance, Explanation, Scenario, Signal, SimulationTruth} from './types';
import {routingEdges, type MapMode} from './controlRoom';
import 'maplibre-gl/dist/maplibre-gl.css';
const coord=(n:{x:number;y:number;lat?:number|null;lng?:number|null}):[number,number]=>n.lat!=null&&n.lng!=null?[n.lng,n.lat]:[75.78+n.x/100000,26.92-n.y/100000];
type Props = {
 scenario:Scenario; fleet:Ambulance[]; selected?:Ambulance; explanation?:Explanation|null; mode:MapMode;
 closures:string[]; signals?:Record<string,Signal>; truth?:SimulationTruth;
 locate:number; follow:boolean; onDrag:()=>void; onEdge:(id:string)=>void;
 onAmbulance:(id:string)=>void; onJunction:(id:string)=>void;
};
export function NetworkMap({scenario,fleet,selected,explanation,mode,closures,signals,truth,locate,follow,onDrag,onEdge,onAmbulance,onJunction}:Props){
 const container=useRef<HTMLDivElement>(null),map=useRef<maplibregl.Map|null>(null),selectedRef=useRef(selected);
 const drag=useRef(onDrag),edgeAction=useRef(onEdge),select=useRef(onAmbulance),junctionAction=useRef(onJunction);
 drag.current=onDrag;edgeAction.current=onEdge;select.current=onAmbulance;selectedRef.current=selected;junctionAction.current=onJunction;
 const [ready,setReady]=useState(false),[failure,setFailure]=useState(''),[mapAttempt,setMapAttempt]=useState(0);
 const failureRef=useRef(failure);failureRef.current=failure;
 useEffect(()=>{const retry=()=>{if(failureRef.current)setMapAttempt(n=>n+1);};window.addEventListener('online',retry);return()=>window.removeEventListener('online',retry);},[]);
 const position=(a:Ambulance|undefined)=>{
  if(!a)return coord(scenario.graph.nodes[0]);const road=scenario.graph.edges.find(e=>e.id===a.edge);
  const node=scenario.graph.nodes.find(n=>n.id===(road?.from??a.node))??scenario.graph.nodes[0];
  if(!road)return coord(node);const end=scenario.graph.nodes.find(n=>n.id===road.to)!;const f=a.progress/road.length;
  return coord({x:node.x+(end.x-node.x)*f,y:node.y+(end.y-node.y)*f});
 };
 useEffect(()=>{
  setReady(false);setFailure('');if(container.current)container.current.dataset.roadCount='0';
  let instance:maplibregl.Map;
  try{instance=new maplibregl.Map({container:container.current!,style:{version:8,sources:{},layers:[{id:'background',type:'background',paint:{'background-color':'#0d1722'}}]},center:[75.782,26.918],zoom:16.7,attributionControl:false});}catch(e){setFailure(String(e));return;}
  instance.on('error',e=>setFailure(e.error.message));
  instance.on('idle',()=>{if(container.current&&instance.getLayer('roads-base'))container.current.dataset.roadCount=String(instance.queryRenderedFeatures({layers:['roads-base']}).length);});
  map.current=instance;instance.addControl(new maplibregl.NavigationControl({showCompass:false}),'bottom-right');
  instance.on('dragstart',()=>drag.current());
  instance.on('load',()=>{
   const nodeMap=new Map(scenario.graph.nodes.map(n=>[n.id,n]));
   const roads:FeatureCollection={type:'FeatureCollection',features:scenario.graph.edges.map(e=>({type:'Feature',properties:{id:e.id},geometry:{type:'LineString',coordinates:[coord(nodeMap.get(e.from)!),coord(nodeMap.get(e.to)!)]}}))};
   instance.addSource('roads',{type:'geojson',data:roads});
   instance.addLayer({id:'roads-base',type:'line',source:'roads',paint:{'line-color':'#293949','line-width':12}});
   instance.addLayer({id:'roads-predicted',type:'line',source:'roads',paint:{'line-color':'#7b6c9e','line-width':2,'line-dasharray':[2,2]}});
   instance.addLayer({id:'roads-live',type:'line',source:'roads',filter:['in',['get','id'],['literal',[]]],paint:{'line-color':'#a5b7c8','line-width':2}});
   instance.addLayer({id:'roads-route',type:'line',source:'roads',filter:['in',['get','id'],['literal',[]]],paint:{'line-color':'#22d3ee','line-width':4,'line-opacity':0.8}});
   instance.moveLayer('roads-route','roads-predicted');
   instance.addLayer({id:'roads-fallback',type:'line',source:'roads',paint:{'line-color':'#d8b4fe','line-width':3,'line-dasharray':[1,2]}},'roads-live');
   instance.addLayer({id:'roads-occupancy',type:'line',source:'roads',paint:{'line-color':['interpolate',['linear'],['coalesce',['get','load'],0],0,'#455265',0.5,'#8060a6',1,'#d0a4f6'],'line-width':5,'line-offset':3}});
   instance.addSource('queues',{type:'geojson',data:{type:'FeatureCollection',features:[]}});
   instance.addLayer({id:'road-queues',type:'line',source:'queues',paint:{'line-color':'#dfbcfb','line-width':3,'line-offset':6}});
   instance.addLayer({id:'roads-closed',type:'line',source:'roads',filter:['in',['get','id'],['literal',[]]],paint:{'line-color':'#fb7185','line-width':5,'line-dasharray':[1,1]}});
   instance.addSource('nodes',{type:'geojson',data:{type:'FeatureCollection',features:scenario.graph.nodes.map(n=>({type:'Feature',properties:{id:n.id},geometry:{type:'Point',coordinates:coord(n)}}))}});
   instance.addLayer({id:'nodes',type:'circle',source:'nodes',paint:{'circle-radius':5,'circle-color':'#0d1722','circle-stroke-width':2,'circle-stroke-color':['match',['get','phase'],'GREEN','#55d6a1','AMBER','#f6bf62','ALL_RED','#fb7185','#566d82']}});
   instance.addSource('fleet',{type:'geojson',data:{type:'FeatureCollection',features:[]}});
   instance.addLayer({id:'fleet',type:'circle',source:'fleet',paint:{'circle-radius':6,'circle-color':'#e5edf7','circle-stroke-width':2,'circle-stroke-color':'#52687e'}});
   instance.addSource('ambulance',{type:'geojson',data:{type:'FeatureCollection',features:[]}});
   instance.addLayer({id:'ambulance-halo',type:'circle',source:'ambulance',paint:{'circle-radius':18,'circle-color':'#22d3ee','circle-opacity':0.15}});
   instance.addLayer({id:'ambulance',type:'circle',source:'ambulance',paint:{'circle-radius':8,'circle-color':'#e5fbff','circle-stroke-width':3,'circle-stroke-color':'#22d3ee'}});
   instance.on('click','roads-base',e=>{const id=e.features?.[0]?.properties?.id;if(id)edgeAction.current(String(id));});
   instance.on('click','ambulance',()=>{if(selectedRef.current)select.current(selectedRef.current.id);});
   instance.on('click','fleet',e=>{const id=e.features?.[0]?.properties?.id;if(id)select.current(String(id));});
   instance.on('click','nodes',e=>{const id=e.features?.[0]?.properties?.id;if(id)junctionAction.current(String(id));});
   for(const [id,label] of [[scenario.origin,'Station 01'],[scenario.destination,'City Hospital']]){const el=document.createElement('div');el.className='map-place';el.textContent=label;new maplibregl.Marker({element:el,anchor:'bottom',offset:[0,-14]}).setLngLat(coord(nodeMap.get(id)!)).addTo(instance);}
   instance.fitBounds([coord({x:-80,y:480}),coord({x:480,y:-80})],{padding:70,duration:0});setReady(true);
  });
  return()=>{setReady(false);instance.remove();map.current=null;};
 },[scenario,mapAttempt]);
 const previous=useRef<Ambulance|undefined>(undefined);
 const lastLocate=useRef(0);
 useEffect(()=>{
  const m=map.current;if(!m||!ready||!m.getLayer('roads-live'))return;
  const {live,fallback}=routingEdges(explanation);
  const routing=mode==='routing'&&!!selected;
  for(const layer of ['roads-live','roads-predicted','roads-route','roads-fallback']){
   m.setLayoutProperty(layer,'visibility',routing?'visible':'none');
   m.setPaintProperty(layer,'line-offset',3);
  }
  m.setFilter('roads-live',['in',['get','id'],['literal',live]]);
  m.setFilter('roads-predicted',['!', ['in',['get','id'],['literal',[...live,...fallback]]]]);
  m.setFilter('roads-fallback',['in',['get','id'],['literal',fallback]]);
  m.setFilter('roads-route',['in',['get','id'],['literal',selected?.route??[]]]);
  const physical=mode==='truth'?truth?.physicalEffects:undefined;
  const interval=mode==='truth'?truth?.roads:undefined;
  const routingClosures = routing ? Object.entries(explanation?.roads ?? {})
    .filter(([, estimate])=>estimate.status==='BLOCKED').map(([id])=>id) : [];
  const affected=mode==='truth'?Object.keys(physical??{}):[...new Set([...closures,...routingClosures])];
  m.setFilter('roads-closed',['in',['get','id'],['literal',affected]]);
  m.setPaintProperty('roads-closed','line-offset',3);
  m.setLayoutProperty('roads-occupancy','visibility',interval?'visible':'none');
  m.setLayoutProperty('road-queues','visibility',interval?'visible':'none');
  const points=new Map(scenario.graph.nodes.map(node=>[node.id,coord(node)]));
  (m.getSource('roads') as GeoJSONSource).setData({type:'FeatureCollection',features:scenario.graph.edges.map(edge=>{
   const road=interval?.[edge.id];
   return {type:'Feature',properties:{id:edge.id,load:road?road.occupancy/road.capacity:0},
    geometry:{type:'LineString',coordinates:[points.get(edge.from)!,points.get(edge.to)!]}};
  })});
  (m.getSource('queues') as GeoJSONSource).setData({type:'FeatureCollection',features:scenario.graph.edges.flatMap(edge=>{
   const road=interval?.[edge.id];
   if(!road||road.queued<=0)return [];
   const from=points.get(edge.from)!,to=points.get(edge.to)!;
   const share=Math.min(1,road.queued/road.capacity);
   const start=[to[0]-(to[0]-from[0])*share,to[1]-(to[1]-from[1])*share];
   return [{type:'Feature',properties:{id:edge.id},geometry:{type:'LineString',coordinates:[start,to]}}];
  })});
  (m.getSource('nodes') as GeoJSONSource).setData({type:'FeatureCollection',features:scenario.graph.nodes.map(node=>({
   type:'Feature',properties:{id:node.id,phase:signals?.[node.id]?.phase??''},
   geometry:{type:'Point',coordinates:points.get(node.id)!},
  }))});
 },[scenario,mode,explanation,selected,closures,truth,signals,ready]);
 useEffect(()=>{
  const m=map.current;if(!m||!ready||!m.getSource('fleet'))return;
  const occupied=new Map<string,number>();
  if(selected)occupied.set(position(selected).join(','),1);
  (m.getSource('fleet') as GeoJSONSource).setData({type:'FeatureCollection',features:fleet.filter(a=>a.id!==selected?.id).map(a=>{
   const point=position(a);
   const key=point.join(',');
   const count=occupied.get(key)??0;
   occupied.set(key,count+1);
   const angle=count*Math.PI/2.5;
   const radius=count?0.00007+Math.floor(count/5)*0.00004:0;
   return {type:'Feature',properties:{id:a.id},geometry:{type:'Point',
    coordinates:[point[0]+radius*Math.cos(angle),point[1]+radius*Math.sin(angle)]}};
  })});
  let frame=0;
  if(!selected){
   (m.getSource('ambulance') as GeoJSONSource).setData({type:'FeatureCollection',features:[]});
   previous.current=undefined;
   return;
  }
  const to=position(selected),from=position(previous.current);
  const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
  const animate=!!selected.edge&&selected.id===previous.current?.id&&selected.edge===previous.current.edge&&!reduced;
  const start=performance.now();
  const draw=(now:number)=>{
   const f=animate?Math.min(1,(now-start)/180):1;
   (m.getSource('ambulance') as GeoJSONSource).setData({type:'Point',coordinates:[from[0]+(to[0]-from[0])*f,from[1]+(to[1]-from[1])*f]});
   if(f<1)frame=requestAnimationFrame(draw);
  };
  frame=requestAnimationFrame(draw);
  previous.current=selected;
  if(follow)m.easeTo({center:to,duration:reduced?0:180});
  return()=>cancelAnimationFrame(frame);
 },[fleet,selected,ready,follow]);
 useEffect(()=>{
  if(ready&&selectedRef.current&&locate!==lastLocate.current){
   lastLocate.current=locate;
   map.current?.easeTo({center:position(selectedRef.current),duration:matchMedia('(prefers-reduced-motion: reduce)').matches?0:300});
  }
 },[locate,ready]);
 return <div className="map-surface" ref={container} aria-label="Synthetic road network">{failure&&<div className="map-failure">Map rendering unavailable: {failure}<button onClick={()=>setMapAttempt(n=>n+1)}>Retry map</button></div>}</div>;
}
