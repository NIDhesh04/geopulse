import type {Feature, FeatureCollection, LineString, Point} from 'geojson';
import type {LayerSpecification, MapGeoJSONFeature, Map as CityMap, GeoJSONSource} from 'maplibre-gl';
import type {Coordinate} from './types';

export const cityCenter:Coordinate=[75.804,26.907];
export const cityZoom=12;
const hubs:Coordinate[]=[[75.818,26.923],[75.807,26.914],[75.814,26.901],[75.775,26.906],[75.802,26.869]];
const large=new Set(['motorway','trunk','primary','secondary']);
export const emptyFeatures:FeatureCollection={type:'FeatureCollection',features:[]};
const roadLayer='city-streets';
const streetSource='city-traffic';
const dotSource='city-vehicles';
const colors={free:'#253e56',moderate:'#ec870b',heavy:'#f03e31'};

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

export function streetVehicles(streets:CityStreet[],seconds:number):FeatureCollection<Point> {
  const features:Feature<Point>[]=[];
  // Every visible street is colored. Sample moving dots across road classes to bound animation work.
  const stride=Math.max(1,Math.ceil(streets.length/1400));
  for(let index=0;index<streets.length;index+=stride){
    const road=streets[index];
    const length=road.distance.at(-1)!;
    const count=Math.min(road.tier+2,Math.max(1,Math.round(length/150)));
    for(let i=0;i<count;i++){
      const progress=(road.phase+i/count+seconds*(4+road.tier*3)*(1-road.load*.58)/length)%1;
      const metres=(road.oneWay<0||road.oneWay===0&&i%2===1?1-progress:progress)*length;
      let segment=0;
      while(segment<road.distance.length-2&&road.distance[segment+1]<metres)segment++;
      const span=road.distance[segment+1]-road.distance[segment];
      const proportion=span?(metres-road.distance[segment])/span:0;
      const [a,b]=[road.points[segment],road.points[segment+1]];
      const coordinate:Coordinate=[a[0]+(b[0]-a[0])*proportion,a[1]+(b[1]-a[1])*proportion];
      features.push({type:'Feature',properties:{color:road.load>=.7?'#ff623a':road.load>=.48?'#ffb52b':'#25c6ff',
        radius:1.45+road.tier*.5},geometry:{type:'Point',coordinates:coordinate}});
    }
  }
  return {type:'FeatureCollection',features};
}

const layers:LayerSpecification[]=[
  {id:'city-traffic-glow',type:'line',source:streetSource,layout:{'line-cap':'round','line-join':'round'},
    paint:{'line-color':['step',['get','load'],colors.free,.48,colors.moderate,.70,colors.heavy],
      'line-opacity':['step',['get','load'],.10,.48,.35,.70,.50],
      'line-width':['match',['get','tier'],2,10,1,6,2.5],'line-blur':3}},
  {id:'city-traffic-lines',type:'line',source:streetSource,layout:{'line-cap':'round','line-join':'round'},
    paint:{'line-color':['step',['get','load'],colors.free,.48,colors.moderate,.70,colors.heavy],
      'line-width':['match',['get','tier'],2,3.8,1,2.35,1.15], 'line-opacity':.94}},
  {id:'city-vehicles-glow',type:'circle',source:dotSource,
    paint:{'circle-color':['get','color'],'circle-radius':['+',['get','radius'],2.6],'circle-blur':.85,'circle-opacity':.7}},
  {id:'city-vehicles-dot',type:'circle',source:dotSource,
    paint:{'circle-color':['get','color'],'circle-radius':['get','radius'],'circle-opacity':.97}},
];

export function addCityTraffic(map:CityMap) {
  map.addSource(streetSource,{type:'geojson',data:emptyFeatures});
  map.addSource(dotSource,{type:'geojson',data:emptyFeatures});
  for(const layer of layers)map.addLayer(layer,'route-glow');
}

export function runCityTraffic(map:CityMap,reduced:boolean,onCount:(count:number)=>void) {
  const lines=map.getSource<GeoJSONSource>(streetSource)!;
  const dots=map.getSource<GeoJSONSource>(dotSource)!;
  let streets:CityStreet[]=[];
  let pending=0;
  let signature='';
  const refresh=()=>{
    pending=0;
    const next=visibleStreets(map.queryRenderedFeatures({layers:[roadLayer]}));
    const key=next.map(road=>road.id).sort().join('|');
    if(key===signature)return;
    signature=key;
    streets=next;
    lines.setData(streetLines(streets));
    dots.setData(streetVehicles(streets,reduced?0:performance.now()/1000));
    onCount(streets.length);
  };
  const schedule=()=>{if(!pending)pending=window.setTimeout(refresh,120);};
  const sourceChanged=(event:{sourceId?:string})=>{if(event.sourceId==='jaipur-context')schedule();};
  map.on('moveend',schedule);
  map.on('sourcedata',sourceChanged);
  schedule();
  const frame=reduced?0:window.setInterval(()=>{
    if(streets.length&&document.visibilityState==='visible')dots.setData(streetVehicles(streets,performance.now()/1000));
  },90);
  return ()=>{
    window.clearTimeout(pending);
    window.clearInterval(frame);
    map.off('moveend',schedule);
    map.off('sourcedata',sourceChanged);
    // React may tear down the whole map before cleaning up this effect.
    if(map.getSource(streetSource)===lines){
      lines.setData(emptyFeatures);
      dots.setData(emptyFeatures);
    }
    onCount(0);
  };
}
