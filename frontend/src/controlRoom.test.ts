import {describe, expect, it} from 'vitest';
import {filterFleet, routingEdges} from './controlRoom';
import type {Ambulance, Explanation, Scenario} from './types';

describe('control room projections', () => {
  it('combines fleet identifier and current zone filters', () => {
    const scenario = {graph:{nodes:[{id:'north', y:0},{id:'south', y:100}]}} as Scenario;
    const fleet = [{id:'AMB-008', node:'north'}, {id:'AMB-009', node:'south'}] as Ambulance[];
    expect(filterFleet(fleet, ' amb-00 ', 'South', scenario)).toEqual([fleet[1]]);
    expect(filterFleet(fleet, 'AMB-008', 'South', scenario)).toEqual([]);
  });

  it('excludes historical fallbacks from solid live road styling', () => {
    const explanation: Explanation = {
      routingRevision:'1',time:0,incoming:'station',candidates:[],liveEdges:['a','b'],
      roads:{
        a:{source:'LIVE',status:'AVAILABLE',seconds:2,reason:null},
        b:{source:'HISTORICAL_FALLBACK',status:'AVAILABLE',seconds:3,reason:'No live estimate'},
      },
    };
    expect(routingEdges(explanation)).toEqual({live:['a'], fallback:['b']});
    expect(routingEdges(null)).toEqual({live:[], fallback:[]});
  });
});
