import type {LayerSpecification, StyleSpecification} from 'maplibre-gl';

export function jaipurStyle():StyleSpecification {
  const osm='jaipur-context';
  const layers:LayerSpecification[]=[
    {id:'background',type:'background',paint:{'background-color':'#07131e'}},
    {id:'parks',type:'fill',source:osm,'source-layer':'park',paint:{'fill-color':'#102c2d'}},
    {id:'water',type:'fill',source:osm,'source-layer':'water',paint:{'fill-color':'#123a52'}},
    {id:'building-footprints',type:'fill',source:osm,'source-layer':'building',minzoom:12,
      paint:{'fill-color':'#202f46','fill-opacity':.66}},
    {id:'city-streets',type:'line',source:osm,'source-layer':'transportation',
      filter:['!',['in',['get','class'],['literal',['path','rail','transit']]]],
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
  ];
  return {version:8,glyphs:'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf',
    sources:{[osm]:{type:'vector',url:'https://tiles.openfreemap.org/planet'}},layers};
}
