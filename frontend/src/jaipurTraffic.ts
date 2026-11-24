import type {FeatureCollection, LineString} from 'geojson';
import type {LayerSpecification, MapGeoJSONFeature, Map as CityMap, GeoJSONSource} from 'maplibre-gl';
import type {Coordinate} from './types';

export const cityCenter:Coordinate=[75.804,26.907];
export const cityZoom=12;
const hubs:Coordinate[]=[[75.818,26.923],[75.807,26.914],[75.814,26.901],[75.775,26.906],[75.802,26.869]];
const large=new Set(['motorway','trunk','primary','secondary']);
export const emptyFeatures:FeatureCollection={type:'FeatureCollection',features:[]};
const roadLayer='city-streets';
const streetSource='city-traffic';
const colors={free:'#253e56',moderate:'#ec870b',heavy:'#f03e31'};
const dotColors=['#25c6ff','#ffb52b','#ff623a'];

export type CityStreet={
  id:string;name:string;kind:string;tier:number;points:Coordinate[];distance:number[];phase:number;load:number;oneWay:number;
};

function fraction(key:string) {
  let hash=2166136261;
  for(let i=0;i<key.length;i++)hash=Math.imul(hash^key.charCodeAt(i),16777619);
  return (hash>>>0)/4294967296;
}

export function visibleStreets(features:Pick<MapGeoJSONFeature,'geometry'|'properties'>[]):CityStreet[] {
  const result=new Map<string,CityStreet>();
  for(const feature of features){
    const {geometry,properties}=feature;
    if(geometry.type!=='LineString'&&geometry.type!=='MultiLineString')continue;
    const kind=String(properties?.class??'minor');
    const tier=large.has(kind)?2:kind==='tertiary'?1:0;
    const lines=geometry.type==='LineString'?[geometry.coordinates]:geometry.coordinates;
    for(const raw of lines){
      if(raw.length<2)continue;
      const points=raw.map(([lng,lat]):Coordinate=>[lng,lat]);
      const middle=points[Math.floor(points.length/2)];
      if(middle[0]<75.705||middle[0]>75.885||middle[1]<26.795||middle[1]>26.995)continue;
      const key=points.map(point=>point.map(value=>value.toFixed(6)).join(',')).join(';');
      if(result.has(key))continue;
      const phase=fraction(key);
      const distance=[0];
      for(let i=1;i<points.length;i++){
        const [lng,lat]=points[i], [lastLng,lastLat]=points[i-1];
        distance.push(distance[i-1]+Math.hypot((lng-lastLng)*99200,(lat-lastLat)*111200));
      }
      if(distance.at(-1)===0)continue;
      const nearby=Math.max(0,...hubs.map(([lng,lat])=>1-Math.hypot((middle[0]-lng)*19,(middle[1]-lat)*20)));
      const load=Math.min(.96,.06+.16*tier+.25*nearby+.49*phase*(tier===0?.72:1));
      const oneWay=properties?.oneway===-1||properties?.oneway==='-1'?-1:
        properties?.oneway===1||properties?.oneway==='yes'||properties?.oneway===true?1:0;
      result.set(key,{id:key,name:String(properties?.['name:en']??properties?.name??'Unnamed street'),kind,tier,points,distance,phase,load,oneWay});
    }
  }
  return [...result.values()];
}

export function streetLines(streets:CityStreet[]):FeatureCollection<LineString> {
  return {type:'FeatureCollection',features:streets.map(({name,kind,tier,points,load})=>({
    type:'Feature',properties:{name,kind,tier,load},geometry:{type:'LineString',coordinates:points},
  }))};
}

export function prepareStreetVehicles(streets:CityStreet[]) {
  // Sample moving dots independently of the entire colored network.
  const stride=Math.max(1,Math.ceil(streets.length/1400));
  const vehicles=[];
  for(let index=0;index<streets.length;index+=stride){
    const road=streets[index];
    const length=road.distance.at(-1)!;
    const count=Math.min(road.tier+2,Math.max(1,Math.round(length/150)));
    vehicles.push({road,length,count,cyclesPerSecond:(4+road.tier*3)*(1-road.load*.58)/length,
      color:road.load>=.70?2:road.load>=.48?1:0});
  }
  return vehicles;
}

export function sampleStreetVehicles(
  flow:ReturnType<typeof prepareStreetVehicles>[number],
  points:readonly {x:number;y:number}[],seconds:number,draw:(x:number,y:number)=>void,
) {
  const {road,length,count,cyclesPerSecond}=flow;
  for(let i=0;i<count;i++){
    const progress=(road.phase+i/count+seconds*cyclesPerSecond)%1;
    const metres=(road.oneWay<0||road.oneWay===0&&i%2===1?1-progress:progress)*length;
    let segment=0;
    while(segment<road.distance.length-2&&road.distance[segment+1]<metres)segment++;
    const span=road.distance[segment+1]-road.distance[segment];
    const proportion=span?(metres-road.distance[segment])/span:0;
    const a=points[segment],b=points[segment+1];
    draw(a.x+(b.x-a.x)*proportion,a.y+(b.y-a.y)*proportion);
  }
}

function vehicleSprite(color:string,tier:number) {
  const sprite=document.createElement('canvas');
  sprite.width=24;
  sprite.height=24;
  const brush=sprite.getContext('2d')!;
  const glow=brush.createRadialGradient(12,12,1,12,12,10);
  glow.addColorStop(0,color);
  glow.addColorStop(1,color+'00');
  brush.fillStyle=glow;
  brush.fillRect(0,0,24,24);
  brush.fillStyle=color;
  brush.beginPath();
  brush.arc(12,12,2.9+tier,0,2*Math.PI);
  brush.fill();
  return sprite;
}

const layers:LayerSpecification[]=[
  {id:'city-traffic-glow',type:'line',source:streetSource,layout:{'line-cap':'round','line-join':'round'},
    paint:{'line-color':['step',['get','load'],colors.free,.48,colors.moderate,.70,colors.heavy],
      'line-opacity':['step',['get','load'],.10,.48,.35,.70,.50],
      'line-width':['match',['get','tier'],2,10,1,6,2.5],'line-blur':3}},
  {id:'city-traffic-lines',type:'line',source:streetSource,layout:{'line-cap':'round','line-join':'round'},
    paint:{'line-color':['step',['get','load'],colors.free,.48,colors.moderate,.70,colors.heavy],
      'line-width':['match',['get','tier'],2,3.8,1,2.35,1.15], 'line-opacity':.94}},
];

export function addCityTraffic(map:CityMap) {
  map.addSource(streetSource,{type:'geojson',data:emptyFeatures});
  for(const layer of layers)map.addLayer(layer,'route-glow');
}

export function runCityTraffic(map:CityMap,reduced:boolean,onCount:(count:number)=>void) {
  const lines=map.getSource<GeoJSONSource>(streetSource)!;
  const canvas=document.createElement('canvas');
  canvas.className='city-traffic-canvas';
  canvas.setAttribute('aria-hidden','true');
  const brush=canvas.getContext('2d');
  map.getCanvasContainer().append(canvas);
  const sprites=brush?dotColors.map(color=>[0,1,2].map(tier=>vehicleSprite(color,tier))):[];
  let vehicles:ReturnType<typeof prepareStreetVehicles>=[];
  let projected:ReturnType<CityMap['project']>[][]=[];
  let projectionDirty=true;
  let width=0,height=0;
  let frame=0;
  let pending=0;
  let signature='';
  const paint=(now:number)=>{
    frame=0;
    if(!brush)return;
    if(projectionDirty){
      projected=vehicles.map(({road})=>road.points.map(point=>map.project(point)));
      projectionDirty=false;
    }
    brush.clearRect(0,0,width,height);
    const seconds=reduced?0:now/1000;
    vehicles.forEach((flow,index)=>{
      const sprite=sprites[flow.color][flow.road.tier];
      sampleStreetVehicles(flow,projected[index],seconds,(x,y)=>{
        if(x>=-6&&x<=width+6&&y>=-6&&y<=height+6)brush.drawImage(sprite,x-6,y-6,12,12);
      });
    });
    if(!reduced&&vehicles.length)frame=requestAnimationFrame(paint);
  };
  const redraw=()=>{
    projectionDirty=true;
    if(!frame&&brush)frame=requestAnimationFrame(paint);
  };
  const resize=()=>{
    const surface=map.getCanvas();
    width=surface.clientWidth;
    height=surface.clientHeight;
    const scale=Math.min(devicePixelRatio,1.5);
    canvas.width=Math.round(width*scale);
    canvas.height=Math.round(height*scale);
    brush?.setTransform(scale,0,0,scale,0,0);
    redraw();
  };
  const refresh=()=>{
    pending=0;
    const next=visibleStreets(map.queryRenderedFeatures({layers:[roadLayer]}));
    const key=next.map(road=>road.id).sort().join('|');
    if(key===signature)return;
    signature=key;
    lines.setData(streetLines(next));
    vehicles=prepareStreetVehicles(next);
    redraw();
    onCount(next.length);
  };
  const schedule=()=>{
    window.clearTimeout(pending);
    if(!map.isMoving())pending=window.setTimeout(refresh,160);
  };
  const sourceChanged=(event:{sourceId?:string})=>{if(event.sourceId==='jaipur-context')schedule();};
  map.on('move',redraw);
  map.on('resize',resize);
  map.on('moveend',schedule);
  map.on('sourcedata',sourceChanged);
  resize();
  schedule();
  return ()=>{
    window.clearTimeout(pending);
    cancelAnimationFrame(frame);
    map.off('move',redraw);
    map.off('resize',resize);
    map.off('moveend',schedule);
    map.off('sourcedata',sourceChanged);
    canvas.remove();
    if(map.getSource(streetSource)===lines)lines.setData(emptyFeatures);
    onCount(0);
  };
}
