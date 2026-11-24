import {useEffect,useRef,useState} from 'react';
import * as maplibregl from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
maplibregl.setWorkerUrl(workerUrl);
import type {GeoJSONSource} from 'maplibre-gl';
import type {FeatureCollection} from 'geojson';
import type {Scenario,Snapshot} from './types';
import 'maplibre-gl/dist/maplibre-gl.css';
const coord=(n:{x:number;y:number;lat?:number|null;lng?:number|null}):[number,number]=>n.lat!=null&&n.lng!=null?[n.lng,n.lat]:[75.78+n.x/100000,26.92-n.y/100000];
export function NetworkMap({scenario,snapshot,locate,follow,onDrag,onEdge,onAmbulance}:{scenario:Scenario;snapshot:Snapshot|null;locate:number;follow:boolean;onDrag:()=>void;onEdge:(id:string)=>void;onAmbulance:()=>void}){
 const container=useRef<HTMLDivElement>(null),map=useRef<maplibregl.Map|null>(null),snapshotRef=useRef(snapshot);
 const drag=useRef(onDrag),edgeAction=useRef(onEdge),select=useRef(onAmbulance);drag.current=onDrag;edgeAction.current=onEdge;select.current=onAmbulance;snapshotRef.current=snapshot;
 const [ready,setReady]=useState(false),[failure,setFailure]=useState(''),[mapAttempt,setMapAttempt]=useState(0);
 const failureRef=useRef(failure);failureRef.current=failure;
 useEffect(()=>{const retry=()=>{if(failureRef.current)setMapAttempt(n=>n+1);};window.addEventListener('online',retry);return()=>window.removeEventListener('online',retry);},[]);
 const position=(s:Snapshot|null)=>{
  if(!s)return coord(scenario.graph.nodes[0]);const a=s.ambulance;const road=scenario.graph.edges.find(e=>e.id===a.edge);
  const node=scenario.graph.nodes.find(n=>n.id===(road?.from??a.node))!;
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
   instance.addLayer({id:'roads-closed',type:'line',source:'roads',filter:['in',['get','id'],['literal',[]]],paint:{'line-color':'#fb7185','line-width':5,'line-dasharray':[1,1]}});
   instance.addSource('nodes',{type:'geojson',data:{type:'FeatureCollection',features:scenario.graph.nodes.map(n=>({type:'Feature',properties:{id:n.id},geometry:{type:'Point',coordinates:coord(n)}}))}});
   instance.addLayer({id:'nodes',type:'circle',source:'nodes',paint:{'circle-radius':4,'circle-color':'#0d1722','circle-stroke-width':2,'circle-stroke-color':'#566d82'}});
   instance.addSource('ambulance',{type:'geojson',data:{type:'Point',coordinates:position(snapshotRef.current)}});
   instance.addLayer({id:'ambulance-halo',type:'circle',source:'ambulance',paint:{'circle-radius':18,'circle-color':'#22d3ee','circle-opacity':0.15}});
   instance.addLayer({id:'ambulance',type:'circle',source:'ambulance',paint:{'circle-radius':8,'circle-color':'#e5fbff','circle-stroke-width':3,'circle-stroke-color':'#22d3ee'}});
   instance.on('click','roads-base',e=>{const id=e.features?.[0]?.properties?.id;if(id)edgeAction.current(String(id));});
   instance.on('click','ambulance',()=>select.current());
   for(const [id,label] of [[scenario.origin,'Station 01'],[scenario.destination,'City Hospital']]){const el=document.createElement('div');el.className='map-place';el.textContent=label;new maplibregl.Marker({element:el,anchor:'bottom',offset:[0,-14]}).setLngLat(coord(nodeMap.get(id)!)).addTo(instance);}
   instance.fitBounds([coord({x:-80,y:480}),coord({x:480,y:-80})],{padding:70,duration:0});setReady(true);
  });
  return()=>{setReady(false);instance.remove();map.current=null;};
 },[scenario,mapAttempt]);
 const previous=useRef<Snapshot|null>(null);
 useEffect(()=>{
  const m=map.current;if(!m||!ready||!m.getLayer('roads-live'))return;const live=snapshot?.explanation?.liveEdges??[];
  m.setFilter('roads-live',['in',['get','id'],['literal',live]]);
  m.setFilter('roads-predicted',['!', ['in',['get','id'],['literal',live]]]);
  m.setFilter('roads-route',['in',['get','id'],['literal',snapshot?.ambulance.route??[]]]);
  m.setFilter('roads-closed',['in',['get','id'],['literal',snapshot?.reportedClosures??[]]]);
  const to=position(snapshot),from=position(previous.current);let frame=0;
  const animate=Boolean(snapshot?.ambulance.edge&&snapshot.ambulance.edge===previous.current?.ambulance.edge&&!matchMedia('(prefers-reduced-motion: reduce)').matches);
  const start=performance.now();const draw=(now:number)=>{const f=animate?Math.min(1,(now-start)/180):1;const point:[number,number]=[from[0]+(to[0]-from[0])*f,from[1]+(to[1]-from[1])*f];(m.getSource('ambulance') as GeoJSONSource).setData({type:'Point',coordinates:point});if(f<1)frame=requestAnimationFrame(draw);};frame=requestAnimationFrame(draw);previous.current=snapshot;
  if(follow)m.easeTo({center:to,duration:180});return()=>cancelAnimationFrame(frame);
 },[snapshot,ready,follow]);
 useEffect(()=>{if(ready&&locate)map.current?.easeTo({center:position(snapshotRef.current),duration:matchMedia('(prefers-reduced-motion: reduce)').matches?0:300});},[locate,ready]);
 return <div className="map-surface" ref={container} aria-label="Synthetic road network">{failure&&<div className="map-failure">Map rendering unavailable: {failure}<button onClick={()=>setMapAttempt(n=>n+1)}>Retry map</button></div>}</div>;
}
