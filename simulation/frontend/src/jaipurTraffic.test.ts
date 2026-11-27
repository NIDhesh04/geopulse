import {expect,it} from 'vitest';
import type {Geometry} from 'geojson';
import {prepareStreetVehicles,sampleStreetVehicles,streetLines,visibleStreets} from './jaipurTraffic';

it('includes major roads, little service lanes and each part of a multi-line street',()=>{
  const single=(coordinates:number[][],kind:string)=>({
    geometry:{type:'LineString',coordinates} as Geometry,properties:{class:kind},
  });
  const highway=single([[75.8,26.9],[75.81,26.9]],'motorway');
  const service=single([[75.8,26.9],[75.80004,26.9]],'service');
  const streets=visibleStreets([highway,highway,service,{
    geometry:{type:'MultiLineString',coordinates:[[[75.81,26.90],[75.81,26.91]],[[75.82,26.91],[75.82,26.92]]]},
    properties:{class:'minor'},
  },single([[77.2,28.6],[77.22,28.6]],'primary')]);
  expect(streets.map(road=>road.kind)).toEqual(['motorway','service','minor','minor']);
  expect(streetLines(streets).features).toHaveLength(4);
  const traffic=prepareStreetVehicles(streets);
  const samples=(time:number)=>traffic.flatMap(flow=>{
    const points:number[][]=[];
    const screen=flow.road.points.map(([x,y])=>({x,y}));
    sampleStreetVehicles(flow,screen,time,(x,y)=>points.push([x,y]));
    return points;
  });
  expect(samples(0).length).toBeGreaterThanOrEqual(4);
  expect(samples(1/60)).not.toEqual(samples(0));
});
