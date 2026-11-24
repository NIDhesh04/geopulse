import type {LayerSpecification, StyleSpecification} from 'maplibre-gl';
import type {FeatureCollection,Point} from 'geojson';
import type {Coordinate} from './types';

const landmarks:[string,Coordinate,boolean][]=[
  ['H · Manipal',[75.7784,26.9526],true],['H · SDMH',[75.8086,26.8968],true],
  ['H · CK Birla',[75.7892,26.8692],true],['H · Fortis',[75.8058,26.8538],true],
  ['H · Eternal',[75.8005,26.8414],true],
  ['JHOTWARA',[75.7545,26.9395],false],['VAISHALI NAGAR',[75.7446,26.9124],false],
  ['BANI PARK',[75.789,26.928],false],['SODALA',[75.7743,26.9068],false],
  ['DEVI NAGAR',[75.766,26.890],false],['KARTARPURA',[75.795,26.885],false],
  ['ADARSH NAGAR',[75.837,26.903],false],['GOPALPURA',[75.795,26.867],false],
];
const labelData:FeatureCollection<Point>={type:'FeatureCollection',features:landmarks.map(([label,coordinates,hospital])=>({
  type:'Feature',properties:{label,hospital},geometry:{type:'Point',coordinates},
}))};

export function jaipurStyle():StyleSpecification {
  const osm='jaipur-context';
  const layers:LayerSpecification[]=[
    {id:'background',type:'background',paint:{'background-color':'#07131e'}},
    {id:'parks',type:'fill',source:osm,'source-layer':'park',paint:{'fill-color':'#102c2d'}},
    {id:'water',type:'fill',source:osm,'source-layer':'water',paint:{'fill-color':'#123a52'}},
    {id:'building-footprints',type:'fill',source:osm,'source-layer':'building',minzoom:12,
      paint:{'fill-color':'#202f46','fill-opacity':.66}},
    {id:'city-streets',type:'line',source:osm,'source-layer':'transportation',
      filter:['!',['in',['get','class'],['literal',['path','rail','transit','aerialway','ferry']]]],
      paint:{'line-color':['match',['get','class'],'primary','#546074','secondary','#3b4b61','motorway','#596175','#28394d'],
        'line-width':['interpolate',['linear'],['zoom'],11,.5,14,1.3,17,4]}},
    {id:'city-buildings',type:'fill-extrusion',source:osm,'source-layer':'building',minzoom:13,
      paint:{'fill-extrusion-color':['interpolate',['linear'],['coalesce',['get','render_height'],8],0,'#182b43',45,'#2c4c69'],
        'fill-extrusion-height':['coalesce',['get','render_height'],8],
        'fill-extrusion-base':['coalesce',['get','render_min_height'],0],
        'fill-extrusion-opacity':.8}},
    {id:'city-street-labels',type:'symbol',source:osm,'source-layer':'transportation_name',minzoom:13,
      layout:{'symbol-placement':'line','text-field':['coalesce',['get','name:en'],['get','name']],
        'text-font':['Noto Sans Regular'],'text-size':11},
      paint:{'text-color':'#b2c3d6','text-halo-color':'#07131e','text-halo-width':1.2}},
    {id:'city-districts',type:'symbol',source:'jaipur-landmarks',filter:['==',['get','hospital'],false],
      layout:{'text-field':['get','label'],'text-font':['Noto Sans Bold'],'text-size':12,'text-letter-spacing':.11},
      paint:{'text-color':'#b2bcc9','text-halo-color':'#070d16','text-halo-width':2}},
    {id:'city-hospital-pins',type:'circle',source:'jaipur-landmarks',filter:['==',['get','hospital'],true],
      paint:{'circle-radius':6,'circle-color':'#0acba0','circle-stroke-color':'#073b33','circle-stroke-width':2}},
    {id:'city-hospital-names',type:'symbol',source:'jaipur-landmarks',filter:['==',['get','hospital'],true],
      layout:{'text-field':['get','label'],'text-font':['Noto Sans Bold'],'text-size':12,'text-offset':[0,-1.25]},
      paint:{'text-color':'#bdf5e2','text-halo-color':'#0b2830','text-halo-width':2}},
  ];
  return {version:8,glyphs:'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf',
    sources:{[osm]:{type:'vector',url:'https://tiles.openfreemap.org/planet'},
      'jaipur-landmarks':{type:'geojson',data:labelData}},layers};
}
