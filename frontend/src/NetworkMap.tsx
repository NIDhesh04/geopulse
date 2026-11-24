import {useEffect,useMemo,useRef,useState,useSyncExternalStore} from 'react';
import * as maplibregl from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
maplibregl.setWorkerUrl(workerUrl);
import type {GeoJSONSource} from 'maplibre-gl';
import type {FeatureCollection} from 'geojson';
import type {Ambulance, Coordinate, Explanation, Scenario, Signal, SimulationTruth} from './types';
import {routingEdges, type MapMode} from './controlRoom';
import {mapCoordinate as coord,queuedRoad,roadGeometry,sampleRoad} from './mapGeometry';
import {jaipurStyle} from './jaipurMap';
import 'maplibre-gl/dist/maplibre-gl.css';
const motionQuery = '(prefers-reduced-motion: reduce)';
const reducedMotion = () => matchMedia(motionQuery).matches;
const subscribeMotion = (listener:()=>void) => {
 const query=matchMedia(motionQuery);
 query.addEventListener('change',listener);
 return ()=>query.removeEventListener('change',listener);
};
type Props = {
 scenario:Scenario; fleet:Ambulance[]; selected?:Ambulance; explanation?:Explanation|null; mode:MapMode;
 closures:string[]; signals?:Record<string,Signal>; truth?:SimulationTruth;
 locate:number; follow:boolean; onDrag:()=>void; onEdge:(id:string)=>void;
 onAmbulance:(id:string)=>void; onJunction:(id:string)=>void;
 showNavigationControls?:boolean;
 navigation?:boolean;
};
export function NetworkMap({scenario,fleet,selected,explanation,mode,closures,signals,truth,locate,follow,onDrag,onEdge,onAmbulance,onJunction,showNavigationControls=true,navigation=false}:Props){
 const reduced=useSyncExternalStore(subscribeMotion,reducedMotion);
 const geographic=!!scenario.edgeGeometry;
 const geometry=useMemo(()=>roadGeometry(scenario),[scenario]);
 const container=useRef<HTMLDivElement>(null),map=useRef<maplibregl.Map|null>(null),selectedRef=useRef(selected);
 const drag=useRef(onDrag),edgeAction=useRef(onEdge),select=useRef(onAmbulance),junctionAction=useRef(onJunction);
 drag.current=onDrag;edgeAction.current=onEdge;select.current=onAmbulance;selectedRef.current=selected;junctionAction.current=onJunction;
 const [ready,setReady]=useState(false),[failure,setFailure]=useState(''),[mapAttempt,setMapAttempt]=useState(0);
 const [tilted,setTilted]=useState(true),[contextUnavailable,setContextUnavailable]=useState(false);
 const failureRef=useRef(failure);failureRef.current=failure;
 useEffect(()=>{const retry=()=>{if(failureRef.current)setMapAttempt(n=>n+1);};window.addEventListener('online',retry);return()=>window.removeEventListener('online',retry);},[]);
 const position=(a:Ambulance|undefined)=>{
  if(!a)return coord(scenario.graph.nodes[0]);const road=scenario.graph.edges.find(e=>e.id===a.edge);
  const node=scenario.graph.nodes.find(n=>n.id===(road?.from??a.node))??scenario.graph.nodes[0];
  return road?sampleRoad(geometry.get(road.id)!,a.progress/road.length):coord(node);
 };
 useEffect(()=>{
  setReady(false);setFailure('');setContextUnavailable(false);
  const surface=container.current?.parentElement;
  if(surface)surface.dataset.roadCount='0';
  let instance:maplibregl.Map;
  const context=geographic?jaipurStyle():null;
  try{instance=new maplibregl.Map({container:container.current!,style:{version:8,...(context?{glyphs:context.glyphs}:{}),sources:{},
    layers:[{id:'background',type:'background',paint:{'background-color':geographic?'#07131e':'#0d1722'}}]},
    center:coord(scenario.graph.nodes[0]),zoom:geographic?13:16.7,maxPitch:68,attributionControl:false});}catch(e){setFailure(String(e));return;}
  instance.on('error',e=>{
   if(geographic&&instance.getLayer('roads-base'))setContextUnavailable(true);
   else setFailure(e.error.message);
  });
  const reportDrawnRoads=()=>{
   if(surface?.dataset.roadCount==='0'&&instance.getLayer('roads-base'))
    surface.dataset.roadCount=String(instance.queryRenderedFeatures({layers:['roads-base']}).length);
  };
  instance.on('render',reportDrawnRoads);
  instance.on('idle',reportDrawnRoads);
  map.current=instance;
  if(showNavigationControls)instance.addControl(new maplibregl.NavigationControl({showCompass:geographic,visualizePitch:geographic}),'bottom-right');
  instance.on('dragstart',()=>drag.current());
  instance.on('load',()=>{
   const nodeMap=new Map(scenario.graph.nodes.map(n=>[n.id,n]));
   const roads:FeatureCollection={type:'FeatureCollection',features:scenario.graph.edges.map(e=>({type:'Feature',properties:{id:e.id},geometry:{type:'LineString',coordinates:geometry.get(e.id)!}}))};
   instance.addSource('roads',{type:'geojson',data:roads});
   instance.addLayer({id:'roads-base',type:'line',source:'roads',layout:{'line-cap':'round','line-join':'round'},
    paint:{'line-color':geographic?'#56768b':'#293949','line-width':geographic?5:12}});
   instance.addLayer({id:'roads-predicted',type:'line',source:'roads',paint:{'line-color':'#7b6c9e','line-width':2,'line-dasharray':[2,2]}});
   instance.addLayer({id:'roads-live',type:'line',source:'roads',filter:['in',['get','id'],['literal',[]]],paint:{'line-color':'#a5b7c8','line-width':2}});
   instance.addLayer({id:'route-glow',type:'line',source:'roads',filter:['in',['get','id'],['literal',[]]],
    layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':'#13d7ff','line-width':16,'line-blur':8,'line-opacity':.72}});
   instance.addLayer({id:'roads-route',type:'line',source:'roads',filter:['in',['get','id'],['literal',[]]],
    layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':'#24dbff','line-width':geographic?6:4,'line-opacity':0.9}});
   instance.moveLayer('route-glow','roads-predicted');
   instance.moveLayer('roads-route','roads-predicted');
   instance.addLayer({id:'roads-fallback',type:'line',source:'roads',paint:{'line-color':'#d8b4fe','line-width':3,'line-dasharray':[1,2]}},'roads-live');
   instance.addLayer({id:'roads-occupancy',type:'line',source:'roads',paint:{'line-color':['interpolate',['linear'],['coalesce',['get','load'],0],0,'#455265',0.5,'#8060a6',1,'#d0a4f6'],'line-width':5,'line-offset':3}});
   instance.addSource('queues',{type:'geojson',data:{type:'FeatureCollection',features:[]}});
   instance.addLayer({id:'road-queues',type:'line',source:'queues',paint:{'line-color':'#dfbcfb','line-width':3,'line-offset':6}});
   if(geographic){
    instance.addSource('traffic-flow',{type:'geojson',data:{type:'FeatureCollection',features:[]}});
    instance.addLayer({id:'traffic-flow',type:'circle',source:'traffic-flow',paint:{'circle-color':'#d5bdff',
     'circle-radius':2.6,'circle-blur':.12,'circle-stroke-color':'#7850b9','circle-stroke-width':1.4}});
   }
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
   for(const [id,label] of [[scenario.origin,'Station 01'],[scenario.destination,'City Hospital']]){
    const el=document.createElement('div');el.className='map-place';el.textContent=scenario.nodeNames?.[id]??label;
    new maplibregl.Marker({element:el,anchor:'bottom',offset:[0,-14]}).setLngLat(coord(nodeMap.get(id)!)).addTo(instance);
   }
   if(context){
    for(const [id,source] of Object.entries(context.sources))instance.addSource(id,source);
    for(const layer of context.layers.slice(1))instance.addLayer(layer,'roads-base');
    const bounds=new maplibregl.LngLatBounds();
    for(const line of geometry.values())line.forEach(point=>bounds.extend(point));
    instance.fitBounds(bounds,{padding:45,duration:0,maxZoom:15});
    if(instance.getContainer().clientWidth>=650&&instance.getZoom()<13.25)instance.jumpTo({zoom:13.25});
   } else instance.fitBounds([coord({id:'',x:-80,y:480}),coord({id:'',x:480,y:-80})],{padding:70,duration:0});
   setReady(true);
  });
  return()=>{setReady(false);instance.remove();map.current=null;};
 },[scenario,mapAttempt,showNavigationControls,geographic,geometry]);
 useEffect(()=>{
  const m=map.current;if(!ready||!geographic||!m?.getLayer('city-buildings'))return;
  m.setLayoutProperty('city-buildings','visibility',tilted?'visible':'none');
  const camera={pitch:tilted?48:0,bearing:tilted?-12:0};
  if(reduced)m.jumpTo(camera);else m.easeTo({...camera,duration:320});
 },[ready,geographic,tilted,reduced]);
 const previous=useRef<Ambulance|undefined>(undefined);
 const lastLocate=useRef(0);
 useEffect(()=>{
  const m=map.current;if(!m||!ready||!m.getLayer('roads-live'))return;
  const {live,fallback}=routingEdges(explanation);
  const routing=mode==='routing'&&!!selected&&!navigation;
  for(const layer of ['roads-live','roads-predicted','roads-route','roads-fallback']){
   m.setLayoutProperty(layer,'visibility',routing?'visible':'none');
   m.setPaintProperty(layer,'line-offset',3);
  }
  m.setFilter('roads-live',['in',['get','id'],['literal',live]]);
  m.setFilter('roads-predicted',['!', ['in',['get','id'],['literal',[...live,...fallback]]]]);
  m.setFilter('roads-fallback',['in',['get','id'],['literal',fallback]]);
  for(const layer of ['route-glow','roads-route']){
   m.setFilter(layer,['in',['get','id'],['literal',selected?.route??[]]]);
   m.setLayoutProperty(layer,'visibility',selected&&(routing||navigation||geographic&&mode==='operational')?'visible':'none');
  }
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
    geometry:{type:'LineString',coordinates:geometry.get(edge.id)!}};
  })});
  (m.getSource('queues') as GeoJSONSource).setData({type:'FeatureCollection',features:scenario.graph.edges.flatMap(edge=>{
   const road=interval?.[edge.id];
   if(!road||road.queued<=0)return [];
   return [{type:'Feature',properties:{id:edge.id},geometry:{type:'LineString',
    coordinates:queuedRoad(geometry.get(edge.id)!,road.queued/road.capacity)}}];
  })});
  (m.getSource('nodes') as GeoJSONSource).setData({type:'FeatureCollection',features:scenario.graph.nodes.map(node=>({
   type:'Feature',properties:{id:node.id,phase:signals?.[node.id]?.phase??''},
   geometry:{type:'Point',coordinates:points.get(node.id)!},
  }))});
 },[scenario,mode,explanation,selected,closures,truth,signals,ready,navigation,geographic,geometry]);
 useEffect(()=>{
  const source=map.current?.getSource<GeoJSONSource>('traffic-flow');
  if(!ready||!geographic||!source)return;
  const visible=mode==='truth'&&!!truth;
  const flows=visible?Object.entries(truth.roads).flatMap(([id,road])=>{
   const line=geometry.get(id);
   const count=Math.min(5,Math.ceil(road.occupancy-road.queued));
   return line&&count>0?[{line,count}]:[];
  }):[];
  const draw=(time:number)=>{
   source.setData({type:'FeatureCollection',features:flows.flatMap(({line,count})=>
    Array.from({length:count},(_,i)=>({type:'Feature',properties:{},geometry:{type:'Point',
      coordinates:sampleRoad(line,(i/count+time/12000)%1)}})))});
  };
  draw(0);
  if(!flows.length||reduced)return;
  const interval=window.setInterval(()=>draw(performance.now()),85);
  return()=>window.clearInterval(interval);
 },[ready,geographic,mode,truth,geometry,reduced]);
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
  const to=position(selected),from=previous.current;
  const animate=!!selected.edge&&selected.id===previous.current?.id&&selected.edge===previous.current.edge&&!reduced;
  const start=performance.now();
  const draw=(now:number)=>{
   const f=animate?Math.min(1,(now-start)/180):1;
   const buffered=animate&&from?{...selected,progress:from.progress+(selected.progress-from.progress)*f}:selected;
   const point:Coordinate=position(buffered);
   (m.getSource('ambulance') as GeoJSONSource).setData({type:'Point',coordinates:point});
   if(f<1)frame=requestAnimationFrame(draw);
  };
  frame=requestAnimationFrame(draw);
  previous.current=selected;
  if(follow){
   const camera={center:to,zoom:geographic&&navigation?Math.max(14.7,m.getZoom()):m.getZoom()};
   if(reduced)m.jumpTo(camera);
   else m.easeTo({...camera,duration:180});
  }
  return()=>cancelAnimationFrame(frame);
 },[fleet,selected,ready,follow,reduced,navigation,geographic,geometry]);
 useEffect(()=>{
  if(ready&&selectedRef.current&&locate!==lastLocate.current){
   lastLocate.current=locate;
   const center=position(selectedRef.current);
   if(reduced)map.current?.jumpTo({center});
   else map.current?.easeTo({center,duration:300});
  }
 },[locate,ready,reduced]);
 return <div className={geographic?'map-surface geographic-map':'map-surface'}>
  <div className="map-canvas" ref={container} aria-label={geographic?'Jaipur road network':'Synthetic road network'}/>
  {geographic&&<div className="geo-map-label">
   <span>Jaipur · Simulated traffic and signals</span>
   <small>{contextUnavailable&&'Context tiles unavailable · '}
    <a href="https://openfreemap.org/">OpenFreeMap</a> · <a href="https://openmaptiles.org/">© OpenMapTiles</a> · <a href="https://www.openstreetmap.org/copyright">© OpenStreetMap</a>
   </small>
  </div>}
  {geographic&&showNavigationControls&&<button className="map-tilt secondary" disabled={!ready}
   aria-pressed={tilted} onClick={()=>setTilted(value=>!value)}>3D view</button>}
  {failure&&<div className="map-failure">Map rendering unavailable: {failure}<button onClick={()=>setMapAttempt(n=>n+1)}>Retry map</button></div>}
 </div>;
}
