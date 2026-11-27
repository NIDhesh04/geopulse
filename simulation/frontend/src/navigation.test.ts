import {describe, expect, it} from 'vitest';
import {navigationEta, routeGuidance, signalMessage} from './navigation';
import type {Ambulance, Scenario} from './types';

const vehicle:Ambulance = {
  id:'AMB-001',status:'MOVING',node:'a',edge:'ab',progress:25,destination:'c',route:['ab','bc'],
  activatedAt:10,arrivedAt:null,replans:0,reroutes:0,reason:null,initialEta:70,estimatedArrival:80,
};

describe('driver navigation', () => {
  it('uses a strict simulation-clock ETA boundary and measures arrival from departure', () => {
    expect(navigationEta(vehicle,60)).toEqual({label:'Estimated arrival',remaining:'20s',arrival:'00:01:20'});
    expect(navigationEta(vehicle,80).label).toBe('Estimate exceeded');
    expect(navigationEta({...vehicle,arrivedAt:91},91).measured).toBe('1m 21s');
    expect(navigationEta({...vehicle,status:'STOPPED',reason:'ROAD_IMPASSABLE'},20).reason)
      .toBe('The current road is impassable.');
  });

  it('calculates upcoming maneuver and remaining distance along the confirmed route', () => {
    const scenario:Scenario = {id:'test',name:'Test',mode:'FLEET_TRAFFIC',origin:'a',destination:'c',graph:{
      nodes:[{id:'a',x:0,y:0},{id:'b',x:100,y:0},{id:'c',x:100,y:100}],
      edges:[{id:'ab',from:'a',to:'b',length:100,freeSpeed:10},{id:'bc',from:'b',to:'c',length:100,freeSpeed:10}],
    }};
    expect(routeGuidance(vehicle,scenario)).toMatchObject({turn:'Turn right',distance:175,stepDistance:75,junction:'b'});
  });

  it('distinguishes an ordinary red wait from green on the selected approach', () => {
    const signal = {phase:'GREEN',approaches:['a','b'],permissions:[0,1]};
    expect(signalMessage(signal,'a',true)).toBe('Waiting at red light');
    expect(signalMessage(signal,'b',true)).toBe('Green for your approach');
  });
});
